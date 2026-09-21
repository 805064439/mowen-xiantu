# -*- coding: utf-8 -*-
"""未决之事台账（v3.5）：开线有上限、推进要认名、到期给了结、逾期由代码沉底。

「有头无尾」的根因是状态里根本没有地方记着悬而未决的事——AI 每轮只看得见上一轮的
结尾钩子，于是顺着它再往前走一步：五条线全开、零条收束。台账就是给这份债建账。

这一层与江湖人物同构：**AI 提议，代码裁决**。AI 只能申报 open / advance / close，
准不准开、算不算同一条线、逾期怎么处置，全由代码说了算。
"""
from __future__ import annotations


def _plain_choices():
    """三个都不指向任何线索的普通选项（用来触发回访兜底）。"""
    return [
        {"id": "A", "text": "收拾行装，继续赶路", "risk": "mid", "tag": "explore"},
        {"id": "B", "text": "就地调息，养足精神", "risk": "low", "tag": "rest"},
        {"id": "C", "text": "四下打量周遭情形", "risk": "low", "tag": "explore"},
    ]


class TestOpenAndClose:
    def test_open_writes_full_card(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "荒泽白影", "cat": "疑窦", "note": "塘心有物反光"}]})
        th = base_state["threads"][0]
        assert th["title"] == "荒泽白影"
        assert th["cat"] == "疑窦"
        assert th["open"] == 0 and th["last"] == 0
        assert th["due"] == engine.THREAD_DUE_TURNS
        assert th["note"] == "塘心有物反光"

    def test_open_rejected_when_ledger_full(self, engine, base_state):
        for t in ("甲事", "乙事", "丙事"):
            engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": t}]})
        assert len(base_state["threads"]) == engine.THREAD_MAX
        out = engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "丁事"}]})
        assert out["dropped"] == 1
        assert len(base_state["threads"]) == engine.THREAD_MAX       # 旧线一条不掉
        assert "丁事" not in [t["title"] for t in base_state["threads"]]

    def test_at_most_one_new_thread_per_turn(self, engine, base_state):
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "甲事"}, {"op": "open", "title": "乙事"}]})
        assert out["opened"] == ["甲事"]
        assert out["dropped"] == 1

    def test_reopening_known_thread_advances_it(self, engine, base_state):
        """已在册的线再被 open → 视作推进。**一件悬事不许被拆成两件**。"""
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "荒泽白影"}]})
        base_state["turn"] = 3
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "荒泽白影", "note": "又见白影"}]})
        assert len(base_state["threads"]) == 1
        assert out["advanced"] == ["荒泽白影"]
        assert base_state["threads"][0]["last"] == 3
        assert base_state["threads"][0]["note"] == "又见白影"

    def test_advance_matches_by_substring(self, engine, base_state):
        """「那白影」要能落到「荒泽白影」上——AI 换个写法不该另起一条。"""
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "荒泽白影"}]})
        base_state["turn"] = 2
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "advance", "title": "那白影", "note": "逼近数丈"}]})
        assert out["advanced"] == ["荒泽白影"]
        assert len(base_state["threads"]) == 1
        assert base_state["threads"][0]["last"] == 2

    def test_advance_on_unknown_thread_opens_it(self, engine, base_state):
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "advance", "title": "素衣少女", "cat": "人情"}]})
        assert out["opened"] == ["素衣少女"]

    def test_advance_on_unknown_thread_dropped_when_full(self, engine, base_state):
        for t in ("甲事", "乙事", "丙事"):
            engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": t}]})
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "advance", "title": "丁事"}]})
        assert out["dropped"] == 1 and out["opened"] == []

    def test_close_moves_thread_to_chronicle(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "荒泽白影"}]})
        base_state["turn"] = 4
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "close", "title": "荒泽白影", "note": "原来是避水兽的鳞"}]})
        assert out["closed"] == ["荒泽白影"]
        assert base_state["threads"] == []
        assert any("荒泽白影" in c and "避水兽" in c for c in base_state["chronicle"])

    def test_close_unknown_thread_does_nothing(self, engine, base_state):
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "close", "title": "无此事"}]})
        assert out["dropped"] == 1
        assert base_state["threads"] == [] and base_state["chronicle"] == []

    def test_bad_category_falls_back_to_keyword(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "血海深仇", "cat": "瞎写的类别"}]})
        assert base_state["threads"][0]["cat"] == "恩怨"

    def test_garbage_input_is_ignored(self, engine, base_state):
        out = engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "delete", "title": "甲事"}, {"op": "open", "title": "   "}, "not a dict"]})
        assert base_state["threads"] == []
        assert out["dropped"] == 1          # 空标题直接跳过，不计入 dropped

    def test_missing_field_is_a_noop(self, engine, base_state):
        out = engine.apply_thread_updates(base_state, {})
        assert out == {"opened": [], "advanced": [], "closed": [], "dropped": 0}
        assert base_state["threads"] == []


