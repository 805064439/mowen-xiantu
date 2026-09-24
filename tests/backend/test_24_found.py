# -*- coding: utf-8 -*-
"""追索的终点必须是「找着人」（v3.12）。

用户原话：「我希望结果是可以找得到这个人物，并不是说这个人物突然间就死了或者是
失踪了，再找不到什么的。」

日志实证：2026-09-23 那一局，AI 用「柳三娘殁于腊月十九」加一块无字木牌，把九轮追索
了结了；2026-09-24 那一局，同一个人追了 9 轮，一次面都没照上。旧口径只说
「写死须交代凭据」——AI 照着做照样能把人写死，而代码兜底句本身就是
「再无下落，此事就此划去」。两头都不给活人。

现在：
  · 提示词只留一条路——让这个人出场，写花坟/失踪一概列为严禁；
  · 代码兜底句必须是「人已寻着」，整套收场文案里不许出现任何一个死讯词；
  · 摘到的大事记若含死讯，作废，退回中性照面句；
  · 接管不再注销线索，而是转成「当面在此」留在册上——注销等于这件事没了。
"""
from __future__ import annotations

TAIL_DEAD = "第8轮 · 苏禾：柳三娘殁于腊月十九，只余一块无字木牌"
TAIL_DEAD2 = "第9轮 · 苏禾：苏禾下落不明，恐怕早已过世"
TAIL_ALIVE = "第8轮 · 苏禾：人说她去了岳州港，明早还从这里上船"


def _run(engine, s, data, meta, action):
    return engine._postprocess_turn(s, data, meta, action, "explore", tier="mid")


def _takeover(engine, s, chronicle_tail=None, action="去寻苏禾"):
    """把计数堆到接管阈值并跑一轮；chronicle_tail 模拟 AI 刚写下的那一句收尾。"""
    s["chronicle"] = [chronicle_tail] if chronicle_tail else []
    for _ in range(engine.STALL_TAKEOVER_TURNS):
        engine.update_stall(s, action)
    meta: dict = {}
    narrative, choices, *_ = _run(engine, s, {
        "delta": {}, "narrative": "仍未寻着。", "memory": "",
        "choices": [{"id": "A", "text": "就地打坐", "risk": "low", "tag": "cultivate"},
                    {"id": "B", "text": "再往东去寻", "risk": "mid", "tag": "explore"},
                    {"id": "C", "text": "问那老丈", "risk": "mid", "tag": "explore"}],
    }, meta, action)
    return meta, narrative, choices


# ---------------------------------------------------------------- 死讯识别
class TestDeadEndFilter:
    def test_one_tombstone_is_a_dead_end(self, engine):
        """「柳三娘殁于腊月十九，只余一块无字木牌」——典型的一座坟打发九轮追索。"""
        assert engine.is_dead_end_line("柳三娘殁于腊月十九，只余一块无字木牌") is True

    def test_missing_or_untraceable_is_a_dead_end(self, engine):
        for s in ("人早已失踪", "下落不明", "查无此人", "此后音讯断绝", "就此划去"):
            assert engine.is_dead_end_line(s) is True, f"漏判：{s}"

    def test_the_20260925_online_leak_is_a_dead_end(self, engine):
        """线上抓到的原句：这句被当成有效线索摘进了收场句，与「当面见了」并存。

        2026-09-25 v3.12.1 验证时，收场句是
        「这一趟没有落空，当面见了——寻着柳三娘，得素银簪，菱姑已三年无音信」。
        「只堵杳无音信」是不够的，AI 换个说法就绕过去了，这一族要成对堵。
        """
        leak = "寻着柳三娘，得素银簪，菱姑已三年无音信"
        assert engine.is_dead_end_line(leak) is True
        for s in ("菱姑无音信", "音信全无", "再无消息", "不见踪影", "踪影全无"):
            assert engine.is_dead_end_line(s) is True, f"漏判：{s}"

    def test_a_lead_is_not_a_dead_end(self, engine):
        """「她去了岳州港」是有去处的活线索，别把它跟死讯一起滤掉。"""
        assert engine.is_dead_end_line("人说她去了岳州港，明早还从这里上船") is False

    def test_last_clue_line_drops_the_death_notice(self, engine, base_state):
        base_state["chronicle"] = [TAIL_DEAD]
        assert engine.last_clue_line(base_state) == ""

    def test_last_clue_line_keeps_a_real_lead(self, engine, base_state):
        base_state["chronicle"] = [TAIL_ALIVE]
        assert "岳州港" in engine.last_clue_line(base_state)


