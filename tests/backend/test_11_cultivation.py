# -*- coding: utf-8 -*-
"""修炼节奏：行动系数 / 连击加成 / 状态修正 / tag 推断 / 闭门保护 / 单轮上限。

这些数值是「玩家选择能否加速修行」的全部依据，一旦漂移，本文件必须先红。
计算方法统一见 server.cultivate_multiplier：
    最终 exp = AI_base × 灵根 × 行动系数 × 连击加成 × 状态修正（向下取整）
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------- 杠杆 1：行动类型系数
class TestActionCoefficient:
    def test_table_values_match_design(self, engine):
        assert engine.ACTION_CULTIVATE_COEFF == {
            "cultivate": 1.8, "rest": 1.3, "fight": 1.2,
            "explore": 1.0, "trade": 0.8, "other": 1.0,
        }

    def test_every_tag_has_a_label(self, engine):
        """每个系数都要有中文名，否则前端只能显示英文 tag。"""
        for tag in engine.ACTION_CULTIVATE_COEFF:
            assert tag in engine.ACTION_CULTIVATE_LABEL
            assert engine.ACTION_CULTIVATE_LABEL[tag]

    @pytest.mark.parametrize("tag,expected", [
        ("cultivate", 18),   # 10 × 1.8
        ("rest", 13),        # 10 × 1.3
        ("fight", 12),       # 10 × 1.2
        ("explore", 10),     # 基准
        ("trade", 8),        # 10 × 0.8
        ("other", 10),
        ("unknown_tag", 10),  # 未知 tag 退为基准，不得抛错
    ])
    def test_exp_scaled_by_action(self, engine, base_state, tag, expected):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
            {}, "行动", tag)
        assert delta["exp"] == expected

    def test_cultivate_is_more_than_twice_trade(self, engine, base_state):
        """潜心修行相对坊市交易必须拉开明显差距，否则取舍不成立。"""
        gains = {}
        for tag in ("cultivate", "trade"):
            s = engine.sanitize_state({**base_state, "spirit_stones": 999})
            _, _, delta, _, _ = engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "行动", tag)
            gains[tag] = delta["exp"]
        assert gains["cultivate"] > gains["trade"] * 2


# ---------------------------------------------------------------- tag 推断（保证机制不退化）
class TestInferActionTag:
    @pytest.mark.parametrize("action,expected", [
        ({"tag": "cultivate", "text": "随便写什么"}, "cultivate"),   # 合法 tag 直接用
        ({"tag": "FIGHT", "text": "出手"}, "fight"),                  # 大小写不敏感
        ({"tag": "打坐", "text": "静下心来"}, "cultivate"),           # 中文 tag 也参与推断
        ({"tag": "", "text": "在破庙打坐半日"}, "cultivate"),          # 关键词推断
        ({"tag": "", "text": "疗伤包扎"}, "rest"),
        ({"tag": "", "text": "继续赶路，前往青牛镇"}, "explore"),
        ({"tag": "", "text": "向摊主问价"}, "trade"),
        ({"tag": "", "text": "拔剑动手"}, "fight"),
        ({"tag": "", "text": "出手相助那位道友"}, "other"),            # 不得误判为斗法
        ({"tag": "", "text": "沉吟片刻"}, "other"),
        ({"tag": "breakthrough", "text": "闭关，冲击炼气二层"}, "breakthrough"),  # 冲关 tag 保留
        ({"tag": "", "text": "闭关修炼"}, "cultivate"),                # "闭关"非冲关时算修行
        ("not a dict", "other"),
        (None, "other"),
    ])
    def test_inference(self, engine, action, expected):
        assert engine.infer_action_tag(action) == expected

    def test_choices_are_normalized(self, engine, base_state):
        """AI 输出中文 tag 时，下发给前端的 tag 必须已是合法枚举。"""
        raw = [
            {"text": "在破庙打坐", "risk": "low", "tag": "修炼"},
            {"text": "向摊主问价", "risk": "low", "tag": "交易"},
            {"text": "拔剑动手", "risk": "high", "tag": "打架"},
        ]
        out = engine.normalize_choices(raw, base_state)
        assert [c["tag"] for c in out] == ["cultivate", "trade", "fight"]

    def test_free_text_choice_still_gets_a_tag(self, engine, base_state):
        """自由输入的 tag 由前端回传，缺失时走关键词而不是全退 other。"""
        assert engine.infer_action_tag({"type": "custom", "text": "盘膝打坐运转周天"}) == "cultivate"


# ---------------------------------------------------------------- 杠杆 2：连击
class TestCultivateStreak:
    def test_streak_counts_only_cultivation(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        engine._update_cultivate_streak(s, "cultivate")
        engine._update_cultivate_streak(s, "rest")
        assert s["cultivate_streak"] == 2
        engine._update_cultivate_streak(s, "explore")   # 出门 → 断
        assert s["cultivate_streak"] == 0

    def test_streak_stored_capped(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        for _ in range(50):
            engine._update_cultivate_streak(s, "cultivate")
        assert s["cultivate_streak"] == engine.STREAK_STORE_MAX
        # 存储可以超限，但加成只认表格，不会无限膨胀
        assert engine._cultivate_streak_coeff(s) == 1.4

    @pytest.mark.parametrize("streak,expected", [
        (0, 1.0), (1, 1.0), (2, 1.10), (3, 1.20), (4, 1.20), (5, 1.40), (99, 1.40),
    ])
    def test_streak_coeff_table(self, engine, streak, expected):
        assert engine._cultivate_streak_coeff({"cultivate_streak": streak}) == pytest.approx(expected)

    def test_streak_bonus_applies_from_third_turn(self, engine, base_state):
        """连修第 3 轮才吃到加成——第一轮的连击是 0，不能自肥。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        seen = []
        for _ in range(4):
            meta = {}
            _, _, delta, _, _ = engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                meta, "打坐", "cultivate")
            seen.append((s["cultivate_streak"], delta["exp"]))
        assert seen[0] == (1, 18)     # 10 × 1.8
        assert seen[1] == (2, 18)     # 连击 1 → 仍无加成
        assert seen[2] == (3, 19)     # 连击 2 → 1.1 → 19.8
        assert seen[3] == (4, 21)     # 连击 3 → 1.2 → 21.6

    def test_streak_survives_roundtrip(self, engine, base_state):
        """连击随存档往返：前端存了就得认，且被钳在合法区间。"""
        s = engine.sanitize_state({**base_state, "cultivate_streak": 99})
        assert s["cultivate_streak"] == engine.STREAK_STORE_MAX
        s = engine.sanitize_state({**base_state, "cultivate_streak": -5})
        assert s["cultivate_streak"] == 0
        s = engine.sanitize_state({**base_state})
        assert s["cultivate_streak"] == 0     # 旧档没有此字段 → 默认 0


