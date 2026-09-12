# -*- coding: utf-8 -*-
"""经济系统：坊市固定价格、买卖双向、修炼消耗、濒死惩罚。

坊市是全局唯一的经济锚点，价格不受 AI 影响，
一旦这里的算术出错，整个经济系统会通胀或通缩。
"""
import pytest


class TestShopPrices:
    def test_buy_table_is_complete(self, engine):
        for name, info in engine.SHOP_BUY.items():
            assert isinstance(info["price"], int) and info["price"] > 0
            assert info["rarity"] in engine.VALID_RARITY

    def test_sell_price_is_half_of_buy(self, engine):
        """卖出价 = 买入价 × 50%，且向下取整。"""
        assert engine.SHOP_SELL_RATIO == 0.5
        for name, info in engine.SHOP_BUY.items():
            expected = int(info["price"] * engine.SHOP_SELL_RATIO)
            # 复用 /api/shop 的算式
            assert int(engine.SHOP_BUY[name]["price"] * engine.SHOP_SELL_RATIO) == expected

    def test_buy_then_sell_loses_value(self, engine, base_state):
        """买后立刻卖必然亏损 —— 防止无限刷灵石套利。"""
        for name, info in engine.SHOP_BUY.items():
            buy_total = info["price"]
            sell_price = int(engine.SHOP_BUY[name]["price"] * engine.SHOP_SELL_RATIO)
            assert sell_price < buy_total or (buy_total == 1 and sell_price == 0), \
                f"{name} 存在刷钱空间: 买{buy_total} 卖{sell_price}"


class TestShopEndpoint:
    def test_buy_success(self, engine, client, base_state):
        """买 2 枚回气丹：扣 50 灵石，数量并入既有堆叠（默认背包已有 2 枚）。"""
        before_qty = next(i["qty"] for i in base_state["items"] if i["name"] == "回气丹")
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 100},
            "action": {"type": "shop_buy", "name": "回气丹", "qty": 2},
        }).json()
        assert r["ok"] is True
        assert r["state"]["spirit_stones"] == 50
        got = next(i for i in r["state"]["items"] if i["name"] == "回气丹")
        assert got["qty"] == before_qty + 2 and got["rarity"] == "下品"
        assert r["delta_applied"]["spirit_stones"] == -50
        assert "50枚灵石" in r["narrative"]

    def test_buy_stacks_into_empty_bag(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 100, "items": []},
            "action": {"type": "shop_buy", "name": "回气丹", "qty": 2},
        }).json()
        assert r["state"]["items"] == [{"name": "回气丹", "qty": 2, "rarity": "下品"}]

    def test_buy_unknown_item(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": base_state, "action": {"type": "shop_buy", "name": "仙丹", "qty": 1},
        }).json()
        assert r["ok"] is False and r["error"]["code"] == "ITEM_NOT_SOLD"

    def test_buy_insufficient_stones(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 10},
            "action": {"type": "shop_buy", "name": "凝气丹", "qty": 1},
        }).json()
        assert r["ok"] is False and r["error"]["code"] == "NOT_ENOUGH_STONES"
        assert "40枚" in r["error"]["message"]

    def test_buy_exactly_affordable(self, engine, client, base_state):
        """边界：钱刚好够时必须成功。"""
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 25},
            "action": {"type": "shop_buy", "name": "回气丹", "qty": 1},
        }).json()
        assert r["ok"] is True
        assert r["state"]["spirit_stones"] == 0

    def test_sell_success(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 0,
                      "items": [{"name": "回气丹", "qty": 3, "rarity": "下品"}]},
            "action": {"type": "shop_sell", "name": "回气丹", "qty": 2},
        }).json()
        assert r["ok"] is True
        assert r["state"]["spirit_stones"] == 24      # int(25*0.5)=12 每件 × 2
        assert r["state"]["items"][0]["qty"] == 1
        assert r["delta_applied"]["items_remove"] == [{"name": "回气丹", "qty": 2}]

    def test_sell_last_stack_removes_item(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": {**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}]},
            "action": {"type": "shop_sell", "name": "回气丹", "qty": 1},
        }).json()
        assert r["ok"] is True and r["state"]["items"] == []

    def test_sell_unowned_item(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": {**base_state, "items": []},
            "action": {"type": "shop_sell", "name": "回气丹", "qty": 1},
        }).json()
        assert r["ok"] is False and r["error"]["code"] == "ITEM_NOT_OWNED"

    def test_sell_more_than_owned(self, engine, client, base_state):
        r = client.post("/api/shop", json={
            "state": {**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}]},
            "action": {"type": "shop_sell", "name": "回气丹", "qty": 5},
        }).json()
        assert r["ok"] is False and r["error"]["code"] == "ITEM_NOT_OWNED"

    def test_sell_non_shop_item_uses_fallback_price(self, engine, client, base_state):
        """非坊市在售物也能卖，走兜底价 10 → 卖 5。"""
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 0,
                      "items": [{"name": "铁背蜥甲", "qty": 1, "rarity": "中品"}]},
            "action": {"type": "shop_sell", "name": "铁背蜥甲", "qty": 1},
        }).json()
        assert r["ok"] is True and r["state"]["spirit_stones"] == 5

    def test_unknown_op(self, engine, client, base_state):
        r = client.post("/api/shop", json={"state": base_state, "action": {"type": "steal"}}).json()
        assert r["ok"] is False and r["error"]["code"] == "UNKNOWN_OP"

    def test_empty_action(self, engine, client, base_state):
        r = client.post("/api/shop", json={"state": base_state, "action": {}}).json()
        assert r["ok"] is False and r["error"]["code"] == "UNKNOWN_OP"

    def test_qty_is_clamped(self, engine, client, base_state):
        """qty 上限 10，下限 1 —— 防止一次买爆或负数套利。"""
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 99999, "items": []},
            "action": {"type": "shop_buy", "name": "辟谷丹", "qty": 999},
        }).json()
        assert r["ok"] is True
        assert r["state"]["items"][0]["qty"] == 10

        r2 = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": 99999, "items": []},
            "action": {"type": "shop_buy", "name": "辟谷丹", "qty": -5},
        }).json()
        assert r2["state"]["items"][0]["qty"] == 1

    def test_state_is_sanitized_on_return(self, engine, client, base_state):
        """返回的 state 必须是白名单清洗过的，不能携带脏字段。"""
        dirty = {**base_state, "spirit_stones": 100, "hacked": True, "realm_index": 99}
        r = client.post("/api/shop", json={
            "state": dirty, "action": {"type": "shop_buy", "name": "辟谷丹", "qty": 1},
        }).json()
        assert r["ok"] is True
        assert "hacked" not in r["state"]
        assert r["state"]["realm_index"] <= engine.MAX_REALM_INDEX

    def test_round_trip_economy(self, engine, client, base_state):
        """完整往返：买 → 卖 → 灵石必然减少，杜绝刷钱。"""
        before = 200
        r = client.post("/api/shop", json={
            "state": {**base_state, "spirit_stones": before, "items": []},
            "action": {"type": "shop_buy", "name": "凝气丹", "qty": 1},
        }).json()
        mid_state = r["state"]
        r2 = client.post("/api/shop", json={
            "state": mid_state, "action": {"type": "shop_sell", "name": "凝气丹", "qty": 1},
        }).json()
        assert r2["state"]["spirit_stones"] < before


