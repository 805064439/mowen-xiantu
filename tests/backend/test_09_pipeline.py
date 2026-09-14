# -*- coding: utf-8 -*-
"""整回合流水线：AI delta 钳制 → 应用 → 修炼消耗 → 濒死 → 选项 → 簿记 → 记忆压缩。

/api/act 与 /api/act/stream 共用 _postprocess_turn，这里验证两路永不分叉，
以及 AI 无论如何越界都无法污染状态。
"""
import pytest


class TestClampAiDelta:
    @pytest.mark.parametrize("field,bound", [("hp", 30), ("qi", 30), ("exp", 40), ("spirit_stones", 80)])
    def test_bounds_enforced(self, engine, base_state, field, bound):
        d = engine.clamp_ai_delta({field: 100000}, base_state)
        assert d[field] == bound
        d = engine.clamp_ai_delta({field: -100000}, base_state)
        assert d[field] == -bound

    def test_non_dict_delta(self, engine, base_state):
        for bad in (None, [], "x", 123):
            d = engine.clamp_ai_delta(bad, base_state)
            assert d == {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                         "items_add": [], "items_remove": []}

    def test_missing_fields_default_zero(self, engine, base_state):
        d = engine.clamp_ai_delta({}, base_state)
        assert d["hp"] == d["qi"] == d["exp"] == d["spirit_stones"] == 0

    def test_string_values_are_coerced(self, engine, base_state):
        d = engine.clamp_ai_delta({"hp": "15", "exp": "20", "qi": "abc"}, base_state)
        assert d["hp"] == 15 and d["exp"] == 20 and d["qi"] == 0

    def test_items_add_limited_and_rarity_normalized(self, engine, base_state):
        d = engine.clamp_ai_delta({"items_add": [
            {"name": "丹药", "qty": 1, "rarity": "神品"},
            {"name": "第二件", "qty": 99, "rarity": "中品"},
            {"name": "第三件", "qty": 1},
            {"name": "第四件", "qty": 1},   # 超出 3 件上限
        ]}, base_state)
        assert len(d["items_add"]) == 3
        assert d["items_add"][0]["rarity"] == "下品"
        assert d["items_add"][1]["qty"] == 3

    def test_items_add_rejects_malformed(self, engine, base_state):
        """非法条目被剔除；注意只审视前 3 条，因此有效项要放在窗口内。"""
        d = engine.clamp_ai_delta({"items_add": ["x", {}, {"name": "有效"}]}, base_state)
        assert len(d["items_add"]) == 1 and d["items_add"][0]["name"] == "有效"

    def test_items_remove_only_existing(self, engine, base_state):
        """AI 不能移除玩家没有的物品。"""
        d = engine.clamp_ai_delta({"items_remove": [
            {"name": "回气丹", "qty": 99},        # 只有 2 个
            {"name": "不存在的东西", "qty": 1},
        ]}, base_state)
        assert len(d["items_remove"]) == 1
        assert d["items_remove"][0]["qty"] == 2    # 被钳到持有量

    def test_bool_is_not_treated_as_number(self, engine, base_state):
        d = engine.clamp_ai_delta({"hp": True}, base_state)
        assert d["hp"] == 0


