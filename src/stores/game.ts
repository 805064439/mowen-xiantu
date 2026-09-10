/* 游戏中枢：状态 + 行动流程（SSE 流式 + 降级）+ 打字机 + 飘字
   —— 数值运算全在后端，前端只做渲染与存档 */

import { reactive, computed } from "vue";
import type { GameAction, GameState, Choice, ActResponse, ScenePara, FloatItem, EngineMeta } from "../game/types";
import { REALMS, OPENING, INIT_CHOICES } from "../game/constants";
import {
  readSave, writeSave, removeSave, freshState,
  loadReincarnations, saveReincarnations,
} from "../game/storage";

const API = (location.protocol.startsWith("http") ? "" : "http://localhost:8000") + "/api";

interface ErrorCard { message: string; action: GameAction }

/* ---------------- 响应式状态 ---------------- */
export const game = reactive({
  state: null as GameState | null,   // 后端权威状态
  choices: [] as Choice[],           // 当前选项
  ended: false,
  loading: false,                    // 请求进行中
  inputLocked: true,                 // 选项与自由输入的禁用闸（请求中/打字中/流式中）
  scenes: [] as ScenePara[],         // 已上屏叙事段落
  floats: [] as FloatItem[],         // 飘字
  btFlash: null as string | null,    // 突破特效（境界名）
  endingShown: false,                // 结局印章
  errorCard: null as ErrorCard | null,
  lastMeta: null as EngineMeta | null,
  mockMode: false,
  confirmOpen: false,
  confirmText: "",
});

/* ---------------- 打字机 ---------------- */
let typerTimer: ReturnType<typeof setInterval> | null = null;
let typerFinish: (() => void) | null = null;
let paraSeq = 0;
let floatSeq = 0;

function scrollStory() {
  const card = document.querySelector("#story-card");
  if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

/** 中止打字机：不清段落（弃段场景由调用方清 scenes） */
function abortTyper() {
  if (typerTimer) clearInterval(typerTimer);
  typerTimer = null;
  typerFinish = null;
}

function typeNarrative(text: string, onDone?: () => void) {
  if (typerFinish) typerFinish(); // 上一段仍在打字 → 先补完
  const para: ScenePara = { id: ++paraSeq, text: "" };
  game.scenes.push(para);
  scrollStory();
  const plain = String(text);
  let i = 0;
  const speed = plain.length > 150 ? 16 : 24;
  const finish = () => {
    if (typerTimer) clearInterval(typerTimer);
    typerTimer = null;
    para.text = plain;
    typerFinish = null;
    scrollStory();
    onDone && onDone();
  };
  typerFinish = finish;
  typerTimer = setInterval(() => {
    i += 2;
    para.text = plain.slice(0, i);
    if (i % 20 === 0) scrollStory();
    if (i >= plain.length) finish();
  }, speed);
}

function skipTyper() {
  if (typerFinish) typerFinish();
}

/* ---------------- 飘字 ---------------- */
function floatText(text: string, cls = "") {
  const item: FloatItem = { id: ++floatSeq, text, cls };
  game.floats.push(item);
  setTimeout(() => {
    const i = game.floats.indexOf(item);
    if (i >= 0) game.floats.splice(i, 1);
  }, 2500);
}

function floatDeltas(d: { hp?: number; qi?: number; exp?: number; spirit_stones?: number; items_add?: { name: string; qty: number }[]; items_remove?: { name: string; qty: number }[] }) {
  const names: Record<string, string> = { hp: "气血", qi: "灵力", exp: "修为", spirit_stones: "灵石" };
  for (const k of ["hp", "qi", "exp", "spirit_stones"] as const) {
    const v = (d[k] ?? 0) | 0;
    if (v > 0) floatText(`+${v} ${names[k]}`, "f-pos");
    else if (v < 0) floatText(`${v} ${names[k]}`, "f-neg");
  }
  (d.items_add || []).forEach(it => floatText(`获得 ${it.name}×${it.qty}`, "f-item"));
  (d.items_remove || []).forEach(it => floatText(`失去 ${it.name}×${it.qty}`, "f-neg"));
}

/* ---------------- 特效 ---------------- */
function playBreakthrough(to: string) {
  game.btFlash = to;
  setTimeout(() => { game.btFlash = null; }, 2000);
}

/* ---------------- 存档 ---------------- */
function save() {
  const last = game.scenes[game.scenes.length - 1];
  writeSave(game.state!, game.ended, last ? last.text : "", game.choices);
}

function pushReincarnation() {
  // 此生落幕 → 写入轮回名册（供下一世的江湖传说）
  const s = game.state;
  if (!s || !s.turn) return;
  const list = loadReincarnations();
  list.unshift({
    realm: REALMS[s.realm_index] || "凡人",
    turn: s.turn,
    memory: (s.memory || []).slice(-3),
    ended: !!game.ended,
  });
  saveReincarnations(list);
}

/* ---------------- 场景应用 ---------------- */
function applyScene(d: ActResponse) {
  game.state = d.state;
  game.choices = d.choices;
  typeNarrative(d.narrative, () => applySceneEffects(d));
}

function applySceneEffects(d: ActResponse) {
  if (d.breakthrough && d.breakthrough.success) playBreakthrough(d.breakthrough.to);
  else if (d.breakthrough && !d.breakthrough.success) floatText("冲关失败", "f-neg");
  if (d.near_death) {
    document.body.classList.add("near-death");
    setTimeout(() => document.body.classList.remove("near-death"), 1200);
  }
  floatDeltas(d.delta_applied || {});
  game.state = d.state;
  game.choices = d.choices;
  game.lastMeta = d.engine_meta;
  game.errorCard = null;
  game.inputLocked = false;        // 叙事完毕，恢复选项与自由输入
  if (d.ending && !game.ended) {
    game.ended = true;
    setTimeout(() => { game.endingShown = true; }, 1400);
  }
  save();
}

function showError(action: GameAction, e: { message: string }) {
  game.errorCard = { message: e.message, action };
  game.choices = [];            // 选项区让位给错误卡片 + 重试
  game.inputLocked = false;     // 出错时也允许改走自由输入，不必死磕重试
}

/* ---------------- 核心行动 ---------------- */
function parseSSEFrame(frame: string): { event: string; data: Record<string, unknown> } | null {
  let event = "message";
  let data: Record<string, unknown> | null = null;
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) {
      try { data = JSON.parse(line.slice(6)); } catch (e) { data = null; }
    }
  }
  return data === null ? null : { event, data };
}

