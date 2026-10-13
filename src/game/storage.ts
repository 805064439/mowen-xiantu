/* 本地持久化：存档 / 轮回名册 / 自由输入历史
   —— 键名与数据结构与旧版（单文件 index.html）完全一致，老档无缝迁移 */

import type { GameState, Choice, Reincarnation } from "./types";
import { INIT_STATE } from "./constants";

export const SAVE_KEY = "mowen_save_v1";
export const REINC_KEY = "mowen_reincarnations_v1";
export const HISTORY_KEY = "mowen_history_v1";
/** 走过的世数（已完成并抹去的轮回条数）——与名册分开存，见 loadCycleCount */
export const CYCLE_KEY = "mowen_cycle_count_v1";

export interface SaveFile {
  v: 1;
  state: GameState;
  ended: boolean;
  lastScene: { narrative: string; choices: Choice[] };
}

export function loadReincarnations(): Reincarnation[] {
  try { return JSON.parse(localStorage.getItem(REINC_KEY) || "[]"); }
  catch (e) { return []; }
}

export function saveReincarnations(list: Reincarnation[]) {
  try { localStorage.setItem(REINC_KEY, JSON.stringify(list.slice(0, 5))); } catch (e) { /* 忽略 */ }
}

/* 世数：名册只留最近 5 条（要塞进提示词当「江湖传说」，不能无限长），
   所以**绝不能用名册长度当世数**——满了 5 条就永远停在「第 6 段」。
   世数单独存一个只增不减的整数。 */
export function loadCycleCount(): number {
  const raw = localStorage.getItem(CYCLE_KEY);
  if (raw === null || raw === "") {
    // 旧档升级：没有计数键时，以名册里躺着的条数起算（老玩家的 5 条 → 从 5 接着走）
    const n = loadReincarnations().length;
    saveCycleCount(n);
    return n;
  }
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function saveCycleCount(n: number) {
  try { localStorage.setItem(CYCLE_KEY, String(Math.max(0, n | 0))); } catch (e) { /* 忽略 */ }
}

/** 又走完一世：世数 +1。名册有没有记上是另一回事（开局即重开无名册可记）。 */
export function bumpCycleCount(): number {
  const n = loadCycleCount() + 1;
  saveCycleCount(n);
  return n;
}

export function loadHistory(): string[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch (e) { return []; }
}

export function pushHistory(text: string): string[] {
  const h = [text, ...loadHistory().filter(t => t !== text)].slice(0, 5);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); } catch (e) { /* 忽略 */ }
  return h;
}

/** 初始 state 深拷贝（含轮回名册注入点） */
export function freshState(): GameState {
  const s = JSON.parse(JSON.stringify(INIT_STATE)) as GameState;
  s.reincarnations = loadReincarnations();
  return s;
}

export function readSave(): SaveFile | null {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    if (!s || s.v !== 1 || !s.state || !s.lastScene) return null;
    if (!s.state.reincarnations) s.state.reincarnations = loadReincarnations(); // 旧档平滑升级
    return s;
  } catch (e) { return null; }
}

export function writeSave(state: GameState, ended: boolean, lastNarrative: string, choices: Choice[]) {
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify({
      v: 1, state, ended,
      lastScene: { narrative: lastNarrative, choices },
    }));
  } catch (e) { /* 存储满等异常静默 */ }
}

export function removeSave() {
  localStorage.removeItem(SAVE_KEY);
}

/** 彻底清档：抹掉本设备上全部本地数据（存档/轮回名册/世数/输入历史）。不可恢复。
 *  与 removeSave 的区别：那个只抹今生（名册与世数留给江湖记忆），这个是一切归零。 */
export function wipeAllStorage(): void {
  for (const k of [SAVE_KEY, REINC_KEY, CYCLE_KEY, HISTORY_KEY]) {
    try { localStorage.removeItem(k); } catch (e) { /* 隐私模式等：忽略 */ }
  }
}

/* ---------------- 仙缘令（存档 ↔ 文本码，跨设备迁移） ----------------
   格式：MW1Z.<base64(deflate-raw(json))>，浏览器不支持压缩时降级 MW1R.<base64(json)> */

const CODE_ZIP = "MW1Z";
const CODE_RAW = "MW1R";

function bytesToB64(bytes: Uint8Array): string {
  let bin = "";
  const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CH));
  }
  return btoa(bin);
}

function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64.replace(/\s+/g, ""));
  const buf = new ArrayBuffer(bin.length);
  const out = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** 当前存档 → 仙缘令文本 */
export async function encodeSaveCode(save: SaveFile): Promise<string> {
  const json = JSON.stringify(save);
  if (typeof CompressionStream !== "undefined") {
    try {
      const stream = new Blob([json]).stream().pipeThrough(new CompressionStream("deflate-raw"));
      const buf = new Uint8Array(await new Response(stream).arrayBuffer());
      return CODE_ZIP + "." + bytesToB64(buf);
    } catch (e) { /* 压缩失败 → 原文降级 */ }
  }
  return CODE_RAW + "." + bytesToB64(new TextEncoder().encode(json));
}

/** 仙缘令文本 → 存档（校验失败返回 null，调用方负责提示） */
export async function decodeSaveCode(code: string): Promise<SaveFile | null> {
  const s = (code || "").trim();
  const dot = s.indexOf(".");
  if (dot < 0) return null;
  const prefix = s.slice(0, dot);
  const body = s.slice(dot + 1).replace(/\s+/g, "");
  try {
    let json = "";
    if (prefix === CODE_ZIP) {
      if (typeof DecompressionStream === "undefined") return null;
      const stream = new Blob([b64ToBytes(body)]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      json = await new Response(stream).text();
    } else if (prefix === CODE_RAW) {
      json = new TextDecoder().decode(b64ToBytes(body));
    } else {
      return null;
    }
    const save = JSON.parse(json) as SaveFile;
    if (!save || save.v !== 1 || !save.state || !save.lastScene) return null;
    const st = save.state as unknown as Record<string, unknown>;
    if (!st || typeof st.turn !== "number" || typeof st.hp !== "number"
        || typeof st.realm_index !== "number" || !Array.isArray(st.items)) return null;
    return save;
  } catch (e) {
    return null;
  }
}
