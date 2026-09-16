# -*- coding: utf-8 -*-
"""v3.2：修行粒度三档（span）+ 场景节奏（scene_pace）

承接《已确定的未实现方案》方案二与方案三：

**方案二 span**——v3.1 的 `short` 布尔只有「片刻 / 五年」两极，中间没有维度。
现升级为三档粒度 short(1~7天) / medium(30~120天) / long(1260~2340天)。
⚠️ 粒度只改天数、不改日效率：修为随天数等比缩放，**绝不引入裸修为 lump**，
   否则「修为 = 天数 × 日效率」这条地基又会被凿穿。

**方案三 scene_pace**——系统不知道「此刻处在什么节奏」，于是在片刻场景里
也给出整段闭关选项。新增状态 action / resolve / downtime，纯代码推断，
只决定「该给什么选项」，不碰任何数值。

这里钉死五件事：
    1. 三档天数各自落在表内，且互不重叠（short < medium < long）；
    2. 判定：显式 span 优先 > short 兼容别名 > 文字关键词 > 默认 long；
    3. 透传：normalize_choices / sanitize_last_choices 不得丢弃 span（丢了等于修复失效）；
    4. scene_pace：白名单防注入、推断规则正确、回合末写入下一轮；
    5. 守恒：三档修为与天数成正比——粒度是换「投入」，不是换「效率」。
"""
from __future__ import annotations

import pytest


def _scripted(monkeypatch, engine, randints=(), randoms=()):
    it_i, it_f = iter(randints), iter(randoms)
    monkeypatch.setattr(engine.random, "randint", lambda a, b: next(it_i, a))
    monkeypatch.setattr(engine.random, "random", lambda: next(it_f, 0.99))


def _state(engine, **extra):
    return engine.sanitize_state({"realm_index": 8, "spirit_root": "三灵根·金木水",
                                  "spirit_stones": 999, **extra})


def _run(engine, state, tag="cultivate", span=None, meta=None, trial=None):
    return engine._postprocess_turn(
        state,
        {"delta": {"exp": 0}, "choices": [], "narrative": "正文。", "memory": ""},
        meta if meta is not None else {}, "行动", tag, span=span, trial=trial)


# ---------------------------------------------------------------- 方案二：三档表
class TestCultivateSpanTable:
    def test_three_spans_exist_and_are_ordered(self, engine):
        """三档必须严格递增且不重叠——否则玩家分不出档位差别。"""
        assert set(engine.CULTIVATE_SPAN) == {"short", "medium", "long"}
        s_lo, s_hi = engine.CULTIVATE_SPAN["short"]
        m_lo, m_hi = engine.CULTIVATE_SPAN["medium"]
        l_lo, l_hi = engine.CULTIVATE_SPAN["long"]
        assert s_lo >= 1 and s_hi < m_lo          # 片刻 < 一次行功
        assert m_hi < l_lo                         # 一次行功 < 整段闭关

    def test_long_span_equals_the_legacy_action_days(self, engine):
        """long 档必须与 ACTION_DAYS['cultivate'] 同值，否则老存档会突然变慢/变快。"""
        assert engine.CULTIVATE_SPAN["long"] == engine.ACTION_DAYS["cultivate"]

    def test_short_alias_still_points_at_the_same_table(self, engine):
        """v3.1 的 SHORT_CULTIVATE_DAYS 是兼容别名，不得与 short 档脱钩。"""
        assert engine.SHORT_CULTIVATE_DAYS == engine.CULTIVATE_SPAN["short"]

    @pytest.mark.parametrize("span", ["short", "medium", "long"])
    def test_each_span_stays_inside_its_range(self, engine, span):
        lo, hi = engine.CULTIVATE_SPAN[span]
        for _ in range(120):
            _, days, _ = engine.action_exp("cultivate", None, False, span)
            assert lo <= days <= hi, f"{span} 档越界: {days}"

    def test_legacy_short_bool_maps_to_the_short_span(self, engine):
        """short=True 必须等价于 span='short'——老前端不传 span 也不会退化。"""
        lo, hi = engine.CULTIVATE_SPAN["short"]
        for _ in range(60):
            _, days, _ = engine.action_exp("cultivate", None, True)
            assert lo <= days <= hi

    def test_span_is_ignored_by_non_cultivate(self, engine):
        """粒度只对修行有意义：静养/探索等不得被 span 污染。"""
        for tag in ("rest", "explore", "trade", "fight", "other"):
            lo, hi = engine.ACTION_DAYS.get(tag, (5, 20))
            for _ in range(40):
                _, days, _ = engine.action_exp(tag, None, False, "short")
                assert lo <= days <= hi, f"{tag} 被 span 污染了"

    def test_unknown_span_falls_back_to_the_default(self, engine):
        """非法 span（注入/笔误）不得崩溃，回落到整段闭关。"""
        lo, hi = engine.ACTION_DAYS["cultivate"]
        for _ in range(40):
            _, days, _ = engine.action_exp("cultivate", None, False, "HACK")
            assert lo <= days <= hi


