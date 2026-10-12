# -*- coding: utf-8 -*-
"""v3.13 地理 + NPC 主动操作 + 结契 的契约测试。

覆盖三块：
  M1 地理：地点白名单、location sanitize、AI 申报移动（location_update）
  N2 /api/npc：赠礼 / 论道 / 打听 / 切磋，含防刷阀门（门槛、冷却、耗时）
  N3 结契：bond≥90 才能结、每种契同最多一人、三处 buff 挂载
"""
from __future__ import annotations

import pytest

from server import (
    LOCATIONS, DEFAULT_LOCATION,
    location_key_of, apply_location_update,
    pact_of, NPC_PACT_BOND, PACT_TYPES,
)


# ---------------------------------------------------------------- M1 地理


class TestLocationWhitelist:
    def test_default_location_applied(self, engine):
        s = engine.sanitize_state({})
        assert s["location"] == DEFAULT_LOCATION

    def test_unknown_location_clamped_to_default(self, engine):
        s = engine.sanitize_state({"location": "不存在的仙岛"})
        assert s["location"] == DEFAULT_LOCATION

    def test_valid_location_preserved(self, engine):
        s = engine.sanitize_state({"location": "wangxian_cheng"})
        assert s["location"] == "wangxian_cheng"

    def test_location_key_strips_verbs(self):
        assert location_key_of("望仙城") == "wangxian_cheng"
        assert location_key_of("去望仙城") == "wangxian_cheng"
        assert location_key_of(" 往 青牛镇 ") == "qingniu_zhen"

    def test_location_key_rejects_unknown(self):
        assert location_key_of("蓬莱仙山") is None
        assert location_key_of("") is None

    def test_apply_move_updates_state(self, engine):
        s = engine.sanitize_state({})
        moved = apply_location_update(s, {"location_update": {"to": "乌山镇"}})
        assert moved == "乌山镇"
        assert s["location"] == "wushan_zhen"

    def test_apply_move_same_place_is_noop(self, engine):
        s = engine.sanitize_state({})
        moved = apply_location_update(s, {"location_update": {"to": "青牛山"}})
        assert moved is None
        assert s["location"] == DEFAULT_LOCATION

    def test_apply_move_fabricated_place_dropped(self, engine):
        s = engine.sanitize_state({})
        moved = apply_location_update(s, {"location_update": {"to": "海外仙山"}})
        assert moved is None
        assert s["location"] == DEFAULT_LOCATION

    def test_whitelist_has_expected_keys(self):
        assert set(LOCATIONS) == {
            "qingniu_shan", "qingniu_zhen", "qingfeng_du", "wushan_zhen",
            "yueling", "heifeng_zhai", "beihuang_ze", "wangxian_cheng",
        }


# ---------------------------------------------------------------- N2 /api/npc


def _npc_state(engine, name="苏禾", bond=40, turn=10, stones=100):
    s = engine.sanitize_state({
        "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
        "exp": 0, "spirit_stones": stones, "spirit_root": "",
        "items": [{"name": "凝气丹", "qty": 1, "rarity": "中品"}],
        "memory": [], "recent": [], "style_echo": [], "memory_summary": "",
        "pending_events": [], "fail_streak": 0, "last_near_death_turn": -999,
        "turn": turn, "npcs": [{"name": name, "title": "采药人", "bond": bond, "met_turn": 5}],
    })
    return s


def _call_npc(client, s, action):
    return client.post("/api/npc", json={"state": s, "action": action})


