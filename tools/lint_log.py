# -*- coding: utf-8 -*-
"""对局日志体检：把一份导出日志量成一组能判断「叙事到底有没有推进」的数。

为什么要有它
------------
单看一堆 narrative 很容易被骗——写得顺不等于有进展。真正在动的是藏在
`engine_meta` 里的那些计数：开了几条线、收了几条、连续几轮两手空空、
有没有整句照抄上一轮。这些数肉眼数不出来，而「有头无尾」恰恰是它们的函数。

用法
----
    python tools/lint_log.py <日志文件或目录> [--json] [--strict] [--top N]

退出码：0 = 没问题；1 = 出现 ERROR（只在 --strict 下）；2 = 读不到日志。

输入支持两种：`.jsonl`（导出面板里的 JSONL，字段最全，推荐）；
`.txt` / `.md` 也能体检，但这两种导出不含 engine_meta，只能做结构、复读、
重复点击这几项能提取出来的检查（报告会标注「文本模式」）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

# 与 server.py 同源的取值集合。tools 层不 import server（避免拉起 fastapi/openai），
# 由 tests/backend/test_20_lint_log.py 逐条比对，保证两边不被改歪。
# 注意 ACTION_TAGS 比选项里常见的六个多了 "breakthrough"——那是服务端内部标签，
# 偶尔会出现在选项上，放进来是为了不至于误报 ERROR。
ACTION_TAGS = ("cultivate", "rest", "fight", "explore", "trade", "other", "breakthrough")
RISKS = ("low", "mid", "high")
SPANS = ("short", "medium", "long")

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"
LEVEL_ORDER = {ERROR: 0, WARN: 1, INFO: 2}


# ---------------------------------------------------------------- 读入
def parse_jsonl(text: str) -> list:
    """JSONL：一行一条完整记录。空行与坏行跳过（坏行单独丢，别让整份报告挂掉）。"""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            obj.setdefault("partial", False)
            out.append(obj)
    return out


_TXT_TURN_RE = re.compile(r"^—\s*第\s*(\d+)\s*轮\s*·\s*(.+?)\s*·\s*(\d+)\s*岁\s*—\s*$")
_MD_TURN_RE = re.compile(r"^##\s*第\s*(\d+)\s*轮\s*·\s*(.+?)\s*·\s*(\d+)\s*岁\s*/\s*寿元\s*(\d+)\s*$")
_TXT_HEAD_RE = re.compile(r"^本轮选项：\s*(.*)$")
_MD_HEAD_RE = re.compile(r"^-\s*本轮选项：\s*$")
_DELTA_RE = re.compile(r"^变化：\s*(.*)$")
_MD_DELTA_RE = re.compile(r"^-\s*变化：\s*(.*)$")
_CHOICE_RE = re.compile(r"^([A-D])\s+(.*?)(?:（([^）]*?)）)?$")
_DAYS_RE = re.compile(r"天数\s*(\d+)")

_PARTIAL_SNAPSHOT = {"realm": "", "age": 0, "lifespan": 0, "threads": [],
                     "hp": 0, "hp_max": 0, "qi": 0, "qi_max": 0,
                     "exp": 0, "spirit_stones": 0, "items": [], "npcs": []}


def _partial_entry() -> dict:
    return {"partial": True, "engine_meta": {}, "snapshot": dict(_PARTIAL_SNAPSHOT),
            "choices": [], "breakthrough": None, "delta_applied": {},
            "npc_events": [], "action": {"type": "choice", "text": ""}}


def _parse_choices(spec: str) -> list:
    """把「A 上山探索（explore / mid）；B 打坐（cultivate / low / short）」解成选项列表。"""
    out = []
    for piece in spec.split("；"):
        piece = piece.strip()
        if not piece:
            continue
        m = _CHOICE_RE.match(piece)
        if not m:
            continue
        cid, ctext, bits = m.group(1), m.group(2).strip(), m.group(3)
        c = {"id": cid, "text": ctext}
        if bits:
            for p in (x.strip() for x in bits.split("/")):
                if p in ACTION_TAGS:
                    c["tag"] = p
                elif p in RISKS:
                    c["risk"] = p
                elif p in SPANS:
                    c["span"] = p
        out.append(c)
    return out


def parse_text_log(text: str) -> list:
    """尽力解析 txt / md 导出。这类导出没有 engine_meta，只能体检能从文本看出的部分。"""
    md = ("## 第 " in text) or text.lstrip().startswith("# 墨问仙途")
    turn_re = _MD_TURN_RE if md else _TXT_TURN_RE
    out, cur, body = [], None, []

    def flush():
        if cur is not None:
            cur["narrative"] = "\n".join(body).strip()
            out.append(cur)

    for raw in text.splitlines():
        stripped = raw.strip()
        m = turn_re.match(stripped)
        if m:
            flush()
            body = []
            cur = _partial_entry()
            cur["turn"] = int(m.group(1))
            cur["snapshot"]["realm"] = m.group(2).strip()
            cur["snapshot"]["age"] = int(m.group(3))
            if md and m.lastindex and m.lastindex >= 4:
                cur["snapshot"]["lifespan"] = int(m.group(4))
            continue
        if cur is None:
            continue
        if md:
            if stripped.startswith("- 你的选择："):
                cur["action"]["text"] = stripped[len("- 你的选择："):].strip()
            elif _MD_HEAD_RE.match(stripped):
                cur["_in_choices"] = True
            elif cur.get("_in_choices") and stripped.startswith("- "):
                cur["choices"].extend(_parse_choices(stripped[2:].strip()))
                continue
            elif stripped.startswith("- "):
                cur["_in_choices"] = False
        else:
            if stripped.startswith("你的选择："):
                cur["action"]["text"] = stripped[len("你的选择："):].strip()
            elif _TXT_HEAD_RE.match(stripped):
                cur["choices"] = _parse_choices(_TXT_HEAD_RE.match(stripped).group(1))

        m = (_MD_DELTA_RE if md else _DELTA_RE).match(stripped)
        if m:
            dm = _DAYS_RE.search(m.group(1))
            if dm:
                cur["engine_meta"] = {"cultivate": {"days": int(dm.group(1))}}

        if md and stripped.startswith("- 剧情："):
            body.append(stripped[len("- 剧情："):].strip())
        elif stripped and not stripped.startswith(
                ("你的选择：", "本轮选项：", "变化：", "道缘：", "突破：", "剧情：",
                 "未决之事：", "- ", "# ")):
            body.append(raw)
    flush()
    for e in out:
        e.pop("_in_choices", None)
    return out


def load_entries(path: str) -> tuple:
    """读入日志。返回 (entries, format_name)。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.lower().endswith(".jsonl") or not text.lstrip().startswith(("#", "墨问")):
        entries = parse_jsonl(text)
        if entries:
            return entries, "jsonl"
    entries = parse_text_log(text)
    if entries:
        return entries, "md" if "## 第 " in text else "txt"
    return [], "unknown"


