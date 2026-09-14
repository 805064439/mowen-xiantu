# -*- coding: utf-8 -*-
"""江湖人物（NPC）：道缘升降、称谓语义、天机事件阈值与冷却、相识上限淘汰。

这一层是「AI 提议，代码裁决」的典型：AI 只能提出道缘±20 的变化，
是否触发事件、是否淘汰旧人，全部由代码说了算。
"""
import pytest


class TestBondLabel:
    @pytest.mark.parametrize("bond,label", [
        (-100, "死敌"), (-60, "死敌"), (-59, "敌视"), (-20, "敌视"),
        (-19, "相识"), (0, "相识"), (19, "相识"),
        (20, "友善"), (49, "友善"),
        (50, "亲近"), (79, "亲近"),
        (80, "生死之交"), (100, "生死之交"),
    ])
    def test_label_boundaries(self, engine, bond, label):
        assert engine.bond_label(bond) == label

    def test_labels_are_monotonic(self, engine):
        labels = [engine.bond_label(b) for b in range(-100, 101, 10)]
        order = ["死敌", "敌视", "相识", "友善", "亲近", "生死之交"]
        idx = [order.index(l) for l in labels]
        assert idx == sorted(idx), "称谓随道缘非单调递进"


class TestNpcUpdates:
    def test_new_npc_is_created(self, engine, base_state):
        ev = engine.apply_npc_updates(base_state, {"npc_updates": [
            {"name": "青云子", "title": "散修", "delta": 5},
        ]})
        assert base_state["npcs"][0]["name"] == "青云子"
        assert base_state["npcs"][0]["title"] == "散修"
        assert base_state["npcs"][0]["bond"] == 5
        assert base_state["npcs"][0]["met_turn"] == base_state["turn"]
        assert ev == [{"name": "青云子", "delta": 5}]

    def test_existing_npc_accumulates(self, engine, base_state):
        engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "青云子", "delta": 10}]})
        engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "青云子", "delta": 12}]})
        assert base_state["npcs"][0]["bond"] == 22

    def test_delta_capped_at_20(self, engine, base_state):
        """单轮道缘变化被钳在 ±20：先钳幅度，再叠加 —— 因此不会一跃成为生死之交。"""
        ev_up = engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "青云子", "delta": 999}]})
        assert ev_up == [{"name": "青云子", "delta": 20}]     # 上报的飘字已钳制
        assert base_state["npcs"][0]["bond"] == 20
        ev_down = engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "青云子", "delta": -999}]})
        assert ev_down == [{"name": "青云子", "delta": -20}]
        assert base_state["npcs"][0]["bond"] == 0

    def test_bond_clamped_to_100(self, engine, base_state):
        for _ in range(20):
            engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "青云子", "delta": 20}]})
        assert base_state["npcs"][0]["bond"] == 100

    def test_zero_delta_produces_no_events(self, engine, base_state):
        """无变化的更新不产生飘字。"""
        ev = engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "青云子", "delta": 0}]})
        assert ev == []

    def test_only_three_updates_per_turn(self, engine, base_state):
        """单轮最多处理 3 条 AI 上报的道缘变化，防止一次性灌满名册。"""
        ups = [{"name": f"人{i}", "delta": 1} for i in range(10)]
        ev = engine.apply_npc_updates(base_state, {"npc_updates": ups})
        assert len(ev) == 3
        assert len(base_state["npcs"]) == 3

    def test_malformed_updates_are_dropped(self, engine, base_state):
        ups = ["string", {}, {"name": "  "}, {"name": "仅名字"}, 42, {"delta": 5}]
        ev = engine.apply_npc_updates(base_state, {"npc_updates": ups})
        assert ev == []
        assert base_state["npcs"] == []

    def test_non_list_input_is_ignored(self, engine, base_state):
        for bad in (None, "x", 123, {}):
            assert engine.apply_npc_updates(base_state, {"npc_updates": bad}) == []

    def test_list_is_truncated_to_max(self, engine, base_state):
        """名册整体也不得超过 NPC_MAX —— 多次更新后仍需被剪到上限。"""
        for round_i in range(6):
            ups = [{"name": f"人{round_i}_{i}", "delta": 1} for i in range(3)]
            engine.apply_npc_updates(base_state, {"npc_updates": ups})
        assert len(base_state["npcs"]) <= engine.NPC_MAX

    def test_old_friend_survives_eviction(self, engine, base_state):
        """相识满员时，道缘深且结识久的人更难被淡忘。"""
        base_state["turn"] = 50
        base_state["npcs"] = [
            {"name": "生死交", "title": "道长", "bond": 100, "met_turn": 1, "fired": {}},
            {"name": "路人脸", "title": "商贩", "bond": 1, "met_turn": 49, "fired": {}},
            {"name": "泛泛乙", "title": "商贩", "bond": 2, "met_turn": 48, "fired": {}},
            {"name": "泛泛丙", "title": "商贩", "bond": 3, "met_turn": 47, "fired": {}},
            {"name": "泛泛丁", "title": "商贩", "bond": 4, "met_turn": 46, "fired": {}},
            {"name": "泛泛戊", "title": "商贩", "bond": 5, "met_turn": 45, "fired": {}},
        ]
        assert len(base_state["npcs"]) == engine.NPC_MAX   # 已满员才会触发淘汰
        ev = engine.apply_npc_updates(base_state, {"npc_updates": [{"name": "新人", "delta": 1}]})
        names = [n["name"] for n in base_state["npcs"]]
        assert ev == [{"name": "新人", "delta": 1}]
        assert "新人" in names and "生死交" in names, "至交被误淘汰"
        assert len(names) == engine.NPC_MAX


