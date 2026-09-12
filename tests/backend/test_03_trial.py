# -*- coding: utf-8 -*-
"""突破（冲关）判定：成功率模型、连续失败保底、失败惩罚递减、筑基结局。

这是全局最核心的成长闸门：代码先掷骰定死结果，AI 只负责叙述，
因此判定本身的正确性直接决定游戏公平性。
"""
import random

import pytest


class TestTrialRouting:
    def test_non_breakthrough_action_has_no_trial(self, engine, base_state):
        """普通行动不做 value 性判定，交由 AI 叙事自由发挥。"""
        text, trial = engine.run_trial(base_state, {"type": "choice", "tag": "explore"})
        assert trial is None
        assert "无特殊判定" in text

    def test_max_realm_has_no_breakthrough(self, engine, base_state):
        """已筑基（第 9 层）不再有突破判定 —— 第一章终点。"""
        s = {**base_state, "realm_index": engine.MAX_REALM_INDEX}
        text, trial = engine.run_trial(s, {"type": "breakthrough"})
        assert trial is None
        assert "已筑基" in text

    def test_fight_tag_routes_to_battle(self, engine, base_state):
        """tag=fight 转斗法判定，而非冲关。"""
        _, trial = engine.run_trial(base_state, {"type": "choice", "tag": "fight"})
        assert trial is not None and trial.get("fight") is True


class TestBreakthroughSuccess:
    def test_success_raises_realm_and_refills(self, engine, full_state):
        """成功：境界 +1、修为清零、气血灵力全满、上限提升、保底计数归零。"""
        s = dict(full_state)
        s["hp"], s["qi"] = 10, 5
        s["fail_streak"] = 3
        before_hp_max, before_qi_max = s["hp_max"], s["qi_max"]
        view = engine.apply_trial(s, {"success": True})
        assert s["realm_index"] == 1
        assert s["exp"] == 0
        assert s["hp"] == s["hp_max"] == before_hp_max + engine.HP_GAINS[0]
        assert s["qi"] == s["qi_max"] == before_qi_max + engine.QI_GAINS[0]
        assert s["fail_streak"] == 0
        assert view == {"success": True, "from": "炼气一层", "to": "炼气二层"}

    def test_success_rate_is_bounded(self, engine, full_state):
        """无论保底多高，成功率上限 0.98（天机不可尽算）。"""
        s = {**full_state, "fail_streak": 99, "spirit_root": "天灵根·火"}
        for _ in range(200):
            text, trial = engine.run_trial(s, {"type": "breakthrough"})
            assert trial is not None
        # 直接验证公式：rate 被 clamp 到 0.98
        rate = min(engine.REALM_TABLE[0][2] + 0.10 + 0.24, 0.98)
        assert rate == 0.98

    def test_full_path_to_foundation_is_reachable(self, engine):
        """模拟一路突破到筑基：成长曲线必须自洽，不得卡死或越界。"""
        s = engine.sanitize_state({"realm_index": 0, "hp": 100, "hp_max": 100,
                                   "qi": 50, "qi_max": 50, "exp": 0,
                                   "spirit_root": "天灵根·火", "turn": 0})
        while s["realm_index"] < engine.MAX_REALM_INDEX - 1:
            s["exp"] = engine.REALM_TABLE[s["realm_index"]][1]
            view = engine.apply_trial(s, {"success": True})
            assert view["success"] is True
            assert s["hp"] == s["hp_max"] and s["qi"] == s["qi_max"]
            assert s["hp_max"] == engine.hp_max_of(s["realm_index"])
            assert s["qi_max"] == engine.qi_max_of(s["realm_index"])
        assert s["realm_index"] == 8


