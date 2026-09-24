# -*- coding: utf-8 -*-
"""追索停滞（v3.6）：同一件事连追数轮无果 → 先逼结果，再由代码收场。

日志实证：一段 39 轮的存档里有三处悬置——追青衣少女 16 轮 217 天、挖石函 11 轮 683 天、
追查溪畔女子 8 轮 322 天（其中六轮点的同一个选项）。三者到收场都没给结果。

根因不在提示词，而在三个引擎层面的洞：
  · 回访闸门只要「选项沾到线索的字」就判已照顾，于是「追查某人」可以每轮出现、每轮无果；
  · 台账全靠 AI 申报，AI 不申报就是空册，到期 / 逾期 / 回访四套机制集体罢工；
  · 探索掉落掷在 AI 写完之后，行囊悄悄进账、剧情里两手空空。

这一层补的是**代码自己的计数**：不管 AI 有没有申报，数到阈值就先逼结果、再强行收场。
"""
from __future__ import annotations


def _dig_choices():
    """挖石函那一段的典型选项：三条都在原地打转，没有一条是出口。"""
    return [
        {"id": "A", "text": "再掘数下，将那物起出来", "risk": "high", "tag": "fight"},
        {"id": "B", "text": "抽剑退开，坐调息稳住水气", "risk": "low", "tag": "rest"},
        {"id": "C", "text": "以剑挑起一角，细辨是何物", "risk": "mid", "tag": "explore"},
    ]


def _hit_choices():
    """第三条沾着线索的字（旧闸门的盲区）。"""
    return [
        {"id": "A", "text": "往北寻访旬日", "risk": "mid", "tag": "explore"},
        {"id": "B", "text": "就地打坐数日", "risk": "low", "tag": "cultivate", "span": "short"},
        {"id": "C", "text": "追查溪畔女子", "risk": "mid", "tag": "explore"},
    ]


# ---------------------------------------------------------------- 认「同一件事」
class TestSamePursuit:
    def test_identical_text_is_same_pursuit(self, engine):
        assert engine.same_pursuit("追查溪畔女子", "追查溪畔女子") is True

    def test_choice_prefix_is_stripped(self, engine):
        """「C 追查溪畔女子」与「追查溪畔女子」是同一件事——选项前缀不该影响判定。"""
        assert engine.same_pursuit("C 追查溪畔女子", "追查溪畔女子") is True

    def test_longer_restatement_still_same(self, engine):
        """玩家越追越急，句子越写越长（「…直到找到为止」）：仍是同一件事。"""
        assert engine.same_pursuit("再去找一下那位青衣少女",
                                   "再去找一下那位青衣少女，直到找到为止") is True

    def test_unrelated_actions_are_never_merged(self, engine):
        """挖石函每轮换个说法，不该被误判成同一件事——那是「空转连击」的活。

        宁可漏判（少逼一次），不可误判（把两件事算成一件，平白催玩家收手）。
        """
        assert engine.same_pursuit("以剑掘那水下硬物", "再沉腕力，撬开这石函") is False

    def test_empty_is_never_same(self, engine):
        assert engine.same_pursuit("", "追查某人") is False
        assert engine.same_pursuit("追查某人", "") is False


# ---------------------------------------------------------------- 文字指纹计数
class TestStallCount:
    def test_count_climbs_on_repeat(self, engine, base_state):
        for _ in range(4):
            engine.update_stall(base_state, "追查溪畔女子")
        assert base_state["stall"]["count"] == 4

    def test_count_resets_on_a_new_target(self, engine, base_state):
        engine.update_stall(base_state, "追查溪畔女子")
        engine.update_stall(base_state, "追查溪畔女子")
        engine.update_stall(base_state, "入坊市换些干粮")
        assert base_state["stall"]["count"] == 1
        assert base_state["stall"]["label"] == "入坊市换些干粮"

    def test_label_keeps_the_first_wording(self, engine, base_state):
        """越追越长的句子不该把展示用的标签也顶掉。"""
        engine.update_stall(base_state, "追查溪畔女子")
        engine.update_stall(base_state, "追查溪畔女子，直到找到为止")
        assert base_state["stall"]["count"] == 2
        assert base_state["stall"]["label"] == "追查溪畔女子"

    def test_blank_input_starts_no_pursuit(self, engine, base_state):
        engine.update_stall(base_state, "")
        assert base_state["stall"]["count"] == 0

    def test_sanitize_clamps_the_counter(self, engine):
        s = engine.sanitize_state({"stall": {"key": "追查某人", "count": 99999, "label": "追查某人"}})
        assert s["stall"]["count"] == 999
        # tid = 归因到的台账线索 id，比措辞稳定（AI 换地名也冲不掉）
        assert engine.sanitize_state({})["stall"] == {"key": "", "count": 0, "label": "", "tid": 0}


