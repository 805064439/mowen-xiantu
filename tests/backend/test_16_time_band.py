# -*- coding: utf-8 -*-
"""v3.4：叙事时间带 —— 天数前置，剧情必须覆盖这段跨度

事故回顾：天数原先在 AI 写完剧情**之后**才掷出（`_postprocess_turn` 里），
模型动笔时对「这一轮要过多久」一无所知，于是永远写「当下这一刻」：
一份实测日志里，11 轮剧情从「天色微暮」到「天已全黑」——一夜都没过完，
系统却累计推进了 683 天（探索 mid 档一档就是 25~60 天，high 档 80~160 天）。

修法不改任何数值表，只改**谁知道天数、什么时候知道**：
    1. 天数前置到调 AI 之前（action_exp 只吃 tag/tier/span，与 AI 输出无关）；
    2. 天数 + 所属时间带 + 该带的落笔要求，一并注入提示词；
    3. 剧情与时间带打架只记录不重试（先攒真实冲突率，再决定要不要加严）。

这里钉死四件事：
    1. 时间带分界与文案正确（跨带即换写法要求）；
    2. 天数前置后**不会掷第二次**——同一轮掷两次，提示词里的天数就与结算分家了；
    3. 提示词确实带上了天数与写法要求，系统铁律里也有对应约束；
    4. 冲突自检能抓住「写着片刻却过了上百天」和它的反面。
"""
from __future__ import annotations

import pytest


def _state(engine, **extra):
    return engine.sanitize_state({"realm_index": 0, "spirit_root": "单灵根·水",
                                  "spirit_stones": 999, **extra})


# ---------------------------------------------------------------- 时间带
class TestTimeBand:
    @pytest.mark.parametrize("days,label", [
        (0, "片刻"), (1, "片刻"),
        (2, "一两日"), (7, "一两日"),
        (8, "旬日内"), (20, "旬日内"),
        (21, "半月到一月"), (45, "半月到一月"),
        (46, "月余"), (90, "月余"),
        (91, "数月"), (200, "数月"),
        (201, "经年"), (2340, "经年"),
    ])
    def test_band_boundaries(self, engine, days, label):
        """跨带即换落笔要求，边界值必须落对——错一档，写法要求就对不上天数。"""
        assert engine.time_band_of(days)["label"] == label

    def test_band_carries_writing_rule(self, engine):
        """每条带都要带写法要求：只给天数不给写法，模型照样写瞬间动作。"""
        for days in (1, 15, 30, 60, 150, 1800):
            band = engine.time_band_of(days)
            assert band["days"] == days
            assert len(band["rule"]) >= 8, f"{days} 天这一档没给落笔要求"

    def test_long_bands_demand_time_progression(self, engine):
        """长跨度必须要求写出时间推进——这正是旧版缺失的那句话。"""
        for days in (46, 150, 1800):
            rule = engine.time_band_of(days)["rule"]
            assert any(w in rule for w in ("推进", "略写", "收束", "变化", "辗转", "迁徙")), rule

    def test_garbage_days_do_not_crash(self, engine):
        assert engine.time_band_of(None)["label"] == "片刻"
        assert engine.time_band_of("nonsense")["label"] == "片刻"
        assert engine.time_band_of(-50)["days"] == 0