# ---------------------------------------------------------------- 杠杆 3：状态修正
class TestVitalityCoefficient:
    @pytest.mark.parametrize("hp,qi,expected", [
        (100, 50, 1.0),      # 满血满灵
        (70, 35, 0.91),      # 七成
        (50, 25, 0.85),      # 半状态
        (10, 5, 0.73),       # 濒死
        (0, 0, 0.7),         # 理论下限（实际会触发濒死协议）
    ])
    def test_vitality(self, engine, base_state, hp, qi, expected):
        s = engine.sanitize_state({**base_state, "hp": hp, "qi": qi})
        assert engine._vitality_coeff(s) == pytest.approx(expected, abs=0.01)

    def test_wounded_cultivation_is_slower(self, engine, base_state):
        """同样的打坐，重伤时收获更少——回血因此有了修行意义。"""
        results = {}
        for hp in (100, 40):
            s = engine.sanitize_state({**base_state, "spirit_stones": 999, "hp": hp, "qi": 50})
            _, _, delta, _, _ = engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "打坐", "cultivate")
            results[hp] = delta["exp"]
        assert results[100] > results[40]


# ---------------------------------------------------------------- 综合取值范围
class TestCombinedRange:
    def _mult(self, engine, root, tag, streak, hp_ratio):
        s = engine.sanitize_state({
            "realm_index": 0, "hp_max": 100, "qi_max": 50,
            "spirit_root": root, "cultivate_streak": streak,
            "hp": int(100 * hp_ratio), "qi": int(50 * hp_ratio),
        })
        coeff, _ = engine.cultivate_multiplier(s, tag)
        return coeff

    def test_slowest_is_about_half(self, engine):
        """四灵根 + 坊市交易 + 气血灵力尽枯 ≈ 0.42。"""
        assert self._mult(engine, "四灵根·伪灵根", "trade", 0, 0.0) == pytest.approx(0.42, abs=0.01)

    def test_fastest_is_about_four(self, engine):
        """天灵根 + 潜心修行 + 满连击 + 满状态 ≈ 4.03（尚属有效修行，不吃闭门惩罚）。"""
        assert self._mult(engine, "天灵根·火", "cultivate", 5, 1.0) == pytest.approx(4.03, abs=0.01)

    def test_spirit_root_still_matters_under_fast_play(self, engine):
        """行动系数不得盖过灵根差异：天灵根与四灵根同时潜心修行，仍须拉开一倍以上。"""
        fast = self._mult(engine, "天灵根·火", "cultivate", 5, 1.0)
        slow = self._mult(engine, "四灵根·伪灵根", "cultivate", 5, 1.0)
        assert fast > slow * 2

    def test_negative_exp_skips_all_multipliers(self, engine, base_state):
        """惩罚不吃任何加成/减免，否则修得快的人连掉血都掉得少。"""
        s = engine.sanitize_state({**base_state, "spirit_root": "天灵根·火", "exp": 50,
                                   "spirit_stones": 999})
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": -10}, "choices": [], "narrative": "n", "memory": "m"},
            {}, "受伤", "other")
        assert delta["exp"] == -10