class TestCultivationCost:
    @pytest.mark.parametrize("realm,expected", [(0, 1), (1, 1), (2, 2), (3, 2), (5, 3), (9, 5)])
    def test_cost_grows_with_realm(self, engine, base_state, realm, expected):
        assert engine.cultivate_cost({**base_state, "realm_index": realm}) == expected

    def test_cost_is_never_free_nor_huge(self, engine, base_state):
        for lv in range(10):
            cost = engine.cultivate_cost({**base_state, "realm_index": lv})
            assert 1 <= cost <= 5


class TestNearDeath:
    def test_first_near_death_penalty(self, engine, base_state):
        """首次濒死：HP 恢复至 35%，灵石减半，修为折损 15%。"""
        s = {**base_state, "hp": 0, "spirit_stones": 100, "exp": 100, "turn": 10}
        fx = engine.near_death_protocol(s)
        assert s["hp"] == int(100 * engine.NEAR_DEATH_HP_RATIO) == 35
        assert s["spirit_stones"] == 50
        assert s["exp"] == 85
        assert s["last_near_death_turn"] == 10
        assert fx["hp"] == 35 and fx["spirit_stones"] == -50 and fx["exp"] == -15

    def test_repeat_within_cooldown_is_harsher(self, engine, base_state):
        """5 轮内再濒死：灵石只剩 25%。"""
        s = {**base_state, "hp": 0, "spirit_stones": 100, "exp": 100,
             "turn": 12, "last_near_death_turn": 10}
        engine.near_death_protocol(s)
        assert s["spirit_stones"] == 25

    def test_after_cooldown_returns_to_half(self, engine, base_state):
        s = {**base_state, "hp": 0, "spirit_stones": 100, "exp": 100,
             "turn": 20, "last_near_death_turn": 10}
        engine.near_death_protocol(s)
        assert s["spirit_stones"] == 50

    def test_hp_floor_of_10(self, engine, base_state):
        """低血量上限时仍保底 10 点 —— 绝不允许开局即死锁。"""
        s = {**base_state, "hp": 0, "hp_max": 20}
        engine.near_death_protocol(s)
        assert s["hp"] == 10

    def test_exp_never_negative(self, engine, base_state):
        s = {**base_state, "hp": 0, "exp": 0}
        fx = engine.near_death_protocol(s)
        assert s["exp"] == 0 and fx["exp"] == 0
