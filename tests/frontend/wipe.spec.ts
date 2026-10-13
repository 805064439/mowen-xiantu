/* 彻底清档（v3.13.2）：一键抹掉本设备全部本地数据

   事故防线：与 v3.12.5「世数卡第 6 段」同类——**该归零的没归零**。
   清档漏一个键，用户以为重开了，实际世数/名册/日志还在，
   下一次「再入轮回」仍旧从第 N 段起算。所以这里既测功能（真删），
   也测「src 里出现的每一个 mowen_ 键都被清档覆盖」（防新增键漏网）。 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  SAVE_KEY, REINC_KEY, HISTORY_KEY, CYCLE_KEY,
  wipeAllStorage, writeSave, freshState,
  saveReincarnations, saveCycleCount, pushHistory,
  loadReincarnations, loadCycleCount, loadHistory, readSave,
} from "../../src/game/storage";
import { JOURNAL_KEY, wipeJournal, loadJournal, appendTurn } from "../../src/game/journal";
import type { ActResponse } from "../../src/game/types";
import { readFileSync } from "node:fs";
import * as path from "node:path";

/* 自带一份内存 localStorage：不依赖 happy-dom 的实现细节 */
function installMemoryStorage() {
  const store = new Map<string, string>();
  const impl = {
    get length() { return store.size; },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    store,
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: impl, configurable: true, writable: true,
  });
  return impl;
}

beforeEach(() => installMemoryStorage());

/** 造一轮假响应，用来往日志里塞数据 */
function fakeTurn(turn: number): ActResponse {
  return {
    state: { ...freshState(), turn } as ActResponse["state"],
    choices: [], narrative: "测试剧情", delta_applied: {},
    npc_events: [], breakthrough: null, engine_meta: {},
  } as unknown as ActResponse;
}

describe("wipeAllStorage：四类本地数据一次抹净", () => {
  it("写入全部四类数据后，清档即一切归零（公开 API 校验，不只看原始键）", () => {
    writeSave(freshState(), false, "n", []);
    saveReincarnations([{ realm: "炼气三层", turn: 30, memory: ["旧事"] }]);
    saveCycleCount(7);
    pushHistory("去寻阿菱");

    // 前置确认：数据都在
    expect(readSave()).not.toBeNull();
    expect(loadReincarnations()).toHaveLength(1);
    expect(loadCycleCount()).toBe(7);
    expect(loadHistory()).toHaveLength(1);

    wipeAllStorage();

    // 原始键先查：loadCycleCount 命中「旧档升级」会回写 "0"，放后面查会被它自己打脸
    for (const k of [SAVE_KEY, REINC_KEY, CYCLE_KEY, HISTORY_KEY]) {
      expect(localStorage.getItem(k), `${k} 未删除`).toBeNull();
    }
    // 公开 API 视角同样归零
    expect(readSave()).toBeNull();
    expect(loadReincarnations()).toEqual([]);
    expect(loadCycleCount()).toBe(0);
    expect(loadHistory()).toEqual([]);
  });

  it("空存储上调用不抛异常", () => {
    expect(() => wipeAllStorage()).not.toThrow();
  });

  it("storage.ts 里每个存储键常量都被清档覆盖（新增键漏网即红）", () => {
    const src = readFileSync(path.join(process.cwd(), "src/game/storage.ts"), "utf-8");
    const fn = src.slice(src.indexOf("export function wipeAllStorage"),
                        src.indexOf("/* ---------------- 仙缘令"));
    // 清档函数引用的是常量名（SAVE_KEY……），判据就得是常量名，不是字面量
    const decls = [...src.matchAll(/export const (\w+)\s*=\s*"(mowen_[a-z0-9_]+)"/g)];
    expect(decls.length, "没在 storage.ts 解析到存储键常量").toBeGreaterThanOrEqual(4);
    for (const [, name, key] of decls) {
      expect(fn, `wipeAllStorage 漏清了 ${key}（常量 ${name}）`).toContain(name);
    }
  });
});

