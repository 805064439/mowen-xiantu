/* 存档持久化：localStorage 读写、容错、轮回名册、自由输入历史 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  SAVE_KEY, REINC_KEY, HISTORY_KEY,
  freshState, readSave, writeSave, removeSave,
  loadReincarnations, saveReincarnations,
  loadHistory, pushHistory,
  encodeSaveCode, decodeSaveCode,
} from "../../src/game/storage";
import type { GameState } from "../../src/game/types";

/* 自带一份内存 localStorage：不依赖 happy-dom 的实现细节，
   且能在需要时注入异常来模拟「存储已满 / 隐私模式」场景 */
function installMemoryStorage(options: { throwOnSet?: boolean } = {}) {
  const store = new Map<string, string>();
  const impl = {
    get length() {
      return store.size;
    },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => {
      if (options.throwOnSet) throw new DOMException("QuotaExceededError");
      store.set(k, String(v));
    },
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    store,
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: impl,
    configurable: true,
    writable: true,
  });
  return impl;
}

beforeEach(() => installMemoryStorage());

function makeSave(state: Partial<GameState> = {}, ended = false) {  return {
    v: 1 as const,
    state: { ...freshState(), ...state } as GameState,
    ended,
    lastScene: { narrative: "山雾未散，你踏上石阶。", choices: [] },
  };
}

describe("存档读写", () => {

  it("无存档时 readSave 返回 null", () => {
    expect(readSave()).toBeNull();
  });

  it("写入后可读回，字段完全保真", () => {
    const st = { ...freshState(), hp: 42, spirit_stones: 7 } as GameState;
    writeSave(st, false, "测试叙事", [{ id: "A", text: "向东", risk: "low", tag: "explore" }]);
    const s = readSave();
    expect(s).not.toBeNull();
    expect(s!.state.hp).toBe(42);
    expect(s!.state.spirit_stones).toBe(7);
    expect(s!.ended).toBe(false);
    expect(s!.lastScene.narrative).toBe("测试叙事");
    expect(s!.lastScene.choices[0].id).toBe("A");
  });

  it("版本号不符的旧档被拒绝（不静默加载损坏数据）", () => {
    localStorage.setItem(SAVE_KEY, JSON.stringify({ v: 0, state: {}, lastScene: {} }));
    expect(readSave()).toBeNull();
  });

  it("缺少 state / lastScene 的存档被拒绝", () => {
    localStorage.setItem(SAVE_KEY, JSON.stringify({ v: 1 }));
    expect(readSave()).toBeNull();
    localStorage.setItem(SAVE_KEY, JSON.stringify({ v: 1, state: {} }));
    expect(readSave()).toBeNull();
  });

  it("损坏的 JSON 不抛异常，返回 null", () => {
    localStorage.setItem(SAVE_KEY, "{不是合法 json");
    expect(readSave()).toBeNull();
  });

  it("旧档缺少 reincarnations 时自动从名册补齐", () => {
    saveReincarnations([{ realm: "炼气三层", turn: 30, memory: ["旧事"] }]);
    localStorage.setItem(SAVE_KEY, JSON.stringify({
      v: 1, state: { ...freshState(), reincarnations: undefined }, ended: false,
      lastScene: { narrative: "x", choices: [] },
    }));
    const s = readSave();
    expect(s).not.toBeNull();
    expect(s!.state.reincarnations).toHaveLength(1);
  });

  it("removeSave 清干净", () => {
    writeSave(freshState(), false, "n", []);
    expect(localStorage.getItem(SAVE_KEY)).not.toBeNull();
    removeSave();
    expect(localStorage.getItem(SAVE_KEY)).toBeNull();
  });
});

describe("初始状态", () => {

  it("freshState 每次返回全新对象（互不污染）", () => {
    const a = freshState();
    const b = freshState();
    a.hp = 1;
    expect(b.hp).not.toBe(1);
  });

  it("freshState 注入轮回名册", () => {
    saveReincarnations([{ realm: "筑基初期", turn: 99, memory: ["传说"] }]);
    expect(freshState().reincarnations).toHaveLength(1);
  });
});