class TestNpcEvents:
    def test_gift_event_at_high_bond(self, engine, base_state):
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 75, "met_turn": 0, "fired": {}}]
        engine.check_npc_events(base_state)
        assert base_state["pending_events"] == [{"type": "gift", "npc": "青云子", "at": 0}]

    def test_no_gift_below_threshold(self, engine, base_state):
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 69, "met_turn": 0, "fired": {}}]
        engine.check_npc_events(base_state)
        assert base_state["pending_events"] == []

    def test_vendetta_takes_priority_over_gift(self, engine, base_state):
        base_state["npcs"] = [
            {"name": "死敌甲", "title": "邪修", "bond": -80, "met_turn": 0, "fired": {}},
            {"name": "挚友乙", "title": "道长", "bond": 90, "met_turn": 0, "fired": {}},
        ]
        engine.check_npc_events(base_state)
        types = [e["type"] for e in base_state["pending_events"]]
        assert types[0] == "vendetta"

    def test_repeat_cooldown_blocks_immediate_retrigger(self, engine, base_state):
        base_state["turn"] = 12
        npc = {"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0,
               "fired": {"gift": 10}}
        base_state["npcs"] = [npc]
        engine.check_npc_events(base_state)
        assert base_state["pending_events"] == [], "冷却期内不应重复触发"

    def test_trigger_allowed_after_cooldown(self, engine, base_state):
        base_state["turn"] = 25
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0,
                               "fired": {"gift": 10}}]
        engine.check_npc_events(base_state)
        assert len(base_state["pending_events"]) == 1

    def test_teach_requires_prior_gift(self, engine, base_state):
        base_state["turn"] = 0
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0, "fired": {}}]
        # 首次触发只会走到 gift（elif 链）
        engine.check_npc_events(base_state)
        assert base_state["pending_events"][0]["type"] == "gift"

        base_state["turn"] = 20
        base_state["pending_events"] = []
        base_state["npcs"][0]["fired"]["gift"] = 15
        engine.check_npc_events(base_state)
        assert base_state["pending_events"][0]["type"] == "teach"

    def test_teach_needs_gap_after_gift(self, engine, base_state):
        base_state["turn"] = 16
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0,
                               "fired": {"gift": 15}}]
        engine.check_npc_events(base_state)
        assert base_state["pending_events"] == [], "gift 触发后不足 3 轮不应立刻传功"

    def test_pending_events_capped_at_three(self, engine, base_state):
        base_state["npcs"] = [
            {"name": f"人{i}", "title": "道", "bond": 90, "met_turn": 0, "fired": {}}
            for i in range(10)
        ]
        engine.check_npc_events(base_state)
        assert len(base_state["pending_events"]) <= 3

    def test_check_is_idempotent_per_turn(self, engine, base_state):
        """同一轮重复调用不应刷出更多事件（fired 已被写入）。"""
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0, "fired": {}}]
        engine.check_npc_events(base_state)
        n1 = len(base_state["pending_events"])
        engine.check_npc_events(base_state)
        assert len(base_state["pending_events"]) == n1


