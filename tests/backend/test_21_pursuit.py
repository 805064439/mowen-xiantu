# -*- coding: utf-8 -*-
"""test_21_pursuit.py —— 追索收束（v3.8）

日志实证：2026-09-23 那份 46 轮日志里，玩家连点 6 轮「追查溪畔女子」也没有结果。
查下来是两个独立缺陷：

① 接管豁免条件写成了 `not thread_res["closed"]`——只要 AI 这轮了结了**任意一条线**，
   天道就罢手。而【追索已滞】的提示词恰好教 AI「断干净也行，close 掉它」，
   AI 每轮用一次豁免权，接管从 v3.6 上线起一次都没真正触发过（线上 5 连击实测，
   level 已到 5，takeover 恒为 None）。

② AI 的拖延手法是「这条线断了，往下一处问」——每站都给确凿情报，每张车票都指向
   下一站。而 stall 数的是「玩家是不是还在说同一句话」，选项文字每站都被改写，
   指纹因此重置，计数永不起跳。

本次锁定：
  · pursuit_resolved —— 只有了结的正是当前追索才算数
  · update_hop      —— 换乘（close 且 open）计数
  · 接管条件        —— 轮数或换乘任一达标即收场，且收场必须给下落而非「作罢」
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------- pursuit_resolved

class TestPursuitResolved:
    def test_empty_closed_never_resolved(self, engine, base_state):
        """什么都没了结 → 当然不算有了交代。"""
        engine.update_stall(base_state, "追查溪畔女子")
        assert engine.pursuit_resolved(base_state, [], "追查溪畔女子") is False

    def test_closed_that_very_thing(self, engine, base_state):
        """了结的正是玩家在追的这条 → 算数。"""
        engine.update_stall(base_state, "追查溪畔女子")
        assert engine.pursuit_resolved(base_state, ["追查溪畔女子"], "追查溪畔女子") is True

    def test_closed_something_else_not_counted(self, engine, base_state):
        """【核心】了结别的线 ≠ 这件事有了交代。

        v3.6 的漏洞就在这里：AI 每轮 close 一条无关的线就能换来豁免，
        于是「结果」永远不必兑现。
        """
        engine.update_stall(base_state, "追查溪畔女子")
        assert engine.pursuit_resolved(base_state, ["梧州白芨"], "追查溪畔女子") is False

    def test_closed_matches_action_text(self, engine, base_state):
        """指纹也能从玩家本轮的原话比对得到（AI 的台账标题常与玩家用词不同）。"""
        s = base_state
        engine.update_stall(s, "追查溪畔女子")
        assert engine.pursuit_resolved(s, ["溪畔女子下落"], "追查溪畔女子") is True

    def test_multiple_closed_one_hits(self, engine, base_state):
        """一批线里只要有一条是这件事，就算了结了。"""
        engine.update_stall(base_state, "追查溪畔女子")
        hit = engine.pursuit_resolved(base_state, ["梧州白芨", "溪畔女子"], "追查溪畔女子")
        assert hit is True

    def test_short_candidates_skipped(self, engine, base_state):
        """过短的指纹不参与比对（单字会把八竿子打不着的东西认亲）。"""
        base_state["stall"] = {"key": "", "count": 3, "label": ""}
        assert engine.pursuit_resolved(base_state, ["线"], "") is False


# ---------------------------------------------------------------- 换乘计数

class TestUpdateHop:
    def test_close_and_open_is_a_hop(self, engine, base_state):
        """了结一条又新开一条 = 目标被搬去了下一站。"""
        n = engine.update_hop(base_state, "explore", {"closed": ["甲处"], "opened": ["乙处"]})
        assert n == 1
        assert base_state["hop"] == 1

    def test_close_only_clears(self, engine, base_state):
        """只了结没开新线 = 真的结束了，清零。"""
        base_state["hop"] = 3
        n = engine.update_hop(base_state, "explore", {"closed": ["甲处"], "opened": []})
        assert n == 0
        assert base_state["hop"] == 0

    def test_open_only_keeps(self, engine, base_state):
        """只开不了结，属于正常推进，不记换乘。"""
        base_state["hop"] = 2
        n = engine.update_hop(base_state, "explore", {"closed": [], "opened": ["乙处"]})
        assert n == 2

    def test_calm_action_not_counted(self, engine, base_state):
        """打坐、做买卖不是追索，不该攒换乘。"""
        base_state["hop"] = 1
        n = engine.update_hop(base_state, "cultivate", {"closed": ["甲"], "opened": ["乙"]})
        assert n == 1

    def test_accumulates(self, engine, base_state):
        for i in range(3):
            engine.update_hop(base_state, "explore", {"closed": [f"甲{i}"], "opened": [f"乙{i}"]})
        assert base_state["hop"] == 3


# ---------------------------------------------------------------- 下落提取

class TestLastClueLine:
    def test_extracts_from_chronicle(self, engine, base_state):
        base_state["chronicle"] = ["第2轮 · 芦溪集寻人：人已不在集上，另有去处"]
        assert engine.last_clue_line(base_state) == "人已不在集上，另有去处"

    def test_empty_chronicle(self, engine, base_state):
        assert engine.last_clue_line(base_state) == ""

    def test_no_separator(self, engine, base_state):
        base_state["chronicle"] = ["第3轮 · 没有冒号的记录"]
        assert engine.last_clue_line(base_state) == ""


# ---------------------------------------------------------------- 接管

def _turn(engine, s, action="追查溪畔女子", tag="explore", thread_updates=None,
          chronicle_preset=None):
    """跑一轮 _postprocess_turn；thread_updates 模拟 AI 的申报。"""
    if chronicle_preset is not None:
        s["chronicle"] = list(chronicle_preset)
    data = {
        "narrative": "追查了一程，仍未见人。",
        "memory": "寻人不遇",
        "delta": {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                  "items_add": [], "items_remove": []},
        "choices": [{"id": "A", "text": "再追一程", "risk": "mid", "tag": "explore"},
                    {"id": "B", "text": "就地调息", "risk": "low", "tag": "cultivate", "span": "short"},
                    {"id": "C", "text": "追查溪畔女子", "risk": "mid", "tag": "explore"}],
    }
    if thread_updates:
        data["thread_updates"] = thread_updates
    meta = {}
    engine.update_stall(s, action)
    engine._postprocess_turn(s, data, meta, action, tag, tier="mid")
    return meta


def _thread(title, note="", tid=1, cat="疑窦"):
    return {"id": tid, "title": title, "cat": cat, "open": 0, "last": 0, "due": 9, "note": note}


class TestTakeover:
    def test_unrelated_close_no_longer_grants_immunity(self, engine, base_state):
        """【本次的核心修复】AI 了结别的线，不再能挡住天道收场。

        在册里放了两条：正在追的「溪畔女子」，以及顺手牵来的「梧州白芨」。
        AI 本轮把白芨了结了——v3.6 会因此认定「已有交代」而罢手，
        于是「追查溪畔女子」这件事可以继续无限期悬着。
        """
        s = base_state
        s["threads"] = [_thread("溪畔女子", "追查中", 1), _thread("梧州白芨", "顺手牵的", 2)]
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(s, "追查溪畔女子")
        assert engine.stall_level(s) >= engine.STALL_TAKEOVER_TURNS, "计数要先到阈值"
        meta = _turn(engine, s, thread_updates=[{"op": "close", "title": "梧州白芨",
                                                 "note": "白芨赠旧笺，指路别处"}])
        assert meta["threads"]["closed"] == ["梧州白芨"], "这条无关线确实要被了结才算复现"
        assert meta["stall"]["takeover"] is True

    def test_closing_this_very_thread_avoids_takeover(self, engine, base_state):
        """反过来：了结的确实是这件事本身，天道就不必插手。"""
        s = base_state
        s["threads"] = [_thread("溪畔女子", "追查中", 1)]
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(s, "追查溪畔女子")
        meta = _turn(engine, s, thread_updates=[{"op": "close", "title": "溪畔女子",
                                                 "note": "已查明去向"}])
        assert meta["stall"]["takeover"] is False

    def test_hop_max_forces_takeover(self, engine, base_state):
        """换乘到第 3 站就收场，哪怕同一句话还没追够 5 轮。"""
        s = base_state
        s["hop"] = 3
        meta = _turn(engine, s, thread_updates=[{"op": "close", "title": "甲处", "note": "不在"},
                                                {"op": "open", "title": "乙处", "note": "线索"}])
        assert meta["stall"]["takeover"] is True

    def test_takeover_gives_whereabouts_not_giveup(self, engine, base_state):
        """收场要给下落，不是「算了别找了」——这是玩家追了这么多轮想听的东西。"""
        s = base_state
        clue = "柳氏已随沈姓船去了岳州港"
        s["threads"] = [_thread("追查柳氏", "追查中", 1), _thread("青芦镇陈姓渔户", clue, 2)]
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(s, "追查柳氏")
        meta = _turn(engine, s, action="追查柳氏",
                     thread_updates=[{"op": "close", "title": "青芦镇陈姓渔户", "note": clue}])
        assert meta["stall"]["takeover"] is True
        line = meta["stall_takeover"]["line"]
        assert clue in line, f"收场没给出下落：{line}"
        for word in ("作罢", "放下", "断绝"):
            assert word not in line, f"又写成劝退了：{line}"

    def test_takeover_fallback_without_clue(self, engine, base_state):
        """没有线索可摘时，退回兜底文案，不能崩也不能空白。"""
        s = base_state
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(s, "追查某人")
        meta = _turn(engine, s, action="追查某人",
                     thread_updates=[{"op": "open", "title": "某条新线", "note": "x"}])
        assert meta["stall"]["takeover"] is True
        assert meta["stall_takeover"]["line"]

    def test_takeover_resets_counter(self, engine, base_state):
        """收场后计数归零，下一轮不会连着再收一次。"""
        s = base_state
        s["threads"] = [_thread("溪畔女子", "追查中", 1), _thread("梧州白芨", "顺手牵的", 2)]
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(s, "追查溪畔女子")
        meta = _turn(engine, s, thread_updates=[{"op": "close", "title": "梧州白芨", "note": "x"}])
        assert meta["stall"]["takeover"] is True
        assert s["stall"]["count"] == 0
        assert s["dry"] == 0
        assert s["hop"] == 0


# ---------------------------------------------------------------- 端到端：每站都走空

class TestRelayScenario:
    def test_relay_stops_at_third_station(self, engine, base_state):
        """复现日志里的搬运术：甲处→乙处→丙处→丁处，每站都给一处新去处。

        改之前：stall 数的是「玩家是不是还在说同一句话」，而选项文字每站被 AI 改写
        （问白芨 → 问陈老六 → 问沈船家），指纹因此重置，计数永远停在 1~2。
        改之后：换乘记到 STALL_HOP_MAX 就收场。
        """
        s = base_state
        s["threads"] = [_thread("落脚0", "人在落脚0", 1)]
        took_line = None
        hops = []
        for i in range(4):
            meta = _turn(engine, s, action=f"寻访落脚{i}",
                         thread_updates=[
                             {"op": "close", "title": f"落脚{i}",
                              "note": f"人不在此，已往落脚{i + 1}"},
                             {"op": "open", "title": f"落脚{i + 1}",
                              "note": f"据称落脚{i + 1}可问到"}])
            hops.append(s.get("hop"))
            # 下一轮要能 close 命中，须先把新开的那条线补进在册（真实链路如此）
            if not meta["stall"]["takeover"] and not any(
                    t.get("title") == f"落脚{i + 1}" for t in (s.get("threads") or [])):
                s["threads"].append(_thread(f"落脚{i + 1}", f"落脚{i + 1}", 10 + i))
            if meta["stall"]["takeover"]:
                took_line = meta["stall_takeover"]["line"]
                break
        assert took_line is not None, f"连搬三站都没收场（hop 轨迹={hops}）"
        assert "落脚" in took_line, f"收场没提到最后的下落：{took_line}"