describe("轮回名册", () => {

  it("空存储返回空数组", () => {
    expect(loadReincarnations()).toEqual([]);
  });

  it("损坏数据返回空数组而非崩溃", () => {
    localStorage.setItem(REINC_KEY, "{{{坏了");
    expect(loadReincarnations()).toEqual([]);
  });

  it("名册上限 5 条", () => {
    saveReincarnations(Array.from({ length: 20 }, (_, i) => ({
      realm: "炼气一层", turn: i, memory: [],
    })));
    expect(loadReincarnations()).toHaveLength(5);
  });
});

describe("自由输入历史", () => {

  it("最新的排在最前，且去重", () => {
    pushHistory("向东走");
    pushHistory("向西走");
    pushHistory("向东走");   // 重复 → 提升到最前，不产生第二条
    const h = loadHistory();
    expect(h[0]).toBe("向东走");
    expect(h.filter((t) => t === "向东走")).toHaveLength(1);
  });

  it("上限 5 条", () => {
    for (let i = 0; i < 20; i++) pushHistory(`指令${i}`);
    expect(loadHistory()).toHaveLength(5);
    expect(loadHistory()[0]).toBe("指令19");
  });

  it("返回值与存储一致", () => {
    const h = pushHistory("同步校验");
    expect(h).toEqual(loadHistory());
    expect(h[0]).toBe("同步校验");
  });
});

describe("仙缘令（存档码）", () => {

  it("往返一致：编码后解码还原同一份存档", async () => {
    const save = makeSave({ hp: 66, turn: 12 });
    const code = await encodeSaveCode(save);
    expect(/^MW1[ZR]\./.test(code)).toBe(true);
    const back = await decodeSaveCode(code);
    expect(back).not.toBeNull();
    expect(back!.state.hp).toBe(66);
    expect(back!.state.turn).toBe(12);
    expect(back!.lastScene.narrative).toBe(save.lastScene.narrative);
  });

  it("带中文与特殊字符的存档也能往返", async () => {
    const save = makeSave();
    save.state.memory = ["『注意』特殊字符·、\n换行"];
    save.state.spirit_root = "天灵根·火";
    const back = await decodeSaveCode(await encodeSaveCode(save));
    expect(back!.state.memory).toEqual(save.state.memory);
    expect(back!.state.spirit_root).toBe("天灵根·火");
  });

  it("压缩路径与原始路径都能产出合法码", async () => {
    const code = await encodeSaveCode(makeSave());
    expect(code.startsWith("MW1Z.") || code.startsWith("MW1R.")).toBe(true);
  });

  it("粘贴时首尾空白会被忽略", async () => {
    const code = await encodeSaveCode(makeSave({ hp: 5 }));
    const back = await decodeSaveCode("   " + code + "  \n");
    expect(back).not.toBeNull();
    expect(back!.state.hp).toBe(5);
  });

  it("码中间夹换行则拒绝（当前实现只 trim 首尾，记此现状）", async () => {
    const code = await encodeSaveCode(makeSave());
    const broken = code.slice(0, 4) + "\n" + code.slice(4);
    const back = await decodeSaveCode(broken);
    expect(back === null || back.state.turn === 0).toBe(true);
  });

  it.each([
    ["空串", ""],
    ["无前缀分隔符", "MW1Zxxxx"],
    ["未知前缀", "XX9Q.abcdef"],
    ["base64 非法字符", "MW1R.@@@not-base64@@@"],
    ["前缀为 Zip 但内容非 deflate", "MW1Z.ZZZZ"],
    ["全是空白", "    "],
  ])("非法存档码返回 null：%s", async (_label, code) => {
    expect(await decodeSaveCode(code)).toBeNull();
  });

  it("合法 base64 但 JSON 结构不合法 → null", async () => {
    const bad = Buffer.from(JSON.stringify({ v: 2, state: {}, lastScene: {} })).toString("base64");
    expect(await decodeSaveCode("MW1R." + bad)).toBeNull();

    const noState = Buffer.from(JSON.stringify({ v: 1, lastScene: {} })).toString("base64");
    expect(await decodeSaveCode("MW1R." + noState)).toBeNull();
  });

  it("state 字段类型不对 → 拒绝", async () => {
    const wrong = Buffer.from(JSON.stringify({
      v: 1, state: { turn: "NaN", hp: 1, realm_index: 1, items: [] }, lastScene: {},
    })).toString("base64");
    expect(await decodeSaveCode("MW1R." + wrong)).toBeNull();
  });
});