# ---------------------------------------------------------------- 保护机制
class TestSafeguards:
    def test_seclusion_penalty_after_cap(self, engine, base_state):
        """连修越过加成封顶（第 6 轮）还枯坐 → 效率打六折 + 剧情提示出门。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "cultivate_streak": 6})
        meta = {}
        narrative, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "你闭目行功。", "memory": "m"},
            meta, "闭关苦修", "cultivate")
        # 1.8 × 1.4 = 2.52 → 再 ×0.6 = 1.512 → 15
        assert meta["cultivate"]["secluded"] is True
        assert meta["cultivate"]["seclusion"] == 0.6
        assert delta["exp"] == 15
        assert engine.SECLUSION_HINT in narrative

    @pytest.mark.parametrize("streak,expected", [
        (5, 25),   # 刚好吃满加成：1.8 × 1.4 = 2.52
        (6, 15),   # ×0.6
        (7, 9),    # ×0.36
        (8, 7),    # ×0.216 → 触底 0.3 → 1.8×1.4×0.3 = 0.756
        (12, 7),   # 触底后不再恶化，但不至于归零
    ])
    def test_seclusion_decays_with_floor(self, engine, base_state, streak, expected):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "cultivate_streak": streak})
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
            {}, "枯坐", "cultivate")
        assert delta["exp"] == expected

    def test_cap_is_reachable_before_penalty(self, engine):
        """封顶档必须落在惩罚之前——否则 1.4 加成永远吃不到，取舍就成了假的。"""
        assert engine.STREAK_CAP < engine.SECLUSION_STREAK

    def test_seclusion_does_not_hit_exploration(self, engine, base_state):
        """闭门惩罚只针对枯坐，出门照样全额。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "cultivate_streak": 9})
        meta = {}
        narrative, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "下山去了。", "memory": "m"},
            meta, "下山采买", "explore")
        assert meta["cultivate"]["secluded"] is False
        assert delta["exp"] == 10
        assert engine.SECLUSION_HINT not in narrative
        assert s["cultivate_streak"] == 0   # 出门即断连

    def test_single_turn_can_not_fill_a_realm(self, engine, base_state):
        """AI 给到上限 40 修为时，最强配置也不许一轮圆满。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "spirit_root": "天灵根·火", "cultivate_streak": 5})
        meta = {}
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 40}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "闭关", "cultivate")
        assert delta["exp"] <= engine.exp_max_of(0) // 2
        assert meta["cultivate"]["capped"] is True

    def test_cap_not_triggered_in_late_realm(self, engine, base_state):
        """后期境界需求大，正常收益不该被误伤。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "realm_index": 8,
                                   "hp": 300, "hp_max": 300, "qi": 200, "qi_max": 200})
        meta = {}
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 40}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "行功", "cultivate")
        assert meta["cultivate"]["capped"] is False
        assert delta["exp"] == 72      # 40 × 1.8


# ---------------------------------------------------------------- meta 契约（前端据此渲染）
class TestCultivateMeta:
    def test_meta_shape(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "cultivate_streak": 3})
        meta = {}
        engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "打坐", "cultivate")
        c = meta["cultivate"]
        assert c["action"] == "cultivate"
        assert c["action_label"] == "潜心修行"
        assert c["action_coeff"] == 1.8
        assert c["streak"] == 3
        assert c["streak_coeff"] == 1.2
        assert isinstance(c["vitality"], float)
        assert c["secluded"] is False
        assert c["base"] == 10
        assert isinstance(c["coeff"], float)

    def test_meta_absent_when_no_exp(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta = {}
        engine._postprocess_turn(
            s, {"delta": {}, "choices": [], "narrative": "n", "memory": "m"}, meta, "闲逛", "explore")
        assert "cultivate" not in meta


# ---------------------------------------------------------------- 冲关成功率：所见即所掷
class TestBreakthroughHint:
    def test_hint_matches_actual_roll_rate(self, engine, base_state):
        """选项上写的成功率必须就是掷的那一枚骰 —— 两者共用 breakthrough_rate。"""
        s = engine.sanitize_state({**base_state, "spirit_root": "天灵根·火", "fail_streak": 2})
        s["exp"] = engine.exp_max_of(0)
        rate, _ = engine.breakthrough_rate(s)
        choices = engine.normalize_choices([], s)
        bt = next(c for c in choices if c.get("special") == "breakthrough")
        assert f"{int(rate * 100)}%" in bt["hint"]

    def test_hint_shows_pity_bonus(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "fail_streak": 3})
        s["exp"] = engine.exp_max_of(0)
        bt = next(c for c in engine.normalize_choices([], s) if c.get("special") == "breakthrough")
        assert "天道眷顾" in bt["hint"] and "+24%" in bt["hint"]

    def test_no_hint_without_pity(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "fail_streak": 0})
        s["exp"] = engine.exp_max_of(0)
        bt = next(c for c in engine.normalize_choices([], s) if c.get("special") == "breakthrough")
        assert "天道眷顾" not in bt["hint"]

    def test_no_breakthrough_option_when_exp_insufficient(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "exp": 1})
        assert not [c for c in engine.normalize_choices([], s) if c.get("special") == "breakthrough"]

    def test_fail_streak_survives_sanitize(self, engine):
        """保底加成读的是 sanitize 后的 fail_streak，不能被路径吞掉。"""
        s = engine.sanitize_state({"fail_streak": 3, "realm_index": 0})
        _, pity = engine.breakthrough_rate(s)
        assert pity == pytest.approx(0.24)


