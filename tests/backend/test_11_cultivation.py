# -*- coding: utf-8 -*-
"""修炼节奏：行动系数 / 连击加成 / 状态修正 / tag 推断 / 闭门保护 / 单轮上限。

这些数值是「玩家选择能否加速修行」的全部依据，一旦漂移，本文件必须先红。

v2 起修为改「按天产出」（见《时间/寿元系统 最终配平方案 v2》）：
    最终 exp = (天数 × 日效率 + 奇遇) × 灵根 × 连击 × 状态 × 闭门衰减 × 风险波动
行动差异已由 DAY_EFF 表达（0.110 vs 0.002），故该路径不再乘 ACTION_CULTIVATE_COEFF；
行动系数表保留，仅供展示与兼容（coeff 明细里的 action_coeff 仍会回传前端）。
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

    @pytest.mark.parametrize("tag", ["cultivate", "rest", "fight", "explore",
                                      "trade", "other", "unknown_tag"])
    def test_exp_scaled_by_action(self, engine, base_state, tag, lock_days, expect_exp):
        """修为 = 天数 × 日效率 × 系数；未知 tag 退为 other 的基准，不得抛错。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        lo = engine.ACTION_DAYS.get(tag, (5, 20))[0]
        lock_days(lo)   # 固定天数 + 关掉奇遇，验证公式本身
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
            {}, "行动", tag, risk_roll=0)
        assert delta["exp"] == expect_exp(s, tag, lo)

    def test_ai_exp_does_not_leak_into_the_number(self, engine, base_state, lock_days, expect_exp):
        """v2：AI 只管叙事，修为由代码按天产出——AI 提议的修为不再入账（AI_EXP_WEIGHT=0）。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        lo = engine.ACTION_DAYS["cultivate"][0]
        lock_days(lo)
        _, _, low, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 1}, "choices": [], "narrative": "n", "memory": "m"},
            {}, "行动", "cultivate", risk_roll=0)
        s2 = engine.sanitize_state({**base_state, "spirit_stones": 999})
        lock_days(lo)
        meta = {}
        _, _, high, _, _ = engine._postprocess_turn(
            s2, {"delta": {"exp": 40}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "行动", "cultivate", risk_roll=0)
        assert low == high                       # AI 给 1 还是 40，入账完全一样
        assert meta["cultivate"]["ai_exp"] == 40  # 但仍在明细里留痕，便于排查

    def test_cultivate_is_more_than_twice_trade(self, engine, base_state, lock_days):
        """潜心修行相对坊市交易必须拉开明显差距，否则取舍不成立。"""
        gains = {}
        for tag in ("cultivate", "trade"):
            s = engine.sanitize_state({**base_state, "spirit_stones": 999})
            lock_days(engine.ACTION_DAYS[tag][0])
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

    def test_streak_bonus_grows_the_day_yield(self, engine, base_state, lock_days):
        """连修第 3 轮才吃到加成——第一轮的连击是 0，不能自肥。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        days = engine.ACTION_DAYS["cultivate"][0]
        seen = []
        for _ in range(4):
            lock_days(days)
            meta = {}
            _, _, delta, _, _ = engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                meta, "打坐", "cultivate")
            seen.append((s["cultivate_streak"], delta["exp"]))
        # 天数相同、系数随连击递增 → 修为必须单调不减，且第 3 轮起明显抬升
        assert seen[0][1] == seen[1][1]      # 连击 0 / 1 都无加成
        assert seen[2][1] > seen[1][1]       # 连击 2 → 1.1
        assert seen[3][1] > seen[2][1]       # 连击 3 → 1.2

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

    def test_wounded_cultivation_is_slower(self, engine, base_state, lock_days):
        """同样的打坐，重伤时收获更少——回血因此有了修行意义。"""
        results = {}
        for hp in (100, 40):
            s = engine.sanitize_state({**base_state, "spirit_stones": 999, "hp": hp, "qi": 50})
            lock_days(engine.ACTION_DAYS["cultivate"][0])   # 天数一致，只比状态系数
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
    def test_seclusion_penalty_after_cap(self, engine, base_state, lock_days):
        """枯坐越过阈值（第 6 轮）仍不收手 → 效率打八折（v2：0.6 → 0.8）+ 剧情提示出门。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "cultivate_streak": 6, "seclusion_streak": 6})
        lock_days(engine.ACTION_DAYS["cultivate"][0])
        meta = {}
        narrative, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "你闭目行功。", "memory": "m"},
            meta, "闭关苦修", "cultivate")
        assert meta["cultivate"]["secluded"] is True
        assert meta["cultivate"]["seclusion"] == pytest.approx(0.8)
        assert delta["exp"] > 0
        assert engine.SECLUSION_HINT in narrative

    @pytest.mark.parametrize("streak,expected", [
        (5, 1.0),   # 未越界：不衰减
        (6, 0.8),   # 0.8^1
        (7, 0.64),  # 0.8^2
        (8, 0.6),   # 0.8^3 = 0.512 → 触底 0.6
        (12, 0.6),  # 触底后不再恶化，但不至于归零
    ])
    def test_seclusion_decays_with_floor(self, engine, base_state, streak, expected):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "seclusion_streak": streak})
        assert engine._seclusion_coeff(s, "cultivate") == pytest.approx(expected)

    def test_rest_keeps_streak_but_breaks_seclusion(self, engine, base_state):
        """v2 的关键分离：静养吃连击加成，但不算枯坐——闭门只惩罚真正的死磕。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        for _ in range(5):
            engine._update_cultivate_streak(s, "cultivate")
        engine._update_cultivate_streak(s, "rest")
        assert s["cultivate_streak"] == 6      # 连击继续攒
        assert s["seclusion_streak"] == 0      # 枯坐归零 → 不吃衰减
        assert engine._seclusion_coeff(s, "cultivate") == 1.0
        assert engine._cultivate_streak_coeff(s) == 1.4

    def test_cap_is_reachable_before_penalty(self, engine):
        """封顶档必须落在惩罚之前——否则 1.4 加成永远吃不到，取舍就成了假的。"""
        assert engine.STREAK_CAP < engine.SECLUSION_STREAK

    def test_seclusion_does_not_hit_exploration(self, engine, base_state, lock_days):
        """闭门惩罚只针对枯坐，出门照样全额。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "cultivate_streak": 9, "seclusion_streak": 9})
        lock_days(engine.ACTION_DAYS["explore"][0])
        meta = {}
        narrative, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 10}, "choices": [], "narrative": "下山去了。", "memory": "m"},
            meta, "下山采买", "explore", risk_roll=0)   # 均值：验证闭门惩罚只对枯坐生效
        assert meta["cultivate"]["secluded"] is False
        assert engine.SECLUSION_HINT not in narrative
        assert s["cultivate_streak"] == 0   # 出门即断连
        assert s["seclusion_streak"] == 0

    def test_single_turn_can_not_fill_a_realm(self, engine, base_state, lock_days):
        """最强配置 + 最长时间的闭关，也不许一轮圆满。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "spirit_root": "天灵根·火", "cultivate_streak": 5})
        lock_days(engine.ACTION_DAYS["cultivate"][1])   # 810 天，闭关上限
        meta = {}
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 40}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "闭关", "cultivate")
        assert delta["exp"] <= engine.exp_max_of(0) // 2
        assert meta["cultivate"]["capped"] is True

    def test_cap_not_triggered_in_late_realm(self, engine, base_state, lock_days):
        """后期境界需求大，正常收益不该被误伤。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "realm_index": 8,
                                   "hp": 300, "hp_max": 300, "qi": 200, "qi_max": 200})
        lock_days(engine.ACTION_DAYS["cultivate"][0])   # 270 天，闭关下限
        meta = {}
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 40}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "行功", "cultivate")
        assert meta["cultivate"]["capped"] is False
        assert delta["exp"] > 0


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
        assert isinstance(c["base"], float)      # 天数 × 日效率
        assert isinstance(c["days"], int)        # 本轮流逝天数（时间系统的地基）
        assert c["day_exp"] > 0
        assert isinstance(c["coeff"], float)

    def test_meta_absent_when_exp_is_penalty(self, engine, base_state):
        """AI 给的修为折损不产出任何修为明细——惩罚不吃加成，也不该有「本轮速度」。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta = {}
        engine._postprocess_turn(
            s, {"delta": {"exp": -5}, "choices": [], "narrative": "n", "memory": "m"},
            meta, "走火入魔", "other")
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
    """跑完炼气九层，验证「选择决定节奏」确实成立。

    v2 起修为按天产出，故不再喂固定基准修为——量的就是「时间换修为」的速度。
    不掷骰（突破一律成功），才能稳定量出期望速度；随机性由 tools/sim_lifespan.py 覆盖。
    注意：炼气九层总需求 3450（= EXP_NEED[0]），REALM_TABLE 的曲线才是权威。
    """

    ALWAYS = staticmethod(lambda engine, s: "cultivate")
    # 「张弛有度」：枯坐到阈值前出门一趟，把衰减永久重置
    SMART = staticmethod(lambda engine, s: "explore" if s["seclusion_streak"] >= engine.SECLUSION_STREAK
                         else "cultivate")

    @staticmethod
    def run(engine, pick, root="三灵根·水火木", max_turns=4000):
        """pick(engine, state) → 本轮 tag。返回 (轮数, 终局年龄)。"""
        s = engine.sanitize_state({
            "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
            "exp": 0, "spirit_stones": 99999, "spirit_root": root,
            "items": [], "memory": [], "recent": [], "turn": 0,
        })
        turns = 0
        while s["realm_index"] < 9 and turns < max_turns:
            turns += 1
            engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "行动", pick(engine, s), risk_roll=0)
            # 修为圆满即冲关（确定性：必定成功）
            if s["exp"] >= engine.exp_max_of(s["realm_index"]):
                engine.apply_trial(s, {"success": True})
        return turns, s["age"]

    @staticmethod
    def tag_picker(tag):
        return lambda engine, s: tag

    def test_cultivate_beats_explore_and_trade(self, engine):
        smart, _ = self.run(engine, self.SMART)
        explore, _ = self.run(engine, self.tag_picker("explore"))
        trade, _ = self.run(engine, self.tag_picker("trade"))
        assert smart < explore * 0.8
        assert explore < trade

    def test_mindless_meditation_is_not_optimal(self, engine):
        """无脑连点打坐必然撞上枯坐惩罚，反而比「修行—出门」的节奏更慢。

        这是本机制的关键价值：让玩家真的需要做取舍，而不是找到一键最优解。"""
        mindless, _ = self.run(engine, self.ALWAYS)
        smart, _ = self.run(engine, self.SMART)
        assert mindless > smart
        # 而且慢的那条路要多耗寿命——这正是寿元压力的来源
        assert self.run(engine, self.ALWAYS)[1] > self.run(engine, self.SMART)[1]

    def test_focused_route_is_in_reasonable_range(self, engine):
        """取舍流的量级锚点：约 70 轮 / 100 岁（与 tools/sim_lifespan.py 同量级）。"""
        turns, age = self.run(engine, self.SMART)
        assert 50 <= turns <= 110
        assert 80 <= age <= 140

    def test_no_single_button_route_beats_the_tradeoff(self, engine):
        """任何「一键到底」的路线都不该打赢需要取舍的节奏流。

        若某条单键路线反超，玩家会立刻收敛到它，整套节奏设计就白做了。"""
        smart, _ = self.run(engine, self.SMART)
        for tag in ("cultivate", "rest", "explore", "trade", "fight"):
            assert self.run(engine, self.tag_picker(tag))[0] > smart, f"单键路线 {tag} 反超了取舍流"

    def test_baseline_total_is_the_balance_anchor(self, engine):
        """炼气期总需求 3450 = EXP_NEED[0]，是整套配平的分母。"""
        total = sum(row[1] for row in engine.REALM_TABLE)
        assert total == 3450
        assert engine.EXP_NEED[0] == total