describe("wipeJournal：日志连批次号一起清", () => {
  it("日志与批次号都被抹掉", () => {
    appendTurn(null, fakeTurn(3));
    appendTurn(null, fakeTurn(4));
    expect(loadJournal()).toHaveLength(2);

    wipeJournal();

    expect(loadJournal()).toEqual([]);
    expect(localStorage.getItem(JOURNAL_KEY)).toBeNull();
    expect(localStorage.getItem("mowen_journal_sid")).toBeNull();
  });

  it("与 clearJournal 的区别：批次号也清（跨轮回对比的锚点不再续用）", () => {
    const src = readFileSync(path.join(process.cwd(), "src/game/journal.ts"), "utf-8");
    const clearFn = src.slice(src.indexOf("export function clearJournal"), src.indexOf("export function wipeJournal"));
    const wipeFn = src.slice(src.indexOf("export function wipeJournal"));
    expect(clearFn).not.toContain("SID_KEY");   // 旧函数只管日志本体
    expect(wipeFn).toContain("SID_KEY");        // 清档连批次号一起
  });
});

describe("交互链：二步确认 + 调用链（源码契约）", () => {
  const gameSrc = readFileSync(path.join(process.cwd(), "src/stores/game.ts"), "utf-8");
  const modalSrc = readFileSync(path.join(process.cwd(), "src/components/ConfirmModal.vue"), "utf-8");
  const cssSrc = readFileSync(path.join(process.cwd(), "src/style.css"), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "");

  it("wipeAll 抹存储 + 抹日志 + 重开天地，且不写名册（清档不该留前世记录）", () => {
    const fn = gameSrc.slice(gameSrc.indexOf("function wipeAll()"), gameSrc.indexOf("/* ---------------- 仙缘令"));
    expect(fn).toContain("wipeAllStorage()");
    expect(fn).toContain("wipeJournal()");
    expect(fn).toContain("newGame(true)");
    expect(fn, "清档不得写入轮回名册").not.toContain("pushReincarnation()");
    expect(fn, "清档不得推进世数").not.toContain("bumpCycleCount()");
    expect(fn, "清档后必须关掉二步确认态").toContain("game.confirmWipe = false");
  });

  it("requestWipe / cancelWipe / wipeAll 都挂进了 actions", () => {
    const actions = gameSrc.slice(gameSrc.indexOf("export const actions = {"));
    for (const name of ["requestWipe", "cancelWipe", "wipeAll"]) {
      expect(actions, `actions 缺 ${name}`).toContain(name);
    }
  });

  it("confirmWipe 状态存在（二步确认的闸）", () => {
    expect(gameSrc).toMatch(/confirmWipe:\s*false/);
  });

  it("弹窗是二步结构：入口按钮 → 换题换钮 → 终确认", () => {
    // 第一步：入口
    expect(modalSrc).toContain('id="btn-wipe-all"');
    expect(modalSrc).toContain("actions.requestWipe()");
    // 闸：v-if/v-else 挂在 confirmWipe 上
    expect(modalSrc).toMatch(/v-if="!game\.confirmWipe"/);
    expect(modalSrc).toMatch(/v-else/);
    // 第二步：终确认与回返
    expect(modalSrc).toContain('id="btn-wipe-confirm"');
    expect(modalSrc).toContain("actions.wipeAll()");
    expect(modalSrc).toContain('id="btn-wipe-cancel"');
    expect(modalSrc).toContain("actions.cancelWipe()");
    // 文案要点名「无法恢复」，且发生在终确认那一步
    const step2 = modalSrc.slice(modalSrc.indexOf("v-else"));
    expect(step2).toContain("无法恢复");
  });

  it("ghost 按钮继承 .cbtn 基础排版（不会退化成浏览器默认按钮）", () => {
    const base = cssSrc.match(/\.cbtn\{([^}]*)\}/);
    expect(base, ".cbtn 基础规则不见了").not.toBeNull();
    expect(base![1]).toContain("font-family:inherit");
    expect(base![1]).toContain("cursor:pointer");
    const ghost = cssSrc.match(/\.cbtn\.ghost\{([^}]*)\}/);
    expect(ghost, ".cbtn.ghost 没有样式——会有样式但无低调态").not.toBeNull();
    expect(ghost![1]).toContain("color:var(--muted)");
    const solid = cssSrc.match(/\.cbtn\.danger\.solid\{([^}]*)\}/);
    expect(solid, "终确认按钮没有实心压秤样式").not.toBeNull();
    expect(solid![1]).toContain("background:var(--seal)");
  });
});
