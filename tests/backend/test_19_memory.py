# -*- coding: utf-8 -*-
"""v3.7 记忆增强：结构化前尘摘要、句内防复读、最近剧情时序标注。

三件事指向同一个病根——AI 看不见自己写过的东西，于是同样的句子、同样的悬事、
同样的因果错位反复出现。这里锁的是「它确实看得见」。
"""
from __future__ import annotations

import pytest


class TestStructuredSummary:
    """前尘摘要不再是自由散文：分栏才能被检索，也才能在下次被拆回来增量更新。"""

    def test_assemble_emits_only_nonempty_sections(self, engine):
        s = engine._assemble_summary({"人": "李慕雪", "地": "", "债": "欠王五一个人情"})
        assert s.count("\n") == 1
        assert "人：李慕雪" in s and "债：" in s
        assert "地：" not in s

    def test_assemble_orders_by_canonical_keys(self, engine):
        s = engine._assemble_summary({"疑": "线索", "人": "某人", "境": "炼气"})
        idx = [s.index(f"{k}：") for k in ("人", "境", "疑")]
        assert idx == sorted(idx)

    def test_assemble_respects_section_and_total_limit(self, engine):
        long = "甲乙丙丁" * 50
        s = engine._assemble_summary({k: long for k in engine.SUMMARY_SECTION_KEYS})
        assert len(s) <= engine.SUMMARY_MAX
        for line in s.splitlines():
            body = line.split("：", 1)[1]
            assert len(body) <= engine.SUMMARY_SECTION_MAX

    def test_assemble_strips_whitespace(self, engine):
        assert engine._assemble_summary({"人": " 李 慕 雪 "}) == "人：李慕雪"

    def test_parse_reads_labeled_text_back(self, engine):
        d = engine._parse_summary("人：李慕雪；王五\n地：青牛山\n债：欠一个人情")
        assert d["人"] == "李慕雪；王五"
        assert d["地"] == "青牛山"
        assert d["得"] == ""

    def test_parse_accepts_halfwidth_colon(self, engine):
        d = engine._parse_summary("人: 李慕雪")
        assert d["人"] == "李慕雪"

    def test_parse_falls_back_for_legacy_prose(self, engine):
        """老档是整段散文（没有栏名），不能因为格式变了就把旧事丢掉。"""
        prose = "早年独守青牛山破庙三年，与李慕雪相识于微时。"
        d = engine._parse_summary(prose)
        assert d["境"] == prose
        assert d["人"] == ""

    def test_parse_of_empty_is_all_empty(self, engine):
        d = engine._parse_summary("")
        assert not any(d.values())

    def test_roundtrip_preserves_content(self, engine):
        parts = {"人": "李慕雪", "债": "欠王五人情", "疑": "溪畔女子下落不明"}
        again = engine._parse_summary(engine._assemble_summary(parts))
        for k, v in parts.items():
            assert again[k] == v

    def test_parse_is_injection_resistant(self, engine):
        """栏名之外的东西一律不认，脏数据不会污染摘要。"""
        d = engine._parse_summary("游客 trash\n人：真内容")
        assert d["人"] == "真内容"
        assert "trash" not in d.values()

    def test_struct_summary_offline_returns_empty(self, engine):
        """无 key（测试环境恒如此）→ 空串，由调用方走规则兜底。"""
        assert engine._struct_summary("前尘旧事", ["新事一"]) == ""

    def test_historian_summary_falls_back_offline(self, engine):
        out = engine._historian_summary("前尘旧事", ["加入青云宗"])
        assert "前尘旧事" in out and "青云宗" in out

    @pytest.mark.parametrize("bad", [None, [], 123, {"summary": 1}])
    def test_summary_never_explodes_on_junk(self, engine, bad):
        s = engine._historian_summary("前尘", ["a"]) if bad is None else engine._assemble_summary(bad)
        assert isinstance(s, str)


