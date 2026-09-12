# -*- coding: utf-8 -*-
"""线上端到端：直接打到已部署的 Vercel 环境，验证真实运行时的行为。

与本地单测的区别：
  · 本地测的是「函数」；这里测的是「部署产物」—— 冷启动、CORS、SSE、真实 AI 调用
  · 这里的失败意味着线上玩家正在遇到问题，优先级最高

运行：
    set ONLINE_BASE_URL=https://mowen-xiantu.vercel.app
    python -m pytest tests/online -q -s
"""
from __future__ import annotations

import json
import os
import time

import httpx
import pytest

DEFAULT_URL = "https://mowen-xiantu.vercel.app"
BASE_URL = (os.environ.get("ONLINE_BASE_URL") or DEFAULT_URL).rstrip("/")

# 真实 AI 调用较慢，且 Vercel 冷启动偶发抖动 —— 统一放宽超时并允许重试
HTTP_TIMEOUT = float(os.environ.get("ONLINE_TIMEOUT", "45"))
MAX_RETRY = 3

ACT_FIELDS = ["ok", "state", "narrative", "choices", "delta_applied",
              "breakthrough", "near_death", "ending", "engine_meta"]


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def http(base_url):
    with httpx.Client(base_url=base_url, timeout=HTTP_TIMEOUT, follow_redirects=True) as c:
        yield c