class TestOverdue:
    def test_expires_after_grace(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "荒泽白影"}]})
        base_state["turn"] = engine.THREAD_DUE_TURNS + engine.THREAD_OVERDUE_GRACE + 1
        gone = engine.expire_overdue_threads(base_state)
        assert gone == ["荒泽白影"]
        assert base_state["threads"] == []
        assert any("终无下文" in c for c in base_state["chronicle"])
        assert any("终无下文" in m for m in base_state["memory"])

    def test_no_expire_before_grace_is_up(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "荒泽白影"}]})
        base_state["turn"] = engine.THREAD_DUE_TURNS + engine.THREAD_OVERDUE_GRACE
        assert engine.expire_overdue_threads(base_state) == []
        assert len(base_state["threads"]) == 1

    def test_empty_ledger_is_cheap(self, engine, base_state):
        assert engine.expire_overdue_threads(base_state) == []


class TestSanitize:
    def test_old_save_without_threads(self, engine):
        s = engine.sanitize_state({"realm_index": 0, "hp": 10, "hp_max": 100, "days": 0})
        assert s["threads"] == [] and s["chronicle"] == []

    def test_title_category_and_turns_are_clamped(self, engine):
        s = engine.sanitize_state({
            "threads": [{"title": "很长很长" * 20, "cat": "瞎写", "open": 99999, "due": -5}],
            "chronicle": ["大" * 80] * 20,
        })
        th = s["threads"][0]
        assert len(th["title"]) <= engine.THREAD_TITLE_MAX
        assert th["cat"] in engine.THREAD_CATEGORIES
        assert 0 <= th["open"] <= 9999 and 0 <= th["due"] <= 9999
        assert len(s["chronicle"]) == engine.CHRONICLE_MAX
        assert all(len(c) <= engine.CHRONICLE_LINE_MAX for c in s["chronicle"])

    def test_ledger_capped_at_max(self, engine):
        s = engine.sanitize_state({"threads": [{"title": f"悬事{i}"} for i in range(9)]})
        assert len(s["threads"]) == engine.THREAD_MAX


class TestPromptInjection:
    def test_threads_section_present(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "荒泽白影", "cat": "疑窦", "note": "塘心有物"}]})
        p = engine.build_user_prompt(base_state, {"text": "继续赶路"}, "无特殊判定")
        assert "【未决之事】" in p
        assert "荒泽白影" in p and "疑窦" in p
        assert f"在册 1/{engine.THREAD_MAX}" in p

    def test_overdue_section_only_when_overdue(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "荒泽白影"}]})
        assert "【逾期未决】" not in engine.build_user_prompt(base_state, {"text": "赶路"}, "无")
        base_state["turn"] = engine.THREAD_DUE_TURNS + 1
        p = engine.build_user_prompt(base_state, {"text": "赶路"}, "无")
        assert "【逾期未决】" in p and "已逾期 1 轮" in p

    def test_chronicle_section_present(self, engine, base_state):
        base_state["chronicle"] = ["第3轮 · 荒泽白影：原来是避水兽"]
        assert "【大事记】" in engine.build_user_prompt(base_state, {"text": "赶路"}, "无")