# ---------------------------------------------------------------- 杠杆 X：高风险行动波动收益
class TestRiskVolatility:
    """文档总览原称「机缘/风险系数」——高风险行动修为有 ± 宽幅随机波动，均值 1.0。"""

    def test_low_risk_tags_never_fluctuate(self, engine):
        for tag in ("cultivate", "rest", "trade", "other"):
            assert engine._risk_coeff(tag) == 1.0
            assert engine._risk_coeff(tag, roll=0.9) == 1.0   # 低风险即便指定 roll 也不波动

    def test_bounds_with_explicit_roll(self, engine):
        assert engine._risk_coeff("fight", roll=1.0) == pytest.approx(1.4)    # 1 + 0.40
        assert engine._risk_coeff("fight", roll=-1.0) == pytest.approx(0.6)   # 1 - 0.40
        assert engine._risk_coeff("explore", roll=1.0) == pytest.approx(1.18) # 1 + 0.18
        assert engine._risk_coeff("explore", roll=-1.0) == pytest.approx(0.82)

    def test_zero_roll_is_the_mean(self, engine):
        assert engine._risk_coeff("fight", roll=0) == 1.0
        assert engine._risk_coeff("explore", roll=0) == 1.0

    def test_random_mean_is_near_one(self, engine):
        rolls = [engine._risk_coeff("fight") for _ in range(3000)]
        assert abs(sum(rolls) / len(rolls) - 1.0) < 0.04

    def test_multiplier_carries_risk_detail(self, engine, base_state):
        s = engine.sanitize_state({**base_state})
        _, d = engine.cultivate_multiplier(s, "cultivate", risk_roll=0)
        assert d["risk"] == 1.0 and d["risk_label"] == ""
        _, d2 = engine.cultivate_multiplier(s, "fight", risk_roll=1.0)
        assert d2["risk"] == pytest.approx(1.4)
        assert d2["risk_label"] == "机缘"
        _, d3 = engine.cultivate_multiplier(s, "fight", risk_roll=-1.0)
        assert d3["risk_label"] == "事与愿违"

    def test_volatility_enters_total_coeff(self, engine, base_state):
        """满 roll 的斗法，综合系数应比均值明显更高（验证波动真的进了结算）。"""
        s = engine.sanitize_state({**base_state, "spirit_root": "天灵根·火"})
        _, mean = engine.cultivate_multiplier(s, "fight", risk_roll=0)
        _, best = engine.cultivate_multiplier(s, "fight", risk_roll=1.0)
        assert best["coeff"] > mean["coeff"] * 1.3


