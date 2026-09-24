# -*- coding: utf-8 -*-
"""test_22_intent.py —— 玩家意图与选项落地（v3.10）

2026-09-23 那份 58 轮日志的病理（阿菱 / 柳三娘）：
  ① 正文写的是阿菱，选项主位却是「寻柳三娘，往南溪谷一探」——柳三娘只是
     正文末句一句闲话捎出来的人物，一点选项就登堂入室成了主线；
  ② 玩家连打 4 轮「去寻阿菱」，阿菱始终进不了台账（THREAD_MAX 满了禁开新线，
     自由输入又没有任何开线机制），提示词还逼着 AI 优先还自己造的债——
     于是玩家的意图被接到 AI 的线上，阿菱被一站一站搬走、最终写死；
  ③ 收场文案「另寻寻柳三娘往南溪谷以外的出路」叠了动词（label 自带「寻」）。

本次锁定：
  · open_player_thread —— 自由输入连追 2 轮，代码替玩家立线（满则挤最旧疑窦）
  · ground_choices     —— 选项里查无出处的人名作废，按序补兜底（不掷骰）
  · stall_prompt_note  —— 「断干净 ≠ 把人写死」，写死须交代是谁/何时/何据
  · ensure_resolve_choice —— 拼「另寻{}」前先剥掉 label 开头的动词
"""
from __future__ import annotations

import pytest


def _thread(title, note="", tid=1, cat="疑窦", last=0, due=9):
    return {"id": tid, "title": title, "cat": cat, "open": 0, "last": last, "due": due, "note": note}


def _npc(name, title="路人", bond=0):
    return {"name": name, "title": title, "bond": bond, "alias": []}


# ---------------------------------------------------------------- 短语整形（D）

class TestPursuitHead:
    def test_strips_lead_verbs(self, engine):
        assert engine._pursuit_head("去寻阿菱") == "阿菱"

    def test_cuts_destination(self, engine):
        """「寻柳三娘往南溪谷」→ 追的是柳三娘，不是南溪谷。"""
        assert engine._pursuit_head("寻柳三娘往南溪谷") == "柳三娘"

    def test_strips_whereabouts_tail(self, engine):
        assert engine._pursuit_head("查溪畔女子下落") == "溪畔女子"

    def test_all_verbs_falls_back(self, engine):
        assert engine._pursuit_head("再去") == ""

    def test_plain_phrase_kept(self, engine):
        assert engine._pursuit_head("溪畔女子") == "溪畔女子"


class TestResolveChoiceWording:
    def test_no_doubled_verb(self, engine, base_state):
        """【D 修复】label 自带「寻」，不剥会拼出「另寻寻柳三娘…」。"""
        s = base_state
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(s, "寻柳三娘往南溪谷")
        raw = [{"id": "A", "text": "再追一程", "risk": "mid", "tag": "explore"},
               {"id": "B", "text": "就地调息", "risk": "low", "tag": "cultivate", "span": "short"},
               {"id": "C", "text": "换个方向打听", "risk": "mid", "tag": "explore"}]
        out, used = engine.ensure_resolve_choice(raw, s)
        assert used is True
        text = out[2]["text"]
        assert "另寻寻" not in text, f"叠动词病句仍在：{text}"
        assert "柳三娘" in text

    def test_already_has_resolve_word_untouched(self, engine, base_state):
        s = base_state
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(s, "寻柳三娘往南溪谷")
        raw = [{"id": "A", "text": "就此作罢，先回去休整", "risk": "low", "tag": "other"},
               {"id": "B", "text": "就地调息", "risk": "low", "tag": "cultivate"},
               {"id": "C", "text": "换个方向打听", "risk": "mid", "tag": "explore"}]
        out, used = engine.ensure_resolve_choice(raw, s)
        assert used is False


# ---------------------------------------------------------------- 玩家意图开线（B）