# ---------------------------------------------------------------- 空转连击（换说法也照抓）
class TestDryStreak:
    def test_dry_climbs_when_nothing_happens(self, engine, base_state):
        for _ in range(3):
            engine.update_dry(base_state, "explore", gained=False)
        assert base_state["dry"] == 3

    def test_dry_resets_on_a_real_gain(self, engine, base_state):
        engine.update_dry(base_state, "explore", gained=False)
        engine.update_dry(base_state, "explore", gained=True)
        assert base_state["dry"] == 0

    def test_cultivate_never_counts_as_dry(self, engine, base_state):
        """打坐本就该没产出——不算空转，否则闭关流会被无端催着了结。"""
        for _ in range(5):
            engine.update_dry(base_state, "cultivate", gained=False)
        assert base_state["dry"] == 0


# ---------------------------------------------------------------- 提示词：第 3 轮起下死命令
class TestStallPrompt:
    def test_silent_before_the_threshold(self, engine, base_state):
        engine.update_stall(base_state, "追查溪畔女子")
        engine.update_stall(base_state, "追查溪畔女子")
        assert engine.stall_prompt_note(base_state) is None

    def test_orders_a_result_from_the_third_turn(self, engine, base_state):
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(base_state, "追查溪畔女子")
        note = engine.stall_prompt_note(base_state)
        assert note is not None
        assert "追索已滞" in note
        assert "严禁" in note
        assert "追查溪畔女子" in note

    def test_dry_alone_can_force_it(self, engine, base_state):
        """挖石函：选项每轮换说法，文字指纹抓不住，靠空转连击兜住。"""
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_dry(base_state, "explore", gained=False)
        assert engine.stall_prompt_note(base_state) is not None

    def test_forced_turn_is_below_the_takeover_turn(self, engine):
        """先给 AI 两轮机会，再谈接管。"""
        assert engine.STALL_FORCE_TURNS < engine.STALL_TAKEOVER_TURNS


# ---------------------------------------------------------------- 出口：第三选项
class TestResolveChoice:
    def test_untouched_before_the_threshold(self, engine, base_state):
        engine.update_stall(base_state, "水下石函")
        out, used = engine.ensure_resolve_choice(_dig_choices(), base_state)
        assert used is False
        assert out == _dig_choices()

    def test_third_choice_becomes_a_way_out(self, engine, base_state):
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(base_state, "水下石函")
        out, used = engine.ensure_resolve_choice(_dig_choices(), base_state)
        assert used is True
        assert any(w in out[2]["text"] for w in engine.RESOLVE_WORDS)
        assert out[0]["text"] == _dig_choices()[0]["text"]     # 前两条不动

    def test_ai_already_offered_a_way_out(self, engine, base_state):
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(base_state, "水下石函")
        cs = _dig_choices()
        cs[2]["text"] = "就此罢手，回坊市另寻机缘"
        out, used = engine.ensure_resolve_choice(cs, base_state)
        assert used is False

    def test_never_shrinks_the_choice_list(self, engine, base_state):
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(base_state, "水下石函")
        out, _ = engine.ensure_resolve_choice(_dig_choices(), base_state)
        assert len(out) == 3


# ---------------------------------------------------------------- 回访闸门：逾期压过沾字
class TestOverdueBeatsKeywordHit:
    """日志里最要命的一处：选项写着「追查溪畔女子」，沾了线索的字，
    旧的闸门就判「已经照顾到了」——于是这条选项可以每轮出现、每轮无果。"""

    def test_keyword_hit_spares_the_choice_when_not_overdue(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "溪畔女子"}]})
        out, used = engine.ensure_thread_choice(_hit_choices(), base_state)
        assert used is False
        assert out[2]["text"] == "追查溪畔女子"

    def test_overdue_line_is_forced_anyway(self, engine, base_state):
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "溪畔女子"}]})
        base_state["turn"] = engine.THREAD_DUE_TURNS + 1
        out, used = engine.ensure_thread_choice(_hit_choices(), base_state)
        assert used is True
        assert out[2]["text"] != "追查溪畔女子"

    def test_closing_template_is_stronger_than_recall(self, engine, base_state):
        """逾期给的是终局话术，不是「再去看看」。"""
        for cat in engine.THREAD_CATEGORIES:
            tpl = engine.THREAD_CLOSE_TPL[cat][0]
            assert tpl != engine.THREAD_RECALL[cat][0]
        assert "了断" in engine.THREAD_CLOSE_TPL["恩怨"][0]