# ---------------------------------------------------------------- 收场给的是活人
class TestTakeoverGivesALivePerson:
    def test_even_a_tombstone_note_yields_a_meeting(self, engine, base_state):
        """AI 那一句即便已经写了死讯，代码兜底也不替它宣布——收场句必须是找着了人。"""
        meta, narrative, _ = _takeover(engine, base_state, TAIL_DEAD)
        assert meta["stall"]["takeover"] is True
        line = meta["stall_takeover"]["line"]
        assert engine.is_dead_end_line(line) is False, f"兜底句里传出死讯：{line}"
        assert any(c.endswith(line) for c in base_state["chronicle"]), "收场句没进大事记"

    def test_missing_note_also_yields_a_meeting(self, engine, base_state):
        meta, _, _ = _takeover(engine, base_state, TAIL_DEAD2)
        line = meta["stall_takeover"]["line"]
        assert engine.is_dead_end_line(line) is False, f"兜底句里传出失踪：{line}"

    def test_narrative_says_the_person_is_right_there(self, engine, base_state):
        meta, narrative, _ = _takeover(engine, base_state)
        tail = narrative[len("仍未寻着。"):]
        assert len(tail) > 0
        assert engine.is_dead_end_line(tail) is False
        assert any(w in tail for w in ("就在前头", "寻着", "见面", "找着")), tail

    def test_all_takeover_wordings_are_free_of_death(self, engine):
        """这是硬约束：整套收场文案里一个死讯词都不许有。"""
        pool = list(engine.STALL_TAKEOVER_LINES) + [
            engine.STALL_TAKEOVER_LINE_FALLBACK, engine.STALL_TAKEOVER_TEXT,
            engine.STALL_TAKEOVER_ITEM_TEXT]
        for t in pool:
            assert engine.is_dead_end_line(t) is False, f"收场文案沾了死讯：{t}"

    def test_found_notice_is_not_a_dead_end(self, engine):
        """留在线上的那句标记也得是活人语气。"""
        assert engine.is_dead_end_line(engine.STALL_FOUND_NOTE) is False


# ---------------------------------------------------------------- 人找着了，线要留下
class TestThreadStaysFound:
    def test_thread_is_kept_and_marked(self, engine, base_state):
        engine.apply_thread_updates(
            base_state, {"thread_updates": [{"op": "open", "title": "苏禾", "note": "采药人"}]})
        _takeover(engine, base_state)
        assert len(base_state["threads"]) == 1, "人找着了，这条线不该从台账上消失"
        th = base_state["threads"][0]
        assert th["found"] == 1
        assert th["note"] == engine.STALL_FOUND_NOTE

    def test_found_thread_is_no_longer_chased(self, engine, base_state):
        """照过面就不该再被当成新一轮追索——否则下一轮又从头数五轮。"""
        engine.apply_thread_updates(
            base_state, {"thread_updates": [{"op": "open", "title": "苏禾", "note": "采药人"}]})
        _takeover(engine, base_state)
        base_state["threads"][0]["chase"] = 3        # 就算还有旧计数也不算数
        assert engine.top_chase_thread(base_state) is None

    def test_found_survives_sanitize(self, engine, base_state):
        engine.apply_thread_updates(
            base_state, {"thread_updates": [{"op": "open", "title": "苏禾", "note": "采药人"}]})
        _takeover(engine, base_state)
        clean = engine.sanitize_state(dict(base_state))
        assert clean["threads"][0]["found"] == 1