# ---------------------------------------------------------------- 端到端：节奏真的变快了吗
class TestPacingSimulation:
    """用固定 10 点基准修为跑完炼气九层，验证「选择决定节奏」确实成立。

    不掷骰（突破一律成功），量的纯粹是「攒修为速度」。
    注意：炼气九层总需求 3450，比设计文档表格里的 2270 高——
    REALM_TABLE 的曲线才是权威，故此处按真实曲线校准断言。
    """

    ALWAYS = staticmethod(lambda engine, s: "cultivate")
    SMART = staticmethod(lambda engine, s: "explore" if s["cultivate_streak"] >= engine.SECLUSION_STREAK
                         else "cultivate")

    @staticmethod
    def run(engine, pick, base_exp=10, root="三灵根·水火木", max_turns=3000):
        """pick(engine, state) → 本轮 tag。返回跑完炼气九层所需轮数。"""
        s = engine.sanitize_state({
            "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
            "exp": 0, "spirit_stones": 99999, "spirit_root": root,
            "items": [], "memory": [], "recent": [], "turn": 0,
        })
        turns = 0
        while s["realm_index"] < 9 and turns < max_turns:
            turns += 1
            engine._postprocess_turn(
                s, {"delta": {"exp": base_exp}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "行动", pick(engine, s))
            # 修为圆满即冲关（确定性：必定成功）
            if s["exp"] >= engine.exp_max_of(s["realm_index"]):
                engine.apply_trial(s, {"success": True})
        return turns

    @staticmethod
    def tag_picker(tag):
        return lambda engine, s: tag

    def test_cultivate_beats_explore_and_trade(self, engine):
        smart = self.run(engine, self.SMART)
        explore = self.run(engine, self.tag_picker("explore"))
        trade = self.run(engine, self.tag_picker("trade"))
        # 连修 + 断连的专注流应比基准快三成以上，交易流则应最慢
        assert smart < explore * 0.7
        assert explore < trade

    def test_mindless_meditation_is_not_optimal(self, engine):
        """无脑连点打坐必然撞上枯坐惩罚，反而比「修行—出门」的节奏更慢。

        这是本机制的关键价值：让玩家真的需要做取舍，而不是找到一键最优解。"""
        mindless = self.run(engine, self.ALWAYS)
        smart = self.run(engine, self.SMART)
        assert mindless > smart * 1.5

    def test_focused_route_is_in_reasonable_range(self, engine):
        """专注流的实际量级约 180 轮（真实曲线下的合理值，非文档旧表的 95 轮）。"""
        assert 140 <= self.run(engine, self.SMART) <= 230

    def test_no_single_button_route_beats_the_tradeoff(self, engine):
        """任何「一键到底」的路线都不该打赢需要取舍的专注流。

        若某条单键路线反超，玩家会立刻收敛到它，整套节奏设计就白做了。"""
        smart = self.run(engine, self.SMART)
        for tag in ("cultivate", "rest", "explore", "trade", "fight"):
            assert self.run(engine, self.tag_picker(tag)) > smart, f"单键路线 {tag} 反超了取舍流"

    def test_baseline_route_matches_known_total(self, engine):
        """基准线 = 总需求 ÷ 每轮基准收益：3450 ÷ 10 = 345 轮（守曲线的锚点）。"""
        total = sum(row[1] for row in engine.REALM_TABLE)
        assert total == 3450
        assert self.run(engine, self.tag_picker("explore")) == 345