class TestOpenPlayerThread:
    def _pursue(self, engine, s, text="去寻阿菱", rounds=2):
        for _ in range(rounds):
            engine.update_stall(s, text)
        return s

    def test_opens_after_two_rounds(self, engine, base_state):
        """【B 核心】自由输入连追 2 轮，玩家的意图自己成为一条债。"""
        s = self._pursue(engine, base_state)
        title = engine.open_player_thread(s, "去寻阿菱", "other", is_custom=True)
        assert title == "阿菱"
        threads = s["threads"]
        assert len(threads) == 1
        assert threads[0]["title"] == "阿菱"
        assert threads[0]["due"] == s["turn"] + engine.THREAD_DUE_TURNS

    def test_explore_tag_also_opens(self, engine, base_state):
        """tag 认得出 explore（如「去查探阿菱住处」）同样开线。"""
        s = self._pursue(engine, base_state, "去查探阿菱住处")
        title = engine.open_player_thread(s, "去查探阿菱住处", "explore", is_custom=True)
        assert title == "阿菱住处"

    def test_not_custom_never_opens(self, engine, base_state):
        """点选项不算自由输入——选项有自己的归宿（ensure_thread_choice）。"""
        s = self._pursue(engine, base_state)
        assert engine.open_player_thread(s, "去寻阿菱", "explore", is_custom=False) is None
        assert s["threads"] == []

    def test_single_round_never_opens(self, engine, base_state):
        s = self._pursue(engine, base_state, rounds=1)
        assert engine.open_player_thread(s, "去寻阿菱", "other", is_custom=True) is None

    def test_calm_actions_never_open(self, engine, base_state):
        """连打两轮「闭关苦修」不该开出「闭关苦修」这种线索。"""
        s = self._pursue(engine, base_state, "闭关苦修")
        assert engine.open_player_thread(s, "闭关苦修", "cultivate", is_custom=True) is None

    def test_no_pursuit_word_never_opens(self, engine, base_state):
        """tag 认不出、字面又没有追索字眼的重复输入（如「吃顿饱饭」）不开线。"""
        s = self._pursue(engine, base_state, "吃顿饱饭")
        assert engine.open_player_thread(s, "吃顿饱饭", "other", is_custom=True) is None

    def test_already_ledgered_not_duplicated(self, engine, base_state):
        """AI 若已为同一件事开过线，认得就行，绝不另立一条。"""
        s = self._pursue(engine, base_state)
        s["threads"] = [_thread("阿菱", "追查中", 1)]
        assert engine.open_player_thread(s, "去寻阿菱", "other", is_custom=True) is None
        assert len(s["threads"]) == 1

    def test_full_ledger_evicts_oldest_doubt(self, engine, base_state):
        """台账满 → 挤掉最旧的疑窦线。AI 造的线可以让位，玩家的意图不能。"""
        s = self._pursue(engine, base_state)
        s["threads"] = [
            _thread("旧祠异响", "疑窦线A", 1, cat="疑窦", last=1),
            _thread("残卷来历", "疑窦线B", 2, cat="疑窦", last=5),
            _thread("北荒灵脉", "机缘线", 3, cat="机缘", last=3),
        ]
        title = engine.open_player_thread(s, "去寻阿菱", "other", is_custom=True)
        assert title == "阿菱"
        titles = [t["title"] for t in s["threads"]]
        assert "旧祠异响" not in titles, "该挤掉的是最旧的那条疑窦线"
        assert titles.count("阿菱") == 1
        assert len(s["threads"]) == engine.THREAD_MAX

    def test_full_ledger_without_doubt_evicts_oldest(self, engine, base_state):
        s = self._pursue(engine, base_state)
        s["threads"] = [
            _thread("灵脉机缘", "机缘", 1, cat="机缘", last=2),
            _thread("夺灵之仇", "恩怨", 2, cat="恩怨", last=6),
            _thread("故人托付", "人情", 3, cat="人情", last=4),
        ]
        engine.open_player_thread(s, "去寻阿菱", "other", is_custom=True)
        titles = [t["title"] for t in s["threads"]]
        assert "灵脉机缘" not in titles, "没有疑窦线时挤最旧的一条"

    def test_opened_thread_recognized_by_takeover(self, engine, base_state):
        """开出来的线要能被收场逻辑认走——同一套 find_thread 归并。"""
        s = self._pursue(engine, base_state, rounds=engine.STALL_TAKEOVER_TURNS)
        engine.open_player_thread(s, "去寻阿菱", "other", is_custom=True)
        hit = engine.find_thread(s["threads"], "去寻阿菱")
        assert hit is not None and hit["title"] == "阿菱"


