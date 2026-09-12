# -*- coding: utf-8 -*-
"""轻量斗法：三档胜负判定、战力模型、敌人分层、战利品、五行克制。

斗法结果与 AI 完全解耦 —— 天道先把胜负、伤亡、得失定死，
这里验证「每一档证监会给予的奖惩符号与量级」符合设计，且状态永不被写坏。
"""
import random

import pytest


def force_ratio(monkeypatch, target: float, player_cp_mult: float = 1.0):
    """把敌方战力压到 player_cp * target 的确定性位置，用于命中指定胜负档位。"""
    monkeypatch.setattr(random, "uniform", lambda a, b: target)


class TestCombatPower:
    def test_formula(self, engine, base_state):
        s = {**base_state, "spirit_root": "三灵根·金木水"}  # 系数 1.0
        expected = s["hp"] * 0.5 + s["qi"] * 0.4 + s["realm_index"] * 25 + s["exp"] * 0.2
        assert engine.combat_power(s) == pytest.approx(expected)

    def test_power_scales_with_every_dimension(self, engine, base_state):
        base = engine.combat_power(base_state)
        assert engine.combat_power({**base_state, "hp": base_state["hp"] + 100}) > base
        assert engine.combat_power({**base_state, "qi": base_state["qi"] + 40}) > base
        assert engine.combat_power({**base_state, "realm_index": 3}) > base
        assert engine.combat_power({**base_state, "exp": 200}) > base

    def test_spirit_root_multiplies_power(self, engine, base_state):
        best = engine.combat_power({**base_state, "spirit_root": "天灵根·火"})
        worst = engine.combat_power({**base_state, "spirit_root": "四灵根·伪灵根"})
        assert best > worst
        assert best / worst == pytest.approx(1.6 / 0.75)

    def test_zero_state_is_safe(self, engine):
        """全空状态不得算出负战力或除零。"""
        s = engine.sanitize_state({"hp": 0, "qi": 0, "realm_index": 0, "exp": 0})
        assert engine.combat_power(s) >= 0


class TestEnemyPool:
    def test_pool_covers_all_realms(self, engine):
        """任何境界都必须有敌人可打，否则玩家会卡在无敌可刷的空档。"""
        for lv in range(10):
            pool = [e for e in engine.ENEMY_DATA if e["lo"] <= lv <= e["hi"]]
            assert pool, f"境界 {lv} 无对应敌人"

    def test_monsters_are_unique_and_complete(self, engine):
        names = [e["name"] for e in engine.ENEMY_DATA]
        assert len(names) == len(set(names)), "敌人重名"
        for e in engine.ENEMY_DATA:
            assert e["elem"] in engine.FIVE_ELEMENTS
            assert 0 <= e["loot_tier"] < len(engine.LOOT_TIERS)
            assert e["cp_base"] > 0

    def test_difficulty_increases_with_realm_tier(self, engine):
        """高层敌人的基础战力必须高于低层。"""
        low = max(e["cp_base"] for e in engine.ENEMY_DATA if e["hi"] <= 2)
        mid = max(e["cp_base"] for e in engine.ENEMY_DATA if e["lo"] >= 2 and e["hi"] <= 5)
        high = max(e["cp_base"] for e in engine.ENEMY_DATA if e["lo"] >= 6)
        assert low < mid < high

    def test_pick_enemy_by_name(self, engine, base_state):
        e = engine._pick_enemy(base_state, "山野妖鼠")
        assert e["name"] == "山野妖鼠"

    def test_unknown_name_gets_stand_in_but_keeps_narrative_name(self, engine, base_state):
        """死敌是江湖人物（不在怪物册）：借用同境界战力，名号保留给叙事。"""
        e = engine._pick_enemy(base_state, "青云子")
        assert e["name"] == "青云子"
        assert e["cp_base"] > 0 and e["elem"] in engine.FIVE_ELEMENTS

    def test_pick_anonymous_enemy_matches_realm(self, engine, base_state):
        for lv in (0, 3, 5, 8):
            s = {**base_state, "realm_index": lv}
            for _ in range(30):
                e = engine._pick_enemy(s)
                assert e["lo"] <= lv <= e["hi"]


