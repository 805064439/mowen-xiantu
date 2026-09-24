# -*- coding: utf-8 -*-
"""目标级追索计数（v3.11）——追人追到第几轮，由台账说了算，不由选项措辞说了算。

67 轮日志（2026-09-24）实证：玩家从头追到尾都在找同一个人，但每一轮点的选项都是
AI 新起的地名：

    追查苏姓女子 → 追查苏姓女子 → 追查苏姓女子 → 往越岭深处寻访苏氏药户
    → 追查苏禾踪迹 → 往落雁坡问周姓药农苏禾之事 → 西行乌山镇寻苏禾
    → 入镇寻访，探苏禾音信

这些句子两两之间没有足够的连续二字重合，same_pursuit 全部判「不是同一件事」，
stall.count 每轮换一次地名就清零一次，从头到尾停在 1~2 —— 5 轮的收场闸门一次都没合上，
9 轮过去人还没找到。

台账不会跟着 AI 换地名：同一件事立起来之后就是同一条线。于是把计数挂到线上。
"""
from __future__ import annotations


def _lines(state, *titles):
    """往台账里预置几条线。"""
    ths = state.setdefault("threads", [])
    for i, t in enumerate(titles, start=1):
        ths.append({"id": i, "title": t, "cat": "人情", "open": 1, "last": 1,
                    "due": 30, "note": "越岭苏氏采药人，春上来取过药"})
    return ths


# ---------------------------------------------------------------- bump_chase：给被推进的线累加
class TestBumpChase:
    def test_declared_advance_raises_the_counter(self, engine, base_state):
        _lines(base_state, "苏禾")
        res = {"advanced": ["苏禾"], "opened": [], "closed": []}
        assert engine.bump_chase(base_state, res, "explore", "往落雁坡问周姓药农苏禾之事") == ["苏禾"]
        assert base_state["threads"][0]["chase"] == 1

    def test_two_rounds_make_two(self, engine, base_state):
        _lines(base_state, "苏禾")
        for _ in range(2):
            engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", "寻苏禾")
        assert base_state["threads"][0]["chase"] == 2

    def test_calm_action_does_not_count(self, engine, base_state):
        """打坐不追人——它就算动了台账也不该涨追索轮数。"""
        _lines(base_state, "苏禾")
        engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "cultivate", "就地打坐调息")
        assert base_state["threads"][0].get("chase", 0) == 0

    def test_unlisted_title_is_ignored(self, engine, base_state):
        _lines(base_state, "苏禾")
        engine.bump_chase(base_state, {"advanced": ["别的线"]}, "explore", "寻苏禾")
        assert base_state["threads"][0].get("chase", 0) == 0

    def test_opening_a_line_starts_the_count(self, engine, base_state):
        """AI 首轮只用 open 把线立起来：那一轮就得算，否则 5 轮的闸门会滑到第 7 轮。

        线上实测（2026-09-24）：正是这一轮没算进去，连着两轮计数停在 1。
        """
        _lines(base_state, "苏禾")
        engine.bump_chase(base_state, {"advanced": [], "opened": ["苏禾"]}, "explore", "寻苏禾")
        assert base_state["threads"][0]["chase"] == 1

    def test_free_text_pursuit_counts(self, engine, base_state):
        """玩家手打的「去寻阿菱」被判成 other，但字面是追索——照样算。"""
        _lines(base_state, "阿菱")
        engine.bump_chase(base_state, {"advanced": ["阿菱"]}, "other", "去寻阿菱")
        assert base_state["threads"][0]["chase"] == 1


# ---------------------------------------------------------------- top_chase_thread：归因到线
class TestTopChaseThread:
    def test_none_when_nothing_chased(self, engine, base_state):
        _lines(base_state, "苏禾")
        assert engine.top_chase_thread(base_state) is None

    def test_picks_the_most_chased(self, engine, base_state):
        _lines(base_state, "苏禾", "乌木牌")
        th = engine.top_chase_thread(base_state)
        engine.bump_chase(base_state, {"advanced": ["乌木牌"]}, "explore", "追查乌木牌")
        for _ in range(3):
            engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", "追查苏禾")
        assert engine.top_chase_thread(base_state)["title"] == "苏禾"