# ---------------------------------------------------------------- 人名提取与落地（A）

class TestPersonTokens:
    def test_a_prefix(self, engine):
        assert "阿菱" in engine._person_tokens("去寻阿菱")

    def test_digit_kin(self, engine):
        """柳三娘＝姓＋数字＋娘，正是事故现场的那个名字。"""
        assert "柳三娘" in engine._person_tokens("寻柳三娘，往南溪谷一探数日")

    def test_suffix(self, engine):
        assert "沈船家" in engine._person_tokens("问沈船家旧事")

    def test_ranked(self, engine):
        assert "陈老六" in engine._person_tokens("找陈老六问话")

    def test_common_words_not_names(self, engine):
        """柳树 / 陈年 / 林间——看着像「姓+字」，实则日常用词，绝不能误伤。"""
        for text in ("在柳树下打坐", "喝些陈年老酒", "穿林而过", "月挂柳梢"):
            assert engine._person_tokens(text) == set(), text


class TestGroundChoices:
    """事故现场重演：正文主场景写阿菱，末句闲话抛出柳三娘，选项主位给了柳三娘。"""

    NARRATIVE = (
        "茶棚里人声嘈杂。卖炭老汉压低嗓子提起「阿菱姑娘」，说她前几日还在溪畔浣纱。"
        "你循话望去，檐下确实坐着个青衣女子，侧影沉静。"
        "这几日在坊间听来几句闲话：南边三十里外有个叫柳三娘的女修，专收散修的碎料灵材，行踪不定。"
    )

    def _raw(self):
        return [
            {"id": "A", "text": "寻柳三娘，往南溪谷一探数日", "risk": "mid", "tag": "explore"},
            {"id": "B", "text": "去寻阿菱", "risk": "low", "tag": "explore"},
            {"id": "C", "text": "就地打坐，调息养气", "risk": "low", "tag": "cultivate", "span": "short"},
        ]

    def test_hijack_choice_replaced(self, engine, base_state):
        """【A 核心】末句闲话里的人名不算出处——柳三娘的选项当场作废。"""
        out, swaps = engine.ground_choices(self._raw(), base_state, self.NARRATIVE, "找个美女搭话")
        texts = [c["text"] for c in out]
        assert not any("柳三娘" in t for t in texts), f"闲话人物还占着选项：{texts}"
        assert "去寻阿菱" in texts, "正文主场景的人物（阿菱）不该被误伤"
        assert "就地打坐，调息养气" in texts
        assert swaps and swaps[0]["names"] == ["柳三娘"]

    def test_replacement_from_filler_pool_deterministic(self, engine, base_state):
        """补位从兜底池按序取、不掷骰——随机流顺序是高压线。"""
        out1, _ = engine.ground_choices(self._raw(), base_state, self.NARRATIVE, "找个美女搭话")
        out2, _ = engine.ground_choices(self._raw(), base_state, self.NARRATIVE, "找个美女搭话")
        assert [c["text"] for c in out1] == [c["text"] for c in out2]
        pool = {c["text"] for c in engine.filler_choices(base_state)}
        # 柳三娘那条作废后，补位的兜底追加在末尾（kept 顺序保持原位）
        assert out1[2]["text"] in pool, f"补位不在兜底池里：{out1[2]['text']}"

    def test_grounded_by_thread_title(self, engine, base_state):
        """已在册的柳三娘线，回访选项必须保留——那是玩家的债。"""
        base_state["threads"] = [_thread("南溪谷柳三娘", "行踪不定", 1)]
        out, swaps = engine.ground_choices(self._raw(), base_state, self.NARRATIVE, "找个美女搭话")
        assert swaps == []
        assert "寻柳三娘，往南溪谷一探数日" in [c["text"] for c in out]

    def test_grounded_by_npc_registry(self, engine, base_state):
        base_state["npcs"] = [_npc("柳三娘", "散修女修")]
        out, swaps = engine.ground_choices(self._raw(), base_state, self.NARRATIVE, "找个美女搭话")
        assert swaps == []

    def test_grounded_by_player_input(self, engine, base_state):
        """玩家自己点名要找的人，天经地义有着落。"""
        out, swaps = engine.ground_choices(self._raw(), base_state, self.NARRATIVE, "去找柳三娘")
        assert swaps == []

    def test_grounded_by_recent_turns(self, engine, base_state):
        """上一轮正文里立住的人物（阿牛），这一轮选项提他不该被拦。"""
        base_state["recent"] = [{"action": "四处走动", "narrative": "村口遇放牛郎阿牛，他说后山有异动。", "turn": 1, "days": 3}]
        raw = [{"id": "A", "text": "回去找阿牛问个明白", "risk": "low", "tag": "explore"},
               {"id": "B", "text": "就地调息", "risk": "low", "tag": "rest"},
               {"id": "C", "text": "上山看看", "risk": "mid", "tag": "explore"}]
        out, swaps = engine.ground_choices(raw, base_state, "山风吹过，别无他事。", "上山看看")
        assert swaps == []
        assert "回去找阿牛问个明白" in [c["text"] for c in out]

    def test_mid_narrative_mention_grounded(self, engine, base_state):
        """正文主体里登场的柳三娘（非末句闲话）是主场景人物，选项可以指她。"""
        narr = ("那女子自报家门，姓柳行三，人称柳三娘，邀你同去南溪谷走一遭。"
                "你略一沉吟，没有立刻应下。")
        raw = [{"id": "A", "text": "寻柳三娘，往南溪谷一探数日", "risk": "mid", "tag": "explore"},
               {"id": "B", "text": "跟上去看看", "risk": "low", "tag": "explore"},
               {"id": "C", "text": "原地不动，静观其变", "risk": "low", "tag": "other"}]
        out, swaps = engine.ground_choices(raw, base_state, narr, "找个美女搭话")
        assert swaps == []
        assert "寻柳三娘，往南溪谷一探数日" in [c["text"] for c in out]

    def test_non_explore_tag_untouched(self, engine, base_state):
        """打坐/买卖类选项即使带生名字也不拦——它们不会把人捧成主线。"""
        raw = [{"id": "A", "text": "把灵草卖给柳三娘", "risk": "low", "tag": "trade"},
               {"id": "B", "text": "就地调息", "risk": "low", "tag": "rest"},
               {"id": "C", "text": "收拾行装赶路", "risk": "mid", "tag": "explore"}]
        out, swaps = engine.ground_choices(raw, base_state, "茶棚无事。", "赶路")
        assert swaps == []
        assert "把灵草卖给柳三娘" in [c["text"] for c in out]

    def test_special_choice_preserved(self, engine, base_state):
        """冲关注入项（id=BT）不参与落地校验，也不被补位挤掉。"""
        raw = self._raw() + [{"id": "BT", "text": "闭关，冲击炼气二层", "risk": "high",
                              "tag": "breakthrough", "special": "breakthrough"}]
        out, _ = engine.ground_choices(raw, base_state, self.NARRATIVE, "找个美女搭话")
        assert any(c.get("special") == "breakthrough" for c in out)
        assert len([c for c in out if not c.get("special")]) == 3

    def test_all_three_swapped_still_three(self, engine, base_state):
        raw = [
            {"id": "A", "text": "寻柳三娘", "risk": "mid", "tag": "explore"},
            {"id": "B", "text": "去找阿菱问问", "risk": "mid", "tag": "fight"},
            {"id": "C", "text": "探阿九的底", "risk": "high", "tag": "explore"},
        ]
        out, swaps = engine.ground_choices(raw, base_state, "山道无事，一夜平安。", "赶路")
        assert len(swaps) == 3
        assert len(out) == 3