# ---------------------------------------------------------------- 方案二：判定
class TestSpanDetection:
    def test_explicit_span_wins(self, engine):
        for sp in ("short", "medium", "long"):
            assert engine.span_of_cultivate(
                {"text": "闭关苦修", "tag": "cultivate", "span": sp}) == sp

    def test_keyword_fallback(self, engine):
        assert engine.span_of_cultivate({"text": "行功一个周天", "tag": "cultivate"}) == "short"
        assert engine.span_of_cultivate({"text": "静修数月", "tag": "cultivate"}) == "medium"

    def test_long_when_text_says_so(self, engine):
        assert engine.span_of_cultivate(
            {"text": "闭关苦修，不问寒暑", "tag": "cultivate"}) == "long"

    def test_year_wording_beats_generic_medium_words(self, engine):
        """写明了年头就必须按年走。

        「静修 / 潜修」只是对修行的泛称，若它们抢在「三年」前面命中，
        玩家点的是三年、系统只推进数十天——寿元被静默吞掉，
        而 AI 的叙事还照着文本写「三年将尽」，数值与叙事当场打架。
        这是 2026-09-16 在线上实测到的真实样本（当时只过了 50 天）。
        """
        cases = (
            "闭关静修，入定三年",     # 触发过故障的原始样本
            "入定五年",
            "闭关数载",
            "十年寒窗苦修",
            "长年闭关不出",
            "这一坐便是七年",
        )
        for text in cases:
            assert engine.span_of_cultivate(
                {"text": text, "tag": "cultivate"}) == "long", text

    def test_year_wording_advances_years(self, engine):
        """判成 long 就得真的推进年：天数必须落在 long 档 1260~2340。"""
        lo, hi = engine.CULTIVATE_SPAN["long"]
        sp = engine.span_of_cultivate({"text": "闭关静修，入定三年", "tag": "cultivate"})
        for _ in range(40):
            _, days, _ = engine.action_exp("cultivate", None, False, sp)
            assert lo <= days <= hi

    def test_medium_wording_survives_the_year_regex(self, engine):
        """年档正则不得误伤 medium：「半载 / 一季 / 数月」仍按 medium 走。"""
        cases = ("静修数月", "闭关一季", "半载之内潜心修行", "小闭关一月", "旬日行功")
        for text in cases:
            assert engine.span_of_cultivate(
                {"text": text, "tag": "cultivate"}) == "medium", text

    def test_legacy_short_bool_is_honoured(self, engine):
        assert engine.span_of_cultivate(
            {"text": "闭关苦修", "tag": "cultivate", "short": True}) == "short"

    def test_non_cultivate_has_no_span(self, engine):
        assert engine.span_of_cultivate({"text": "行功一个周天", "tag": "explore"}) is None
        assert engine.span_of_cultivate(None) is None

    def test_is_short_cultivate_still_works(self, engine):
        """v3.1 的布尔接口保留：等价于 span == short。"""
        assert engine.is_short_cultivate({"text": "行功一个周天", "tag": "cultivate"}) is True
        assert engine.is_short_cultivate({"text": "静修数月", "tag": "cultivate"}) is False