class TestLoot:
    @pytest.mark.parametrize("tier", list(range(4)))
    def test_loot_always_valid(self, engine, tier):
        for _ in range(200):
            loot = engine.roll_loot(tier)
            assert loot["name"] and loot["qty"] == 1
            assert loot["rarity"] in ("下品", "中品", "上品")
            pool_names = [x[0] for x in engine.LOOT_TIERS[tier]]
            assert loot["name"] in pool_names

    def test_tier_overflow_clamps_to_best(self, engine):
        """越界 tier 不应崩溃，且降级到最高层掉落。"""
        top_names = [x[0] for x in engine.LOOT_TIERS[-1]]
        for tier in (4, 99):
            assert engine.roll_loot(tier)["name"] in top_names

    def test_weights_sum_to_one(self, engine):
        for tier in engine.LOOT_TIERS:
            assert sum(w for _, _, w in tier) == pytest.approx(1.0)


class TestFightOutcome:
    def _run(self, engine, state, monkeypatch, uniform_value, **kw):
        monkeypatch.setattr(random, "uniform", lambda a, b: uniform_value)
        return engine.run_fight_trial(state, **kw)

    def test_win_branch(self, engine, base_state, monkeypatch):
        """完胜（ratio<0.75）：小幅受伤、正收益、可能有掉落。"""
        monkeypatch.setattr(random, "random", lambda: 0.0)  # 必掉落
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        text, trial = self._run(engine, base_state, monkeypatch, 0.1)
        assert trial["fight"] is True
        assert trial["outcome"] == "win"
        fx = trial["fx"]
        assert -12 <= fx["hp"] <= -4
        assert -15 <= fx["qi"] <= -6
        assert 15 <= fx["exp"] <= 30 * 1.6 + 1   # 含灵根加成
        assert fx["spirit_stones"] > 0
        assert fx["items_add"], "必掉落档位未产出战利品"
        assert "斗法判定" in text and "不得改写胜负" in text

    def test_narrow_branch(self, engine, base_state, monkeypatch):
        """险胜（0.75≤ratio≤1.05）：中幅伤亡、收益偏低。"""
        monkeypatch.setattr(random, "random", lambda: 0.99)  # 不掉落
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        text, trial = self._run(engine, base_state, monkeypatch, 0.9)
        assert trial["outcome"] == "narrow"
        fx = trial["fx"]
        assert -32 <= fx["hp"] <= -16
        assert -30 <= fx["qi"] <= -18
        assert fx["spirit_stones"] > 0
        assert fx["items_add"] == []
        assert "两败俱伤" in text

    def test_lose_branch(self, engine, base_state, monkeypatch):
        """落败（ratio>1.05）：重伤、灵石散落、修为无灵根加成。"""
        monkeypatch.setattr(random, "randint", lambda a, b: a)
        text, trial = self._run(engine, base_state, monkeypatch, 3.0)
        assert trial["outcome"] == "lose"
        fx = trial["fx"]
        hp_max = base_state["hp_max"]
        looting = int(hp_max * 0.3)
        assert fx["hp"] <= -looting and fx["hp"] >= -int(hp_max * 0.5)
        assert fx["qi"] < 0
        assert fx["spirit_stones"] < 0, "落败必须损失灵石"
        assert fx["exp"] == 3 * 1  # 落败不给灵根加成
        assert "不得改写胜负" in text

    def test_element_advantage_shifts_outcome(self, engine, base_state, monkeypatch):
        """同一敌人同一骰子下，克制/被克必须在判定文本中明示。"""
        monkeypatch.setattr(random, "randint", lambda a, b: 1)
        # 玩家金 vs 疯道散修（火）：火克金 → 被克，提示吃力
        upper, trial_up = engine.run_fight_trial({**base_state, "spirit_root": "单灵根·金"}, "疯道散修")
        assert "颇为吃力" in upper
        assert engine.element_multiplier("单灵根·金", "火") == pytest.approx(0.85)
        # 玩家水 vs 疯道散修（火）：水克火 → 克制，提示上风
        lower, trial_low = engine.run_fight_trial({**base_state, "spirit_root": "单灵根·水"}, "疯道散修")
        assert "占据上风" in lower
        assert engine.element_multiplier("单灵根·水", "火") == pytest.approx(1.15)

    def test_pseudo_root_never_gets_element_hint(self, engine, base_state, monkeypatch):
        monkeypatch.setattr(random, "randint", lambda a, b: 1)
        text, _ = engine.run_fight_trial({**base_state, "spirit_root": "四灵根·伪灵根"}, "山野妖鼠")
        assert "占据上风" not in text and "颇为吃力" not in text

    def test_hard_mode_is_tougher(self, engine, base_state, monkeypatch):
        """死敌寻仇：浮动区间抬高到 1.0~1.5，同 tier 下敌方战力不应低于普通模式。"""
        enemy = engine._pick_enemy(base_state, "山野妖鼠")
        scale = 1.0 + base_state["realm_index"] * 0.08
        player = engine.combat_power(base_state)
        hard_low = enemy["cp_base"] * scale * 1.0
        soft_low = enemy["cp_base"] * scale * 0.7
        assert hard_low > soft_low
        # 且 hard 必定掉落
        monkeypatch.setattr(random, "randint", lambda a, b: 1)
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.1)
        _, trial = engine.run_fight_trial(base_state, "山野妖鼠", hard=True)
        assert trial["fx"]["items_add"], "死敌寻仇必掉落"