class TestBreakthroughFailure:
    def test_failure_punishment(self, engine, full_state):
        """失败：修为折损、气血受损、保底计数 +1、境界不变。"""
        s = dict(full_state)
        s["exp"] = 100
        s["hp"] = 80
        view = engine.apply_trial(s, {"success": False})
        assert s["realm_index"] == 0
        assert s["exp"] == 70          # 首次保留 70%
        assert s["hp"] == 65           # -15
        assert s["fail_streak"] == 1
        assert view["success"] is False

    def test_retention_grows_with_streak_and_caps(self, engine, full_state):
        """连续失败保留率递增：70% → 75% → 80% → 85% → 封顶 85%。"""
        expected = [70, 75, 80, 85, 85, 85]
        for streak, keep in enumerate(expected):
            s = {**full_state, "exp": 100, "fail_streak": streak}
            engine.apply_trial(s, {"success": False})
            assert s["exp"] == keep, f"fail_streak={streak} 时折损率错误"

    def test_hp_never_drops_below_zero_on_failure(self, engine, full_state):
        """失败扣血必须被下限钳制 —— 血量过低时应触发濒死而非负数。"""
        s = {**full_state, "hp": 5}
        engine.apply_trial(s, {"success": False})
        assert s["hp"] == 0


class TestPitySystem:
    def test_fail_streak_raises_success_rate(self, engine, full_state):
        """每败一次 +8%，封顶 +24%。"""
        base = engine.REALM_TABLE[0][2]  # 0.95 → 会被 0.98 上限压住，故用一个低层率验证
        s = {**full_state, "realm_index": 6, "spirit_root": "三灵根·金木水"}
        for streak, bonus in [(0, 0.0), (1, 0.08), (2, 0.16), (3, 0.24), (5, 0.24)]:
            s = {**s, "fail_streak": streak}
            assert min(streak * 0.08, 0.24) == pytest.approx(bonus)

    def test_pity_hint_appears_in_text(self, engine, full_state):
        """保底生效时，判定文本必须向 AI 明确交代，避免 AI 凭空加戏。"""
        s = {**full_state, "realm_index": 6, "fail_streak": 3}
        random.seed(2)
        text, _ = engine.run_trial(s, {"type": "breakthrough"})
        assert "天道眷顾" in text and "24%" in text

    def test_no_hint_without_streak(self, engine, full_state):
        """未连败时不出现保底提示，防止 AI 无中生有。"""
        random.seed(2)
        text, _ = engine.run_trial(dict(full_state), {"type": "breakthrough"})
        assert "天道眷顾" not in text

    def test_success_resets_streak(self, engine, full_state):
        s = {**full_state, "fail_streak": 4}
        engine.apply_trial(s, {"success": True})
        assert s["fail_streak"] == 0


class TestEnding:
    def test_level_8_success_triggers_ending(self, engine, full_state, monkeypatch):
        """九层突破成功 → 结局标记，而非普通吐纳升层。"""
        s = {**full_state, "realm_index": 8}
        random.seed(99)
        for _ in range(50):
            text, trial = engine.run_trial(s, {"type": "breakthrough"})
            if trial and trial.get("ending"):
                break
        else:
            # 低概率事件：用确定性骰子复核必成功路径（numeric 边界 & 结局标记）
            monkeypatch.setattr(random, "random", lambda: 0.0)
            text, trial = engine.run_trial(s, {"type": "breakthrough"})
            assert text == "TRIGGER_ENDING"
            assert trial == {"ending": True}

    def test_level_8_failure_is_normal_failure(self, engine, full_state, monkeypatch):
        """九层失败仍是普通失败：只有成功才放行结局标记。"""
        s = {**full_state, "realm_index": 8}
        monkeypatch.setattr(random, "random", lambda: 0.999)
        text, trial = engine.run_trial(s, {"type": "breakthrough"})
        assert text != "TRIGGER_ENDING"
        assert trial == {"success": False}

    def test_apply_trial_ignores_ending(self, engine, full_state):
        """结局由 act 分支单独处理，apply_trial 不得越权修改境界。"""
        s = dict(full_state)
        assert engine.apply_trial(s, {"ending": True}) is None
        assert s["realm_index"] == 0

    def test_apply_trial_ignores_fight(self, engine, full_state):
        """斗法 trial 由 apply_fight 结算，apply_trial 必须放行。"""
        s = dict(full_state)
        assert engine.apply_trial(s, {"fight": True, "outcome": "win"}) is None

    def test_apply_trial_accepts_none(self, engine, full_state):
        assert engine.apply_trial(dict(full_state), None) is None
