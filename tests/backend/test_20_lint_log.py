# -*- coding: utf-8 -*-
"""tools/lint_log.py 日志体检。

这个工具是给「叙事到底有没有推进」定量的——所以它自己必须先准，
否则收束率、空转率、复读率三个数一错，基于它们的判断全废。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def lint():
    spec = importlib.util.spec_from_file_location("lint_log", ROOT / "tools" / "lint_log.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def snap(**kw):
    """一条合格的状态快照（不写全 key 的检查项会自动跳过，见各 check 的守卫）。"""
    base = {"realm": "炼气一层", "age": 21, "lifespan": 95, "threads": [],
            "hp": 50, "hp_max": 100, "qi": 20, "qi_max": 50,
            "exp": 10, "spirit_stones": 30, "items": [], "npcs": []}
    base.update(kw)
    return base


def entry(turn=1, **kw):
    e = {"i": turn, "turn": turn, "partial": False, "action": {"type": "choice", "text": "上山"},
         "narrative": "你沿着溪岸走了半日。", "choices": [], "delta_applied": {},
         "npc_events": [], "breakthrough": None, "engine_meta": {}, "snapshot": snap()}
    e.update(kw)
    return e


def write_log(tmp_path, entries, name="log.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
                 encoding="utf-8")
    return str(p)


class TestConstantsMirrorServer:
    """取值集合必须与 server 一致：改一边忘另一边会让体检结论失真。"""

    def test_action_tags(self, engine, lint):
        assert lint.ACTION_TAGS == engine.VALID_TAGS

    def test_risks(self, engine, lint):
        assert lint.RISKS == engine.VALID_RISK

    def test_spans(self, engine, lint):
        assert set(lint.SPANS) == set(engine.CULTIVATE_SPAN.keys())


class TestParsing:
    def test_parse_jsonl(self, lint):
        text = json.dumps(entry(1)) + "\n\n" + json.dumps(entry(2)) + "\n"
        got = lint.parse_jsonl(text)
        assert [e["turn"] for e in got] == [1, 2]

    def test_parse_jsonl_skips_broken_lines(self, lint):
        text = "not json at all\n" + json.dumps(entry(1)) + "\n{broken\n"
        assert len(lint.parse_jsonl(text)) == 1

    def test_parse_jsonl_ignores_non_objects(self, lint):
        assert lint.parse_jsonl("[1,2]\n\"str\"\n") == []

    def test_parse_choices_reads_tag_risk_span(self, lint):
        got = lint._parse_choices("A 上山（explore / mid）；B 打坐（cultivate / low / short）")
        assert got[0]["tag"] == "explore" and got[0]["risk"] == "mid"
        assert got[1]["tag"] == "cultivate" and got[1]["span"] == "short"

    def test_parse_choices_without_parens(self, lint):
        got = lint._parse_choices("A 什么也不做")
        assert got == [{"id": "A", "text": "什么也不做"}]

    def test_parse_text_log_txt(self, lint, tmp_path):
        text = (
            "墨问仙途 · 对局日志（2 轮）\n\n"
            "— 第 12 轮 · 炼气一层 · 21岁 —\n"
            "你的选择：C 再去溪畔寻那女子踪迹\n"
            "本轮选项：A 就此罢手（other / low）；B 打坐（cultivate / low / short）\n"
            "变化：修为 +3 · 天数 45（半月到一月）\n"
            "溪水很凉。你什么也没找到。\n\n"
            "— 第 13 轮 · 炼气一层 · 21岁 —\n"
            "你的选择：C 再去溪畔寻那女子踪迹\n"
            "变化：修为 +1\n"
            "又是一日无功而返。\n"
        )
        p = tmp_path / "a.txt"
        p.write_text(text, encoding="utf-8")
        entries, fmt = lint.load_entries(str(p))
        assert fmt == "txt" and len(entries) == 2
        assert entries[0]["turn"] == 12
        assert entries[0]["action"]["text"] == "C 再去溪畔寻那女子踪迹"
        assert entries[0]["choices"][0]["tag"] == "other"
        assert entries[0]["choices"][1]["span"] == "short"
        assert entries[0]["engine_meta"]["cultivate"]["days"] == 45

    def test_load_entries_prefers_jsonl(self, lint, tmp_path):
        p = write_log(tmp_path, [entry(1), entry(2)])
        entries, fmt = lint.load_entries(p)
        assert fmt == "jsonl" and len(entries) == 2

    def test_load_entries_on_garbage(self, lint, tmp_path):
        p = tmp_path / "x.jsonl"
        p.write_text("完全不是日志\n", encoding="utf-8")
        entries, fmt = lint.load_entries(str(p))
        assert entries == [] and fmt == "unknown"


class TestChoiceSchema:
    def test_illegal_tag_reported(self, lint):
        f, _ = lint.check_choice_schema([entry(1, choices=[{"id": "A", "text": "x", "tag": "run"}])])
        assert any(x[1] == "choice_tag" and x[0] == lint.ERROR for x in f)

    def test_illegal_risk_reported(self, lint):
        f, _ = lint.check_choice_schema([entry(1, choices=[{"id": "A", "text": "x", "risk": "extreme"}])])
        assert any(x[1] == "choice_risk" for x in f)

    def test_cultivate_without_span_reported(self, lint):
        """闭关选项缺 span 会让「一个周天」吃成五年，必须报错。"""
        f, _ = lint.check_choice_schema(
            [entry(1, choices=[{"id": "A", "text": "行功周天", "tag": "cultivate"}])])
        assert any(x[1] == "missing_span" for x in f)

    def test_cultivate_with_span_passes(self, lint):
        f, _ = lint.check_choice_schema(
            [entry(1, choices=[{"id": "A", "text": "行功周天", "tag": "cultivate", "span": "short"}])])
        assert f == []

    def test_clean_log_is_silent(self, lint):
        f, _ = lint.check_choice_schema([
            entry(1, choices=[{"id": "A", "text": "x", "tag": "explore", "risk": "mid"}])])
        assert f == []


class TestStateBounds:
    def test_hp_over_max_reported(self, lint):
        f, _ = lint.check_state_bounds([entry(1, snapshot=snap(hp=150, hp_max=100))])
        assert any(x[1] == "bound" for x in f)

    def test_negative_stones_reported(self, lint):
        f, _ = lint.check_state_bounds([entry(1, snapshot=snap(spirit_stones=-5))])
        assert any("灵石为负" in x[3] for x in f)

    def test_text_mode_missing_bounds_is_skipped(self, lint):
        """文本模式抓不到 hp_max，就不该一整份日志全是假 ERROR。"""
        f, _ = lint.check_state_bounds([entry(1, snapshot={"threads": []})])
        assert f == []


class TestThreads:
    def test_rate_counts_only_resolved_among_opened(self, lint):
        es = [
            entry(1, engine_meta={"threads": {"opened": ["甲", "乙"], "closed": [], "expired": []}}),
            entry(2, engine_meta={"threads": {"opened": [], "closed": ["甲"], "expired": []}}),
        ]
        _, st = lint.check_threads(es)
        assert st["opened"] == 2 and st["closed"] == 1 and st["rate"] == 0.5

    def test_expired_counts_as_resolved(self, lint):
        es = [entry(1, engine_meta={"threads": {"opened": ["甲"], "closed": [], "expired": ["甲"]}})]
        _, st = lint.check_threads(es)
        assert st["rate"] == 1.0

    def test_leftover_reported(self, lint):
        es = [entry(9, engine_meta={"threads": {"opened": ["溪畔女子"], "closed": [], "expired": []}},
                    snapshot=snap(threads=[{"title": "溪畔女子"}]))]
        f, st = lint.check_threads(es)
        assert st["leftover"] == ["溪畔女子"]
        assert any(x[1] == "thread_open" for x in f)

    def test_no_thread_data_is_informative_not_error(self, lint):
        f, _ = lint.check_threads([entry(1)])
        assert all(x[0] == lint.INFO for x in f)


class TestStallAndRepetition:
    def test_long_dry_streak_warned(self, lint):
        es = [entry(i, engine_meta={"stall": {"dry": i, "level": i}}) for i in range(1, 7)]
        f, st = lint.check_stall(es)
        assert st["max_dry"] == 6
        assert any(x[1] == "dry_run" for x in f)

    def test_takeover_counted(self, lint):
        es = [entry(5, engine_meta={"stall": {"level": 5, "takeover": True, "dry": 0}})]
        f, st = lint.check_stall(es)
        assert st["takeovers"] == 1

    def test_repeat_clicks_detected(self, lint):
        es = [entry(i, action={"text": "再去找那位青衣少女"}) for i in range(1, 5)]
        es += [entry(5, action={"text": "回头算了"})]
        f, st = lint.check_repeat_clicks(es)
        assert st["max_run"] == 4 and st["runs"] == 1

    def test_two_repeats_is_tolerated(self, lint):
        """连点两轮不算毛病——有时玩家的坚持是有道理的。"""
        f, st = lint.check_repeat_clicks([entry(i, action={"text": "同上"}) for i in range(1, 3)])
        assert st["runs"] == 0

    def test_deja_hits_accumulated(self, lint):
        es = [entry(1, engine_meta={"deja": {"hits": 2}}), entry(2, engine_meta={"deja": {"hits": 0}})]
        f, st = lint.check_deja(es)
        assert st["hits_total"] == 2 and st["hit_turns"] == 1
        assert st["hits_per_turn"] == 1.0

    def test_deja_per_turn_drives_level(self, lint):
        es = [entry(1, engine_meta={"deja": {"hits": 0}})] * 4
        es.append(entry(5, engine_meta={"deja": {"hits": 1}}))
        f, st = lint.check_deja(es)
        assert any(x[0] == lint.INFO for x in f)


class TestEndToEnd:
    def test_lint_on_clean_log(self, lint, tmp_path):
        p = write_log(tmp_path, [
            entry(1, engine_meta={"cultivate": {"days": 3}, "threads": {"opened": ["甲"], "closed": []}}),
            entry(2, engine_meta={"cultivate": {"days": 7}, "threads": {"opened": [], "closed": ["甲"]}}),
        ])
        rep = lint.lint(p)
        assert rep["turns"] == 2 and rep["format"] == "jsonl"
        assert rep["counts"].get(lint.ERROR, 0) == 0

    def test_lint_reports_empty_file(self, lint, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("\n\n", encoding="utf-8")
        rep = lint.lint(str(p))
        assert rep["counts"][lint.ERROR] == 1
        assert rep["findings"][0]["kind"] == "empty"

    def test_render_contains_key_sections(self, lint, tmp_path):
        p = write_log(tmp_path, [entry(1, engine_meta={
            "cultivate": {"days": 45}, "threads": {"opened": ["甲"], "closed": ["甲"]}})])
        out = lint.render(lint.lint(p))
        for sec in ("线索收束", "追索空转", "句式复读", "重复点击", "时序一致", "== 汇总 =="):
            assert sec in out

    def test_render_notes_text_mode(self, lint, tmp_path):
        p = tmp_path / "a.txt"
        p.write_text("— 第 1 轮 · 炼气一层 · 21岁 —\n你的选择：上山\n变化：无增减\n走了很久。\n",
                     encoding="utf-8")
        out = lint.render(lint.lint(str(p)))
        assert "文本模式" in out

    def test_main_strict_exit_code(self, lint, tmp_path):
        good = write_log(tmp_path, [entry(1)], name="good.jsonl")
        assert lint.main([good, "--strict"]) == 0
        bad = write_log(tmp_path, [entry(1, choices=[{"id": "Z", "text": "x"}])], name="bad.jsonl")
        assert lint.main([bad, "--strict"]) == 1
        assert lint.main([bad]) == 0     # 不加 --strict 就只看报告

    def test_main_missing_file(self, lint, tmp_path):
        assert lint.main([str(tmp_path / "nope.jsonl")]) == 2

    def test_main_json_output(self, lint, tmp_path, capsys):
        p = write_log(tmp_path, [entry(1)])
        lint.main([p, "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["turns"] == 1 and "counts" in data

    def test_main_reads_directory(self, lint, tmp_path, capsys):
        write_log(tmp_path, [entry(1), entry(2)], name="a.jsonl")
        assert lint.main([str(tmp_path)]) == 0
        assert "读入 2 轮" in capsys.readouterr().out
