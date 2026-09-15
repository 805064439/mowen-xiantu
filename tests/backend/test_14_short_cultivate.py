# -*- coding: utf-8 -*-
"""§6 修复：片刻行功（周天 / 小坐）不再一次吃掉五年寿元。

现象：选项写「行功一个周天」「原地打坐」，点下去年岁却推进 3.5~6.5 年。
根因：ACTION_DAYS["cultivate"] 是写死的 (1260, 2340)，所有 cultivate 标签的选项
      无论文字写什么，都走同一个五年跨度——机制与叙事完全脱节。

修复原则：给 cultivate 类选项加**可选 short 标记**，标记的走 SHORT_CULTIVATE_DAYS(1,7)，
不标记的保持 5 年跨度。周天只是「天数少」的修行 → 修为自然也少，
**不引入任何 lump**，与「修为 = 天数 × 日效率」地基一致。

这里钉死四件事：
    1. 天数：short → 1~7 天；不 short → 仍是 1260~2340；
    2. 年岁：一轮 short 修行推进 < 1 岁（这是玩家能直接感知的部分）；
    3. 守恒：short 的修为必然远小于整段闭关（否则就成了新的白嫖口）；
    4. 标记链路：normalize_choices 不得丢弃 short（丢了等于修复失效）。
"""
from __future__ import annotations

import pytest


def _scripted(monkeypatch, engine, randints=(), randoms=()):
    it_i, it_f = iter(randints), iter(randoms)
    monkeypatch.setattr(engine.random, "randint", lambda a, b: next(it_i, a))
    monkeypatch.setattr(engine.random, "random", lambda: next(it_f, 0.99))


def _cultivate(engine, state, meta=None, short=False):
    return engine._postprocess_turn(
        state,
        {"delta": {"exp": 0}, "choices": [], "narrative": "正文。", "memory": ""},
        meta if meta is not None else {}, "行功一个周天" if short else "闭关苦修",
        "cultivate", short=short)


# ---------------------------------------------------------------- 天数跨度
class TestShortCultivateDays:
    def test_short_span_is_within_the_table(self, engine):
        assert engine.SHORT_CULTIVATE_DAYS == (1, 7)
        lo, hi = engine.SHORT_CULTIVATE_DAYS
        for _ in range(80):
            _, days, _ = engine.action_exp("cultivate", None, True)
            assert lo <= days <= hi, days

    def test_default_cultivate_is_still_a_five_year_span(self, engine):
        """整段闭关不受影响：仍是一次跨 3.5~6.5 年。"""
        lo, hi = engine.ACTION_DAYS["cultivate"]
        for _ in range(80):
            _, days, _ = engine.action_exp("cultivate")
            assert lo <= days <= hi, days

    def test_short_flag_is_ignored_by_non_cultivate(self, engine):
        """short 只对 cultivate 有意义：探索/静养的天数不受它影响。"""
        for tag in ("explore", "rest", "trade", "fight", "other"):
            lo, hi = engine.ACTION_DAYS.get(tag, (5, 20))
            for _ in range(40):
                _, days, _ = engine.action_exp(tag, None, True)
                assert lo <= days <= hi, f"{tag} 被 short 污染了"

    def test_explore_tier_still_wins_over_short(self, engine):
        """探索带档位时走档位天数，short 不得插手。"""
        lo, hi = engine.EXPLORE_TIERS["high"]["days"]
        for _ in range(40):
            _, days, _ = engine.action_exp("explore", "high", True)
            assert lo <= days <= hi


