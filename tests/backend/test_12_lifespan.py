# -*- coding: utf-8 -*-
"""时间与寿元系统（v2 配平方案）：天数推进 / 按天产出 / 死亡风险 / 静养续命 / 寿终判定。

数值依据《墨问仙途 — 时间/寿元系统 最终配平方案 v2》，
期望量级由 tools/sim_lifespan.py 的蒙特卡洛仿真校准：
    张弛有度（闭关 5 + 出门 1）  ≈  70 轮 / 100 岁 / 0%   死亡
    纯闭关                      ≈  82 轮 / 139 岁 / 23%  死亡
    探索为主                    ≈ 160 轮 /  19 岁 / 0%   死亡
    静养为主（续命后）          ≈ 460 轮 /  54 岁 / 0%   死亡

任何参数改动，先跑 `python tools/sim_lifespan.py`，再改这里的断言。
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------- 常量表
class TestTables:
    def test_time_table_values(self, engine):
        assert engine.DAYS_PER_YEAR == 360
        assert engine.START_AGE == 16
        assert engine.ACTION_DAYS["cultivate"] == (270, 810)
        assert engine.ACTION_DAYS["fight"] == (1, 3)

    def test_day_eff_matches_the_design(self, engine):
        """日效率即行动取舍本身：闭关最高、坊市最低，差两个数量级。"""
        assert engine.DAY_EFF["cultivate"] == 0.110
        assert engine.DAY_EFF["cultivate"] > engine.DAY_EFF["rest"]
        assert engine.DAY_EFF["rest"] > engine.DAY_EFF["explore"]
        assert engine.DAY_EFF["explore"] > engine.DAY_EFF["trade"]

    def test_cultivate_has_no_fortune(self, engine):
        """闭关枯坐不生奇遇——这是「必须出门」的理由。"""
        assert engine.FORTUNE_CHANCE["cultivate"] == 0.0
        assert engine.FORTUNE_CHANCE["explore"] == 0.22
        for tag, (lo, hi) in engine.FORTUNE_EXP.items():
            assert 0 < lo < hi, f"{tag} 奇遇区间非法"

    def test_lifespan_grows_faster_than_exp_need(self, engine):
        """v1 的结构性缺陷正是需求增速 > 寿元增速；这里守住 v2 的修正。"""
        for i in range(len(engine.EXP_NEED) - 1):
            exp_x = engine.EXP_NEED[i + 1] / engine.EXP_NEED[i]
            life = engine.LIFESPAN_TABLE[i + 1]
            last = engine.LIFESPAN_TABLE[i]
            life_x = ((life[1] + life[2]) / 2) / ((last[1] + last[2]) / 2)
            assert life_x > exp_x, f"第 {i + 1} 境：寿元增速 {life_x:.2f} 未超过需求增速 {exp_x:.2f}"

    def test_qi_total_matches_exp_need(self, engine):
        """炼气九层的逐层需求之和必须等于 EXP_NEED[0]，否则两套曲线会打架。"""
        assert sum(r[1] for r in engine.REALM_TABLE) == engine.EXP_NEED[0]


# ---------------------------------------------------------------- 按天产出
class TestActionExp:
    def test_days_within_table(self, engine):
        for tag, (lo, hi) in engine.ACTION_DAYS.items():
            for _ in range(60):
                exp, days, _ = engine.action_exp(tag)
                assert lo <= days <= hi
                assert exp >= days * engine.DAY_EFF[tag]

    def test_exp_is_linear_in_days(self, engine, lock_days):
        """修为 = 天数 × 日效率：天数翻倍，产出翻倍（时间与修为同源）。"""
        lock_days(100)
        e100, d100, _ = engine.action_exp("cultivate")
        lock_days(200)
        e200, d200, _ = engine.action_exp("cultivate")
        assert (d100, d200) == (100, 200)
        assert e200 == pytest.approx(e100 * 2)

    def test_fortune_only_when_rolled(self, engine, lock_days):
        """奇遇由引擎掷定（判定先行）：关掉随机流后，探索不该冒出奇遇修为。"""
        lock_days(10)
        exp, _, fortune = engine.action_exp("explore")
        assert fortune is False
        assert exp == pytest.approx(10 * engine.DAY_EFF["explore"])

    def test_unknown_tag_falls_back(self, engine):
        exp, days, _ = engine.action_exp("nonexistent")
        assert 5 <= days <= 20
        assert exp > 0


# ---------------------------------------------------------------- 时间推进与状态字段
class TestStateFields:
    def test_new_state_defaults(self, engine):
        s = engine.sanitize_state({})
        assert s["age"] == engine.START_AGE
        assert s["days"] == 0
        assert s["rest_count"] == 0
        assert s["life_bonus"] == 0
        assert s["seclusion_streak"] == 0
        assert s["dead"] is False
        lo, hi = engine.LIFESPAN_TABLE[0][1], engine.LIFESPAN_TABLE[0][2]
        assert lo <= s["lifespan"] <= hi

    def test_age_is_derived_from_days(self, engine):
        """age 由 days 推导，杜绝存档里两个字段打架。"""
        s = engine.sanitize_state({"days": 360 * 10})
        assert s["age"] == engine.START_AGE + 10

    def test_age_survives_sanitize(self, engine):
        s = engine.sanitize_state({"days": 3600})
        again = engine.sanitize_state(dict(s))
        assert again["age"] == s["age"] and again["days"] == s["days"]

    def test_days_are_clamped(self, engine):
        assert engine.sanitize_state({"days": 10 ** 9})["days"] == 9999999
        assert engine.sanitize_state({"days": -5})["days"] == 0

    def test_lifespan_is_clamped(self, engine):
        assert engine.sanitize_state({"lifespan": 99999})["lifespan"] == 5000

    def test_dead_flag_survives_roundtrip(self, engine):
        assert engine.sanitize_state({"dead": True})["dead"] is True
        assert engine.sanitize_state({})["dead"] is False


class TestTimeAdvance:
    def test_cultivate_costs_years_explore_costs_days(self, engine, base_state, lock_days):
        """闭关动辄经年、探索不过数日——时间跨度必须真的有量级差。"""
        results = {}
        for tag in ("cultivate", "explore"):
            s = engine.sanitize_state({**base_state, "spirit_stones": 999})
            lock_days(engine.ACTION_DAYS[tag][1])
            engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "行动", tag)
            results[tag] = s["days"]
        assert results["cultivate"] >= 20 * results["explore"]

    def test_age_grows_with_days(self, engine, base_state, lock_days):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        lock_days(720)
        engine._postprocess_turn(
            s, {"delta": {}, "choices": [], "narrative": "n", "memory": "m"}, {}, "闭关", "cultivate")
        assert s["age"] == engine.START_AGE + 2
        assert s["days"] == 720

    def test_meta_carries_age_info(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta = {}
        engine._postprocess_turn(
            s, {"delta": {}, "choices": [], "narrative": "n", "memory": "m"}, meta, "行动", "explore")
        a = meta["age"]
        assert a["age"] == s["age"]
        assert a["lifespan"] == s["lifespan"]
        assert a["level"] == "safe"
        assert a["hint"] == ""
        assert a["dead"] is False


# ---------------------------------------------------------------- 死亡风险曲线
class TestDeathRisk:
    @pytest.mark.parametrize("ratio,expected", [
        (0.50, 0.0), (0.71, 0.0),     # 安全线内：绝无寿终之虞
        (0.72, 0.0),
        (0.80, 0.0123),               # 渐衰
        (0.85, 0.02),
        (0.90, 0.0467),
        (1.00, 0.10),                 # 寿元将尽
        (1.05, 0.13),
    ])
    def test_curve(self, engine, ratio, expected):
        age, limit = int(165 * ratio), 165
        assert engine.death_risk(age, limit) == pytest.approx(expected, abs=0.002)

    def test_risk_is_capped(self, engine):
        assert engine.death_risk(1000, 100) <= 0.95

    def test_zero_lifespan_does_not_crash(self, engine):
        """寿元为 0（脏存档）不得抛异常，按 1 处理。"""
        assert engine.death_risk(16, 0) <= 0.95

    def test_hint_levels(self, engine):
        assert engine.lifespan_hint(100, 165) == ("", "safe")
        text, level = engine.lifespan_hint(130, 165)
        assert level == "faded" and text
        text, level = engine.lifespan_hint(160, 165)
        assert level == "warn" and "续命" in text
        text, level = engine.lifespan_hint(200, 165)
        assert level == "dread"

    def test_safe_line_is_reachable_in_qi_stage(self, engine):
        """炼气期不该被寿元卡死：跑到安全线前的余量必须够爬完九层。"""
        lo = engine.LIFESPAN_TABLE[0][1]
        assert lo * engine.LIFESPAN_SAFE_RATIO - engine.START_AGE > 80


# ---------------------------------------------------------------- 静养续命
class TestRestLifeBonus:
    def _rest(self, engine, s, lock_days, n=1):
        for _ in range(n):
            lock_days(engine.ACTION_DAYS["rest"][0])
            engine._postprocess_turn(
                s, {"delta": {}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "静养", "rest")

    def test_bonus_every_third_rest(self, engine, base_state, lock_days):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "lifespan": 165})
        self._rest(engine, s, lock_days, 2)
        assert s["lifespan"] == 165        # 不足 3 轮
        assert s["rest_count"] == 2
        self._rest(engine, s, lock_days, 1)
        assert s["rest_count"] == 3
        assert s["life_bonus"] == pytest.approx(3.5)
        assert s["lifespan"] == 168        # 只在跨过整岁时 +3

    def test_bonus_is_capped(self, engine, base_state, lock_days):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "lifespan": 165,
                                   "life_bonus": 59.5})
        self._rest(engine, s, lock_days, 3)
        assert s["life_bonus"] == engine.REST_LIFE_BONUS_CAP
        assert s["lifespan"] == 165 + 1    # 59.5 → 60，只补最后 1 岁

    def test_rest_is_not_seclusion(self, engine, base_state, lock_days):
        """静养不算枯坐：连着静养也不吃闭门衰减。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        self._rest(engine, s, lock_days, 10)
        assert s["seclusion_streak"] == 0
        assert engine._seclusion_coeff(s, "cultivate") == 1.0

    def test_rest_alone_will_not_kill_you(self, engine, base_state, lock_days):
        """v1 的静养是必死陷阱（319 年）；v2 加了续命后必须能活着跑完。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "lifespan": 165})
        self._rest(engine, s, lock_days, 300)
        assert s["dead"] is False
        assert s["lifespan"] > 165


# ---------------------------------------------------------------- 寿终判定
class TestLifespanDeath:
    def test_young_never_dies(self, engine):
        s = engine.sanitize_state({"age": 20, "lifespan": 165})
        for _ in range(500):
            assert engine.check_lifespan_death(s) is False

    def test_over_the_limit_can_die(self, engine):
        s = engine.sanitize_state({"days": 360 * 384, "lifespan": 165})   # 400 岁 / 165 寿元
        assert s["age"] == 400
        # 大限之后单轮生死概率已封顶 0.95，连掷必死
        for _ in range(50):
            if engine.check_lifespan_death(s):
                break
        assert s["dead"] is True

    def test_death_lands_at_the_end_of_the_turn(self, engine, base_state, lock_days):
        """寿元判定必须在回合最末：先结算修为、再推进年岁、最后才掷生死骰。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "lifespan": 100,
                                   "days": 360 * 200})   # 216 岁，远超寿元
        lock_days(engine.ACTION_DAYS["explore"][0])
        meta = {}
        narrative, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 0}, "choices": [], "narrative": "正文。", "memory": "m"},
            meta, "出门", "explore")
        # 不管死没死，本轮的修为与时间都已记账
        assert s["age"] == 216
        assert meta["age"]["level"] == "dread"
        if meta.get("lifespan_death"):
            assert s["dead"] is True
            assert engine.LIFESPAN_DEATH_TEXT in narrative