class TestNpcOp:
    def test_unknown_npc_rejected(self, client, engine):
        s = _npc_state(engine)
        r = _call_npc(client, s, {"type": "npc_gift", "name": "不存在", "stones": 30})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "NPC_UNKNOWN"

    def test_unknown_op_rejected(self, client, engine):
        s = _npc_state(engine)
        r = _call_npc(client, s, {"type": "npc_teleport", "name": "苏禾"})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "UNKNOWN_OP"

    def test_gift_stones_raises_bond_and_costs(self, client, engine):
        s = _npc_state(engine, bond=0)
        r = _call_npc(client, s, {"type": "npc_gift", "name": "苏禾", "stones": 30})
        d = r.json()
        assert d["ok"] is True
        assert d["npc_event"]["delta"] > 0
        assert d["delta_applied"]["spirit_stones"] == -30
        assert d["state"]["spirit_stones"] == 70
        # 耗时落账
        assert d["npc_op"]["days"] > 0

    def test_gift_stones_insufficient(self, client, engine):
        s = _npc_state(engine, stones=5)
        r = _call_npc(client, s, {"type": "npc_gift", "name": "苏禾", "stones": 30})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "NOT_ENOUGH_STONES"

    def test_gift_item_deducts_and_raises(self, client, engine):
        s = _npc_state(engine, bond=0)
        r = _call_npc(client, s, {"type": "npc_gift", "name": "苏禾", "item": "凝气丹"})
        d = r.json()
        assert d["ok"] is True
        assert d["delta_applied"]["items_remove"][0]["name"] == "凝气丹"
        assert d["npc_event"]["delta"] > 0

    def test_gift_rejected_when_hostile(self, client, engine):
        s = _npc_state(engine, bond=-60)
        r = _call_npc(client, s, {"type": "npc_gift", "name": "苏禾", "stones": 30})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "GIFT_REJECTED"

    def test_gift_diminishing_returns(self, client, engine):
        # 道缘越高，同样一份礼折的点数越少（边际递减）
        s_low = _npc_state(engine, bond=0)
        d_low = _call_npc(client, s_low, {"type": "npc_gift", "name": "苏禾", "stones": 30}).json()
        s_high = _npc_state(engine, bond=85)
        d_high = _call_npc(client, s_high, {"type": "npc_gift", "name": "苏禾", "stones": 30}).json()
        assert d_low["npc_event"]["delta"] > d_high["npc_event"]["delta"]

    def test_talk_requires_bond_and_grants_exp(self, client, engine):
        s = _npc_state(engine, bond=40)
        r = _call_npc(client, s, {"type": "npc_talk", "name": "苏禾"})
        d = r.json()
        assert d["ok"] is True
        assert d["delta_applied"]["exp"] > 0

    def test_talk_locked_when_bond_low(self, client, engine):
        s = _npc_state(engine, bond=10)
        r = _call_npc(client, s, {"type": "npc_talk", "name": "苏禾"})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "BOND_TOO_LOW"

    def test_ask_requires_bond(self, client, engine):
        s = _npc_state(engine, bond=10)
        r = _call_npc(client, s, {"type": "npc_ask", "name": "苏禾"})
        assert r.json()["ok"] is False

    def test_spar_grants_or_costs_and_bonds(self, client, engine):
        s = _npc_state(engine, bond=30)
        r = _call_npc(client, s, {"type": "npc_spar", "name": "苏禾"})
        d = r.json()
        assert d["ok"] is True
        assert d["delta_applied"]["hp"] < 0  # 切磋必伤血
        assert d["npc_event"]["delta"] != 0  # 道缘必有变化（胜 + 负 -）

    def test_cooldown_blocks_repeat(self, client, engine):
        s = _npc_state(engine, bond=40)
        r1 = _call_npc(client, s, {"type": "npc_talk", "name": "苏禾"})
        assert r1.json()["ok"] is True
        # 同一状态再谈一次：冷却生效
        s2 = r1.json()["state"]
        r2 = _call_npc(client, s2, {"type": "npc_talk", "name": "苏禾"})
        assert r2.json()["ok"] is False
        assert r2.json()["error"]["code"] == "NPC_COOLDOWN"

    def test_op_advances_days_and_age(self, client, engine):
        s = _npc_state(engine, bond=40, turn=10)
        before_days = s["days"]
        r = _call_npc(client, s, {"type": "npc_talk", "name": "苏禾"})
        assert r.json()["state"]["days"] > before_days

    def test_dead_player_blocked(self, client, engine):
        s = _npc_state(engine)
        s["dead"] = True
        r = _call_npc(client, s, {"type": "npc_talk", "name": "苏禾"})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "PLAYER_DEAD"


