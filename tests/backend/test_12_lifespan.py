# -*- coding: utf-8 -*-
"""时间与寿元系统（v2 配平方案）：天数推进 / 按天产出 / 死亡风险 / 静养续命 / 寿终判定。

数值依据《墨问仙途 下一版设计文档》（v3 配平）：
    一次闭关均值 5 年（ACTION_DAYS["cultivate"] = (1260, 2340)）
    DAY_EFF["cultivate"] = 0.200；EXP_NEED = [4659, 8000, 10000, 8000]
    寿元：炼气 115~150 / 筑基 300~400 / 金丹 1500~1800
    静养续命封顶 = 基础寿元的 12%（比例，随境界缩放）

期望量级由 tools/sim_lifespan.py 的蒙特卡洛仿真校准。

任何参数改动，先跑 `python tools/sim_lifespan.py`，再改这里的断言。
"""
from __future__ import annotations

import importlib.util
import pathlib
import random

import pytest

# pacing 仿真用的固定种子：每条路线都从同一起点播种，比较才公平
PACE_SEED = 20260912

# 采样用的种子（TestPacingAnchors）：与 sim_lifespan.py 的 20260913 区分开，
# 避免「同一串随机数既校准又断言」的循环论证。
SAMPLE_SEED = 20260915
SAMPLE_N = 100