def request_with_retry(client, method, url, **kw):
    """网络抖动/冷启动容忍：5xx 与超时重试，4xx 立即失败。"""
    last = None
    for attempt in range(MAX_RETRY):
        try:
            r = client.request(method, url, **kw)
            if r.status_code >= 500 and attempt < MAX_RETRY - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return r
        except (httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError(f"线上请求连续失败 {MAX_RETRY} 次: {last}")


def consume_stream(client, payload):
    """消费一次 SSE，返回 [(event, data), ...]。"""
    with client.stream("POST", "/api/act/stream", json=payload) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        frames, buf = [], ""
        for chunk in resp.iter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                event, data = None, None
                for line in frame.split("\n"):
                    if line.startswith("event: "):
                        event = line[7:].strip()
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                if event:
                    frames.append((event, data))
    return frames


def fresh_state(**over):
    """与前端 INIT_STATE 对齐的开局档。"""
    s = {
        "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
        "exp": 10, "spirit_stones": 30,
        "items": [{"name": "回气丹", "qty": 2, "rarity": "下品"},
                  {"name": "师父的钝剑", "qty": 1, "rarity": "下品"}],
        "memory": ["独守青牛山破庙三年"], "recent": [], "turn": 0,
        "spirit_root": "", "npcs": [], "pending_events": [], "style_echo": [],
        "memory_summary": "", "reincarnations": [], "fail_streak": 0,
        "last_near_death_turn": -999,
    }
    s.update(over)
    return s


# ---------------------------------------------------------------- 冒烟
class TestOnlineSmoke:
    def test_health_is_real(self, http):
        """线上必须挂着有效的 DeepSeek key —— 否则是降级演武模式，玩家拿到的是假剧情。"""
        r = request_with_retry(http, "GET", "/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["mode"] == "real", f"线上跑在降级模式: {body}"
        assert body["model"]

    def test_index_served(self, http):
        """首页必须返回构建后的 HTML，且挂载点存在。"""
        r = request_with_retry(http, "GET", "/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        html = r.text
        assert 'id="app"' in html, "首页缺少 Vue 挂载点"
        assert "src/main.ts" in html or "/assets/" in html, "首页未加载入口脚本"

    def test_static_assets_reachable(self, http):
        """构建产物能被 CDN 正确返回 —— 前端白屏的常见元凶在此暴露。"""
        html = request_with_retry(http, "GET", "/").text
        assets = [a for a in __import__("re").findall(r'/(?:assets|src)/[^\s"\'()]+', html)]
        assets = [a for a in assets if a.endswith((".js", ".css"))][:3]
        assert assets, "首页未引用任何静态资源"
        for a in assets:
            r = request_with_retry(http, "GET", a)
            assert r.status_code == 200, f"静态资源不可达: {a}"

    def test_unknown_api_returns_404(self, http):
        r = request_with_retry(http, "GET", "/api/__not_exist__")
        assert r.status_code == 404

    def test_docs_are_disabled(self, http):
        """生产环境不应暴露 API 文档页面。"""
        r = request_with_retry(http, "GET", "/api/docs")
        assert r.status_code in (404, 405)


# ---------------------------------------------------------------- 坊市（确定性路径，不消耗 AI）
class TestOnlineShop:
    def test_buy_and_sell_roundtrip(self, http):
        s = fresh_state(spirit_stones=200, items=[])
        r = request_with_retry(http, "POST", "/api/shop", json={
            "state": s, "action": {"type": "shop_buy", "name": "凝气丹", "qty": 2},
        }).json()
        assert r["ok"] is True, r
        assert r["state"]["spirit_stones"] == 200 - 80
        assert r["state"]["items"][0]["qty"] == 2

        r2 = request_with_retry(http, "POST", "/api/shop", json={
            "state": r["state"], "action": {"type": "shop_sell", "name": "凝气丹", "qty": 2},
        }).json()
        assert r2["ok"] is True
        assert r2["state"]["spirit_stones"] == 120 + 40      # int(40*0.5)=20 ×2
        assert r2["state"]["items"] == []

    @pytest.mark.parametrize("action,code", [
        ({"type": "shop_buy", "name": "不存在的丹"}, "ITEM_NOT_SOLD"),
        ({"type": "shop_buy", "name": "凝气丹", "qty": 99}, "NOT_ENOUGH_STONES"),
        ({"type": "shop_sell", "name": "无此物"}, "ITEM_NOT_OWNED"),
        ({"type": "unknown_op"}, "UNKNOWN_OP"),
    ])
    def test_error_codes(self, http, action, code):
        r = request_with_retry(http, "POST", "/api/shop", json={
            "state": fresh_state(spirit_stones=10), "action": action,
        }).json()
        assert r["ok"] is False
        assert r["error"]["code"] == code, r

    def test_malicious_state_is_cleaned(self, http):
        """玩家篡改的存档（越界境界、私有字段）必须被服务端洗掉。"""
        dirty = fresh_state(spirit_stones=99999, realm_index=99, Cheat=True, hp=10 ** 9)
        r = request_with_retry(http, "POST", "/api/shop", json={
            "state": dirty, "action": {"type": "shop_buy", "name": "辟谷丹", "qty": 1},
        }).json()
        assert r["ok"] is True
        st = r["state"]
        assert st["realm_index"] <= 9
        assert "Cheat" not in st
        assert st["hp"] <= st["hp_max"]
        assert st["spirit_stones"] <= 99999

    def test_inf_payload_does_not_crash(self, http):
        """JSON 允许 1e999 这类字面量，服务端不得 500（历史上会抛 OverflowError）。"""
        raw = httpx.Request(
            "POST", httpx.URL(f"{BASE_URL}/api/shop"),
            headers={"Content-Type": "application/json"},
            content=json.dumps({"state": {"hp": 1e999, "spirit_stones": 1e999},
                                "action": {"type": "shop_buy", "name": "辟谷丹", "qty": 1}}),
        )
        r = httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True).send(raw)
        assert r.status_code != 500, f"非法数值导致服务端崩溃: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------- 用丹（确定性路径）
class TestOnlineUseItem:
    def test_use_pill_success(self, http):
        s = fresh_state(hp=20, items=[{"name": "回气丹", "qty": 2, "rarity": "下品"}])
        r = request_with_retry(http, "POST", "/api/act", json={
            "state": s, "action": {"type": "use_item", "name": "回气丹"}, "last_choices": [],
        })
        assert r.status_code == 200
        body = r.json()
        for f in ACT_FIELDS:
            assert f in body, f"线上响应缺少字段 {f}"
        assert "npc_events" in body, "用丹响应缺少 npc_events（与 /api/act 不同构）"
        assert body["state"]["items"][0]["qty"] == 1
        assert body["state"]["hp"] == 50          # int(100*0.30)=30 回血
        assert body["engine_meta"]["source"] == "item"
        assert body["engine_meta"]["tokens_out"] == 0   # 用丹不得消耗 token

    def test_use_unowned_pill(self, http):
        body = request_with_retry(http, "POST", "/api/act", json={
            "state": fresh_state(items=[]), "action": {"type": "use_item", "name": "回气丹"},
        }).json()
        assert body["ok"] is False
        assert body["error"]["code"] == "ITEM_NOT_OWNED"

    def test_use_material_is_rejected_softly(self, http):
        s = fresh_state(items=[{"name": "碎星石", "qty": 1, "rarity": "下品"}])
        body = request_with_retry(http, "POST", "/api/act", json={
            "state": s, "action": {"type": "use_item", "name": "碎星石"},
        }).json()
        assert body["ok"] is True
        assert body["state"]["items"][0]["qty"] == 1   # 材料不被吃掉

    def test_invalid_body_returns_422(self, http):
        r = request_with_retry(http, "POST", "/api/act", json={"state": "字符串"})
        assert r.status_code == 422


# ---------------------------------------------------------------- SSE 流式
class TestOnlineStream:
    def test_use_item_streams(self, http):
        frames = consume_stream(http, {
            "state": fresh_state(hp=20, items=[{"name": "回气丹", "qty": 1, "rarity": "下品"}]),
            "action": {"type": "use_item", "name": "回气丹"},
        })
        kinds = [e for e, _ in frames]
        assert kinds[0] == "delta" and kinds[-1] == "done"
        done = frames[-1][1]
        for f in ACT_FIELDS:
            assert f in done
        assert "".join(d["t"] for e, d in frames if e == "delta") == done["narrative"]

    def test_stream_item_payload_matches_non_stream(self, http):
        """流式与非流式在确定性路径上必须给出完全一致的结果。"""
        payload = {
            "state": fresh_state(hp=20, items=[{"name": "回气丹", "qty": 1, "rarity": "下品"}]),
            "action": {"type": "use_item", "name": "回气丹"},
        }
        plain = request_with_retry(http, "POST", "/api/act", json=payload).json()
        done = consume_stream(http, payload)[-1][1]
        assert set(plain) == set(done)
        assert plain["state"] == done["state"]
        assert plain["narrative"] == done["narrative"]


# ---------------------------------------------------------------- 真实 AI（消耗 token，标记 slow）
@pytest.mark.slow
class TestOnlineAI:
    def test_full_turn_with_real_model(self, http):
        """真实调用 DeepSeek：验证 key 可用、输出能通过校验、并回卷合法状态。"""
        r = request_with_retry(http, "POST", "/api/act", json={
            "state": fresh_state(), "action": {"type": "choice", "text": "下山，赶往青牛镇"},
        })
        assert r.status_code == 200
        body = r.json()
        for f in ACT_FIELDS + ["npc_events"]:
            assert f in body, f"AI 回合响应缺少字段 {f}"
        assert body["ok"] is True
        meta = body["engine_meta"]
        assert meta["source"] in ("deepseek", "fallback"), f"引擎来源异常: {meta}"
        if meta["source"] == "deepseek":
            assert meta["tokens_out"] > 0, "未产出任何 token，AI 调用疑似失败"
        assert body["state"]["turn"] == 1
        assert body["state"]["spirit_root"], "首轮未掷定灵根"
        assert body["narrative"], "叙事为空"
        assert len(body["choices"]) >= 3

    def test_ai_fragmented_then_streamed(self, http):
        """SSE 真实流式：能收到增量片段，且 done 帧结构完整。"""
        frames = []
        payload = {"state": fresh_state(), "action": {"type": "choice", "text": "在破庙打坐半日"}}
        with http.stream("POST", "/api/act/stream", json=payload) as resp:
            assert resp.status_code == 200
            buf = ""
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    for line in frame.split("\n"):
                        if line.startswith("event: "):
                            frames.append((line[7:].strip(), None))
        assert frames, "未收到任何流式事件"
        assert frames[-1][0] == "done", f"流未正常收尾: {frames[-3:]}"

    def test_state_chain_across_turns(self, http):
        """多轮闭环：每一轮的 state 都能被下一轮接受并推进 —— 存档的连续性保证。"""
        state = fresh_state(spirit_stones=300)
        for i in range(2):
            body = request_with_retry(http, "POST", "/api/act", json={
                "state": state, "action": {"type": "choice", "text": f"继续探索{i + 1}"},
            }).json()
            assert body["ok"] is True, body
            assert body["state"]["turn"] == i + 1
            state = body["state"]
        assert state["memory"], "多轮之后仍未积累任何记忆"


# ---------------------------------------------------------------- 结局（历史致命缺陷的线上回归）
@pytest.mark.slow
class TestOnlineEnding:
    def test_ending_payload_is_not_null(self, http):
        """九层冲击筑基成功时必须返回完整结局对象。

        历史缺陷：此分支曾漏写 return，HTTP 200 却返回 null，
        玩家在第一章通关瞬间卡死。这里在线上做回归确认。
        """
        s = fresh_state(realm_index=8, exp=800, hp=244, hp_max=244,
                        qi=119, qi_max=119, spirit_stones=100,
                        spirit_root="天灵根·火")
        ending = None
        for attempt in range(30):
            r = request_with_retry(http, "POST", "/api/act", json={
                "state": s, "action": {"type": "breakthrough", "text": "闭关，冲击筑基初期"},
            })
            body = r.json()
            assert body is not None, f"第 {attempt + 1} 次冲击返回了 null —— 结局缺陷仍在!"
            if body.get("ending"):
                ending = body
                break
            s = body["state"]
            s["exp"] = 800           # 失败会折损修为，重灌后可再冲
        if ending is None:
            pytest.skip("30 次冲击内未撞到 25% 的成功判定（非缺陷，纯概率）")

        assert ending["ok"] is True
        assert ending["state"]["realm_index"] == 9
        assert ending["engine_meta"]["source"] == "ending"
        assert ending["narrative"], "结局文案为空"
        assert ending["choices"]

    def test_stream_ending_matches_non_stream(self, http):
        """结局处的两条入口必须给出同构结果。

        注意：突破是**随机判定**（实测成功率约三到五成），所以不能假定
        「同一份存档在非流式撞到成功后，流式也必然成功」——那样写会得到
        一条时红时绿的用例。这里让两路各自反复冲击，直到都撞到结局再比对，
        且每次都从同一份快照起手，避免失败轮折损的修为污染起点。
        """
        import copy

        base = fresh_state(realm_index=8, exp=800, hp=244, hp_max=244, qi=119, qi_max=119,
                           spirit_stones=100, spirit_root="天灵根·火")

        def hit_ending(via_stream: bool):
            for _ in range(40):
                payload = {"state": copy.deepcopy(base), "action": {"type": "breakthrough"}}
                if via_stream:
                    frames = consume_stream(http, payload)
                    data = frames[-1][1] if frames else None
                else:
                    data = request_with_retry(http, "POST", "/api/act", json=payload).json()
                assert data is not None, "结局分支返回了 null —— 历史缺陷复发"
                if data.get("ending"):
                    return data
            return None

        plain = hit_ending(False)
        if plain is None:
            pytest.skip("40 次冲击内非流式未撞到结局（纯概率）")
        stream = hit_ending(True)
        if stream is None:
            pytest.skip("40 次冲击内流式未撞到结局（纯概率）")

        assert stream["ending"] is True
        assert set(plain) == set(stream), "两条入口的结局字段不一致"
        assert stream["state"]["turn"] == plain["state"]["turn"]
        assert stream["state"]["memory"] == plain["state"]["memory"]
        assert stream["narrative"] == plain["narrative"]
        assert stream["engine_meta"]["source"] == "ending"
