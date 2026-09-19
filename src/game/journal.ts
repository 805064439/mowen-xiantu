/* 对局日志：把每一轮的「剧情 + 选项 + 数值」落到独立的 localStorage 键。

   为什么独立：进存档会让 mowen_save_v1 与仙缘令随轮数膨胀（每轮数百字），
   而「每一轮都留一份」只对排查与离线测试有意义，不该塞进玩家随身的行囊。
   所以这里自成一袋——不进 state、不进仙缘令、不参与 sanitize_state，
   localStorage 写失败一律静默，绝不影响主线（游戏照常进行，只是少了日志）。
*/
import type { GameState, Choice, GameAction, ActResponse } from "./types";
import { REALMS } from "./constants";

export const JOURNAL_KEY = "mowen_journal_v1";
export const JOURNAL_MAX = 300;                 // 最多留住多少轮（超出丢最旧）
export const JOURNAL_BYTES_MAX = 1_500_000;     // 总量封顶 ≈1.5MB（配额通常 5MB）
export const JOURNAL_MIN_KEEP = 20;             // 体积再紧张也要留住这么多轮
const SID_KEY = "mowen_journal_sid";            // 当前这一世的日志批次号

export interface JournalEntry {
  i: number;              // 序号（从 1 起）
  ts: number;             // 时间戳
  sid: string;            // 批次号（再入轮回会换号，便于跨轮回对比）
  turn: number;           // 后端轮次
  action: { type?: string; id?: string; text?: string; tag?: string; risk?: string; span?: string };
  narrative: string;      // 本轮完整剧情（不截断）
  choices: Choice[];      // 本轮给出的全部选项
  delta_applied: ActResponse["delta_applied"];
  npc_events?: ActResponse["npc_events"];
  breakthrough: ActResponse["breakthrough"];
  engine_meta: ActResponse["engine_meta"];
  snapshot: {
    realm: string; hp: number; hp_max: number; qi: number; qi_max: number;
    exp: number; spirit_stones: number; age: number; lifespan: number;
    items: { name: string; qty: number; rarity?: string }[];
    npcs: { name: string; title: string; bond: number }[];
  };
}

type JournalList = JournalEntry[];

/* ---------------- 批次号 ---------------- */
function currentSid(): string {
  try {
    let s = localStorage.getItem(SID_KEY);
    if (!s) {
      s = "S" + Date.now().toString(36);
      localStorage.setItem(SID_KEY, s);
    }
    return s;
  } catch (e) {
    return "S0";
  }
}

/** 再入轮回：换新批次号，日志本身保留（跨轮回对比正是测试要的） */
export function rotateSession(): string {
  // 结尾拼一段随机：同毫秒内连续调用也要拿到不同的号
  const s = "S" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  try { localStorage.setItem(SID_KEY, s); } catch (e) { /* 忽略 */ }
  return s;
}