# ---------------------------------------------------------------- 方案二：透传
class TestSpanPlumbing:
    def test_normalize_choices_preserves_span(self, engine, base_state):
        """**关键陷阱**：重建选项字典时丢掉 span，修复即失效。"""
        raw = [
            {"text": "就地行功一个周天", "risk": "mid", "tag": "cultivate", "span": "short"},
            {"text": "静修数月", "risk": "low", "tag": "cultivate", "span": "medium"},
            {"text": "闭关苦修三年", "risk": "low", "tag": "cultivate", "span": "long"},
        ]
        out = engine.normalize_choices(raw, base_state)
        assert [c.get("span") for c in out] == ["short", "medium", "long"]

    def test_normalize_choices_drops_illegal_span(self, engine, base_state):
        raw = [{"text": "闭关苦修", "risk": "low", "tag": "cultivate", "span": "HACK"}]
        out = engine.normalize_choices(raw, base_state)
        assert "span" not in out[0]

    def test_sanitize_last_choices_preserves_span(self, engine, base_state):
        """用丹后沿用上一轮选项，粒度必须跟着回来。"""
        raw = [{"id": "A", "text": "行功一个周天", "risk": "mid", "tag": "cultivate", "span": "short"}]
        out = engine.sanitize_last_choices(raw, base_state)
        assert out[0].get("span") == "short"

    def test_filler_pool_is_chosen_by_pace(self, engine):
        """兜底选项池按场景节奏切换：空白期才给整段闭关。"""
        assert engine.filler_choices({"scene_pace": "action"}) is engine.FILLER_CHOICES
        downtime = engine.filler_choices({"scene_pace": "downtime"})
        assert any(c.get("span") == "long" for c in downtime)
        action = engine.filler_choices({"scene_pace": "action"})
        assert not any(c.get("span") == "long" for c in action)
        assert engine.filler_choices({}) is engine.FILLER_CHOICES      # 未知节奏回落

    def test_prompt_teaches_both_dimensions(self, engine):
        """提示词必须把 tag + span 双维度与节奏铁律都教给模型。"""
        assert "span" in engine.SYSTEM_PROMPT
        assert "medium" in engine.SYSTEM_PROMPT
        assert "downtime" in engine.SYSTEM_PROMPT
        assert "【场景节奏】" in engine.build_user_prompt(
            engine.sanitize_state({}), {"text": "x"}, "无判定")