# ---------------------------------------------------------------- 突破重掷寿元
class TestBreakthroughLifespan:
    def test_qi_layer_breakthrough_keeps_lifespan(self, engine, base_state):
        """炼气期内升层不重掷——寿元只在跨大境界时才跳。"""
        s = engine.sanitize_state({**base_state, "lifespan": 165})
        view = engine.apply_trial(s, {"success": True})
        assert view["success"] is True
        assert s["lifespan"] == 165
        assert "lifespan_gain" not in view

    def test_realm_jump_rerolls_lifespan(self, engine):
        """炼气 → 筑基：寿元从 140~190 跳到 390~510，这一跳就是筑基的意义。"""
        s = engine.sanitize_state({"realm_index": 8, "lifespan": 165,
                                   "hp": 300, "hp_max": 300, "qi": 200, "qi_max": 200})
        view = engine.apply_trial(s, {"success": True})
        assert s["realm_index"] == 9
        lo, hi = engine.LIFESPAN_TABLE[1][1], engine.LIFESPAN_TABLE[1][2]
        assert lo <= s["lifespan"] <= hi + 60
        assert view.get("lifespan_gain", 0) > 0

    def test_ending_payload_reports_lifespan_gain(self, engine, base_state):
        payload = engine._ending_payload(
            engine.sanitize_state({**base_state, "lifespan": 165}), "闭关冲关")
        assert payload["breakthrough"]["lifespan_gain"] > 0
        assert payload["state"]["lifespan"] > 165

    def test_life_bonus_carries_over_the_realm_jump(self, engine):
        """静养攒下的续命不能因为突破被抹掉。"""
        s = engine.sanitize_state({"realm_index": 8, "lifespan": 165, "life_bonus": 20,
                                   "hp": 300, "hp_max": 300, "qi": 200, "qi_max": 200})
        engine.apply_trial(s, {"success": True})
        lo = engine.LIFESPAN_TABLE[1][1]
        assert s["lifespan"] >= lo + 20