# ---------------------------------------------------------------- 检查
def _turn_of(e: dict, i: int) -> int:
    try:
        return int(e.get("turn") or i + 1)
    except Exception:
        return i + 1


def check_choice_schema(entries: list) -> tuple:
    """选项结构：id / tag / risk / span 合法，闭关选项必须带 span。"""
    findings = []
    for i, e in enumerate(entries):
        t = _turn_of(e, i)
        for c in (e.get("choices") or []):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id", "")).strip()
            if cid and cid not in ("A", "B", "C", "D"):
                findings.append((ERROR, "choice_id", t, f"选项 id 非法：{cid}"))
            tag = c.get("tag")
            if tag is not None and tag not in ACTION_TAGS:
                findings.append((ERROR, "choice_tag", t, f"选项 tag 非法：{tag}"))
            risk = c.get("risk")
            if risk is not None and risk not in RISKS:
                findings.append((ERROR, "choice_risk", t, f"选项 risk 非法：{risk}"))
            span = c.get("span")
            if span is not None and span not in SPANS:
                findings.append((ERROR, "choice_span", t, f"选项 span 非法：{span}"))
            if tag == "cultivate" and not span:
                findings.append((ERROR, "missing_span", t,
                                 f"闭关选项缺 span：{str(c.get('text', ''))[:16]}"))
    return findings, {}