# ---------------------------------------------------------------- 标记链路
class TestShortMarkerPlumbing:
    def test_explicit_flag_wins(self, engine):
        assert engine.is_short_cultivate({"text": "闭关苦修", "tag": "cultivate", "short": True}) is True
        assert engine.is_short_cultivate({"text": "行功一个周天", "tag": "cultivate"}) is True

    def test_keyword_fallback_covers_the_narrative_words(self, engine):
        """LLM 常常只在文字里写「周天」而不带标记——这是兜底，必须生效。"""
        for text in ("就地行功一个周天", "小坐片刻，调匀气息", "稍作调息",
                     "原地打坐半日", "数息导引"):
            assert engine.is_short_cultivate({"text": text, "tag": "cultivate"}) is True, text

    def test_full_seclusion_is_not_mistaken_for_short(self, engine):
        for text in ("闭关苦修，不问寒暑", "潜心参悟三年", "打坐修持，冲击筑基"):
            assert engine.is_short_cultivate({"text": text, "tag": "cultivate"}) is False, text

    def test_non_cultivate_never_short(self, engine):
        assert engine.is_short_cultivate({"text": "行功一个周天", "tag": "explore"}) is False
        assert engine.is_short_cultivate({"text": "行功一个周天", "tag": "rest"}) is False
        assert engine.is_short_cultivate(None) is False

    def test_normalize_choices_preserves_short(self, engine, base_state):
        """**关键**：normalize_choices 会重建选项字典，丢掉 short 等于修复失效。"""
        raw = [
            {"text": "就地行功一个周天", "risk": "mid", "tag": "cultivate", "short": True},
            {"text": "闭关苦修三年", "risk": "low", "tag": "cultivate"},
            {"text": "下山赶路", "risk": "low", "tag": "explore"},
        ]
        out = engine.normalize_choices(raw, base_state)
        assert out[0]["short"] is True
        assert out[1]["short"] is False
        assert out[2]["short"] is False

    def test_filler_marked_short(self, engine):
        """占位选项「原地打坐」是片刻工夫，必须是 short。"""
        filler = next(c for c in engine.FILLER_CHOICES if "打坐" in c["text"])
        assert filler["short"] is True

    def test_mock_events_marked_short(self, engine):
        """演武事件里的「周天」选项同样要标——否则演武模式仍会一次跳五年。"""
        texts = [c["text"] for ev in engine.MOCK_EVENTS for c in ev["choices"]]
        assert any("周天" in t for t in texts)
        for ev in engine.MOCK_EVENTS:
            for c in ev["choices"]:
                if "周天" in c["text"]:
                    assert c["short"] is True, c["text"]

    def test_prompt_teaches_the_model(self, engine):
        """提示词必须教模型这个契约，否则真实对局仍会漂回五年。"""
        assert "short" in engine.SYSTEM_PROMPT
        assert "周天" in engine.SYSTEM_PROMPT


# ---------------------------------------------------------------- 端到端：年岁与守恒
class TestShortCultivateSettlement:
    def _state(self, engine, **extra):
        return engine.sanitize_state({"realm_index": 8, "spirit_root": "三灵根·金木水",
                                      "spirit_stones": 999, **extra})

    def test_short_turn_advances_less_than_a_year(self, engine, monkeypatch):
        s = self._state(engine)
        meta: dict = {}
        _scripted(monkeypatch, engine, randints=[7])
        _cultivate(engine, s, meta, short=True)
        assert s["days"] == 7
        assert s["age"] == engine.START_AGE              # 不满一年，年岁不动
        assert meta["cultivate"]["short"] is True
        assert meta["cultivate"]["days"] == 7

    def test_full_turn_still_advances_years(self, engine, monkeypatch):
        s = self._state(engine)
        meta: dict = {}
        _scripted(monkeypatch, engine, randints=[engine.ACTION_DAYS["cultivate"][0]])
        _cultivate(engine, s, meta, short=False)
        assert s["age"] >= engine.START_AGE + 3          # 一次闭关就是数年
        assert "short" not in meta["cultivate"]

    def test_short_yield_is_dwarfed_by_a_full_seclusion(self, engine, monkeypatch):
        """守恒：周天修为 ≪ 整段闭关（252~468），不会变成新的 OP 路线。"""
        s_short = self._state(engine)
        _scripted(monkeypatch, engine, randints=[7])
        _, _, d_short, _, _ = _cultivate(engine, s_short, {}, short=True)

        s_full = self._state(engine)
        _scripted(monkeypatch, engine, randints=[engine.ACTION_DAYS["cultivate"][1]])
        _, _, d_full, _, _ = _cultivate(engine, s_full, {}, short=False)

        assert d_short["exp"] < 5
        assert d_full["exp"] > 100
        assert d_full["exp"] > d_short["exp"] * 20

    def test_short_yield_is_still_time_based(self, engine, monkeypatch):
        """短修行也必须守「修为 = 天数 × 日效率」——不得出现脱离天数的 lump。"""
        got = {}
        for days in (1, 4, 7):
            s = self._state(engine)
            _scripted(monkeypatch, engine, randints=[days])
            _, _, d, _, _ = _cultivate(engine, s, {}, short=True)
            got[days] = d["exp"]
            # 产出 = 天数 × 日效率 × 各项系数；系数 < 3 是宽松上界（灵根 1.2 × 连击/状态）
            assert 0 <= d["exp"] <= days * engine.DAY_EFF["cultivate"] * 3 + 1
        assert got[7] >= got[1]      # 天数越多，产出越多（单调）
        assert got[1] < 5            # 一个周天最多几个修为，绝不可能替代闭关

    def test_short_does_not_trigger_seclusion_hint(self, engine, monkeypatch):
        """短修行不算「闭门日久」，不该劝玩家出门。"""
        s = self._state(engine, seclusion_streak=99)
        _scripted(monkeypatch, engine, randints=[3])
        narrative, _, _, _, _ = _cultivate(engine, s, {}, short=True)
        assert engine.SECLUSION_HINT not in narrative

    def test_short_still_counts_toward_streak(self, engine, monkeypatch):
        """周天廉价攒连击是允许的（基数极小，不滚雪球），但机制上必须真加。"""
        s = self._state(engine)
        _scripted(monkeypatch, engine, randints=[3])
        _cultivate(engine, s, {}, short=True)
        assert s["cultivate_streak"] >= 1


