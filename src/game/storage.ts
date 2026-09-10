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