# ---------------------------------------------------------------- 天数前置
class TestDaysPreRoll:
    def test_preroll_is_used_verbatim(self, engine):
        """传了 pre_roll 就必须原样用——再掷一次，提示词与结算就分家了。"""
        state = _state(engine)
        meta: dict = {}
        pre = engine.action_exp("explore", "high", False, None)
        engine._postprocess_turn(
            state,
            {"delta": {"exp": 0}, "choices": [], "narrative": "正文正文正文正文正文正文。", "memory": ""},
            meta, "探查", "explore", tier="high", pre_roll=pre)
        assert meta["cultivate"]["days"] == pre[1]
        assert meta["time_band"] == engine.time_band_of(pre[1])["label"]

    def test_no_preroll_still_rolls(self, engine):
        """未前置（老调用）时仍要自己掷，兼容性不能断。"""
        state = _state(engine)
        meta: dict = {}
        engine._postprocess_turn(
            state,
            {"delta": {"exp": 0}, "choices": [], "narrative": "正文正文正文正文正文正文。", "memory": ""},
            meta, "静养", "rest")
        days = meta["cultivate"]["days"]
        lo, hi = engine.ACTION_DAYS["rest"]
        assert lo <= days <= hi

    def test_two_turns_with_same_preroll_are_deterministic(self, engine):
        """同一份 pre_roll 走两遍，天数与修为必须一模一样（无二次随机）。"""
        pre = engine.action_exp("cultivate", None, False, "medium")
        out = []
        for _ in range(2):
            state = _state(engine)
            meta: dict = {}
            engine._postprocess_turn(
                state,
                {"delta": {"exp": 0}, "choices": [], "narrative": "正文正文正文正文正文正文。", "memory": ""},
                meta, "行功", "cultivate", span="medium", pre_roll=pre)
            out.append((meta["cultivate"]["days"], meta["cultivate"]["day_exp"]))
        assert out[0] == out[1]


# ---------------------------------------------------------------- 提示词
class TestPromptCarriesDays:
    def test_user_prompt_has_time_section(self, engine):
        state = _state(engine)
        days = 143
        p = engine.build_user_prompt(state, {"type": "choice", "text": "追那足印", "tag": "explore"},
                                     "（无判定）", days=days)
        assert "【本轮时序】" in p
        assert f"将流逝 {days} 天" in p
        assert engine.time_band_of(days)["label"] in p
        assert "不是按下选项的那一瞬间" in p

    def test_no_days_no_section(self, engine):
        """没给天数就不硬塞一段——旧调用路径不该被污染。"""
        state = _state(engine)
        p = engine.build_user_prompt(state, {"type": "choice", "text": "赶路"}, "（无判定）")
        assert "【本轮时序】" not in p

    def test_system_prompt_demands_consistency(self, engine):
        sp = engine.SYSTEM_PROMPT
        assert "【本轮时序】" in sp, "系统铁律没约束叙事与时序必须一致"
        assert "严重脱节" in sp

    def test_system_prompt_explains_tier_is_duration(self, engine):
        """探索三档 = 耗时，这条不讲明白，AI 就永远只按「危险」标 risk。"""
        sp = engine.SYSTEM_PROMPT
        for tier, lo, hi in (("low", 5, 20), ("mid", 25, 60), ("high", 80, 160)):
            assert tier in sp
            assert f"{lo}~{hi} 天" in sp


# ---------------------------------------------------------------- 冲突自检
class TestTimeConflict:
    def test_moment_words_in_long_span(self, engine):
        """过了 143 天，却通篇写「片刻」「半晌」——正是旧日志的样子。"""
        hit = engine.detect_time_conflict("你屏息片刻，半晌后缓过一口气来。", 143)
        assert hit and hit["kind"] == "moment_in_long_span"
        assert hit["hits"] >= 2

    def test_span_words_in_short_turn(self, engine):
        """只过了一天，却写「三年过去」——反向脱节也要抓。"""
        hit = engine.detect_time_conflict("三年过去，你终于出关。", 3)
        assert hit and hit["kind"] == "span_in_short_turn"

    def test_consistent_narrative_is_clean(self, engine):
        assert engine.detect_time_conflict("这一月里，你三度往返荒泽，终无所获。", 40) is None
        assert engine.detect_time_conflict("你屏息片刻，剑锋一颤。", 2) is None

    def test_long_span_with_span_words_is_clean(self, engine):
        """长跨度里出现长时词是正常的，只有「通篇瞬时词」才算问题。"""
        assert engine.detect_time_conflict("数年过去，你鬓角已见霜色。", 1800) is None
