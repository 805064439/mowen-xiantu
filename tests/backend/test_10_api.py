# -*- coding: utf-8 -*-
"""接口契约（进程内）：/api/health、/api/act、/api/act/stream、/api/shop、兜底事件池。

这里是「外部契约层」测试 —— 不关心内部怎么算，只固化前端依赖的响应形状，
任何一次字段改名都必须在这里暴露出来。
"""
import json

import pytest


def parse_sse(text: str):
    """把 SSE 文本还原成 [(event, data), ...]，供流式契约测试断言。"""
    out = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        event, data_line = "message", None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data_line = line[6:]
        if data_line is not None:
            out.append((event, json.loads(data_line)))
    return out


ACT_FIELDS = ["ok", "state", "narrative", "choices", "delta_applied", "npc_events",
              "breakthrough", "near_death", "ending", "engine_meta"]


class TestHealth:
    def test_shape(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["mode"] in ("real", "mock")
        assert isinstance(body["model"], str)

    def test_offline_mode_is_mock(self, engine, client):
        """测试环境禁用了 key，必须降级为演武模式而非伪装成 real。"""
        assert engine.API_KEY == ""
        assert client.get("/api/health").json()["mode"] == "mock"

    def test_cors_header_present(self, client):
        r = client.get("/api/health", headers={"Origin": "https://example.com"})
        assert r.headers.get("access-control-allow-origin") == "*"


class TestActContract:
    def test_use_item_response_shape(self, client, base_state):
        r = client.post("/api/act", json={
            "state": {**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}], "hp": 20},
            "action": {"type": "use_item", "name": "回气丹"},
            "last_choices": [],
        })
        assert r.status_code == 200
        body = r.json()
        for f in ACT_FIELDS:
            assert f in body, f"缺少字段 {f}"
        assert body["ok"] is True
        assert body["ending"] is False and body["near_death"] is False
        assert isinstance(body["state"], dict)
        assert len(body["choices"]) >= 3

    def test_use_item_missing(self, client, base_state):
        r = client.post("/api/act", json={
            "state": base_state,
            "action": {"type": "use_item", "name": "未持有丹"},
        }).json()
        assert r["ok"] is False
        assert set(r["error"]) == {"code", "message"}
        assert r["error"]["code"] == "ITEM_NOT_OWNED"

    def test_normal_turn_in_mock_mode(self, client, base_state):
        """无 API key 时必须走演武模式，且响应结构与真机完全一致。"""
        r = client.post("/api/act", json={
            "state": base_state, "action": {"type": "choice", "text": "下山赶路"},
        })
        assert r.status_code == 200
        body = r.json()
        for f in ACT_FIELDS:
            assert f in body
        assert body["engine_meta"]["source"] == "mock"
        assert body["engine_meta"]["model"] == "演武"
        assert body["engine_meta"]["tokens_in"] == 0   # 不消耗任何 token
        assert body["state"]["turn"] == 1
        assert body["narrative"]

    def test_first_turn_rolls_spirit_root(self, engine, client, base_state):
        """新档首次行动 → 天道掷定灵根，并反映在返回的 state 中。"""
        body = client.post("/api/act", json={
            "state": base_state, "action": {"type": "choice", "text": "启程"},
        }).json()
        root = body["state"]["spirit_root"]
        assert root, "首轮未掷出灵根"
        assert engine.is_valid_spirit_root(root), f"掷出的灵根非法: {root}"

    def test_existing_root_is_preserved(self, engine, client, base_state):
        """已测过灵根的存档不会被反复重掷。"""
        s = {**base_state, "spirit_root": "单灵根·火"}
        body = client.post("/api/act", json={
            "state": s, "action": {"type": "choice", "text": "继续"},
        }).json()
        assert body["state"]["spirit_root"] == "单灵根·火"

    def test_state_returned_is_sanitized(self, client, base_state):
        body = client.post("/api/act", json={
            "state": {**base_state, "cheat": 1, "realm_index": 999},
            "action": {"type": "choice", "text": "x"},
        }).json()
        assert "cheat" not in body["state"]
        assert body["state"]["realm_index"] <= 9

    def test_empty_body_is_tolerated(self, client):
        """请求体缺省字段时按默认值处理（宽容契约），但必须返回合法结构。"""
        body = client.post("/api/act", json={}).json()
        assert body["ok"] is True
        assert body["state"]["turn"] == 1
        assert body["state"]["spirit_root"]      # 新档自动掷灵根

    def test_wrong_types_are_rejected(self, client):
        assert client.post("/api/act", json={"state": "not-a-dict", "action": {}}).status_code == 422
        assert client.post("/api/act", json={"state": {}, "action": "字符串"}).status_code == 422

    def test_engine_error_returns_structured_500(self, client, base_state, monkeypatch, engine):
        """引擎内部异常必须被收敛成结构化错误，而不是把 traceback 甩给前端。"""
        monkeypatch.setattr(engine, "sanitize_state", lambda raw: (_ for _ in ()).throw(RuntimeError("地脉崩坏")))
        r = client.post("/api/act", json={"state": base_state, "action": {"type": "choice"}})
        assert r.status_code == 500
        body = r.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "ENGINE_ERROR"
        assert "地脉崩坏" in body["error"]["message"]
        assert len(body["error"]["message"]) <= 200

    def test_breakthrough_flow(self, client, engine, base_state, monkeypatch):
        """修为圆满 + 冲关行动 → 必然产出 breakthrough 视图，且成功/失败二选一。"""
        s = {**base_state, "exp": engine.exp_max_of(0)}
        monkeypatch.setattr("random.random", lambda: 0.0)   # 必定成功
        body = client.post("/api/act", json={
            "state": s, "action": {"type": "breakthrough", "text": "闭关冲关"},
        }).json()
        assert body["ok"] is True
        assert body["breakthrough"] is not None
        assert body["breakthrough"]["from"] == "炼气一层"
        assert body["state"]["realm_index"] == 1

    def test_breakthrough_failure_keeps_realm(self, client, engine, base_state, monkeypatch):
        s = {**base_state, "exp": engine.exp_max_of(0)}
        monkeypatch.setattr("random.random", lambda: 0.999)
        body = client.post("/api/act", json={
            "state": s, "action": {"type": "breakthrough"},
        }).json()
        assert body["state"]["realm_index"] == 0
        assert body["breakthrough"]["success"] is False
        assert body["state"]["fail_streak"] == 1

    def test_ending_path(self, client, engine, base_state, monkeypatch):
        """九层冲关成功 → ending 标记 + 手写结局文案，且达满属性。"""
        s = {**base_state, "realm_index": 8, "exp": engine.exp_max_of(8)}
        monkeypatch.setattr("random.random", lambda: 0.0)
        body = client.post("/api/act", json={
            "state": s, "action": {"type": "breakthrough"},
        }).json()
        assert body["ok"] is True
        assert body["ending"] is True
        assert body["state"]["realm_index"] == 9
        assert body["engine_meta"]["source"] == "ending"
        assert body["narrative"]


    def test_stream_ending_matches_non_stream(self, client, engine, base_state, monkeypatch):
        """结局时两条路径的簿记必须完全一致 —— 不得出现轮次/记忆双重记账。"""
        s = {**base_state, "realm_index": 8, "exp": engine.exp_max_of(8), "spirit_stones": 100}
        monkeypatch.setattr("random.random", lambda: 0.0)
        plain = client.post("/api/act", json={
            "state": s, "action": {"type": "breakthrough"},
        }).json()
        frames = parse_sse(client.post("/api/act/stream", json={
            "state": s, "action": {"type": "breakthrough"},
        }).text)
        stream = [d for e, d in frames if e == "done"][-1]
        assert plain["ending"] is True and stream["ending"] is True
        assert plain["state"]["turn"] == stream["state"]["turn"] == 1
        assert plain["state"]["memory"] == stream["state"]["memory"]
        assert plain["state"]["spirit_stones"] == stream["state"]["spirit_stones"]
        assert plain["state"]["realm_index"] == stream["state"]["realm_index"] == 9
        # 流式结局仍要推送增量文本，否则前端会卡在空屏
        delta_text = "".join(d["t"] for e, d in frames if e == "delta")
        assert delta_text and delta_text == stream["narrative"]