def load_sim():
    """加载 tools/sim_lifespan.py（与线上引擎共用 _postprocess_turn，不会漂移）。"""
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / "sim_lifespan.py"
    spec = importlib.util.spec_from_file_location("sim_lifespan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 常量表
class TestTables:
    def test_time_table_values(self, engine):
        assert engine.DAYS_PER_YEAR == 360
        assert engine.START_AGE == 16
        assert engine.ACTION_DAYS["cultivate"] == (1260, 2340)   # v3：一次闭关均值 5 年
        assert engine.ACTION_DAYS["fight"] == (1, 3)

    def test_day_eff_matches_the_design(self, engine):
        """日效率即行动取舍本身：闭关最高、坊市最低，差两个数量级。"""
        assert engine.DAY_EFF["cultivate"] == 0.200              # v3：0.110 → 0.200
        assert engine.DAY_EFF["cultivate"] > engine.DAY_EFF["rest"]
        assert engine.DAY_EFF["rest"] > engine.DAY_EFF["explore"]
        assert engine.DAY_EFF["explore"] > engine.DAY_EFF["trade"]

    def test_cultivate_has_no_fortune(self, engine):
        """闭关枯坐不生奇遇——这是「必须出门」的理由。"""
        assert engine.FORTUNE_CHANCE["cultivate"] == 0.0
        assert engine.FORTUNE_CHANCE["explore"] == 0.22
        for tag, (lo, hi) in engine.FORTUNE_EXP.items():
            assert 0 < lo < hi, f"{tag} 奇遇区间非法"

    def test_fortune_no_longer_grants_bare_exp(self, engine):
        """v3.1 地基修复：奇遇表已清空——非闭关行动不得有任何「脱离天数的修为」。

        原表让「出门逛三天」的收益超过「闭关两年」，把「修为 = 天数 × 日效率」
        这条地基打穿（实测纯探索流入筑基率 94%）。表空 = 该分支永不触发。
        """
        assert engine.FORTUNE_EXP == {}

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
            if tag == "explore":
                # 探索正式玩法走三档（EXPLORE_TIERS），低/中/高各有一组天数区间
                for tkey, tspec in engine.EXPLORE_TIERS.items():
                    tlo, thi = tspec["days"]
                    for _ in range(60):
                        exp, days, _ = engine.action_exp("explore", tkey)
                        assert tlo <= days <= thi
                        assert exp >= days * engine.DAY_EFF["explore"]
                continue
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
        """炼气期不该被寿元卡死：跑到安全线前的余量必须够爬完九层。

        v3 起炼气寿元收紧到 115~150（压迫感来源），安全窗口随之变小但仍够用：
        最短寿元 115 → 安全线 82.8 岁，从 16 岁起仍有 66 年可修。
        """
        lo, hi = engine.LIFESPAN_TABLE[0][1], engine.LIFESPAN_TABLE[0][2]
        assert lo * engine.LIFESPAN_SAFE_RATIO - engine.START_AGE > 60
        avg = (lo + hi) / 2
        assert avg * engine.LIFESPAN_SAFE_RATIO - engine.START_AGE > 70


# ---------------------------------------------------------------- 静养续命
class TestRestLifeBonus:
    def _rest(self, engine, s, lock_days, n=1):
        for _ in range(n):
            lock_days(engine.ACTION_DAYS["rest"][0])
            engine._postprocess_turn(
                s, {"delta": {}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "静养", "rest")

    def test_bonus_every_rest(self, engine, base_state, lock_days):
        """v3.3.1：每次静养都结算续命（EVERY 3→1，反馈线性化）。

        旧节奏「每 3 轮才给 1 次」下，通关全程仅 ~4 次静养 → 只触发 1 次 →
        只拿 3.5 岁，连一轮闭关（5 年）都抵不过，续命机制形同虚设。
        """
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "lifespan": 165})
        self._rest(engine, s, lock_days, 1)
        assert s["rest_count"] == 1
        assert s["life_bonus"] == pytest.approx(3.5)
        assert s["lifespan"] == 168        # 只在跨过整岁时 +3
        self._rest(engine, s, lock_days, 1)
        assert s["rest_count"] == 2
        assert s["life_bonus"] == pytest.approx(7.0)
        assert s["lifespan"] == 172        # 3.5→7.0，整数部分 +4

    def test_bonus_is_capped_at_ratio_of_lifespan(self, engine, base_state, lock_days):
        """v3：续命封顶 = 基础寿元的 12%（不再写死 +60，改比例才随境界缩放）。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "lifespan": 165})
        self._rest(engine, s, lock_days, 300)   # 静养足够多轮，必然触顶
        cap = 165 * engine.REST_LIFE_BONUS_CAP  # 19.8
        assert s["life_bonus"] == pytest.approx(cap, abs=0.2)
        assert s["lifespan"] == 165 + int(cap)  # 只加整数岁

    def test_rest_counts_as_seclusion(self, engine, base_state, lock_days):
        """v3.2.4 反套利：静养**也算**枯坐（旧行为：连着静养不吃衰减）。

        rest 曾会把 seclusion_streak 归零 —— 玩家每 6 轮插 1 次静养（成本仅 30 天）
        即可永久规避闭门衰减，静养流 89% 压过探险流 80%，静养成唯一解。
        现在 rest 并入 SECLUSION_TAGS，只有真正出门才清零。
        """
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        self._rest(engine, s, lock_days, 10)
        assert s["seclusion_streak"] > 0                                       # 静养同样累加枯坐
        assert engine._seclusion_coeff(s, "cultivate") == pytest.approx(0.6)    # 衰减到底 0.6 封顶

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
        s = engine.sanitize_state({"realm_index": 8, "lifespan": 165, "life_bonus": 15,
                                   "hp": 300, "hp_max": 300, "qi": 200, "qi_max": 200})
        keep = int(s["life_bonus"])
        engine.apply_trial(s, {"success": True})
        lo = engine.LIFESPAN_TABLE[1][1]
        assert keep > 0
        assert s["lifespan"] >= lo + keep


# ---------------------------------------------------------------- 端到端：量级锚点
class TestPacingAnchors:
    """策略量级锚点 —— 与 tools/sim_lifespan.py **同一份引擎、同一套判据**。

    v3.1 起不再用「单局轮数」当判据：一次闭关就是 5 年、寿元还是掷骰得来的，
    单局噪声大到无法区分好坏路线。改为**多次采样的入筑基成功率**，与文档 §四
    的 n=2000 结论同源（固定种子 → 结果确定可复现）。

    设计意图（v3.3.1 三条核心诉求，缺一不可）：
        1. 探险流是最优解（75~82%）→ 出门历练必须值回票价；
        2. 纯探索流归零 + 纯闭关垫底但可行（45~60%）→ 只认一条键位通吃不了；
        3. 静养流（续命路线 ~68%）与中档流（保守路线）都必须可用、但都低于探险流
           —— 路线有分工（变强 vs 拖时间 vs 低风险），而非某键通吃。
    """

    BALANCED = staticmethod(lambda e, st: "explore"
                            if st["seclusion_streak"] >= e.SECLUSION_STREAK else "cultivate")
    MINDLESS = staticmethod(lambda e, st: "cultivate")

    @classmethod
    def win_rate(cls, engine, sim, name):
        random.seed(SAMPLE_SEED)
        engine._life_rng.seed(SAMPLE_SEED)
        rs = [sim.run(sim.STRATEGIES[name]) for _ in range(SAMPLE_N)]
        return sum(1 for r in rs if r["won"]) / SAMPLE_N

    @staticmethod
    def run(engine, pick, max_turns=4000):
        """单局跑法（供收敛性/寿命对比用）。"""
        random.seed(PACE_SEED)
        engine._life_rng.seed(PACE_SEED)
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

    def test_mindless_meditation_is_the_worst_route(self, engine):
        """纯闭关垫底但可行：一次闭关 5 年、效率封顶且无宝物加成，明显劣于出门流。

        v3.2.4 重标定：cap 0.5→1.0 后纯闭关由 14% 升到 ~55%（设计目标 45~60%）。
        「逼玩家出门」靠的是**显著劣于探险流**（~78%），而非逼死——旧上界 0.35 已作废。
        """
        sim = load_sim()
        pure = self.win_rate(engine, sim, "纯闭关")
        out = self.win_rate(engine, sim, "闭关5+远行1")
        assert pure < out, f"纯闭关 {pure:.0%} 竟然不劣于出门流 {out:.0%}"
        assert 0.45 <= pure <= 0.62, f"纯闭关成功率 {pure:.0%} 不在设计区间 45~60%"

    def test_explore_only_route_never_reaches_foundation(self, engine):
        """v3.1 核心成果：纯探索流 **0%** 入筑基。

        砍掉「奇遇直修为」与「灵丹裸修为」之后，只出门不闭关拿不到修为，
        一生出门数百次也只会耗掉寿元——这正是地基修复要堵的那个洞。
        """
        sim = load_sim()
        for name in ("远行探索流", "秘境探索流"):
            assert self.win_rate(engine, sim, name) == 0.0, f"{name} 竟能靠出门入筑基"

    def test_static_meditation_route_is_no_longer_the_best(self, engine):
        """v3.3.1：静养续命修复（EVERY 3→1）后，静养流 ~68% —— 靠拖时间过关的
        第三条路线真正成形，但**仍低于探险流**（~78%），「探险最优」红线未破。

        旧断言「静养与纯闭关同档（±10pp）」已作废：续命生效后静养流显著高于
        纯闭关（68% vs 55%）——这正是 P1 的目的（静养的变量价值=续命，终于值钱了）。
        """
        sim = load_sim()
        rest = self.win_rate(engine, sim, "修行5+静养1")
        out = self.win_rate(engine, sim, "闭关5+远行1")
        pure = self.win_rate(engine, sim, "纯闭关")
        assert rest < out, f"静养流 {rest:.0%} 仍压过探险流 {out:.0%} —— 红线被破"
        assert rest > pure, f"静养流 {rest:.0%} 未高于纯闭关 {pure:.0%} —— 续命没生效"
        assert 0.60 <= rest <= 0.76, f"静养流成功率 {rest:.0%} 不在设计区间 60~75%"
        assert 0.72 <= out <= 0.86, f"探险流成功率 {out:.0%} 不在设计区间 75~82%"

    def test_exploration_beats_medium_route(self, engine):
        """v3.3.1 红线（P0）：探险流必须显著优于中档流（≥15pp）。

        medium 效率 0.55→0.85 的扫描显示：≥0.90 时「中档5+静养1」会逼近甚至
        反超探险流（0.95 时 81.4% > 77.9%），废掉「探险必须是最优解」的设计主线。
        此测试锁死该边界，防止将来再调 medium 系数时不知不觉挤掉探险流。
        """
        sim = load_sim()
        ex = self.win_rate(engine, sim, "闭关5+远行1")
        md = self.win_rate(engine, sim, "中档5+静养1")
        assert ex - md >= 0.15, f"探险 {ex:.0%} 领先中档 {md:.0%} 不足 15pp"

    def test_medium_route_is_viable(self, engine):
        """v3.3.1（P0）：中档效率 0.85 后，纯中档从 0% 废档救活（~24%）。

        但仍明显弱于纯闭关（~55%）——中档是「保守选择」，不是主力。
        """
        sim = load_sim()
        md = self.win_rate(engine, sim, "纯中档静修")
        pure = self.win_rate(engine, sim, "纯闭关")
        assert md > 0.10, f"纯中档 {md:.0%} 仍是死选项"
        assert md < pure, f"纯中档 {md:.0%} 不应压过纯闭关 {pure:.0%}"

    def test_pure_seclusion_costs_more_lifespan(self, engine):
        """纯闭关：把每一轮都换成 5 年枯坐 → 终局年岁更大。这才是寿元压力的来源。"""
        _, sb = self.run(engine, self.BALANCED)
        _, sm = self.run(engine, self.MINDLESS)
        assert sm["age"] > sb["age"]

    def test_explore_route_stalls_at_the_first_realm(self, engine):
        """探索流轮数极多，但修为**原地不动**——时间作弊被堵死的直接证据。"""
        turns, s = self.run(engine, lambda e, st: "explore")
        assert turns > 60
        assert s["realm_index"] < 9
        assert s["dead"] is True          # 只会寿终，不会飞升

    def test_every_route_terminates(self, engine):
        """任何单键路线都必须在 4000 轮内跑完或寿终，不得死循环。

        ⚠️ 只断言**修行类**（cultivate/rest）：v3.1 砍掉「奇遇直修为」后，
        探索/交易/斗法**自身几乎不产修为**是设计意图（靠宝物与灵丹回哺闭关），
        它们本来就不该收敛于筑基——若强制要求，等于诱导「纯探索刷修为」的隐形陷阱。
        这两条路线只需保证「不崩、不卡死」，故不在此断言。
        """
        for tag in ("cultivate", "rest"):
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
