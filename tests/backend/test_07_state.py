# -*- coding: utf-8 -*-
"""状态清洗：白名单收拢、越界钳制、脏数据兜底、恶意注入防护。

后端无状态 —— 前端每轮回传全量 state，而 state 可被任意篡改。
sanitize_state 是唯一的安全边界，必须有对抗性测试。
"""
import pytest


class TestWhitelist:
    def test_unknown_fields_are_dropped(self, engine, base_state):
        dirty = {**base_state, "admin": True, "god_mode": 1, "realm": 99, "__proto__": {}, "hp_max_cheat": 9999}
        s = engine.sanitize_state(dirty)
        for bad in ("admin", "god_mode", "realm", "__proto__", "hp_max_cheat"):
            assert bad not in s

    def test_required_fields_always_exist(self, engine):
        """空输入也必须产出结构完整的合法状态。"""
        s = engine.sanitize_state({})
        required = ["realm_index", "hp", "hp_max", "qi", "qi_max", "exp", "spirit_stones",
                    "spirit_root", "items", "memory", "memory_summary", "recent",
                    "reincarnations", "npcs", "style_echo", "pending_events",
                    "fail_streak", "last_near_death_turn", "turn"]
        for k in required:
            assert k in s, f"缺少必需字段: {k}"
        assert s["hp"] > 0 and s["qi"] > 0 and s["turn"] == 0

    def test_non_dict_input_is_safe(self, engine):
        for bad in (None, [], "state", 123, True):
            s = engine.sanitize_state(bad)
            assert isinstance(s, dict) and s["realm_index"] == 0


class TestNumericClamping:
    @pytest.mark.parametrize("realm", [-5, 0, 3, 9, 50, "8"])
    def test_realm_index_clamped(self, engine, base_state, realm):
        s = engine.sanitize_state({**base_state, "realm_index": realm})
        assert 0 <= s["realm_index"] <= engine.MAX_REALM_INDEX

    def test_hp_never_exceeds_max(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "hp": 99999})
        assert s["hp"] == s["hp_max"]

    def test_hp_never_negative(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "hp": -500})
        assert s["hp"] == 0

    def test_exp_respects_realm_cap(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "exp": 99999})
        assert s["exp"] == engine.exp_max_of(0)

    def test_stones_bounds(self, engine, base_state):
        assert engine.sanitize_state({**base_state, "spirit_stones": -100})["spirit_stones"] == 0
        assert engine.sanitize_state({**base_state, "spirit_stones": 10**9})["spirit_stones"] == 99999

    def test_hp_max_bounds(self, engine, base_state):
        assert engine.sanitize_state({**base_state, "hp_max": 10**6})["hp_max"] == 400
        assert engine.sanitize_state({**base_state, "hp_max": 1})["hp_max"] == 100
        assert engine.sanitize_state({**base_state, "qi_max": 10**6})["qi_max"] == 250

    def test_fail_streak_bounds(self, engine, base_state):
        assert engine.sanitize_state({**base_state, "fail_streak": 999})["fail_streak"] == 20
        assert engine.sanitize_state({**base_state, "fail_streak": -9})["fail_streak"] == 0

    def test_string_numbers_are_coerced(self, engine, base_state):
        """前端可能送出字符串数字，必须安全转换而非崩溃。"""
        s = engine.sanitize_state({**base_state, "hp": "50", "spirit_stones": "42"})
        assert s["hp"] == 50 and s["spirit_stones"] == 42

    def test_garbage_numbers_fall_back(self, engine, base_state):
        for bad in ("abc", None, {}, [], float("nan") if False else "1e999"):
            s = engine.sanitize_state({**base_state, "hp": bad, "spirit_stones": bad})
            assert 0 <= s["hp"] <= s["hp_max"]
            assert 0 <= s["spirit_stones"] <= 99999

    def test_bool_is_not_counted_as_int(self, engine, base_state):
        """True 不应被当成 1 加成。"""
        s = engine.sanitize_state({**base_state, "hp": True})
        assert s["hp"] == s["hp_max"]

    def test_default_max_values_match_curve(self, engine):
        """不传上限时，按境界自动推算，而不是写死 100/50。"""
        for lv in range(10):
            s = engine.sanitize_state({"realm_index": lv})
            assert s["hp_max"] == engine.hp_max_of(lv)
            assert s["qi_max"] == engine.qi_max_of(lv)