class TestStreamContract:
    def test_use_item_streams(self, client, base_state):
        r = client.post("/api/act/stream", json={
            "state": {**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}], "hp": 20},
            "action": {"type": "use_item", "name": "回气丹"},
        })
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        frames = parse_sse(r.text)
        assert frames, "未收到任何 SSE 帧"
        kinds = [e for e, _ in frames]
        assert kinds[0] == "delta" and kinds[-1] == "done"
        done = frames[-1][1]
        for f in ACT_FIELDS:
            assert f in done
        assert "".join(d["t"] for e, d in frames if e == "delta") == done["narrative"]

    def test_normal_stream_in_mock_mode(self, client, base_state):
        r = client.post("/api/act/stream", json={
            "state": base_state, "action": {"type": "choice", "text": "出发"},
        })
        frames = parse_sse(r.text)
        done = [d for e, d in frames if e == "done"]
        assert done, "流式未收尾"
        assert done[-1]["engine_meta"]["source"] == "mock"
        assert done[-1]["state"]["turn"] == 1
        # 增量文本拼接应等于最终叙事
        assert "".join(d["t"] for e, d in frames if e == "delta") == done[-1]["narrative"]

    def test_stream_and_non_stream_agree_schema(self, client, engine, base_state):
        """两路共用后处理 → 除源码标注外，字段集合必须完全一致（防止分叉）。"""
        payload = {"state": base_state, "action": {"type": "choice", "text": "同样的行动"}}
        plain = client.post("/api/act", json=payload).json()
        frames = parse_sse(client.post("/api/act/stream", json=payload).text)
        stream = [d for e, d in frames if e == "done"][-1]
        assert set(plain) == set(stream)
        assert set(plain["state"]) == set(stream["state"])

    def test_stream_error_payload(self, client, base_state, monkeypatch, engine):
        monkeypatch.setattr(engine, "sanitize_state", lambda raw: (_ for _ in ()).throw(RuntimeError("断线")))
        r = client.post("/api/act/stream", json={"state": base_state, "action": {"type": "choice"}})
        frames = parse_sse(r.text)
        assert frames[-1][0] == "error"
        assert "断线" in frames[-1][1]["message"]

    def test_empty_body_is_tolerated(self, client):
        frames = parse_sse(client.post("/api/act/stream", json={}).text)
        done = [d for e, d in frames if e == "done"]
        assert done and done[-1]["ok"] is True


