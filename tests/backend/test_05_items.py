# -*- coding: utf-8 -*-
"""物品系统：丹药效果表、品级倍率、服丹扣减、材料不可食用、选项沿用。

用丹走纯代码分支（不调 AI），是唯一一条「零延迟零开销」的行动路径，
因此它的正确性必须被完整锁死。
"""
import pytest


class TestItemTable:
    def test_every_effect_is_defined_once(self, engine):
        """效果只在此处定义 —— AI 无权发明药效。"""
        for name, info in engine.ITEM_TABLE.items():
            assert isinstance(name, str) and name
            assert info["effect"], f"{name} 无效果"
            assert info["text"], f"{name} 无描述"

    def test_effect_keys_are_supported(self, engine):
        allowed = {"hp_pct", "qi_pct", "exp", "hp", "qi"}
        for name, info in engine.ITEM_TABLE.items():
            for k in info["effect"]:
                assert k in allowed, f"{name} 使用了未支持的 effect key: {k}"

    def test_rarity_multiplier_is_graduated(self, engine):
        assert engine.RARITY_MULTIPLIER["下品"] < engine.RARITY_MULTIPLIER["中品"] < engine.RARITY_MULTIPLIER["上品"]
        assert engine.RARITY_MULTIPLIER["下品"] == 1.0
        assert tuple(engine.RARITY_MULTIPLIER) == tuple(engine.VALID_RARITY)


class TestUseItem:
    def test_missing_item_is_rejected(self, engine, base_state, fake_req):
        req = fake_req(state=base_state, action={"type": "use_item", "name": "不存在丹"})
        res = engine.handle_use_item(engine.sanitize_state(base_state), req)
        assert res["ok"] is False
        assert res["error"]["code"] == "ITEM_NOT_OWNED"

    def test_zero_qty_is_rejected(self, engine, fake_req):
        """数量为 0 的格子视作不存在（未经清洗的脏数据也不得放行）。"""
        s = {"realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50, "exp": 0,
             "spirit_stones": 0, "items": [{"name": "回气丹", "qty": 0, "rarity": "下品"}],
             "memory": [], "npcs": [], "pending_events": [], "turn": 0}
        req = fake_req(action={"type": "use_item", "name": "回气丹"})
        res = engine.handle_use_item(s, req)
        assert res["ok"] is False and res["error"]["code"] == "ITEM_NOT_OWNED"

    def test_invalid_qty_is_repaired_by_sanitize(self, engine, base_state):
        """sanitize_state 会把非法数量修正为 1，而非让玩家白拿。"""
        s = engine.sanitize_state({**base_state, "items": [{"name": "回气丹", "qty": 0}]})
        assert s["items"][0]["qty"] == 1

    def test_material_cannot_be_eaten(self, engine, base_state, fake_req):
        """材料（不在效果表）不能服用，但也不应报错 —— 返回中性叙事。"""
        s = engine.sanitize_state({**base_state, "items": [{"name": "碎星石", "qty": 1, "rarity": "下品"}]})
        req = fake_req(action={"type": "use_item", "name": "碎星石"})
        res = engine.handle_use_item(s, req)
        assert res["ok"] is True
        assert "并非丹药" in res["narrative"]
        assert res["delta_applied"]["items_remove"] == []   # 材料不被消耗
        assert res["engine_meta"]["source"] == "item"
        assert res["near_death"] is False and res["ending"] is False

    def test_percentage_heal_scales_with_rarity(self, engine, base_state, fake_req):
        """回气丹 30% 最大气血，上品应显著强于下品。"""
        results = {}
        for rarity in ("下品", "中品", "上品"):
            s = engine.sanitize_state({**base_state, "hp": 10,
                                       "items": [{"name": "回气丹", "qty": 1, "rarity": rarity}]})
            req = fake_req(action={"type": "use_item", "name": "回气丹"})
            res = engine.handle_use_item(s, req)
            results[rarity] = res["delta_applied"]["hp"]
        mult = engine.RARITY_MULTIPLIER
        assert results["下品"] == int(100 * 0.30 * mult["下品"])
        assert results["中品"] == int(100 * 0.30 * mult["中品"])
        assert results["上品"] == int(100 * 0.30 * mult["上品"])
        assert results["下品"] < results["中品"] < results["上品"]

    def test_exp_pill_respects_spirit_root(self, engine, base_state, fake_req):
        """凝气丹的经验收益必须过一遍灵根系数。"""
        for root, expect_mult in [("天灵根·火", 1.6), ("四灵根·伪灵根", 0.75)]:
            s = engine.sanitize_state({**base_state, "spirit_root": root, "exp": 0,
                                       "items": [{"name": "凝气丹", "qty": 1, "rarity": "下品"}]})
            req = fake_req(action={"type": "use_item", "name": "凝气丹"})
            res = engine.handle_use_item(s, req)
            assert res["delta_applied"]["exp"] == int(25 * expect_mult)

    def test_pill_is_consumed(self, engine, base_state, fake_req):
        s = engine.sanitize_state({**base_state, "items": [{"name": "回气丹", "qty": 3, "rarity": "下品"}]})
        req = fake_req(action={"type": "use_item", "name": "回气丹"})
        res = engine.handle_use_item(s, req)
        assert res["state"]["items"][0]["qty"] == 2
        assert res["delta_applied"]["items_remove"] == [{"name": "回气丹", "qty": 1}]

    def test_last_pill_disappears_from_bag(self, engine, base_state, fake_req):
        s = engine.sanitize_state({**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}]})
        req = fake_req(action={"type": "use_item", "name": "回气丹"})
        res = engine.handle_use_item(s, req)
        assert res["state"]["items"] == []

    def test_heal_never_exceeds_cap(self, engine, base_state, fake_req):
        """满血服丹不得溢出。"""
        s = engine.sanitize_state({**base_state, "hp": 100,
                                   "items": [{"name": "回气丹", "qty": 1, "rarity": "上品"}]})
        req = fake_req(action={"type": "use_item", "name": "回气丹"})
        res = engine.handle_use_item(s, req)
        assert res["state"]["hp"] == s["hp_max"]

    def test_exp_pill_respects_exp_cap(self, engine, base_state, fake_req):
        """服丹涨经验不得突破当前境界上限（否则直接跳过冲关）。"""
        s = engine.sanitize_state({**base_state, "exp": 95, "spirit_root": "天灵根·火",
                                   "items": [{"name": "凝气丹", "qty": 1, "rarity": "上品"}]})
        req = fake_req(action={"type": "use_item", "name": "凝气丹"})
        res = engine.handle_use_item(s, req)
        assert res["state"]["exp"] == engine.exp_max_of(0)

    def test_flat_effect_pills(self, engine, base_state, fake_req):
        """辟谷丹：固定 +10/+10，同样吃品级倍率。"""
        s = engine.sanitize_state({**base_state, "hp": 10, "qi": 10,
                                   "items": [{"name": "辟谷丹", "qty": 1, "rarity": "上品"}]})
        req = fake_req(action={"type": "use_item", "name": "辟谷丹"})
        res = engine.handle_use_item(s, req)
        assert res["delta_applied"]["hp"] == 25
        assert res["delta_applied"]["qi"] == 25

    def test_qi_pill(self, engine, base_state, fake_req):
        """清心丹：恢复 50% 灵力上限。"""
        s = engine.sanitize_state({**base_state, "qi": 0,
                                   "items": [{"name": "清心丹", "qty": 1, "rarity": "下品"}]})
        req = fake_req(action={"type": "use_item", "name": "清心丹"})
        res = engine.handle_use_item(s, req)
        assert res["delta_applied"]["qi"] == int(50 * 0.5)
        assert res["state"]["qi"] == 25

    def test_choices_are_carried_over(self, engine, base_state, fake_req):
        """用丹不打断剧情节奏：沿用上一轮选项。"""
        last = [{"id": "A", "text": "赶路", "risk": "mid", "tag": "explore"}]
        s = engine.sanitize_state({**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}]})
        req = fake_req(action={"type": "use_item", "name": "回气丹"}, last_choices=last)
        res = engine.handle_use_item(s, req)
        assert res["choices"][0]["text"] == "赶路"