# ---------------------------------------------------------------- 闭门剧情打断（文档 §5.2）
class TestDisturbance:
    """连修枯坐到阈值，强制砸一场「外界打扰」事件进来——惩罚（代码衰减）+ 叙事（打扰）双管齐下。"""

    def test_prompt_note_only_when_secluded(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "seclusion_streak": 6})
        assert isinstance(engine._seclusion_prompt_note(s, "cultivate"), str)   # 枯坐且达阈值
        assert engine._seclusion_prompt_note(s, "explore") is None              # 非枯坐不触发
        assert engine._seclusion_prompt_note(s, "rest") is None                 # 静养不算枯坐
        s2 = engine.sanitize_state({**base_state, "seclusion_streak": 5})
        assert engine._seclusion_prompt_note(s2, "cultivate") is None           # 未达阈值
        # 连修很高但从未枯坐（一直穿插静养）→ 不该触发打扰
        s3 = engine.sanitize_state({**base_state, "cultivate_streak": 9, "seclusion_streak": 0})
        assert engine._seclusion_prompt_note(s3, "cultivate") is None

    def test_disturbance_event_shape(self, engine):
        ev = engine._disturbance_event()
        tags = [c["tag"] for c in ev["choices"]]
        assert "explore" in tags          # 必须给出「出门应对」走向
        assert len(ev["choices"]) == 3

    def test_mock_mode_injects_disturbance(self, engine, base_state, monkeypatch):
        monkeypatch.setattr(engine, "API_KEY", "")
        monkeypatch.setattr(engine, "_OPENAI_OK", False)
        s = engine.sanitize_state({**base_state, "cultivate_streak": 7, "seclusion_streak": 7})
        note = engine._seclusion_prompt_note(s, "cultivate")
        data, meta = engine.generate_scene(s, {"text": "继续打坐"}, "", False, note)
        assert meta.get("disturbance") is True
        assert any(k in data["narrative"] for k in ("秘境", "访客", "邀约"))

    def test_real_mode_sets_disturbance_flag(self, engine, base_state, monkeypatch):
        monkeypatch.setattr(engine, "API_KEY", "x")
        monkeypatch.setattr(engine, "_OPENAI_OK", True)
        monkeypatch.setattr(engine, "_get_client", lambda: (_ for _ in ()).throw(
            RuntimeError("强制走兜底")))
        s = engine.sanitize_state({**base_state, "cultivate_streak": 8, "seclusion_streak": 8})
        note = engine._seclusion_prompt_note(s, "cultivate")
        data, meta = engine.generate_scene(s, {"text": "继续打坐"}, "", False, note)
        assert meta.get("disturbance") is True     # 即便 AI 失败走兜底，标记仍在