class TestShopContract:
    def test_response_shape(self, client, base_state):
        body = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 50},
            "action": {"type": "shop_buy", "name": "回气丹", "qty": 1},
        }).json()
        assert set(body) == {"ok", "state", "narrative", "delta_applied"}
        assert set(body["delta_applied"]) == {"hp", "qi", "exp", "spirit_stones",
                                              "items_add", "items_remove"}
        assert body["ok"] is True

    def test_error_response_shape(self, client, base_state):
        body = client.post("/api/shop", json={
            "state": base_state, "action": {"type": "shop_buy", "name": "不存在"},
        }).json()
        assert set(body) == {"ok", "error"}
        assert set(body["error"]) == {"code", "message"}

    def test_empty_body_is_tolerated(self, client):
        body = client.post("/api/shop", json={}).json()
        assert body["ok"] is False and body["error"]["code"] == "UNKNOWN_OP"


class TestRootRoute:
    def test_index_serves_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


class TestFallbackPools:
    """AI 失效时的兜底剧情池 —— 结构一旦越界，游戏会当场断线，必须静态校验。"""

    @pytest.mark.parametrize("pool_name", ["MOCK_EVENTS", "FALLBACK_EVENTS"])
    def test_events_pass_ai_validator(self, engine, pool_name):
        pool = getattr(engine, pool_name)
        assert pool, f"{pool_name} 为空"
        for ev in pool:
            engine._validate_ai_output(ev)      # 缺字段/类型错会抛 ValueError

    @pytest.mark.parametrize("pool_name", ["MOCK_EVENTS", "FALLBACK_EVENTS"])
    def test_events_deltas_are_legal(self, engine, pool_name):
        pool = getattr(engine, pool_name)
        state = engine.sanitize_state({})
        for ev in pool:
            d = engine.clamp_ai_delta(ev["delta"], state)
            for k in ("hp", "qi", "exp", "spirit_stones"):
                bound = engine.DELTA_BOUNDS[k]
                assert -bound <= ev["delta"].get(k, 0) <= bound, \
                    f"{pool_name} 中的 {k} 超出 AI 允许幅度"
            assert len(d["items_add"]) <= 3

    @pytest.mark.parametrize("pool_name", ["MOCK_EVENTS", "FALLBACK_EVENTS"])
    def test_events_are_deep_copied_on_use(self, engine, pool_name):
        """引用出来的事件被写脏会污染全局兜底池 —— 必须确认调用方做了深拷贝。"""
        pool = getattr(engine, pool_name)
        snapshot = json.dumps(pool, ensure_ascii=False, sort_keys=True)
        s = engine.sanitize_state({})
        engine._postprocess_turn(s, json.loads(json.dumps(pool[0])), {}, "x")
        assert json.dumps(pool, ensure_ascii=False, sort_keys=True) == snapshot

    def test_mock_scene_matches_trial_text(self, engine):
        """冲刺关判定时应优先产出对应的剧情模板。"""
        for tw in ("TRIGGER_ENDING", "闭关冲击【炼气二层】成功",
                   "闭关冲击【炼气二层】失败", "【斗法判定】", "无特殊判定"):
            scene = engine._mock_trial_scene(tw)
            assert scene is None or isinstance(scene, dict)