class TestDejaVu:
    """句内防复读：开篇已经禁了，真正让玩家出戏的是段落里的原句搬运。"""

    def test_sentences_filters_by_length(self, engine):
        text = "短句。这里是一句长度合适的话。太长了" + "啊" * 60
        got = engine._sentences(text)
        assert all(engine.DEJA_MIN <= len(s) <= engine.DEJA_MAX for s in got)
        assert "短句" not in got

    def test_sentences_strips_punctuation(self, engine):
        got = engine._sentences("你沿着溪岸走了半日，只捡到一片残药纸！")
        assert got and all("，" not in s and "！" not in s for s in got)

    def test_update_deja_dedupes(self, engine, base_state):
        engine.update_deja(base_state, "你沿着溪岸走了半日，只捡到一片残药纸。")
        n = len(base_state["deja"])
        engine.update_deja(base_state, "你沿着溪岸走了半日，只捡到一片残药纸。")
        assert len(base_state["deja"]) == n

    def test_update_deja_keeps_only_window(self, engine, base_state):
        for i in range(engine.DEJA_KEEP + 6):
            engine.update_deja(base_state, f"这是第{i}轮发生的一段事情记述。")
        assert len(base_state["deja"]) == engine.DEJA_KEEP
        # 入库时标点已被剥掉，比对要按归一化后的样子来
        assert base_state["deja"][-1] == f"这是第{engine.DEJA_KEEP + 5}轮发生的一段事情记述"

    def test_hits_detects_copied_sentence(self, engine, base_state):
        line = "你沿着溪岸走了半日，只捡到一片残药纸。"
        engine.update_deja(base_state, line)
        assert len(engine.deja_hits(base_state, line + "别的东西不过是另外一句话。")) == 1

    def test_hits_ignores_rewritten_sentence(self, engine, base_state):
        engine.update_deja(base_state, "你沿着溪岸走了半日，只捡到一片残药纸。")
        assert engine.deja_hits(base_state, "溪畔无人，唯有风吹苇动，此事说来话长。") == []

    def test_hits_before_update_does_not_self_match(self, engine, base_state):
        """命中必须先于入库计算，否则本轮会命中自己，复读率永远虚高。"""
        line = "清晨的山雾尚未散去，你踏上石阶。"
        assert engine.deja_hits(base_state, line) == []
        engine.update_deja(base_state, line)
        assert len(engine.deja_hits(base_state, line)) == 1

    def test_hits_tolerates_missing_key(self, engine):
        assert engine.deja_hits({}, "随便一句话而已不管它长短。") == []

    def test_sanitize_caps_deja(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "deja": ["成句" * 30 for _ in range(80)]})
        assert len(s["deja"]) <= engine.DEJA_KEEP
        assert all(len(x) <= engine.DEJA_MAX for x in s["deja"])

    def test_sanitize_drops_junk_deja_entries(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "deja": ["", "  ", None, 123, "有效的一句话在这里"]})
        assert "有效的一句话在这里" in s["deja"]


class TestRecentTimeline:
    """最近剧情必须带轮次与天数，否则 AI 分不出先后、也看不出隔了多久。"""

    def test_prompt_marks_turn_and_days(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "recent": [
            {"action": "入山", "narrative": "走了很久", "turn": 7, "days": 45}]})
        p = engine.build_user_prompt(s, {}, "判定")
        assert "第7轮" in p and "历时45天" in p

    def test_prompt_omits_zero_days(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "recent": [
            {"action": "入山", "narrative": "走了很久", "turn": 7, "days": 0}]})
        p = engine.build_user_prompt(s, {}, "判定")
        assert "第7轮" in p and "历时0天" not in p

    def test_sanitize_defaults_missing_turn_days(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "recent": [{"action": "a", "narrative": "b"}]})
        assert s["recent"][0]["turn"] == 0 and s["recent"][0]["days"] == 0

    def test_sanitize_clamps_injected_turn_days(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "recent": [
            {"action": "a", "narrative": "b", "turn": -3, "days": 10 ** 9}]})
        assert s["recent"][0]["turn"] == 0
        assert s["recent"][0]["days"] <= 99999

    def test_postprocess_stamps_this_turn(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "turn": 9})
        engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": "剧情"},
                                 {}, "行动", "explore", pre_roll=(0, 33, 1.0))
        assert s["recent"][-1]["turn"] == 10
        assert s["recent"][-1]["days"] == 33

    def test_postprocess_records_deja_hits(self, engine, base_state):
        line = "你沿着溪岸走了半日，只捡到一片残药纸。"
        s = engine.sanitize_state(base_state)
        engine.update_deja(s, line)
        meta = {}
        engine._postprocess_turn(s, {"delta": {}, "choices": [], "narrative": line},
                                 meta, "行动", "explore", pre_roll=(0, 10, 1.0))
        assert meta["deja"]["hits"] == 1
        assert meta["deja"]["kept"] >= 1


class TestPromptWiring:
    def test_sentence_ban_injected_when_deja_exists(self, engine, base_state):
        s = engine.sanitize_state({**base_state, "deja": ["你沿着溪岸走了半日只捡到一片残药纸"]})
        assert "句式禁用" in engine.build_user_prompt(s, {}, "判定")

    def test_sentence_ban_absent_when_clean(self, engine, base_state):
        assert "句式禁用" not in engine.build_user_prompt(base_state, {}, "判定")

    def test_opening_ban_still_works(self, engine, base_state):
        s = {**base_state, "style_echo": ["清晨的山雾"]}
        assert "文风禁用" in engine.build_user_prompt(s, {}, "判定")

    def test_recent_header_preserved(self, engine, base_state):
        s = {**base_state, "recent": [{"action": "赶路", "narrative": "走了"}]}
        assert "最近剧情" in engine.build_user_prompt(s, {}, "判定")