async function actLegacy(action: GameAction) {
  const res = await fetch(API + "/act", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state: game.state, action, last_choices: game.choices }),
  });
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  if (!data.ok) throw new Error((data.error && data.error.message) || "未知异象");
  applyScene(data);
}

/** SSE 流式：叙事边生成边上屏。返回 false 表示需降级整段模式。 */
async function actStream(action: GameAction): Promise<boolean> {
  let res: Response;
  try {
    res = await fetch(API + "/act/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: game.state, action, last_choices: game.choices }),
    });
  } catch (e) { return false; }
  const ct = res.headers.get("content-type") || "";
  if (!res.ok || ct.indexOf("text/event-stream") < 0) return false;

  abortTyper();
  const para: ScenePara = { id: ++paraSeq, text: "" };
  game.scenes.push(para);
  scrollStory();
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let done: ActResponse | null = null;
  try {
    while (true) {
      const { value, done: closed } = await reader.read();
      if (closed) break;
      buf += dec.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const ev = parseSSEFrame(frame);
        if (!ev) continue;
        if (ev.event === "delta" && typeof ev.data.t === "string" && ev.data.t) {
          para.text += ev.data.t as string;
          scrollStory();
        } else if (ev.event === "retry") {
          para.text = "（天机紊乱，凝神重推……）";
        } else if (ev.event === "done") {
          done = ev.data as unknown as ActResponse;
        } else if (ev.event === "error") {
          throw new Error(String(ev.data.message || "推演中断"));
        }
      }
    }
  } catch (e) {
    removeScene(para);
    throw e;
  }
  if (!done) { removeScene(para); return false; }   // 流断无 done → 降级
  if (done.ok === false) {
    removeScene(para);
    throw new Error(String((done as { error?: { message?: string } }).error?.message || "未知异象"));
  }
  para.text = done.narrative;   // 以完整叙事静默校正（含濒死补记等后缀）
  applySceneEffects(done);
  return true;
}

function removeScene(para: ScenePara) {
  const i = game.scenes.indexOf(para);
  if (i >= 0) game.scenes.splice(i, 1);
}

async function act(action: GameAction) {
  if (game.loading || !game.state || (game.ended && action.type === "breakthrough")) return;
  game.loading = true;
  game.inputLocked = true;
  game.errorCard = null;
  try {
    const streamed = await actStream(action);   // 优先走 SSE 流式
    if (!streamed) await actLegacy(action);     // 不支持/中断 → 降级整段
  } catch (e) {
    showError(action, e as { message: string });
  } finally {
    game.loading = false;
  }
}

/* ---------------- 生命周期 ---------------- */
function newGame(withOpening = true) {
  abortTyper();
  game.state = freshState();
  game.ended = false;
  game.endingShown = false;
  game.scenes = [];
  if (withOpening) {
    game.scenes.push({ id: ++paraSeq, text: OPENING });
    game.choices = [...INIT_CHOICES];
  }
  game.lastMeta = null;
  game.errorCard = null;
  game.inputLocked = false;
  save();
}

function loadSave(): boolean {
  const s = readSave();
  if (!s) return false;
  abortTyper();
  game.state = s.state;
  game.ended = !!s.ended;
  game.scenes = s.lastScene.narrative ? [{ id: ++paraSeq, text: s.lastScene.narrative }] : [];
  game.choices = s.lastScene.choices || [];
  game.inputLocked = false;
  return true;
}

async function init() {
  if (!loadSave()) newGame(true);
  try {
    const r = await fetch(API + "/health").then(r => r.json());
    if (r.mode === "mock") game.mockMode = true;
  } catch (e) { /* 离线自娱，无妨 */ }
}

function requestRestart() {
  const n = loadReincarnations().length;
  game.confirmText = (n === 0
    ? "重开将抹去今生所有修行、记忆与际遇。"
    : `重开将抹去今生——但江湖会记得。此去，已是第 ${n + 1} 段轮回。`);
  game.confirmOpen = true;
}

function confirmRestart() {
  game.confirmOpen = false;
  pushReincarnation();
  removeSave();
  newGame(true);
}

/* ---------------- 派生 ---------------- */
export const metaText = computed(() => {
  if (!game.state) return "";
  let t = `第 ${game.state.turn + 1} 轮`;
  const meta = game.lastMeta;
  if (meta && meta.elapsed_ms) {
    const sec = (meta.elapsed_ms / 1000).toFixed(2);
    const src = meta.source === "fallback" ? " · 天机补全" : (meta.source === "mock" ? " · 演武" : "");
    t += ` · 天机 ${sec}s${src}`;
  }
  return t;
});

export const actions = { act, init, newGame, requestRestart, confirmRestart, skipTyper, floatText };

export type { GameAction };