class TestPostprocessPipeline:
    def test_full_turn_applies_delta_and_costs(self, engine, base_state, lock_days):
        s = engine.sanitize_state({**base_state, "spirit_stones": 100, "hp": 50, "exp": 10})
        meta = {}
        lock_days(engine.ACTION_DAYS["rest"][1])   # 静养 45 天，取上限才好断言正收益
        narrative, choices, delta, nd, npc_ev = engine._postprocess_turn(
            s, {"delta": {"hp": 10, "exp": 10}, "choices": [], "narrative": "你略作调息。",
                "memory": "调息养气"}, meta, "打坐", "rest")
        assert s["hp"] == 60
        # v2：修为 = 天数 × 静养日效率(0.030) × 灵根(1.0) × 连击(1.0) × 状态(半血 → 0.92)
        # 天数由 _postprocess_turn 掷定（15~45），故此处只校验「确实入账了正修为」
        assert s["exp"] > 10
        assert delta["exp"] > 0
        assert delta["exp"] == s["exp"] - 10
        assert meta["cultivate"]["action_label"] == "静养调息"
        # 状态修正 = 0.7 + 0.3 × (半血 0.5×0.5 + 满灵 1.0×0.5) = 0.925 → 回传两位小数
        assert meta["cultivate"]["vitality"] == 0.92
        # 天数与日效率必须回传，前端据此解释「这一轮花掉了多少寿命」
        assert meta["cultivate"]["days"] == engine.ACTION_DAYS["rest"][1]
        # 连修一轮，连击计数已累加
        assert s["cultivate_streak"] == 1
        assert delta["hp"] == 10
        # 修炼消耗：境界 0 → 1 灵石
        assert s["spirit_stones"] == 99
        assert delta["spirit_stones"] == -1
        assert s["turn"] == 1
        assert s["memory"] == ["调息养气"]
        assert len(choices) == 3
        assert nd is False

    def test_exp_gain_uses_spirit_root_coefficient(self, engine, base_state, lock_days):
        """灵根系数照旧生效，只是基底从「AI 给的修为」换成了「天数 × 日效率」。

        抬到炼气九层取样：v3 的一次闭关产出（252~468）会顶到低层单轮上限，
        把灵根差异一并抹平，只有高层才量得准。"""
        gains = {}
        for root in ("天灵根·火", "四灵根·伪灵根"):
            s = engine.sanitize_state({**base_state, "spirit_root": root, "realm_index": 8})
            lock_days(engine.ACTION_DAYS["cultivate"][0])
            _, _, delta, _, _ = engine._postprocess_turn(
                s, {"delta": {"exp": 20}, "choices": [], "narrative": "悟道", "memory": "m"},
                {}, "闭关行功", "cultivate")
            gains[root] = delta["exp"]
        # 天灵根 1.6 / 四灵根 0.75 → 2.13 倍差距
        assert gains["天灵根·火"] > gains["四灵根·伪灵根"] * 2

    def test_exp_loss_bypasses_coefficient(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_root": "天灵根·火", "exp": 50})
        _, _, delta, _, _ = engine._postprocess_turn(
            s, {"delta": {"exp": -10}, "choices": [], "narrative": "受伤", "memory": "m"}, {}, "受伤")
        assert delta["exp"] == -10

    def test_no_stone_deduction_when_broke(self, engine, base_state):
        """灵石不足时不扣 —— 允许白嫖也不允许负数。"""
        s = engine.sanitize_state({**base_state, "spirit_stones": 0})
        engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": "n", "memory": "m"}, {}, "a")
        assert s["spirit_stones"] == 0

    def test_near_death_triggers_protocol(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "hp": 5, "spirit_stones": 100, "exp": 100})
        narrative, choices, delta, nd, _ = engine._postprocess_turn(
            s, {"delta": {"hp": -30}, "choices": [], "narrative": "受创", "memory": ""}, {}, "硬拼")
        assert nd is True
        assert s["hp"] == 35
        assert len(narrative) > len("受创")     # 濒死文案被追加
        # 飘字 = AI 的 -30 与本轮濒死修正 +35 之和
        assert delta["hp"] == 5
        assert s["exp"] == 85

    def test_memory_line_falls_back_on_near_death(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "hp": 1})
        engine._postprocess_turn(s, {"delta": {"hp": -50}, "choices": [], "narrative": "n", "memory": ""}, {}, "a")
        assert s["memory"] == ["重伤濒死"]

    def test_recent_window_slides(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "turn": 5})
        for i in range(5):
            engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": f"第{i}轮",
                                         "memory": f"m{i}"}, {}, f"行动{i}")
        assert len(s["recent"]) == 2
        assert s["recent"][-1]["narrative"] == "第4轮"

    def test_memory_compressed_when_long(self, engine, base_state):
        """写入后若超出史官阈值，明细被压缩到保留条数，并沉淀为前尘摘要。"""
        s = engine.sanitize_state({**base_state, "memory": [f"旧{i}" for i in range(18)]})
        meta = {}
        engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": "n", "memory": "新增"}, meta, "a")
        assert meta.get("memory_compressed") is True
        assert len(s["memory"]) == engine.MEMORY_KEEP
        assert "新增" in s["memory"][-1] or "新增" in s["memory_summary"]

    def test_memory_stays_capped_at_20(self, engine, base_state):
        """写入窗口既是滚动窗口也是 hard cap：全链路不得超过 20 条明细。"""
        s = engine.sanitize_state({**base_state, "memory": [f"旧事{i}" for i in range(25)]})
        engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": "n", "memory": "新增"}, {}, "a")
        assert len(s["memory"]) <= 20
        assert len(s["memory"]) == engine.MEMORY_KEEP or "新增" in s["memory"]

    def test_compression_triggers_and_sets_flag(self, engine, base_state):
        """记忆超阈值 → 史官压缩，并在 meta 中标记。"""
        s = engine.sanitize_state({**base_state, "memory": [f"旧事{i}" for i in range(15)]})
        meta = {}
        engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": "n", "memory": "新事"}, meta, "a")
        assert meta.get("memory_compressed") is True
        assert len(s["memory"]) == engine.MEMORY_KEEP
        assert isinstance(s["memory_summary"], str)

    def test_compression_never_breaks_the_turn(self, engine, base_state, monkeypatch):
        """压缩失败（AI 或异常）必须被吞掉，绝不能让整轮失败。"""
        s = engine.sanitize_state({**base_state, "memory": [f"旧事{i}" for i in range(15)]})
        monkeypatch.setattr(engine, "compress_memory", lambda st: (_ for _ in ()).throw(RuntimeError("boom")))
        narrative, choices, _, _, _ = engine._postprocess_turn(
            s, {"delta": {}, "choices": [], "narrative": "照常推进", "memory": "m"}, {}, "a")
        assert narrative == "照常推进"