class TestApplyFight:
    def test_hp_qi_never_overflow_or_negative(self, engine, base_state):
        """极端 fx 下状态仍必须落在合法区间。"""
        s = {**base_state, "hp": 5, "qi": 3}
        trial = {"fight": True, "fx": {"hp": -9999, "qi": -9999, "exp": 0,
                                       "spirit_stones": -9999, "items_add": [], "items_remove": []}}
        engine.apply_fight(s, trial)
        assert s["hp"] == 0 and s["qi"] == 0 and s["spirit_stones"] == 0

        s2 = {**base_state, "hp": 90, "qi": 45}
        trial2 = {"fight": True, "fx": {"hp": 9999, "qi": 9999, "exp": 9999,
                                        "spirit_stones": 99999, "items_add": [], "items_remove": []}}
        engine.apply_fight(s2, trial2)
        assert s2["hp"] == s2["hp_max"]
        assert s2["qi"] == s2["qi_max"]
        assert s2["exp"] == engine.exp_max_of(s2["realm_index"])
        assert s2["spirit_stones"] == 99999

    def test_loot_is_added_to_bag(self, engine, base_state):
        s = {**base_state, "items": []}
        trial = {"fight": True, "fx": {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                                       "items_add": [{"name": "碎星石", "qty": 1, "rarity": "中品"}],
                                       "items_remove": []}}
        engine.apply_fight(s, trial)
        assert s["items"] == [{"name": "碎星石", "qty": 1, "rarity": "中品"}]

    def test_duplicate_loot_merges(self, engine, base_state):
        s = {**base_state, "items": [{"name": "碎星石", "qty": 1, "rarity": "中品"}]}
        trial = {"fight": True, "fx": {"items_add": [{"name": "碎星石", "qty": 2, "rarity": "中品"}]}}
        engine.apply_fight(s, trial)
        assert s["items"] == [{"name": "碎星石", "qty": 3, "rarity": "中品"}]

    def test_empty_trial_is_safe(self, engine, base_state):
        s = dict(base_state)
        engine.apply_fight(s, {})
        assert s["hp"] == base_state["hp"]