class TestCollectionCleaning:
    def test_items_are_limited_and_normalized(self, engine, base_state):
        many = [{"name": f"物{i}", "qty": 1, "rarity": "下品"} for i in range(50)]
        s = engine.sanitize_state({**base_state, "items": many})
        assert len(s["items"]) == 20

    def test_item_name_truncated(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "items": [{"name": "超长名称" * 10, "qty": 1}]})
        assert len(s["items"][0]["name"]) <= 12

    def test_item_rarity_normalized(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "items": [{"name": "丹", "rarity": "神品"}]})
        assert s["items"][0]["rarity"] == "下品"

    def test_invalid_items_dropped(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "items": ["不是字典", {}, {"qty": 1}, {"name": "  "}]})
        assert s["items"] == []

    def test_item_qty_bounds(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "items": [{"name": "丹", "qty": 0}, {"name": "丹2", "qty": 999}]})
        assert s["items"][0]["qty"] == 1 and s["items"][1]["qty"] == 99

    def test_memory_truncated_and_capped(self, engine, base_state):
        mem = ["记" * 100 for _ in range(50)]
        s = engine.sanitize_state({**base_state, "memory": mem})
        assert len(s["memory"]) == 20
        assert all(len(m) <= 60 for m in s["memory"])

    def test_memory_summary_capped(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "memory_summary": "摘要" * 500})
        assert len(s["memory_summary"]) <= engine.SUMMARY_MAX

    def test_recent_keeps_only_two(self, engine, base_state):
        recent = [{"action": "a", "narrative": "n"} for _ in range(10)]
        s = engine.sanitize_state({**base_state, "recent": recent})
        assert len(s["recent"]) == 2

    def test_reincarnations_capped(self, engine, base_state):
        re = [{"realm": "筑基初期", "turn": 10, "memory": ["a"]} for _ in range(20)]
        s = engine.sanitize_state({**base_state, "reincarnations": re})
        assert len(s["reincarnations"]) == 5

    def test_npcs_normalized(self, engine, base_state):
        npcs = [{"name": "青云子", "title": "道长", "bond": 999},
                {"name": "", "bond": 1},
                {"name": "铁牛", "bond": -999, "fired": {"gift": 1, "作弊": 2}}]
        s = engine.sanitize_state({**base_state, "npcs": npcs})
        assert len(s["npcs"]) == 2
        assert s["npcs"][0]["bond"] == 100
        assert s["npcs"][0]["title"] == "道长"
        assert s["npcs"][1]["bond"] == -100
        assert s["npcs"][1]["fired"] == {"gift": 1}  # 非法 fired key 被剔除
        assert s["npcs"][1]["title"] == "江湖人"     # 缺省头衔

    def test_pending_events_validated(self, engine, base_state):
        events = [{"type": "gift", "npc": "青云子", "at": 1},
                  {"type": "hack", "npc": "反贼", "at": 1},
                  {"type": "gift", "npc": "", "at": 1},
                  {"type": "gift", "npc": "甲"}, {"type": "gift", "npc": "乙"}, {"type": "gift", "npc": "丙"},
                  {"type": "gift", "npc": "丁"}]
        s = engine.sanitize_state({**base_state, "pending_events": events})
        types = {e["type"] for e in s["pending_events"]}
        assert types == {"gift"}
        assert all(e["npc"] for e in s["pending_events"])
        assert len(s["pending_events"]) <= 3

    def test_style_echo_capped(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "style_echo": ["开篇" * 20 for _ in range(30)]})
        assert len(s["style_echo"]) == 8
        assert all(len(h) <= 16 for h in s["style_echo"])

    def test_spirit_root_truncated(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "spirit_root": "天灵根·火" * 5})
        assert s["spirit_root"] == ""   # 超长即非法 → 置空待重掷


class TestIdempotency:
    def test_sanitize_is_stable(self, engine, base_state):
        once = engine.sanitize_state(base_state)
        twice = engine.sanitize_state(once)
        assert once == twice, "清洗函数不收敛（幂等失效）"

    def test_sanitize_always_yields_defaults(self, engine):
        s = engine.sanitize_state({})
        assert s["spirit_stones"] == 30       # 开局 30 灵石
        assert s["last_near_death_turn"] == -999
        assert s["items"] == [] and s["npcs"] == []