def check_state_bounds(entries: list) -> tuple:
    """数值边界：气血/灵力不得越上限、修为与灵石不得为负。"""
    findings = []
    for i, e in enumerate(entries):
        t = _turn_of(e, i)
        s = e.get("snapshot") or {}
        for lo_key, hi_key in (("hp", "hp_max"), ("qi", "qi_max")):
            lo, hi = s.get(lo_key), s.get(hi_key)
            if not isinstance(lo, int) or not isinstance(hi, int) or hi <= 0:
                continue      # 文本模式抓不到这两个数，跳过
            if lo < 0 or lo > hi:
                findings.append((ERROR, "bound", t, f"{lo_key}={lo} 越界（上限 {hi}）"))
        exp = s.get("exp")
        if isinstance(exp, int) and exp < 0:
            findings.append((ERROR, "bound", t, f"修为为负：{exp}"))
        stones = s.get("spirit_stones")
        if isinstance(stones, int) and stones < 0:
            findings.append((ERROR, "bound", t, f"灵石为负：{stones}"))
    return findings, {}


def check_time_consistency(entries: list) -> tuple:
    """时序：叙事与天数跨度不符记一笔；一轮连天数都没有也要报。"""
    findings = []
    no_days, conflicts = 0, 0
    has_any_days = False
    for i, e in enumerate(entries):
        t = _turn_of(e, i)
        meta = e.get("engine_meta") or {}
        days = (meta.get("cultivate") or {}).get("days")
        if isinstance(days, int):
            has_any_days = True
        elif not e.get("partial"):
            no_days += 1
        if meta.get("time_conflict"):
            conflicts += 1
            findings.append((WARN, "time_conflict", t,
                             f"叙事与时序不符：{meta['time_conflict']}"))
    if has_any_days and no_days:
        findings.append((INFO, "days_missing", 0, f"{no_days} 轮没有天数记录"))
    return findings, {"turns_without_days": no_days, "conflicts": conflicts}


def check_threads(entries: list) -> tuple:
    """线索收束：开了几条、了了几条、几条终无下文、收束率多少。"""
    opened, closed, expired, advanced = [], [], [], []
    for e in entries:
        th = ((e.get("engine_meta") or {}).get("threads")) or {}
        for key, bag in (("opened", opened), ("closed", closed),
                         ("expired", expired), ("advanced", advanced)):
            for x in (th.get(key) or []):
                if isinstance(x, str) and x:
                    bag.append(x)
    close_set = set(closed) | set(expired)
    open_total = set(opened)
    # 收束率 = 开过的线里已经了结的比例。**不能**先把已了结的从分母里剔掉再求交集，
    # 那样交集恒为空，收束率永远算成 0 —— 这正是第一版写错的地方。
    rate = (len(open_total & close_set) / len(open_total)) if open_total else None
    findings = []
    if entries and not (opened or closed or expired):
        findings.append((INFO, "threads_missing", 0,
                         "日志中没有线索台账数据（可能未接 AI、或日志版本过旧）"))
    last = entries[-1]
    final_open = {str(t.get("title"))
                  for t in (((last.get("snapshot") or {}).get("threads")) or [])
                  if isinstance(t, dict) and str(t.get("title"))}
    # 遗留 = 开过且没了结的 ∪ 结束时仍在册的，减去已算了结的
    leftover = sorted((open_total | final_open) - close_set)
    end_turn = _turn_of(last, len(entries) - 1)
    for title in leftover:
        findings.append((WARN, "thread_open", end_turn, f"结束时仍有未了线索：{title}"))
    stats = {"opened": len(open_total),
             "closed": len(set(closed) & open_total),
             "expired": len(set(expired) & open_total),
             "advanced_total": len(advanced), "rate": rate, "leftover": leftover,
             "closed_names": sorted(close_set)}
    return findings, stats