# ---------------------------------------------------------------- 代码接管：第 5 轮收场
class TestTakeover:
    def _run(self, engine, base_state, data, meta, action="再掘一次", tag="explore"):
        return engine._postprocess_turn(base_state, data, meta, action, tag, tier="mid")

    def test_code_wraps_it_up_at_the_takeover_turn(self, engine, base_state):
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(base_state, "水下石函")
        meta = {}
        narrative, choices, *_ = self._run(
            engine, base_state,
            {"delta": {}, "choices": _dig_choices(), "narrative": "石函仍未启。", "memory": ""},
            meta)
        assert meta["stall"]["takeover"] is True
        assert len(narrative) > len("石函仍未启。")          # 收场文案被追加
        assert base_state["stall"]["count"] == 0             # 就此翻篇
        assert base_state["dry"] == 0
        assert any("水下石函" in c for c in base_state["chronicle"])
        assert any(w in choices[2]["text"] for w in ("改道", "另作"))

    def test_no_takeover_when_the_thread_just_closed(self, engine, base_state):
        """AI 自己给了交代 → 代码不必越俎代庖。"""
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "水下石函"}]})
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(base_state, "水下石函")
        meta = {}
        narrative, *_ = self._run(
            engine, base_state,
            {"delta": {}, "choices": _dig_choices(), "narrative": "石函终开。", "memory": "",
             "thread_updates": [{"op": "close", "title": "水下石函", "note": "得残卷"}]},
            meta)
        assert meta["stall"]["takeover"] is False
        assert narrative.strip() == "石函终开。"

    def test_takeover_marks_the_thread_as_found(self, engine, base_state):
        """收场不是注销这条线：人找着了，线要转成「当面在此」留在册上给玩家续话。

        旧做法是 remove(hit)，玩家看到的是台账里凭空少了一条——追了这么久的事
        连个交代的入口都没留下。
        """
        engine.apply_thread_updates(base_state, {"thread_updates": [{"op": "open", "title": "水下石函"}]})
        for _ in range(engine.STALL_TAKEOVER_TURNS):
            engine.update_stall(base_state, "水下石函")
        meta = {}
        self._run(engine, base_state,
                  {"delta": {}, "choices": _dig_choices(), "narrative": "n", "memory": ""}, meta)
        assert meta["stall"]["takeover"] is True
        assert len(base_state["threads"]) == 1, "人找着了，这条线不该从台账上消失"
        th = base_state["threads"][0]
        assert th["note"] == engine.STALL_FOUND_NOTE
        assert th["found"] == 1
        assert th["chase"] == 0, "照过面就不该再被当成新一轮追索"

    def test_no_takeover_below_the_threshold(self, engine, base_state):
        for _ in range(engine.STALL_TAKEOVER_TURNS - 1):
            engine.update_stall(base_state, "水下石函")
        meta = {}
        self._run(engine, base_state,
                  {"delta": {}, "choices": _dig_choices(), "narrative": "n", "memory": ""}, meta)
        assert meta["stall"]["takeover"] is False


# ---------------------------------------------------------------- 机缘前置：所得要写进剧情
class TestFortunePreced:
    def test_fortune_is_rolled_before_the_narrative(self, engine, base_state):
        kinds = set()
        for _ in range(300):
            f = engine.pre_roll_fortune(base_state, "explore", "mid")
            kinds.add(f["kind"])
            if f["kind"] == "treasure":
                assert f["name"] == engine.TREASURE[f["key"]]["name"]
        assert kinds <= {"death", "treasure", "none"}
        assert "treasure" in kinds          # mid 档掉落率 0.75，不该一次都不出

    def test_non_explore_never_rolls_fortune(self, engine, base_state):
        for tag in ("cultivate", "rest", "fight", "trade", "other"):
            assert engine.pre_roll_fortune(base_state, tag, None)["kind"] == "none"

    def test_note_orders_the_loot_into_the_story(self, engine):
        note = engine.fortune_prompt_note({"kind": "treasure", "key": "residual_scroll",
                                           "name": "功法残卷"})
        assert "功法残卷" in note
        assert "narrative" in note

    def test_empty_handed_still_owes_a_lead(self, engine):
        """空手也绝不允许写成「一无所获」——至少落下一条可追的线索。"""
        note = engine.fortune_prompt_note({"kind": "none"})
        assert note is not None
        assert "绝不允许" in note or "不得" in note

    def test_death_is_not_spoiled_to_the_ai(self, engine):
        """凶险照旧由代码在事后追加，不事先告诉 AI，免得它提前写死。"""
        assert engine.fortune_prompt_note({"kind": "death"}) is None

    def test_postprocess_never_rerolls(self, engine, base_state, monkeypatch):
        """传入前置掷点后，后处理只照单兑现——重掷一次，剧情与行囊当场分家。"""
        monkeypatch.setattr(engine.random, "random", lambda: 1.0)   # 若重掷，必定什么也掷不出
        meta = {}
        engine._postprocess_turn(
            base_state, {"delta": {}, "choices": [], "narrative": "n", "memory": ""},
            meta, "远行历练", "explore", tier="mid",
            fortune_pre={"kind": "treasure", "key": "residual_scroll", "name": "功法残卷"})
        assert meta.get("treasure", {}).get("key") == "residual_scroll"
        assert base_state["treasures"].get("residual_scroll") == 1

    def test_full_treasure_falls_back_without_lying(self, engine, base_state):
        """某件已满额时不许硬塞——要么换一件装得下的，要么老实当空手。"""
        base_state["treasures"] = {k: engine.TREASURE_CAP[k] for k in engine.TREASURE_CAP}
        for _ in range(50):
            f = engine.pre_roll_fortune(base_state, "explore", "mid")
            if f["kind"] == "treasure":
                assert f["key"] not in engine.TREASURE_CAP   # 无上限的件（灵丹）仍可入袋