class TestConsumePendingEvent:
    def test_empty_queue(self, engine, base_state):
        text, trial, fx = engine.consume_pending_event(base_state)
        assert trial is None and fx == {}
        assert "无特殊判定" in text

    def test_gift_grants_stones_and_loot(self, engine, base_state):
        base_state["pending_events"] = [{"type": "gift", "npc": "青云子", "at": 0}]
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0, "fired": {}}]
        text, trial, fx = engine.consume_pending_event(base_state)
        assert trial is None
        assert fx["spirit_stones"] >= 30
        assert fx["items_add"] and fx["items_add"][0]["qty"] == 1
        assert base_state["spirit_stones"] >= 30
        assert base_state["items"], "赠宝未真正入包"
        assert base_state["pending_events"] == []  # 已被消费
        assert "勿在 delta 中重复计入" in text

    def test_teach_grants_root_scaled_exp(self, engine, base_state):
        base_state["spirit_root"] = "天灵根·火"
        base_state["pending_events"] = [{"type": "teach", "npc": "青云子", "at": 0}]
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0, "fired": {}}]
        text, trial, fx = engine.consume_pending_event(base_state)
        assert fx["exp"] == 64           # 40 × 1.6
        assert base_state["exp"] == 64
        assert "故人传功" in text

    def test_teach_respects_exp_cap(self, engine, base_state):
        base_state["spirit_root"] = "天灵根·火"
        base_state["exp"] = 99
        base_state["pending_events"] = [{"type": "teach", "npc": "青云子", "at": 0}]
        base_state["npcs"] = [{"name": "青云子", "title": "道长", "bond": 90, "met_turn": 0, "fired": {}}]
        engine.consume_pending_event(base_state)
        assert base_state["exp"] == engine.exp_max_of(0)
        assert base_state["exp"] == engine.REALM_TABLE[0][1]   # 顶到炼气一层的圆满线

    def test_vendetta_starts_fight(self, engine, base_state):
        base_state["pending_events"] = [{"type": "vendetta", "npc": "仇天道", "at": 0}]
        base_state["npcs"] = [{"name": "仇天道", "title": "邪修", "bond": -90, "met_turn": 0, "fired": {}}]
        text, trial, fx = engine.consume_pending_event(base_state)
        assert trial is not None and trial.get("fight") is True
        assert trial["enemy"] == "仇天道"   # 叙事名保留
        assert "hp" in fx

    def test_unknown_npc_name_still_resolves(self, engine, base_state):
        """事件引用的 NPC 已不在册（被淘汰）时不崩溃，称谓回落到『故人』。"""
        base_state["pending_events"] = [{"type": "gift", "npc": "已淡忘者", "at": 0}]
        text, trial, fx = engine.consume_pending_event(base_state)
        assert "已淡忘者" in text and "故人" in text


class TestStyleEcho:
    def test_head_is_recorded_and_deduplicated(self, engine, base_state):
        engine.update_style_echo(base_state, "清晨的山雾尚未散去，你踏上石阶")
        engine.update_style_echo(base_state, "清晨的山雾尚未散去，你踏上石阶")  # 相同不重复
        assert len(base_state["style_echo"]) == 1
        engine.update_style_echo(base_state, "夜色如水，破庙漏下的月光")
        assert len(base_state["style_echo"]) == 2

    def test_echo_keeps_only_eight(self, engine, base_state):
        for i in range(30):
            engine.update_style_echo(base_state, f"第{i}段开篇文字示例")
        assert len(base_state["style_echo"]) == 8

    def test_empty_narrative_is_ignored(self, engine, base_state):
        engine.update_style_echo(base_state, "")
        engine.update_style_echo(base_state, "   ")
        assert base_state["style_echo"] == []