# ---------------------------------------------------------------- 端到端：量级锚点
class TestPacingAnchors:
    """与 tools/sim_lifespan.py 同源的量级校验（跑得动、且不至于跑飞）。"""

    @staticmethod
    def run(engine, pick, max_turns=4000):
        s = engine.sanitize_state({
            "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
            "exp": 0, "spirit_stones": 99999, "spirit_root": "三灵根·水火木",
            "items": [], "memory": [], "recent": [], "turn": 0,
        })
        turns = 0
        while s["realm_index"] < 9 and turns < max_turns and not s["dead"]:
            turns += 1
            engine._postprocess_turn(
                s, {"delta": {"exp": 10}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "行动", pick(engine, s))
            if s["exp"] >= engine.exp_max_of(s["realm_index"]):
                engine.apply_trial(s, {"success": True})
        return turns, s

    def test_balanced_route_is_fast_and_safe(self, engine):
        """张弛有度：出门打断枯坐 → 快且几乎不死。"""
        turns, s = self.run(engine, lambda e, st: "explore"
                            if st["seclusion_streak"] >= e.SECLUSION_STREAK else "cultivate")
        assert 40 <= turns <= 110
        assert s["age"] < 165 * 0.85
        assert s["dead"] is False

    def test_pure_seclusion_is_punished(self, engine):
        """纯闭关：撞上衰减 → 轮数更多、年岁更大。"""
        balanced, sb = self.run(engine, lambda e, st: "explore"
                                if st["seclusion_streak"] >= e.SECLUSION_STREAK else "cultivate")
        mindless, sm = self.run(engine, lambda e, st: "cultivate")
        assert mindless >= balanced
        assert sm["age"] > sb["age"]

    def test_explore_route_costs_almost_no_lifespan(self, engine):
        """探索流靠奇遇吃饭：轮数多，但几乎不老——时间作弊已被堵死。"""
        turns, s = self.run(engine, lambda e, st: "explore")
        assert turns > 60
        assert s["age"] < 60

    def test_every_route_terminates(self, engine):
        """任何单键路线都必须在 4000 轮内跑完或寿终，不得死循环。

        坊市流刻意最慢（约 2000 轮，靠灵石与丹药才是正解），但仍须收敛——
        若它跑不完而玩家又察觉不到，就是个隐形陷阱。
        """
        for tag in ("cultivate", "rest", "explore", "trade", "fight"):
            turns, s = self.run(engine, lambda e, st, t=tag: t)
            assert turns < 4000 or s["dead"], f"{tag} 路线未收敛"


# ---------------------------------------------------------------- 寿终守卫（防无限续命）
class TestDeadGuard:
    """玩家已寿终后，任何行动（含自由输入）都只回寿终响应，世界不再推进。

    这是 v2 上线前必须堵的口子：否则 check_lifespan_death 因 not state.get("dead")
    守卫不再触发，但回合仍照常推进时间/修为，等于死后永生。
    """

    @staticmethod
    def _dead_state():
        return {"dead": True, "age": 200, "lifespan": 165, "days": 360 * 184,
                "realm_index": 0, "exp": 0, "spirit_stones": 999}

    def test_act_returns_dead_payload_and_freezes_world(self, client):
        r = client.post("/api/act", json={
            "state": self._dead_state(),
            "action": {"type": "custom", "text": "再练一甲子"},
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["dead"] is True
        assert d["ending"] is True
        assert d["choices"] == []
        assert d["state"]["days"] == 360 * 184   # 时间未推进
        assert d["state"]["dead"] is True

    def test_stream_returns_dead_payload_and_freezes_world(self, client):
        r = client.post("/api/act/stream", json={
            "state": self._dead_state(),
            "action": {"type": "custom", "text": "x"},
        })
        body = r.text
        assert '"dead": true' in body            # SSE done 携带寿终标记
        assert f'"days": {360 * 184}' in body    # 时间未推进

    def test_use_item_after_death_is_also_blocked(self, client):
        r = client.post("/api/act", json={
            "state": self._dead_state(),
            "action": {"type": "use_item", "item": "长春丹"},
        })
        d = r.json()
        assert d["dead"] is True
        assert d["state"]["days"] == 360 * 184