# ---------------------------------------------------------------- 找到了就得能说话
class TestTakeoverOffersATalk:
    def test_second_choice_is_going_up_to_them(self, engine, base_state):
        engine.apply_thread_updates(
            base_state, {"thread_updates": [{"op": "open", "title": "苏禾", "note": "采药人"}]})
        _, _, choices = _takeover(engine, base_state)
        assert "苏禾" in choices[1]["text"], f"没给说话的入口：{[c['text'] for c in choices]}"
        assert "搭话" in choices[1]["text"]

    def test_no_name_still_offers_a_talk(self, engine):
        """台账标题取不出人名时也得给一条台阶，不能退回泛行程。"""
        out = engine.takeover_choices(
            [{"id": "A", "text": "往北追访", "risk": "mid", "tag": "explore"},
             {"id": "B", "text": "再探下落", "risk": "mid", "tag": "explore"}], "", "追查某人")
        assert "照面" in out[1]["text"], out[1]["text"]


# ---------------------------------------------------------------- 追的是物，别请它搭话
# 2026-09-25 线上实测（v3.12 验证）：AI 这局立的线是「渡口残图」「芦荡废坞」——
# 收场那轮于是给出「上前与渡口残图搭话，当面问个明白」。收场文案只认「人」，
# 遇上追物/追地的线就当场出戏，比不收场还伤。
class TestTakeoverKnowsAThingFromAPerson:
    def test_people_are_people(self, engine):
        for s in ("苏禾", "阿菱", "溪畔女子", "渡口船家", "西市旧画人", "柳三娘"):
            assert engine._looks_like_person(s) is True, f"把人当成了物：{s}"

    def test_things_and_places_are_not_people(self, engine):
        for s in ("渡口残图", "芦荡废坞", "沉沙坞", "无名木牌", "此事", ""):
            assert engine._looks_like_person(s) is False, f"把物当成了人：{s}"

    def test_a_thing_gets_a_look_not_a_talk(self, engine):
        out = engine.takeover_choices(
            [{"id": "A", "text": "往北追访", "risk": "mid", "tag": "explore"},
             {"id": "B", "text": "再探下落", "risk": "mid", "tag": "explore"}],
            "渡口残图", "按图寻去")
        joined = "".join(str(c.get("text") or "") for c in out)
        assert "搭话" not in joined, f"请一张残图去搭话：{joined}"
        assert "细看明白" in out[1]["text"], out[1]["text"]

    def test_a_thing_line_gets_the_thing_narration(self, engine, base_state):
        # label 由 update_stall 从 action 取，故这里把「追的东西」直接当行动传进去——
        # 传一句「去寻苏禾」会让 label 变成人名，这条测试就白测了。
        engine.apply_thread_updates(
            base_state, {"thread_updates": [{"op": "open", "title": "渡口残图", "note": "半角残纸"}]})
        _, narrative, choices = _takeover(engine, base_state, action="渡口残图")
        assert engine.STALL_TAKEOVER_ITEM_TEXT in narrative, narrative[-80:]
        assert engine.STALL_TAKEOVER_TEXT not in narrative
        assert "搭话" not in "".join(str(c.get("text") or "") for c in choices)

    def test_a_person_line_gets_the_person_narration(self, engine, base_state):
        engine.apply_thread_updates(
            base_state, {"thread_updates": [{"op": "open", "title": "苏禾", "note": "采药人"}]})
        _, narrative, choices = _takeover(engine, base_state, action="苏禾")
        assert engine.STALL_TAKEOVER_TEXT in narrative, narrative[-80:]
        assert engine.STALL_TAKEOVER_ITEM_TEXT not in narrative
        assert "搭话" in choices[1]["text"], choices[1]["text"]