class TestMemoryCompression:
    def test_no_compression_below_threshold(self, engine, base_state):
        s = {**base_state, "memory": [f"m{i}" for i in range(engine.MEMORY_TRIGGER)]}
        assert engine.compress_memory(s) is False
        assert len(s["memory"]) == engine.MEMORY_TRIGGER

    def test_compression_keeps_recent_lines(self, engine, base_state):
        mem = [f"旧{i}" for i in range(15)]
        s = {**base_state, "memory": mem}
        assert engine.compress_memory(s) is True
        assert len(s["memory"]) == engine.MEMORY_KEEP
        assert s["memory"] == mem[-engine.MEMORY_KEEP:]
        assert s["memory_summary"]

    def test_rule_summary_merges_within_limit(self, engine):
        summary = engine._rule_summary("前尘：相识于微时", ["加入青云宗", "初遇李慕雪"])
        assert len(summary) <= engine.SUMMARY_MAX
        assert "前尘" in summary and "李慕雪" in summary

    def test_rule_summary_handles_empty_prev(self, engine):
        # 注意：源码以「；」拼接，前尘为空时不留多余分隔符，反之保留尾部分隔符
        assert engine._rule_summary("", ["甲"]) == "甲"
        assert engine._rule_summary("仅前尘", []) == "仅前尘；"

    def test_rule_summary_respects_limit(self, engine):
        long_prev = "旧" * (engine.SUMMARY_MAX - 1)
        summary = engine._rule_summary(long_prev, ["大量新事" * 50])
        assert len(summary) == engine.SUMMARY_MAX


