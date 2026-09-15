# -*- coding: utf-8 -*-
"""探索三档 + 机缘物件系统（v3 · P1）：档位 / 掉落 / 效率与突破加成 / 护道符 / 白名单。

设计核心（《墨问仙途 下一版设计文档》§2.3 / §2.4）：
    探险不是「用时间换寿元」，而是「用风险换效率」——
    掉落功法与法宝提供【闭关效率】与【突破成功率】加成，纯闭关永远拿不到。
    因此这里要钉死三件事：
      1. 效率加成只作用于 cultivate/rest，绝不作用于 explore（否则探险流滚雪球）；
      2. 护道符是一次性的，且只切断「失败 → 折损」这一环；
      3. 死亡率有硬红线，任何档位都不得越过 EXPLORE_DEATH_CEILING。
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------- 小工具
def _scripted(monkeypatch, engine, randints=(), randoms=()):
    """按脚本喂随机流：randint / random 各消费一个序列，耗尽后回落到安全默认值。

    顺序对应 _postprocess_turn 内部真实的调用次序（v3.1 起奇遇已不再消耗随机流，
    因为 FORTUNE_EXP 为空、该分支整体不触发）：
        ① action_exp 的 randint(days)
        ② 探索死亡判定  ③ 探索掉落判定  ④ roll_treasure 的权重掷点
    """
    it_i, it_f = iter(randints), iter(randoms)
    monkeypatch.setattr(engine.random, "randint", lambda a, b: next(it_i, a))
    monkeypatch.setattr(engine.random, "random", lambda: next(it_f, 0.99))


def _explore(engine, state, meta=None, tier="mid", risk_roll=0.0):
    return engine._postprocess_turn(
        state,
        {"delta": {"exp": 0}, "choices": [], "narrative": "正文。", "memory": ""},
        meta if meta is not None else {}, "远行历练", "explore",
        risk_roll=risk_roll, tier=tier)


# ---------------------------------------------------------------- 探索三档
class TestExploreTiers:
    def test_three_tiers_ordered_by_cost_and_risk(self, engine):
        assert set(engine.EXPLORE_TIERS) == {"low", "mid", "high"}
        tiers = [engine.EXPLORE_TIERS[k] for k in ("low", "mid", "high")]
        for a, b in zip(tiers, tiers[1:]):
            assert a["days"][1] < b["days"][1]      # 越深的档耗日越久
            assert a["death"] < b["death"]          # 也越要命
            assert a["drop"] < b["drop"]            # 掉落越厚
            assert a["fortune"] < b["fortune"]

    def test_recommended_tiers_stay_under_the_red_line(self, engine):
        """安全红线的含义：低/中档（推荐路线）单次死亡率必须压在 0.4% 以内——
        探险流一生出门几百次，死亡率是乘法累积的，超过这条线综合分就劣于纯闭关。
        高档是「贪心档」，故意越线：它才是「用命换稀有真诀」的代价所在。"""
        for key in ("low", "mid"):
            assert 0.0 <= engine.EXPLORE_TIERS[key]["death"] <= engine.EXPLORE_DEATH_CEILING
        assert engine.EXPLORE_DEATH_CEILING == 0.004
        assert engine.EXPLORE_TIERS["high"]["death"] > engine.EXPLORE_DEATH_CEILING

    def test_every_tier_has_a_finite_death_risk(self, engine):
        """再贪心的档也不能失控：单次死亡率必须远低于 1（否则等于即死）。"""
        for key, spec in engine.EXPLORE_TIERS.items():
            assert 0.0 <= spec["death"] < 0.05, f"{key} 的死亡率失控"

    def test_only_high_tier_can_drop_rare(self, engine):
        assert engine.EXPLORE_TIERS["high"]["rare"] is True
        assert engine.EXPLORE_TIERS["mid"]["rare"] is False
        assert engine.EXPLORE_TIERS["low"]["rare"] is False

    def test_low_tier_is_harmless_but_sterile(self, engine):
        """寻常走动：不出事，也不出宝——它是安全的社交/打探档，不是farm档。"""
        low = engine.EXPLORE_TIERS["low"]
        assert low["death"] == 0.0 and low["drop"] == 0.0

    @pytest.mark.parametrize("risk,expected", [
        ("low", "low"), ("mid", "mid"), ("high", "high"),
        ("", "mid"), ("bogus", "mid"), (None, "mid"),
    ])
    def test_tier_of_action_maps_risk_to_tier(self, engine, risk, expected):
        assert engine.explore_tier_of({"tag": "explore", "risk": risk}) == expected

    def test_non_explore_action_has_no_tier(self, engine):
        assert engine.explore_tier_of({"tag": "cultivate", "risk": "high"}) is None
        assert engine.explore_tier_of(None) is None

    def test_default_tier_is_mid(self, engine):
        """自由输入 / 无档位时走中档——文档标定的全局最优档。"""
        assert engine.DEFAULT_EXPLORE_TIER == "mid"

    def test_action_exp_respects_tier_days(self, engine):
        for key, spec in engine.EXPLORE_TIERS.items():
            lo, hi = spec["days"]
            for _ in range(60):
                _, days, _ = engine.action_exp("explore", key)
                assert lo <= days <= hi


# ---------------------------------------------------------------- 加成计算
class TestTreasureBonuses:
    def test_eff_bonus_sums_by_quantity(self, engine):
        assert engine.treasure_eff_bonus({"residual_scroll": 3}) == pytest.approx(0.09)
        assert engine.treasure_eff_bonus({"residual_scroll": 3, "immortal_art": 1}) == pytest.approx(0.21)
        assert engine.treasure_eff_bonus({"rare_manual": 2}) == pytest.approx(0.12)

    def test_eff_bonus_is_defensive_about_junk(self, engine):
        assert engine.treasure_eff_bonus(None) == 0.0
        assert engine.treasure_eff_bonus({"不存在": 9}) == 0.0
        assert engine.treasure_eff_bonus({"residual_scroll": "3"}) == pytest.approx(0.09)  # 脏存档容忍

    def test_break_bonus_comes_from_enlight_stone(self, engine):
        assert engine.treasure_break_bonus({"enlight_stone": 2}) == pytest.approx(0.06)
        assert engine.treasure_break_bonus({"guard_talisman": 1}) == 0.0   # 护道符不改成功率
        assert engine.treasure_break_bonus({"immortal_art": 2}) == 0.0     # 真诀只加效率

    def test_break_bonus_feeds_the_roll_rate(self, engine):
        """悟道石要真的进掷骰公式，否则「所见即所掷」就是空话。

        取炼气九层取样：一层的基准率就是 0.95，加成就被上限 0.98 吃掉了。"""
        plain = engine.sanitize_state({"realm_index": 8, "spirit_root": "三灵根·金木水"})
        stone = engine.sanitize_state({"realm_index": 8, "spirit_root": "三灵根·金木水",
                                       "treasures": {"enlight_stone": 2}})
        r0, _ = engine.breakthrough_rate(plain)
        r1, _ = engine.breakthrough_rate(stone)
        assert r1 == pytest.approx(r0 + 0.06)

    def test_eff_bonus_only_feeds_cultivation(self, engine):
        """效率乘数只给 cultivate/rest——探索必须保持原速，否则越探越强、滚雪球。"""
        s = engine.sanitize_state({"realm_index": 8, "spirit_root": "三灵根·金木水",
                                   "treasures": {"residual_scroll": 6}})
        _, dc = engine.cultivate_multiplier(s, "cultivate")
        _, dr = engine.cultivate_multiplier(s, "rest")
        _, de = engine.cultivate_multiplier(s, "explore")
        assert dc["eff"] == pytest.approx(1.18)
        assert dr["eff"] == pytest.approx(1.18)
        assert de["eff"] == pytest.approx(1.0)
        assert de["eff_bonus"] == 0.0

    def test_eff_bonus_raises_the_day_yield(self, engine, base_state, monkeypatch):
        plain = engine.sanitize_state({**base_state, "spirit_stones": 999, "realm_index": 8})
        rich = engine.sanitize_state({**base_state, "spirit_stones": 999, "realm_index": 8,
                                      "treasures": {"immortal_art": 2}})
        gains = {}
        for name, s in (("plain", plain), ("rich", rich)):
            _scripted(monkeypatch, engine, randints=[engine.ACTION_DAYS["cultivate"][0]])
            _, _, delta, _, _ = engine._postprocess_turn(
                s, {"delta": {"exp": 0}, "choices": [], "narrative": "n", "memory": "m"},
                {}, "闭关", "cultivate")
            gains[name] = delta["exp"]
        assert gains["rich"] > gains["plain"]      # +24% 效率真的落到了产出上

    def test_treasure_table_shape(self, engine):
        assert set(engine.TREASURE) == {
            "residual_scroll", "rare_manual", "elixir",
            "enlight_stone", "guard_talisman", "immortal_art"}
        for key, spec in engine.TREASURE.items():
            assert spec["name"] and spec["w"] > 0
            assert set(("eff", "bp", "prot", "rare")) <= set(spec)
        # v3.1：灵丹不再是裸修为，而是限时效率 buff
        assert "exp" not in engine.TREASURE["elixir"]
        assert engine.TREASURE["elixir"]["eff_buff"] > 0
        assert engine.TREASURE["elixir"]["buff_rounds"] > 0


# ---------------------------------------------------------------- 背包增减
class TestTreasureInventory:
    def test_add_respects_cap(self, engine):
        s: dict = {"treasures": {}}
        assert engine._add_treasure(s, "guard_talisman", 5) == 1     # cap 1
        assert s["treasures"]["guard_talisman"] == 1
        assert engine._add_treasure(s, "guard_talisman", 1) == 0     # 已满
        assert engine._add_treasure(s, "residual_scroll", 99) == 6   # cap 6

    def test_add_unknown_key_is_noop(self, engine):
        s: dict = {"treasures": {}}
        assert engine._add_treasure(s, "不存在的物件", 3) == 0
        assert s["treasures"] == {}

    def test_consume_removes_when_exhausted(self, engine):
        s = {"treasures": {"guard_talisman": 1, "residual_scroll": 2}}
        engine._consume_treasure(s, "guard_talisman", 1)
        assert "guard_talisman" not in s["treasures"]
        engine._consume_treasure(s, "residual_scroll", 1)
        assert s["treasures"]["residual_scroll"] == 1

    def test_consume_on_empty_is_safe(self, engine):
        s = {"treasures": {}}
        engine._consume_treasure(s, "guard_talisman", 1)   # 不抛异常
        assert s["treasures"] == {}

    def test_has_guard_talisman(self, engine):
        assert engine.has_guard_talisman({"guard_talisman": 1}) is True
        assert engine.has_guard_talisman({"guard_talisman": 0}) is False
        assert engine.has_guard_talisman(None) is False

    def test_roll_gates_rare_by_tier(self, engine):
        for _ in range(300):
            assert engine.TREASURE[engine.roll_treasure("low")]["rare"] is False
            assert engine.TREASURE[engine.roll_treasure("mid")]["rare"] is False

    def test_roll_can_produce_rare_for_high_tier(self, engine):
        seen = {engine.roll_treasure("high") for _ in range(800)}
        assert "immortal_art" in seen


# ---------------------------------------------------------------- 护道符
class TestGuardedBreakthrough:
    def _state(self, engine, **extra):
        return engine.sanitize_state({"realm_index": 0, "exp": 100,
                                      "spirit_root": "三灵根·金木水", **extra})

    def test_talisman_absorbs_one_failure(self, engine):
        s = self._state(engine, treasures={"guard_talisman": 1})
        view = engine.apply_trial(s, {"success": False})
        assert view["guard_talisman"] is True
        assert s["exp"] == 100                              # 修为不折损
        assert "guard_talisman" not in s["treasures"]        # 一次性：用掉即失
        assert s["fail_streak"] == 1                         # 保底仍在累积

    def test_second_failure_hurts_again(self, engine):
        """护道符只能挡一次——挡完再败就照常折损。"""
        s = self._state(engine, treasures={"guard_talisman": 1})
        engine.apply_trial(s, {"success": False})
        engine.apply_trial(s, {"success": False})
        assert s["exp"] < 100

    def test_without_talisman_exp_is_eaten(self, engine):
        s = self._state(engine)
        engine.apply_trial(s, {"success": False})
        assert s["exp"] < 100
        assert s["hp"] < s["hp_max"]

    def test_success_is_unaffected(self, engine):
        s = self._state(engine, treasures={"guard_talisman": 1})
        view = engine.apply_trial(s, {"success": True})
        assert s["realm_index"] == 1
        assert s["treasures"]["guard_talisman"] == 1        # 成功不消耗


# ---------------------------------------------------------------- 探索结算（掉落 / 灵丹 / 陨落）
class TestExploreSettlement:
    def test_drop_stores_treasure_and_marks_meta(self, engine, base_state, monkeypatch):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta: dict = {}
        # ① 天数 30 ② 不死 ③ 掉落命中 ④ 权重掷点 0.0 → 池中第一件（功法残卷）
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.99, 0.0, 0.0])
        _explore(engine, s, meta, tier="mid")
        assert meta["treasure"]["key"] == "residual_scroll"
        assert s["treasures"]["residual_scroll"] == 1
        assert meta["explore"]["tier"] == "mid"
        assert meta["explore"]["label"]

    def test_elixir_stored_in_inventory_not_immediate(self, engine, base_state, monkeypatch):
        """v3.1：探索掉到的灵丹**入背包**，不再即时加修为。

        灵丹的旧设计（掉落即 +150~600 修为）让「只探索刷丹再服用」成为时间作弊，
        实测纯探索流可飙到 90% 入筑基、年仅 29 岁。现在它必须先入包、再由玩家主动服用。
        """
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "realm_index": 8})
        meta: dict = {}
        # 掉落命中后，权重掷点 0.5 × 96 = 48 → 落在灵丹区间 [42, 62)
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.99, 0.0, 0.5])
        _explore(engine, s, meta, tier="mid")
        assert meta["treasure"]["key"] == "elixir"
        assert "exp" not in meta["treasure"]            # meta 不再回传即时修为
        assert s["exp"] == 0                            # 修为一动不动
        assert s["treasures"]["elixir"] == 1            # 进背包，等玩家自己服

    def test_elixir_use_grants_efficiency_buff(self, engine, base_state, monkeypatch):
        """主动服用灵丹：修为不变，改为开启限时效率 buff。

        这是「修为 = 天数 × 效率」的直接体现——丹只让后面的闭关跑得更快，
        绝不凭空多出修为；且纯探索（不闭关）时 buff 毫无收益。
        """
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "treasures": {"elixir": 2}})
        req = type("Req", (), {"action": {}, "last_choices": None, "state": {}})()
        payload = engine.handle_use_elixir(s, req)
        assert payload["ok"] is True
        assert s["exp"] == 0                                       # 不给裸修为
        assert s["elixir_buff"] == engine.TREASURE["elixir"]["buff_rounds"]
        assert s["treasures"]["elixir"] == 1                       # 只消耗一颗
        assert payload["delta_applied"]["exp"] == 0

        # buff 真的进了乘子，且只作用于修行类
        _, dc = engine.cultivate_multiplier(s, "cultivate")
        _, dr = engine.cultivate_multiplier(s, "rest")
        _, de = engine.cultivate_multiplier(s, "explore")
        assert dc["eff"] == pytest.approx(1.0 + engine.ELIXIR_EFF_BUFF)
        assert dr["eff"] == pytest.approx(1.0 + engine.ELIXIR_EFF_BUFF)
        assert de["eff"] == pytest.approx(1.0)                     # 探索不享受丹力

    def test_elixir_use_without_ownership_is_rejected(self, engine, base_state):
        s = engine.sanitize_state({**base_state})
        req = type("Req", (), {"action": {}, "last_choices": None, "state": {}})()
        payload = engine.handle_use_elixir(s, req)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "ELIXIR_NOT_OWNED"
        assert s["elixir_buff"] == 0

    def test_elixir_buff_ticks_only_while_cultivating(self, engine, base_state, monkeypatch):
        """buff 只在修行回合倒计时：否则反复出门探索即可无限续杯。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "treasures": {"elixir": 1}, "realm_index": 8})
        engine.handle_use_elixir(s, type("Req", (), {"action": {}, "last_choices": None})())
        rounds = engine.ELIXIR_BUFF_ROUNDS

        # 探索一轮：buff 不递减
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.99, 0.99])
        _explore(engine, s, {}, tier="mid")
        assert s["elixir_buff"] == rounds

        # 闭关一轮：递减 1
        _scripted(monkeypatch, engine, randints=[engine.ACTION_DAYS["cultivate"][0]])
        engine._postprocess_turn(
            s, {"delta": {"exp": 0}, "choices": [], "narrative": "n", "memory": ""},
            {}, "闭关", "cultivate")
        assert s["elixir_buff"] == rounds - 1

    def test_elixir_buff_is_clamped_by_whitelist(self, engine):
        """存档里塞 9999 轮 → 钳到上限，防注入。"""
        s = engine.sanitize_state({"elixir_buff": 9999})
        assert s["elixir_buff"] == engine.ELIXIR_BUFF_ROUNDS
        assert engine.sanitize_state({"elixir_buff": -5})["elixir_buff"] == 0
        assert engine.sanitize_state({"elixir_buff": "x"})["elixir_buff"] == 0

    def test_no_drop_when_roll_misses(self, engine, base_state, monkeypatch):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta: dict = {}
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.99, 0.99])   # 掉落不中
        _explore(engine, s, meta, tier="mid")
        assert "treasure" not in meta
        assert s["treasures"] == {}

    def test_low_tier_never_drops(self, engine, base_state, monkeypatch):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta: dict = {}
        _scripted(monkeypatch, engine, randints=[10], randoms=[0.99])
        _explore(engine, s, meta, tier="low")
        assert "treasure" not in meta
        assert meta["explore"]["tier"] == "low"

    def test_explore_death_kills_and_narrates(self, engine, base_state, monkeypatch):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta: dict = {}
        # ① 天数 ② 死亡判定命中
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.0])
        narrative, _, _, _, _ = _explore(engine, s, meta, tier="mid")
        assert s["dead"] is True
        assert meta["explore_death"] is True
        assert "半途" in narrative

    def test_cultivate_never_dies_from_exploration(self, engine, base_state, monkeypatch):
        s = engine.sanitize_state({**base_state, "spirit_stones": 999})
        meta: dict = {}
        _scripted(monkeypatch, engine, randints=[1260])
        engine._postprocess_turn(
            s, {"delta": {"exp": 0}, "choices": [], "narrative": "n", "memory": ""},
            meta, "闭关", "cultivate")
        assert "explore_death" not in meta
        assert s["dead"] is False

    def test_stale_state_carries_treasures_into_the_next_tier(self, engine, base_state, monkeypatch):
        """已得的效率加成会随存档带到下一轮（复利），所以探索是有长期回报的。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 999,
                                   "treasures": {"rare_manual": 3}})
        assert s["eff_bonus"] == pytest.approx(0.18)
        _scripted(monkeypatch, engine, randints=[engine.ACTION_DAYS["cultivate"][0]])
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": 0}, "choices": [], "narrative": "n", "memory": ""},
            {}, "闭关", "cultivate")
        assert delta["exp"] > 0

    @pytest.mark.parametrize("tier", ["low", "mid", "high"])
    def test_explore_yields_no_measurable_exp(self, engine, base_state, monkeypatch, tier):
        """v3.1 地基的核心保证：**非闭关行动不得产出可观修为**。

        探索的按天产出 = 天数 × DAY_EFF["explore"]（0.004），最高档 160 天也只有 0.64——
        取整后恒为 0。过去「奇遇直修为」与「灵丹裸修为」正是从这里把地基打穿的。
        """
        s = engine.sanitize_state({**base_state, "spirit_stones": 999, "realm_index": 8})
        meta: dict = {}
        _scripted(monkeypatch, engine,
                  randints=[engine.EXPLORE_TIERS[tier]["days"][1]], randoms=[0.99, 0.99])
        _, _, delta, _, _ = _explore(engine, s, meta, tier=tier)
        assert delta["exp"] == 0, f"{tier} 档探索产出了修为 {delta['exp']}"
        assert s["exp"] == 0


# ---------------------------------------------------------------- 白名单与派生字段
class TestTreasureSanitize:
    def test_new_state_starts_empty(self, engine):
        s = engine.sanitize_state({})
        assert s["treasures"] == {}
        assert s["eff_bonus"] == 0.0
        assert s["break_bonus"] == 0.0
        assert s["elixir_buff"] == 0

    def test_whitelist_drops_unknown_keys(self, engine):
        s = engine.sanitize_state({"treasures": {"residual_scroll": 1, "作弊钥匙": 99,
                                                 "immortal_art": 2}})
        assert set(s["treasures"]) == {"residual_scroll", "immortal_art"}
        assert s["eff_bonus"] == pytest.approx(0.27)     # 0.03 + 0.12×2

    def test_quantity_is_clamped_to_cap(self, engine):
        s = engine.sanitize_state({"treasures": {"residual_scroll": 999, "guard_talisman": -3,
                                                 "immortal_art": 50}})
        assert s["treasures"]["residual_scroll"] == engine.TREASURE_CAP["residual_scroll"]
        assert s["treasures"]["immortal_art"] == engine.TREASURE_CAP["immortal_art"]
        assert "guard_talisman" not in s["treasures"]    # 负数不入账

    def test_non_dict_treasures_is_ignored(self, engine):
        for junk in (None, [], "x", 5):
            assert engine.sanitize_state({"treasures": junk})["treasures"] == {}

    def test_derived_fields_survive_roundtrip(self, engine):
        s = engine.sanitize_state({"treasures": {"enlight_stone": 3}})
        again = engine.sanitize_state(dict(s))
        assert again["treasures"] == s["treasures"]
        assert again["break_bonus"] == pytest.approx(0.09)


# ---------------------------------------------------------------- 端到端：探索陨落经接口回传
class TestExploreDeathThroughApi:
    def _live_state(self, engine):
        return {
            "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
            "exp": 0, "spirit_stones": 999, "spirit_root": "三灵根·金木水",
            "items": [], "memory": [], "recent": [], "turn": 0, "days": 0,
        }

    def test_act_reports_explore_death(self, engine, client, monkeypatch):
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.0])
        r = client.post("/api/act", json={
            "state": self._live_state(engine),
            "action": {"type": "choice", "text": "深入荒泽秘境", "tag": "explore", "risk": "mid"},
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["dead"] is True
        assert d["state"]["dead"] is True
        assert d["engine_meta"]["explore_death"] is True

    def test_act_keeps_treasure_after_drop(self, engine, client, monkeypatch):
        _scripted(monkeypatch, engine, randints=[30], randoms=[0.99, 0.0, 0.0])
        r = client.post("/api/act", json={
            "state": self._live_state(engine),
            "action": {"type": "choice", "text": "远行历练", "tag": "explore", "risk": "mid"},
        })
        d = r.json()
        assert d["dead"] is False
        assert d["state"]["treasures"].get("residual_scroll") == 1
        assert d["engine_meta"]["treasure"]["name"] == "功法残卷"

    def test_act_routes_use_elixir(self, engine, client):
        """服灵丹走独立纯代码动作：不调 LLM、不给裸修为、只开 buff。"""
        s = self._live_state(engine)
        s["realm_index"] = 8
        s["treasures"] = {"elixir": 1}
        r = client.post("/api/act", json={"state": s, "action": {"type": "use_elixir"}})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["state"]["elixir_buff"] == engine.ELIXIR_BUFF_ROUNDS
        assert d["state"]["treasures"] == {}
        assert d["delta_applied"]["exp"] == 0
        assert d["engine_meta"]["source"] == "item"
        assert d["engine_meta"]["elixir"]["eff"] == pytest.approx(engine.ELIXIR_EFF_BUFF)

    def test_act_use_elixir_without_one_errors(self, engine, client):
        r = client.post("/api/act", json={
            "state": self._live_state(engine), "action": {"type": "use_elixir"}})
        d = r.json()
        assert d["ok"] is False
        assert d["error"]["code"] == "ELIXIR_NOT_OWNED"