def check_stall(entries: list) -> tuple:
    """追索空转：连续几轮探索一无所获，以及天道强行收场的次数。"""
    findings = []
    max_dry, pressed, takeovers = 0, 0, 0
    for i, e in enumerate(entries):
        t = _turn_of(e, i)
        st = ((e.get("engine_meta") or {}).get("stall")) or {}
        if not isinstance(st, dict):
            continue
        max_dry = max(max_dry, int(st.get("dry") or 0))
        if int(st.get("level") or 0) >= 3:
            pressed += 1
        if st.get("takeover"):
            takeovers += 1
            findings.append((INFO, "takeover", t, "天道强行收场（连追数轮仍无结果）"))
    if max_dry >= 5:
        findings.append((WARN, "dry_run", 0, f"最长连续 {max_dry} 轮探索无实质产出"))
    return findings, {"max_dry": max_dry, "pressed_turns": pressed, "takeovers": takeovers}


def check_deja(entries: list) -> tuple:
    """句式复读：engine_meta.deja.hits 的累计（每轮照抄了几个成句）。"""
    findings = []
    total, hit_turns = 0, 0
    for e in entries:
        d = ((e.get("engine_meta") or {}).get("deja")) or {}
        if isinstance(d, dict) and isinstance(d.get("hits"), int):
            total += d["hits"]
            if d["hits"]:
                hit_turns += 1
    stats = {"hits_total": total, "hit_turns": hit_turns}
    if entries and total:
        per = total / len(entries)
        stats["hits_per_turn"] = round(per, 2)
        level = ERROR if per >= 1.0 else (WARN if per >= 0.3 else INFO)
        findings.append((level, "deja_vu", 0,
                         f"累计照抄成句 {total} 句（平均每轮 {per:.2f} 句）"))
    return findings, stats


def check_repeat_clicks(entries: list) -> tuple:
    """同一个行动被连着点了很多轮——往往是选项里没有有效出口，玩家只能复读。"""
    findings = []
    runs, cur_text, cur_n = [], None, 0
    for e in entries:
        txt = str(((e.get("action") or {}).get("text") or "")).strip()
        if txt and txt == cur_text:
            cur_n += 1
        else:
            if cur_n >= 3:
                runs.append((cur_text, cur_n))
            cur_text, cur_n = txt, 1
    if cur_n >= 3:
        runs.append((cur_text, cur_n))
    for txt, n in runs:
        findings.append((WARN, "repeat_click", 0, f"连续 {n} 轮点了同一个行动：{txt[:20]}"))
    return findings, {"runs": len(runs), "max_run": max([n for _, n in runs], default=0)}


def check_ending(entries: list) -> tuple:
    """收尾标记：寿终时空留多少线索没交代。"""
    findings, stats = [], {}
    if not entries:
        return findings, stats
    last = entries[-1]
    meta = last.get("engine_meta") or {}
    dead = bool(meta.get("lifespan_death") or meta.get("explore_death"))
    opened = sum(len(((e.get("engine_meta") or {}).get("threads") or {}).get("opened") or [])
                 for e in entries)
    stats = {"last_turn": _turn_of(last, len(entries) - 1), "dead": dead, "opened_total": opened}
    if dead and opened:
        findings.append((INFO, "ending", stats["last_turn"], f"寿终时共开过 {opened} 条线索"))
    return findings, stats


CHECKS = (
    ("选项结构", check_choice_schema),
    ("数值边界", check_state_bounds),
    ("时序一致", check_time_consistency),
    ("线索收束", check_threads),
    ("追索空转", check_stall),
    ("句式复读", check_deja),
    ("重复点击", check_repeat_clicks),
    ("收尾标记", check_ending),
)


# ---------------------------------------------------------------- 报告
def lint(path: str) -> dict:
    entries, fmt = load_entries(path)
    report = {"file": os.path.basename(path), "format": fmt, "turns": len(entries),
              "findings": [], "stats": {}, "counts": {}}
    if not entries:
        report["findings"].append({"level": ERROR, "kind": "empty", "turn": 0,
                                   "msg": "没有解析出任何一轮日志"})
        report["counts"] = {ERROR: 1}
        return report
    findings = []
    for name, fn in CHECKS:
        fs, st = fn(entries)
        report["stats"][name] = st
        findings.extend(fs)
    findings.sort(key=lambda f: (LEVEL_ORDER.get(f[0], 9), f[2]))
    report["findings"] = [{"level": l, "kind": k, "turn": t, "msg": m} for l, k, t, m in findings]
    report["counts"] = dict(Counter(f[0] for f in findings))
    return report