class TestGroundingViaPostprocess:
    def test_meta_records_swaps(self, engine, base_state):
        """整轮跑下来，替换动作要落在 engine_meta 里，线上排障有据可查。"""
        s = base_state
        data = {
            "narrative": ("茶棚里人声嘈杂。卖炭老汉提起「阿菱姑娘」，说她前几日还在溪畔浣纱。"
                          "这几日在坊间听来几句闲话：南边有个叫柳三娘的女修，行踪不定。"),
            "memory": "茶棚听闻闲话",
            "delta": {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                      "items_add": [], "items_remove": []},
            "choices": [
                {"id": "A", "text": "寻柳三娘，往南溪谷一探数日", "risk": "mid", "tag": "explore"},
                {"id": "B", "text": "去寻阿菱", "risk": "low", "tag": "explore"},
                {"id": "C", "text": "就地打坐，调息养气", "risk": "low", "tag": "cultivate"},
            ],
        }
        meta = {}
        engine._postprocess_turn(s, data, meta, "找个美女搭话", "other", tier="mid")
        assert meta.get("choice_grounding", {}).get("swaps"), "替换没落进 meta"
        assert meta["choice_grounding"]["swaps"][0]["names"] == ["柳三娘"]

    def test_no_swaps_no_meta_noise(self, engine, base_state):
        s = base_state
        data = {
            "narrative": "山道无事，一夜平安。",
            "memory": "赶路",
            "delta": {"hp": 0, "qi": 0, "exp": 0, "spirit_stones": 0,
                      "items_add": [], "items_remove": []},
            "choices": [
                {"id": "A", "text": "继续赶路", "risk": "mid", "tag": "explore"},
                {"id": "B", "text": "原地打坐，调息养气", "risk": "low", "tag": "cultivate"},
                {"id": "C", "text": "四下查看，谨慎观察周遭", "risk": "low", "tag": "explore"},
            ],
        }
        meta = {}
        engine._postprocess_turn(s, data, meta, "继续赶路", "explore", tier="mid")
        assert "choice_grounding" not in meta