# ---------------------------------------------------------------- N3 结契


class TestPact:
    def test_pact_requires_deep_bond(self, client, engine):
        s = _npc_state(engine, bond=89)
        r = _call_npc(client, s, {"type": "npc_pact", "name": "苏禾", "pact": "sworn"})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "BOND_TOO_LOW"

    def test_pact_succeeds_at_threshold(self, client, engine):
        s = _npc_state(engine, bond=NPC_PACT_BOND)
        r = _call_npc(client, s, {"type": "npc_pact", "name": "苏禾", "pact": "master"})
        d = r.json()
        assert d["ok"] is True
        assert d["state"]["npcs"][0]["pact"]["type"] == "master"

    def test_bad_pact_type_rejected(self, client, engine):
        s = _npc_state(engine, bond=95)
        r = _call_npc(client, s, {"type": "npc_pact", "name": "苏禾", "pact": "亲家"})
        assert r.json()["ok"] is False
        assert r.json()["error"]["code"] == "BAD_PACT_TYPE"

    def test_one_pact_per_npc(self, client, engine):
        s = _npc_state(engine, bond=95)
        r1 = _call_npc(client, s, {"type": "npc_pact", "name": "苏禾", "pact": "sworn"})
        assert r1.json()["ok"] is True
        s2 = r1.json()["state"]
        r2 = _call_npc(client, s2, {"type": "npc_pact", "name": "苏禾", "pact": "master"})
        assert r2.json()["ok"] is False
        assert r2.json()["error"]["code"] == "ALREADY_SWORN"

    def test_one_holder_per_pact_type(self, client, engine):
        s = _npc_state(engine, bond=95)
        s["npcs"].append({"name": "阿菱", "title": "女修", "bond": 95, "met_turn": 6})
        r1 = _call_npc(client, s, {"type": "npc_pact", "name": "苏禾", "pact": "sworn"})
        assert r1.json()["ok"] is True
        s2 = r1.json()["state"]
        r2 = _call_npc(client, s2, {"type": "npc_pact", "name": "阿菱", "pact": "sworn"})
        assert r2.json()["ok"] is False
        assert r2.json()["error"]["code"] == "PACT_SLOT_TAKEN"

    def test_pact_of_finds_holder(self, engine):
        s = engine.sanitize_state({
            "npcs": [{"name": "苏禾", "title": "采药人", "bond": 95,
                      "pact": {"type": "master", "turn": 10}}],
        })
        assert pact_of(s, "master")["name"] == "苏禾"
        assert pact_of(s, "sworn") is None

    def test_pact_types_well_formed(self):
        assert set(PACT_TYPES) == {"sworn", "master", "companion"}
        for spec in PACT_TYPES.values():
            assert "label" in spec and "ritual" in spec

    def test_sanitize_drops_bad_pact(self, engine):
        s = engine.sanitize_state({
            "npcs": [{"name": "苏禾", "title": "采药人", "bond": 95,
                      "pact": {"type": "结义兄弟", "turn": 10}}],
        })
        assert s["npcs"][0]["pact"] == {}

    def test_sanitize_keeps_op_cd(self, engine):
        s = engine.sanitize_state({
            "npcs": [{"name": "苏禾", "title": "采药人", "bond": 95,
                      "op_cd": {"gift": 12, "talk": 8, "bogus": 99}}],
        })
        cd = s["npcs"][0]["op_cd"]
        assert cd.get("gift") == 12
        assert cd.get("talk") == 8
        assert "bogus" not in cd  # 白名单外的键被丢弃