class TestDeltaApplication:
    def test_add_items_merges_by_name(self, engine, base_state):
        s = {**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}]}
        engine.apply_delta(s, {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                               "items_add": [{"name": "回气丹", "qty": 2, "rarity": "下品"}],
                               "items_remove": []})
        assert s["items"] == [{"name": "回气丹", "qty": 3, "rarity": "下品"}]

    def test_remove_items_deletes_empty_stack(self, engine, base_state):
        s = {**base_state, "items": [{"name": "回气丹", "qty": 1, "rarity": "下品"}]}
        engine.apply_delta(s, {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                               "items_add": [], "items_remove": [{"name": "回气丹", "qty": 5}]})
        assert s["items"] == []

    def test_bag_capacity_is_20(self, engine, base_state):
        """背包上限 20 —— 防止 AI 无限塞物品撑爆存档。"""
        items = [{"name": f"物{i}", "qty": 1, "rarity": "下品"} for i in range(20)]
        s = {**base_state, "items": items}
        engine.apply_delta(s, {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                               "items_add": [{"name": "溢出物", "qty": 1, "rarity": "下品"}],
                               "items_remove": []})
        assert len(s["items"]) == 20
        assert all(it["name"] != "溢出物" for it in s["items"])

    def test_numeric_clamping(self, engine, base_state):
        s = {**base_state, "hp": 100, "qi": 50, "spirit_stones": 5}
        engine.apply_delta(s, {"hp": 999, "qi": 999, "exp": 999, "spirit_stones": -999,
                               "items_add": [], "items_remove": []})
        assert s["hp"] == s["hp_max"] and s["qi"] == s["qi_max"]
        assert s["spirit_stones"] == 0