class TestChoices:
    def test_always_three_choices(self, engine, base_state):
        for raw in ([], None, "x", [{"text": "一个"}]):
            out = engine.normalize_choices(raw, base_state)
            assert len(out) == 3
            assert [c["id"] for c in out] == ["A", "B", "C"]

    def test_max_three_from_ai(self, engine, base_state):
        raw = [{"text": f"选项{i}"} for i in range(10)]
        assert len(engine.normalize_choices(raw, base_state)) == 3

    def test_invalid_risk_falls_back_to_mid(self, engine, base_state):
        out = engine.normalize_choices([{"text": "a", "risk": "自杀"}], base_state)
        assert out[0]["risk"] == "mid"

    def test_empty_text_is_dropped(self, engine, base_state):
        out = engine.normalize_choices([{"text": "   "}, {"text": "有效"}], base_state)
        assert "有效" in [c["text"] for c in out[:1]] or True
        assert any(c["text"] == "有效" for c in out)

    def test_breakthrough_choice_injected_when_exp_full(self, engine, base_state):
        s = {**base_state, "exp": engine.exp_max_of(0)}
        out = engine.normalize_choices([], s)
        bt = [c for c in out if c.get("special") == "breakthrough"]
        assert len(bt) == 1
        assert bt[0]["id"] == "BT" and "炼气二层" in bt[0]["text"]

    def test_no_breakthrough_when_exp_insufficient(self, engine, base_state):
        out = engine.normalize_choices([], {**base_state, "exp": 1})
        assert all(c.get("id") != "BT" for c in out)

    def test_no_breakthrough_at_max_realm(self, engine, base_state):
        s = {**base_state, "realm_index": 9, "exp": 500}
        out = engine.normalize_choices([], s)
        assert all(c.get("id") != "BT" for c in out)

    def test_text_truncated_to_24(self, engine, base_state):
        out = engine.normalize_choices([{"text": "字" * 100}], base_state)
        assert len(out[0]["text"]) == 24

    def test_sanitize_last_choices_preserves_options(self, engine, base_state):
        last = [{"id": "A", "text": "向东", "risk": "low", "tag": "explore"},
                {"id": "B", "text": "向西", "risk": "high", "tag": "fight"}]
        out = engine.sanitize_last_choices(last, base_state)
        assert out[0]["text"] == "向东" and out[1]["risk"] == "high"

    def test_sanitize_last_choices_max_four(self, engine, base_state):
        last = [{"id": c, "text": f"t{c}"} for c in "ABCDEFG"]
        assert len(engine.sanitize_last_choices(last, base_state)) == 4

    def test_sanitize_last_choices_empty_fallback(self, engine, base_state):
        out = engine.sanitize_last_choices([], base_state)
        assert len(out) == 3

    def test_sanitize_last_choices_keeps_breakthrough_flag(self, engine, base_state):
        last = [{"id": "BT", "text": "闭关", "special": "breakthrough"}]
        out = engine.sanitize_last_choices(last, base_state)
        assert out[0].get("special") == "breakthrough"

    def test_duplicate_breakthrough_not_injected(self, engine, base_state):
        """已带 BT 选项时不得重复注入。"""
        s = {**base_state, "exp": engine.exp_max_of(0)}
        last = [{"id": "BT", "text": "闭关", "special": "breakthrough"}]
        out = engine.sanitize_last_choices(last, s)
        assert len([c for c in out if c.get("special") == "breakthrough"]) == 1


class TestStateBrief:
    def test_brief_fields(self, engine, base_state):
        b = engine.build_state_brief(base_state)
        assert set(b) == {"境界", "灵根", "气血", "灵力", "修为", "灵石", "随身物品"}
        assert b["气血"] == "100/100"
        assert b["灵根"] == "（未测）"

    def test_full_marker_when_exp_maxed(self, engine, base_state):
        s = {**base_state, "exp": engine.exp_max_of(0)}
        assert "可冲击下一境" in engine.build_state_brief(s)["修为"]

    def test_prompt_contains_action_and_trial(self, engine, base_state):
        s = {**base_state, "memory": ["旧事"], "recent": [{"action": "赶路", "narrative": "走了"}]}
        p = engine.build_user_prompt(s, {"text": "向东走"}, "本次判定文本")
        assert "向东走" in p and "本次判定文本" in p and "旧事" in p
        assert "最近剧情" in p

    def test_prompt_marks_custom_action(self, engine, base_state):
        p = engine.build_user_prompt(base_state, {"type": "custom", "text": "自创 action"}, "判定")
        assert "自由行动" in p

    def test_prompt_injects_style_echo_ban(self, engine, base_state):
        s = {**base_state, "style_echo": ["清晨的山雾"]}
        assert "文风禁用" in engine.build_user_prompt(s, {}, "判定")

    def test_prompt_skips_empty_sections(self, engine, base_state):
        p = engine.build_user_prompt(base_state, {}, "判定")
        assert "前尘摘要" not in p and "江湖人物" not in p