# ---------------------------------------------------------------- 写死口径（C）

class TestDeathWording:
    def test_stall_note_forbids_gratuitous_death(self, engine, base_state):
        """断干净 ≠ 人死了——收场提示必须把这条口径写明白。"""
        s = base_state
        for _ in range(engine.STALL_FORCE_TURNS):
            engine.update_stall(s, "去寻阿菱")
        note = engine.stall_prompt_note(s)
        assert note is not None
        assert "把人写死" in note
        assert "是谁、何时、何据" in note
        assert "殃及玩家并未在追" in note

    def test_system_prompt_has_death_clause(self, engine):
        assert "断干净不等于把人写死" in engine.SYSTEM_PROMPT


# ---------------------------------------------------------------- 端到端：演武模式两连击

class TestEndToEndCustom:
    def test_two_custom_rounds_open_intent_thread(self, engine, client):
        """自由输入「去寻阿菱」两轮 → 台账里出现「阿菱」线（演武模式，不出网）。"""
        state = {}
        for _ in range(2):
            r = client.post("/api/act", json={
                "state": state,
                "action": {"type": "custom", "text": "去寻阿菱"},
            })
            assert r.status_code == 200
            body = r.json()
            assert body["ok"], body
            state = body["state"]
        titles = [t["title"] for t in state["threads"]]
        assert "阿菱" in titles, f"玩家追了两轮，意图没进台账：{titles}"
        # 提示词的「债」要认得它：build_user_prompt 里必须能列出这条线
        prompt = engine.build_user_prompt(state, {"type": "custom", "text": "去寻阿菱"},
                                          "（判定）无事发生")
        assert "【未决之事】" in prompt and "阿菱" in prompt