# ---------------------------------------------------------------- 方案二：守恒
class TestSpanConservation:
    """粒度是换「投入多少时间」，不是换「效率」——否则又成白嫖口。"""

    @pytest.mark.parametrize("span", ["short", "medium", "long"])
    def test_yield_is_proportional_to_days(self, engine, monkeypatch, span):
        lo, hi = engine.CULTIVATE_SPAN[span]
        for days in (lo, (lo + hi) // 2, hi):
            s = _state(engine)
            meta: dict = {}
            _scripted(monkeypatch, engine, randints=[days])
            _, _, d, _, _ = _run(engine, s, span=span, meta=meta)
            assert meta["cultivate"]["days"] == days
            # 修为 = 天数 × 日效率 × 系数；系数上限约 3，故给出宽松上界
            assert 0 <= d["exp"] <= days * engine.DAY_EFF["cultivate"] * 3 + 1

    def test_a_long_retreat_outruns_a_moment_by_far(self, engine, monkeypatch):
        """整段闭关的修为必须远多于片刻行功——否则闭关就失去了意义。"""
        s_lo, _ = engine.CULTIVATE_SPAN["short"]
        l_lo, _ = engine.CULTIVATE_SPAN["long"]
        s1 = _state(engine)
        _scripted(monkeypatch, engine, randints=[s_lo])
        _, _, d1, _, _ = _run(engine, s1, span="short")
        s2 = _state(engine)
        _scripted(monkeypatch, engine, randints=[l_lo])
        _, _, d2, _, _ = _run(engine, s2, span="long")
        assert d2["exp"] > d1["exp"] * 20

    def test_span_is_reported_back_to_the_client(self, engine, monkeypatch):
        """前端要靠 detail.span 显示耗时——不回传就等于没做。"""
        for span in ("short", "medium", "long"):
            s = _state(engine)
            meta: dict = {}
            _scripted(monkeypatch, engine, randints=[engine.CULTIVATE_SPAN[span][0]])
            _run(engine, s, span=span, meta=meta)
            assert meta["cultivate"]["span"] == span
            # short 只是 v3.1 兼容标记，只在 short 档回传
            if span == "short":
                assert meta["cultivate"]["short"] is True
            else:
                assert "short" not in meta["cultivate"]


# ---------------------------------------------------------------- 方案三：场景节奏
class TestScenePace:
    def test_default_and_whitelist(self, engine):
        s = engine.sanitize_state({})
        assert s["scene_pace"] in engine.SCENE_PACE

    def test_injected_pace_is_clamped(self, engine):
        """防注入：非法节奏一律回落到默认，不得污染提示词。"""
        s = engine.sanitize_state({"scene_pace": "HACK", "calm_streak": 99999})
        assert s["scene_pace"] == engine.DEFAULT_SCENE_PACE
        assert s["calm_streak"] <= 999

    def test_breakthrough_resolves(self, engine):
        assert engine.infer_scene_pace({}, "cultivate", {"success": True}) == "resolve"
        assert engine.infer_scene_pace({}, "cultivate", {"ending": True}) == "resolve"

    def test_fight_and_npc_resolve(self, engine):
        assert engine.infer_scene_pace({}, "fight", {"fight": True}) == "resolve"
        assert engine.infer_scene_pace({}, "other", None, [{"name": "x"}]) == "resolve"

    def test_explore_is_action(self, engine):
        assert engine.infer_scene_pace({}, "explore") == "action"

    def test_calm_streak_breeds_downtime(self, engine):
        assert engine.infer_scene_pace({"calm_streak": 1}, "rest") == "action"
        assert engine.infer_scene_pace(
            {"calm_streak": engine.DOWNTIME_STREAK}, "rest") == "downtime"

    def test_long_retreat_breaks_the_calm_streak(self, engine):
        """整段闭关不算「平静短行动」——否则连续闭关会误判成空白期。"""
        assert engine.infer_scene_pace(
            {"calm_streak": engine.DOWNTIME_STREAK}, "cultivate", None, None, "long") == "action"

    def test_pace_is_written_at_the_end_of_the_turn(self, engine, monkeypatch):
        """节奏在回合末写入，供**下一轮**使用，并回传给前端。"""
        s = _state(engine)
        meta: dict = {}
        _scripted(monkeypatch, engine, randints=[10])
        _run(engine, s, tag="rest", meta=meta)
        assert s["scene_pace"] in engine.SCENE_PACE
        assert meta["scene_pace"] == s["scene_pace"]
        assert s["calm_streak"] == 1          # rest 是平静行动

    def test_consecutive_calm_turns_reach_downtime(self, engine, monkeypatch):
        s = _state(engine)
        for i in range(engine.DOWNTIME_STREAK):
            _scripted(monkeypatch, engine, randints=[10])
            _run(engine, s, tag="rest")
        assert s["scene_pace"] == "downtime"
        assert s["calm_streak"] >= engine.DOWNTIME_STREAK

    def test_a_fight_resets_to_resolve(self, engine, monkeypatch):
        s = _state(engine)
        _scripted(monkeypatch, engine, randints=[2])
        _run(engine, s, tag="fight", trial={"fight": True, "outcome": "win"})
        assert s["scene_pace"] == "resolve"
        assert s["calm_streak"] == 0


# ---------------------------------------------------------------- 端到端
class TestSpanThroughApi:
    @staticmethod
    def _live_state(engine):
        return engine.sanitize_state({"realm_index": 8, "spirit_root": "三灵根·金木水",
                                      "spirit_stones": 9999})

    @pytest.mark.parametrize("payload,days_hi,expect_span", [
        ({"type": "choice", "text": "行功一个周天", "tag": "cultivate", "span": "short"}, 7, "short"),
        ({"type": "choice", "text": "静修数月", "tag": "cultivate", "span": "medium"}, 120, "medium"),
        ({"type": "choice", "text": "闭关苦修，不问寒暑", "tag": "cultivate", "span": "long"},
         99999, "long"),
    ])
    def test_act_honours_span(self, engine, client, monkeypatch, payload, days_hi, expect_span):
        _scripted(monkeypatch, engine, randints=[engine.CULTIVATE_SPAN[expect_span][0]])
        r = client.post("/api/act", json={"state": self._live_state(engine), "action": payload})
        assert r.status_code == 200
        d = r.json()
        days = d["state"]["days"]
        assert 1 <= days <= days_hi, f"{expect_span} 档推进了 {days} 天"
        assert d["engine_meta"]["cultivate"]["span"] == expect_span

    def test_legacy_short_payload_still_works(self, engine, client, monkeypatch):
        """老前端只发 short=True（不发 span），行为不得改变。"""
        _scripted(monkeypatch, engine, randints=[3])
        r = client.post("/api/act", json={
            "state": self._live_state(engine),
            "action": {"type": "choice", "text": "行功一个周天", "tag": "cultivate", "short": True},
        })
        d = r.json()
        assert d["state"]["days"] <= engine.CULTIVATE_SPAN["short"][1]
        assert d["state"]["age"] == engine.START_AGE

    def test_stream_reports_span_too(self, engine, client, monkeypatch):
        _scripted(monkeypatch, engine, randints=[3])
        r = client.post("/api/act/stream", json={
            "state": self._live_state(engine),
            "action": {"type": "choice", "text": "行功一个周天", "tag": "cultivate", "span": "short"},
        })
        assert r.status_code == 200
        assert '"span": "short"' in r.text or '"span":"short"' in r.text