# ---------------------------------------------------------------- 更新/旧调试 Differential coverage
class TestStallCountsByThread:
    def test_changing_the_place_name_no_longer_resets(self, engine, base_state):
        """日志那一局：连换五个地名追同一个人，计数必须一路涨到收场阈值。"""
        _lines(base_state, "苏禾")
        engine.update_stall(base_state, "追查苏姓女子", "explore")
        engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", "追查苏姓女子")
        seen = []
        for text in ("往越岭深处寻访苏氏药户", "追查苏禾踪迹",
                     "往落雁坡问周姓药农苏禾之事", "西行乌山镇寻苏禾"):
            cur = engine.update_stall(base_state, text, "explore")
            seen.append(cur["count"])
            engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", text)
        assert seen == [2, 3, 4, 5]           # 不再每轮换地名就归零
        assert engine.stall_level(base_state) >= engine.STALL_TAKEOVER_TURNS

    def test_label_follows_the_ledger_not_the_wording(self, engine, base_state):
        """玩家看到的目标名应当是台账标题，而不是当轮那个花哨的地名选项。"""
        _lines(base_state, "苏禾")
        engine.update_stall(base_state, "追查苏姓女子", "explore")
        engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", "追查苏姓女子")
        engine.update_stall(base_state, "西行乌山镇寻苏禾", "explore")
        assert base_state["stall"]["label"] == "苏禾"
        assert base_state["stall"]["tid"] == base_state["threads"][0]["id"]

    def test_switching_target_takes_over_after_it_is_chased_harder(self, engine, base_state):
        """改追另一条线：追到比旧主线更久，归因才认它。

        刻意不一改口味就翻脸——AI 常在一轮里把主线和支线都提一遍，
        若按「最近被提到」归因，计数会在两条线之间来回跳、每跳清零一次
        （线上实测：第 7 轮才收场，就是这么丢的两轮）。
        """
        _lines(base_state, "苏禾", "乌木牌")
        t = 0
        for i in range(3):
            base_state["turn"] = t
            engine.update_stall(base_state, "追查苏禾", "explore")
            engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", "追查苏禾")
            t += 1
        assert base_state["stall"]["count"] >= 3
        for i in range(4):                       # 一门心思改追乌木牌
            base_state["turn"] = t
            engine.update_stall(base_state, "追查乌木牌来历", "explore")
            engine.bump_chase(base_state, {"advanced": ["乌木牌"]}, "explore", "追查乌木牌来历")
            t += 1
        engine.update_stall(base_state, "追查乌木牌", "explore")
        assert base_state["stall"]["tid"] == base_state["threads"][1]["id"]
        assert base_state["stall"]["label"] == "乌木牌"

    def test_side_thread_mentioned_in_passing_does_not_steal_the_attribution(self, engine, base_state):
        """主线每轮都推进，支线只是串场被提一次——归因必须留在主线上。"""
        _lines(base_state, "苏禾", "乌木牌")
        for i in range(3):
            base_state["turn"] = i
            engine.update_stall(base_state, "追查苏禾", "explore")
            bump = {"advanced": ["苏禾"]}
            if i == 1:
                bump = {"advanced": ["苏禾", "乌木牌"]}    # 本轮顺带提了一句支线
            engine.bump_chase(base_state, bump, "explore", "追查苏禾")
        assert base_state["stall"]["tid"] == base_state["threads"][0]["id"]
        assert base_state["stall"]["label"] == "苏禾"

    def test_calm_turn_falls_back_to_the_wording(self, engine, base_state):
        """去打坐了 → 本轮不算在追人，不该继续抬升这条线的计数。"""
        _lines(base_state, "苏禾")
        engine.update_stall(base_state, "追查苏禾", "explore")
        engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", "追查苏禾")
        high = engine.update_stall(base_state, "再追查苏禾", "explore")["count"]
        calm = engine.update_stall(base_state, "在破庙打坐数日", "cultivate")["count"]
        assert calm < high

    def test_text_fingerprint_still_works_without_a_ledger(self, engine, base_state):
        """台账还空着时（刚开局），退回原来的措辞比对。"""
        engine.update_stall(base_state, "追查溪畔女子", "explore")
        cur = engine.update_stall(base_state, "追查溪畔女子", "explore")
        assert cur["count"] == 2
        assert cur["tid"] == 0


# ---------------------------------------------------------------- 白名单
class TestChaseSanitize:
    def test_chase_survives_sanitize(self, engine):
        s = engine.sanitize_state({"threads": [
            {"id": 1, "title": "苏禾", "cat": "人情", "open": 1, "last": 2,
             "due": 20, "note": "采药人", "chase": 4}]})
        assert s["threads"][0]["chase"] == 4

    def test_tid_survives_sanitize(self, engine):
        s = engine.sanitize_state({"stall": {"key": "追查苏禾", "count": 3,
                                             "label": "苏禾", "tid": 7}})
        assert s["stall"]["tid"] == 7

    def test_chase_is_clamped(self, engine):
        s = engine.sanitize_state({"threads": [
            {"id": 1, "title": "苏禾", "chase": 99999}]})
        assert s["threads"][0]["chase"] == 99


# ---------------------------------------------------------------- 提示词口径
class TestStallPromptDemandsAMeeting:
    def test_third_turn_demands_the_target_show_up(self, engine, base_state):
        """旧口径把「换来情报」与「办成」并列，AI 于是专挑最好写的那一项——
        每轮给一个新地名。现在必须首选照面。"""
        _lines(base_state, "苏禾")
        for i in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(base_state, f"追查苏禾第{i}回", "explore")
            engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", f"追查苏禾第{i}回")
        note = engine.stall_prompt_note(base_state)
        assert note is not None
        assert "照面" in note

    def test_ticket_information_is_demoted(self, engine, base_state):
        """「指向下一站的情报」不再是并列的合法出口，只能作为退让项出现。"""
        _lines(base_state, "苏禾")
        for i in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(base_state, f"追查苏禾第{i}回", "explore")
            engine.bump_chase(base_state, {"advanced": ["苏禾"]}, "explore", f"追查苏禾第{i}回")
        note = engine.stall_prompt_note(base_state)
        assert "指向下一站" in note

    def test_takeover_line_no_longer_contradicts_a_meeting(self, engine):
        """收场行不能又写「终未得见」——本轮刚要求 AI 写照面，两句会打架。"""
        joined = "".join(engine.STALL_TAKEOVER_LINES)
        assert "终未得见" not in joined