class TestRecallChoice:
    def test_third_choice_replaced_when_none_point_back(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "素衣少女", "cat": "人情"}]})
        out, used = engine.ensure_thread_choice(_plain_choices(), base_state)
        assert used is True
        assert len(out) == 3
        assert "素衣少女" in out[2]["text"]      # 玩家永远有「回去办那件事」的入口
        assert out[2]["tag"] == "explore" and out[2]["risk"] == "low"

    def test_not_replaced_when_one_already_points_back(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [
            {"op": "open", "title": "素衣少女", "cat": "人情"}]})
        ch = _plain_choices()
        ch[1] = {"id": "B", "text": "回访那素衣少女", "risk": "low", "tag": "explore"}
        out, used = engine.ensure_thread_choice(ch, base_state)
        assert used is False and out is ch

    def test_no_ledger_no_replacement(self, engine, base_state):
        ch = _plain_choices()
        out, used = engine.ensure_thread_choice(ch, base_state)
        assert used is False and out is ch


class TestPaceWiring:
    def test_closing_a_thread_turns_resolve(self, engine, base_state):
        assert engine.infer_scene_pace(base_state, "other", None, None, None,
                                       thread_closed=True) == "resolve"

    def test_empty_ledger_lowers_downtime_bar(self, engine, base_state):
        """无债一身轻：台账空着时更容易进空白期，才轮得到「闭关数年」的选项。"""
        base_state["calm_streak"] = engine.DOWNTIME_STREAK - 1
        assert engine.infer_scene_pace(base_state, "rest", None, None, None) == "downtime"
        base_state["threads"] = [{"id": 1, "title": "荒泽白影", "cat": "疑窦",
                                  "open": 0, "last": 0, "due": 4, "note": ""}]
        assert engine.infer_scene_pace(base_state, "rest", None, None, None) != "downtime"


class TestTurnWiring:
    def test_postprocess_records_ledger_and_patches_choices(self, engine, base_state):
        data = {
            "narrative": "他沿着塘边缓步走了一圈，水面上浮着一层薄雾，此外一无所获。",
            "choices": _plain_choices(),
            "delta": {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0},
            "memory": "绕塘踏探无获",
            "thread_updates": [{"op": "open", "title": "素衣少女", "cat": "人情", "note": "留下半截断苇"}],
        }
        meta: dict = {}
        _n, choices, _d, _nd, _ev = engine._postprocess_turn(
            base_state, data, meta, "循那少女去路", "explore", tier="mid", span=None, trial=None)
        assert meta["threads"]["opened"] == ["素衣少女"]
        assert meta["threads"]["recall_used"] is True
        assert any("素衣少女" in c["text"] for c in choices)
        assert base_state["threads"][0]["title"] == "素衣少女"

    def test_api_act_roundtrips_ledger(self, engine, client):
        s = engine.sanitize_state({
            "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
            "exp": 0, "spirit_stones": 100, "items": [], "memory": [], "recent": [],
            "npcs": [], "turn": 0, "days": 0,
            "threads": [{"id": 1, "title": "荒泽白影", "cat": "疑窦",
                         "open": 0, "last": 0, "due": 4, "note": "塘心有物"}],
        })
        r = client.post("/api/act", json={
            "state": s,
            "action": {"type": "choice", "id": "A", "text": "继续赶路", "tag": "explore", "risk": "mid"},
            "last_choices": [],
        })
        assert r.status_code == 200
        body = r.json()
        assert "threads" in body.get("state", {})
        assert "threads" in body.get("engine_meta", {})
        assert body["state"]["threads"][0]["title"] == "荒泽白影"