# ---------------------------------------------------------------- 经接口端到端
class TestShortCultivateThroughApi:
    def _live_state(self):
        return {
            "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
            "exp": 0, "spirit_stones": 999, "spirit_root": "三灵根·金木水",
            "items": [], "memory": [], "recent": [], "turn": 0, "days": 0,
        }

    @pytest.mark.parametrize("payload,expect_short", [
        ({"type": "choice", "text": "就地行功一个周天", "tag": "cultivate", "short": True}, True),
        ({"type": "choice", "text": "就地行功一个周天", "tag": "cultivate"}, True),   # 关键词兜底
        ({"type": "choice", "text": "闭关苦修，冲击筑基", "tag": "cultivate"}, False),
    ])
    def test_act_honours_short_through_the_api(self, engine, client, monkeypatch, payload, expect_short):
        # 掷出的天数故意取「两个区间的中间值」：若走错区间，断言立刻失败
        days = 7 if expect_short else 1800
        _scripted(monkeypatch, engine, randints=[days])
        r = client.post("/api/act", json={"state": self._live_state(), "action": payload})
        assert r.status_code == 200
        d = r.json()
        got = d["state"]["days"]
        if expect_short:
            assert 1 <= got <= engine.SHORT_CULTIVATE_DAYS[1], f"短修行却推进了 {got} 天"
            assert d["state"]["age"] == engine.START_AGE
        else:
            assert got >= engine.ACTION_DAYS["cultivate"][0], f"整段闭关只推进了 {got} 天"

    def test_stream_honours_short_too(self, engine, client, monkeypatch):
        """两路端点必须同构：SSE 路径不能漏掉 short。"""
        _scripted(monkeypatch, engine, randints=[7])
        r = client.post("/api/act/stream", json={
            "state": self._live_state(),
            "action": {"type": "choice", "text": "行功一个周天", "tag": "cultivate", "short": True},
        })
        assert r.status_code == 200
        done = _sse_done(r.text)
        assert done is not None, "SSE 未回传 done 帧"
        assert done["state"]["days"] == 7                 # 仍是 7 天，不是五年
        assert done["state"]["age"] == engine.START_AGE
        assert done["engine_meta"]["cultivate"]["short"] is True


def _sse_done(body: str) -> dict | None:
    """从 SSE 文本里取出 event: done 的 data 对象（测试用极简解析）。"""
    import json
    for frame in body.split("\n\n"):
        if "event: done" not in frame:
            continue
        for line in frame.split("\n"):
            if line.startswith("data: "):
                try:
                    return json.loads(line[6:])
                except Exception:
                    return None
    return None