/* ---------------- 读写 ---------------- */
export function loadJournal(): JournalList {
  try {
    const raw = localStorage.getItem(JOURNAL_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list as JournalList : [];
  } catch (e) {
    return [];
  }
}

function writeJournal(list: JournalList): void {
  try { localStorage.setItem(JOURNAL_KEY, JSON.stringify(list)); } catch (e) { /* 配额满：静默 */ }
}

export function clearJournal(): void {
  try { localStorage.removeItem(JOURNAL_KEY); } catch (e) { /* 忽略 */ }
}

/** 体积超限就从头丢，直到装得下（至少保留最近 20 轮） */
function byteLen(list: JournalList): number {
  try { return JSON.stringify(list).length; } catch (e) { return 0; }
}

/** 先按条数封顶；体积还超就从最旧开始丢，实在挤不下就把早期剧情截短。 */
function trimTo(list: JournalList): JournalList {
  let out = list.slice(Math.max(0, list.length - JOURNAL_MAX));
  while (out.length > JOURNAL_MIN_KEEP && byteLen(out) > JOURNAL_BYTES_MAX) {
    out = out.slice(Math.max(1, Math.floor(out.length / 10)));   // 每次丢一成
  }
  if (byteLen(out) > JOURNAL_BYTES_MAX && out.length > 5) {
    // 条数已压到下限仍超预算：给早期的剧情截短，保住最近几轮的完整
    const keepFull = Math.min(5, out.length);
    out = out.map((e, i) => (i >= out.length - keepFull
      ? e
      : { ...e, narrative: String(e.narrative || "").slice(0, 120) + "…（日志超限，剧情已截断）" }));
    while (out.length > 5 && byteLen(out) > JOURNAL_BYTES_MAX) out = out.slice(1);
  }
  return out;
}

/** 记一轮。action 为玩家本轮输入，d 为后端本轮响应。 */
export function appendTurn(action: GameAction | null, d: ActResponse): void {
  const s = (d.state || {}) as GameState;
  const prev = loadJournal();
  const entry: JournalEntry = {
    i: (prev.length ? prev[prev.length - 1].i : 0) + 1,
    ts: Date.now(),
    sid: currentSid(),
    turn: Number(s.turn ?? 0),
    action: {
      type: action?.type, id: action?.id, text: action?.text,
      tag: action?.tag, risk: action?.risk, span: action?.span,
    },
    narrative: String(d.narrative ?? ""),
    choices: Array.isArray(d.choices) ? d.choices : [],
    delta_applied: d.delta_applied,
    npc_events: d.npc_events,
    breakthrough: d.breakthrough ?? null,
    engine_meta: d.engine_meta,
    snapshot: {
      realm: REALMS[s.realm_index ?? 0] || "凡人",
      hp: Number(s.hp ?? 0), hp_max: Number(s.hp_max ?? 0),
      qi: Number(s.qi ?? 0), qi_max: Number(s.qi_max ?? 0),
      exp: Number(s.exp ?? 0), spirit_stones: Number(s.spirit_stones ?? 0),
      age: Number(s.age ?? 0), lifespan: Number(s.lifespan ?? 0),
      items: (s.items || []).map(it => ({ name: it.name, qty: it.qty, rarity: it.rarity })),
      npcs: (s.npcs || []).map(n => ({ name: n.name, title: n.title, bond: n.bond })),
    },
  };
  writeJournal(trimTo([...prev, entry]));
}

/* ---------------- 导出 ---------------- */
export type JournalFormat = "jsonl" | "md" | "txt";

function stamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

function choiceLine(c: Choice): string {
  const bits = [c.tag, c.risk, c.span].filter(Boolean).join(" / ");
  return bits ? `${c.id} ${c.text}（${bits}）` : `${c.id} ${c.text}`;
}

function deltaLine(e: JournalEntry): string {
  const d = e.delta_applied || {};
  const parts: string[] = [];
  if (d.hp) parts.push(`气血 ${d.hp > 0 ? "+" : ""}${d.hp}`);
  if (d.qi) parts.push(`灵力 ${d.qi > 0 ? "+" : ""}${d.qi}`);
  if (d.exp) parts.push(`修为 ${d.exp > 0 ? "+" : ""}${d.exp}`);
  if (d.spirit_stones) parts.push(`灵石 ${d.spirit_stones > 0 ? "+" : ""}${d.spirit_stones}`);
  (d.items_add || []).forEach(it => parts.push(`得 ${it.name}×${it.qty}`));
  (d.items_remove || []).forEach(it => parts.push(`失 ${it.name}×${it.qty}`));
  const days = e.engine_meta?.cultivate?.days;
  if (days) parts.push(`天数 ${days}`);
  return parts.length ? parts.join(" · ") : "无增减";
}

function npcLine(e: JournalEntry): string {
  return (e.npc_events || []).filter(x => x && x.delta)
    .map(x => `${x.name} ${x.delta > 0 ? "+" : ""}${x.delta}`).join(" · ");
}

export function toJsonl(list: JournalList): string {
  return list.map(e => JSON.stringify(e)).join("\n") + (list.length ? "\n" : "");
}

export function toText(list: JournalList): string {
  const out: string[] = [`墨问仙途 · 对局日志（${list.length} 轮）`];
  for (const e of list) {
    out.push("");
    out.push(`— 第 ${e.turn} 轮 · ${e.snapshot.realm} · ${e.snapshot.age}岁 —`);
    if (e.action.text) out.push(`你的选择：${e.action.id ? e.action.id + " " : ""}${e.action.text}`);
    if (e.choices.length) out.push(`本轮选项：${e.choices.map(choiceLine).join("；")}`);
    out.push(`变化：${deltaLine(e)}`);
    const np = npcLine(e);
    if (np) out.push(`道缘：${np}`);
    out.push(e.narrative);
  }
  return out.join("\n") + "\n";
}

export function toMarkdown(list: JournalList): string {
  const head = [
    "# 墨问仙途 · 对局日志",
    "",
    `- 导出时间：${new Date().toLocaleString("zh-CN")}`,
    `- 共 ${list.length} 轮`,
  ];
  const body: string[] = [];
  for (const e of list) {
    const s = e.snapshot;
    const lines: string[] = [];
    lines.push(`## 第 ${e.turn} 轮 · ${s.realm} · ${s.age}岁 / 寿元 ${s.lifespan}`);
    if (e.action.text) {
      const tag = [e.action.tag, e.action.risk, e.action.span].filter(Boolean).join("·");
      lines.push(`- 你的选择：${e.action.id ? e.action.id + " " : ""}${e.action.text}${tag ? `（${tag}）` : ""}`);
    }
    if (e.choices.length) {
      lines.push("- 本轮选项：");
      e.choices.forEach(c => lines.push(`  - ${choiceLine(c)}`));
    }
    lines.push(`- 变化：${deltaLine(e)}`);
    const np = npcLine(e);
    if (np) lines.push(`- 道缘：${np}`);
    if (e.breakthrough) lines.push(`- 突破：${e.breakthrough.from} → ${e.breakthrough.to}`);
    lines.push(`- 剧情：${e.narrative}`);
    body.push(lines.join("\n"));
  }
  return head.join("\n") + "\n\n" + body.join("\n\n") + "\n";
}

export interface Exported {
  filename: string;
  content: string;
  mime: string;
}

/** 生成导出内容与文件名；空日志返回 null（调用方据此置灰按钮）。 */
export function exportJournalAs(fmt: JournalFormat, list?: JournalList): Exported | null {
  const data = list || loadJournal();
  if (!data.length) return null;
  const base = `墨问仙途-对局日志-${stamp()}`;
  if (fmt === "jsonl") {
    return { filename: `${base}.jsonl`, content: toJsonl(data), mime: "application/jsonl" };
  }
  if (fmt === "txt") {
    return { filename: `${base}.txt`, content: toText(data), mime: "text/plain" };
  }
  return { filename: `${base}.md`, content: toMarkdown(data), mime: "text/markdown" };
}
