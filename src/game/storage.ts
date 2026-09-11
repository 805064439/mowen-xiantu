/* 本地持久化：存档 / 轮回名册 / 自由输入历史
   —— 键名与数据结构与旧版（单文件 index.html）完全一致，老档无缝迁移 */

import type { GameState, Choice, Reincarnation } from "./types";
import { INIT_STATE } from "./constants";

export const SAVE_KEY = "mowen_save_v1";
export const REINC_KEY = "mowen_reincarnations_v1";
export const HISTORY_KEY = "mowen_history_v1";

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