def render(report: dict, top: int = 8) -> str:
    out = [f"墨问仙途 · 对局日志体检 —— {report['file']}"]
    fmt = report["format"]
    out.append(f"读入 {report['turns']} 轮（格式：{fmt}"
               + ("，文本模式：部分检查不可用）" if fmt != "jsonl" else "）"))
    out.append("")
    out.append("== 体检项 ==")
    th = report["stats"].get("线索收束") or {}
    if th:
        rate = th.get("rate")
        rate_s = "—" if rate is None else f"{rate:.0%}"
        line = (f"  线索收束   开 {th.get('opened', 0)} · 了结 {th.get('closed', 0)}"
                f" · 终无下文 {th.get('expired', 0)} · 收束率 {rate_s}")
        if th.get("leftover"):
            line += f" · 遗留 {len(th['leftover'])} 条"
        out.append(line)
    st = report["stats"].get("追索空转") or {}
    if st:
        out.append(f"  追索空转   最长空转 {st.get('max_dry', 0)} 轮"
                   f" · 触发逼催 {st.get('pressed_turns', 0)} 轮"
                   f" · 天道收场 {st.get('takeovers', 0)} 次")
    dj = report["stats"].get("句式复读") or {}
    if dj:
        line = f"  句式复读   照抄成句 {dj.get('hits_total', 0)} 句 · 命中 {dj.get('hit_turns', 0)} 轮"
        if dj.get("hits_per_turn") is not None:
            line += f" · 均值 {dj['hits_per_turn']}"
        out.append(line)
    rc = report["stats"].get("重复点击") or {}
    if rc:
        out.append(f"  重复点击   连点 {rc.get('runs', 0)} 段 · 最长 {rc.get('max_run', 0)} 轮")
    tc = report["stats"].get("时序一致") or {}
    if tc:
        out.append(f"  时序一致   冲突 {tc.get('conflicts', 0)} 处"
                   f" · 缺天数 {tc.get('turns_without_days', 0)} 轮")
    counts = report.get("counts") or {}
    out.append("")
    out.append(f"== 汇总 ==  ERROR {counts.get(ERROR, 0)} · WARN {counts.get(WARN, 0)}"
               f" · INFO {counts.get(INFO, 0)}")
    fs = report.get("findings") or []
    if fs:
        out.append("")
        out.append(f"== 明细（最多 {top} 条）==")
        for f in fs[:top]:
            where = f"第{f['turn']}轮" if f["turn"] else "全局"
            out.append(f"  [{f['level']:5}] {where} {f['kind']}：{f['msg']}")
        if len(fs) > top:
            out.append(f"  …… 另有 {len(fs) - top} 条")
    else:
        out.append("")
        out.append("  没有问题。")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="墨问仙途 对局日志体检")
    ap.add_argument("path", help="日志文件（.jsonl 推荐，.txt/.md 可部分检查）或目录")
    ap.add_argument("--json", action="store_true", help="输出 json 而非文字报告")
    ap.add_argument("--strict", action="store_true", help="有 ERROR 时以退出码 1 退出")
    ap.add_argument("--top", type=int, default=8, help="明细最多展示几条")
    args = ap.parse_args(argv)

    p = args.path
    if os.path.isdir(p):
        cands = [os.path.join(p, n) for n in sorted(os.listdir(p))
                 if n.lower().endswith((".jsonl", ".txt", ".md"))]
        if not cands:
            print(f"目录里没有日志文件：{p}", file=sys.stderr)
            return 2
        p = cands[-1]
    if not os.path.isfile(p):
        print(f"找不到文件：{p}", file=sys.stderr)
        return 2

    report = lint(p)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report, top=args.top))
    if args.strict and (report.get("counts") or {}).get(ERROR):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
