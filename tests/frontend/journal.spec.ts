/* 对局日志：每轮剧情与选项的独立留存、环形封顶、导出格式与隔离性。
   日志是排查与离线回溯的凭据，所以它必须「绝不影响主线」：
   存储写失败、数据损坏、超限时都不能让游戏本身出问题。 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  JOURNAL_KEY, JOURNAL_MAX,
  loadJournal, clearJournal, appendTurn, rotateSession,
  toJsonl, toText, toMarkdown, exportJournalAs,
} from "../../src/game/journal";
import { SAVE_KEY, writeSave, freshState } from "../../src/game/storage";
import type { ActResponse, GameAction, GameState } from "../../src/game/types";

function installMemoryStorage(options: { throwOnSet?: boolean } = {}) {
  const store = new Map<string, string>();
  const impl = {
    get length() { return store.size; },
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
    value: impl, configurable: true, writable: true,
  });
  return impl;
}

beforeEach(() => installMemoryStorage());

/** 造一轮后端响应（只带日志用得到的字段） */
function makeResponse(over: {
  state?: Partial<GameState>; narrative?: string; choices?: ActResponse["choices"];
  engine_meta?: Partial<ActResponse["engine_meta"]>;
} = {}): ActResponse {
  return {
    ok: true,
    state: { ...freshState(), turn: 7, realm_index: 2, hp: 88, hp_max: 100, qi: 40, qi_max: 50,
             exp: 120, spirit_stones: 260, age: 19, lifespan: 128, ...(over.state || {}) } as GameState,
    narrative: over.narrative ?? "晨光透林，你于溪畔拭剑。",
    choices: over.choices ?? [
      { id: "A", text: "沿溪上行", tag: "explore", risk: "mid" },
      { id: "B", text: "潜心修行", tag: "cultivate", risk: "low", span: "long" },
    ],
    delta_applied: {
      hp: -4, qi: 0, exp: 26, spirit_stones: -10, items_add: [], items_remove: [],
    } as ActResponse["delta_applied"],
    npc_events: [{ name: "青云子", delta: 5 }],
    breakthrough: null,
    near_death: false,
    ending: false,
    engine_meta: { source: "ai", elapsed_ms: 4321, cultivate: { days: 1800 } as never,
                   ...(over.engine_meta || {}) } as ActResponse["engine_meta"],
  };
}

const ACTION: GameAction = {
  type: "choice", id: "B", text: "潜心修行", tag: "cultivate", risk: "low", span: "long",
};

function seed(times = 2) {
  for (let i = 0; i < times; i++) {
    appendTurn(ACTION, makeResponse({ narrative: i === 0 ? "晨光透林，你于溪畔拭剑。" : "第二轮：溪畔遇客" }));
  }
  return loadJournal();
}

describe("追加一轮", () => {
  it("记录玩家的行动与剧情、选项", () => {
    appendTurn(ACTION, makeResponse());
    const list = loadJournal();
    expect(list).toHaveLength(1);
    const e = list[0];
    expect(e.action.text).toBe("潜心修行");
    expect(e.action.span).toBe("long");
    expect(e.narrative).toBe("晨光透林，你于溪畔拭剑。");
    expect(e.choices.map(c => c.id)).toEqual(["A", "B"]);
    expect(e.turn).toBe(7);
  });

  it("同时留下回合末数值快照", () => {
    appendTurn(ACTION, makeResponse());
    const s = loadJournal()[0].snapshot;
    expect(s.hp).toBe(88);
    expect(s.exp).toBe(120);
    expect(s.age).toBe(19);
    expect(s.realm).toBeTruthy();          // 境界名（炼气三层…）
    expect(Array.isArray(s.items)).toBe(true);
    expect(Array.isArray(s.npcs)).toBe(true);
  });

  it("序号连续递增", () => {
    appendTurn(ACTION, makeResponse());
    appendTurn(ACTION, makeResponse({ narrative: "第二轮" }));
    expect(loadJournal().map(e => e.i)).toEqual([1, 2]);
  });

  it("action 缺失（如服丹轮）也不崩", () => {
    appendTurn(null, makeResponse());
    expect(loadJournal()).toHaveLength(1);
    expect(loadJournal()[0].action.text).toBeUndefined();
  });

  it("choices 缺失时记为空数组", () => {
    const r = makeResponse();
    (r as { choices?: unknown }).choices = undefined;
    appendTurn(ACTION, r);
    expect(loadJournal()[0].choices).toEqual([]);
  });
});

describe("与存档隔离", () => {
  it("不写进存档键", () => {
    writeSave(freshState(), false, "存档里的最后一段", []);
    appendTurn(ACTION, makeResponse());
    const raw = localStorage.getItem(SAVE_KEY) || "";
    expect(raw).not.toContain("晨光透林");
    expect(raw).toContain("存档里的最后一段");
  });

  it("有自己的存储键且能清空", () => {
    appendTurn(ACTION, makeResponse());
    expect(localStorage.getItem(JOURNAL_KEY)).toBeTruthy();
    clearJournal();
    expect(loadJournal()).toEqual([]);
  });

  it("存储写失败时静默，不向外抛", () => {
    installMemoryStorage({ throwOnSet: true });
    expect(() => appendTurn(ACTION, makeResponse())).not.toThrow();
    expect(loadJournal()).toEqual([]);
  });

  it("日志被写坏时读回空数组而不是崩溃", () => {
    localStorage.setItem(JOURNAL_KEY, "{不是 json");
    expect(loadJournal()).toEqual([]);
  });
});

describe("容量封顶", () => {
  it("超过上限只留最近若干轮", () => {
    for (let i = 0; i < JOURNAL_MAX + 5; i++) {
      appendTurn(ACTION, makeResponse({ narrative: "第" + i + "轮" }));
    }
    const list = loadJournal();
    expect(list.length).toBe(JOURNAL_MAX);
    expect(list[list.length - 1].narrative).toBe("第" + (JOURNAL_MAX + 4) + "轮");
    expect(list[0].narrative).toBe("第5轮");
  });

  it("体积超限时压缩早期剧情，把预算留给最近几轮", () => {
    const fat = "剧情".repeat(40000);          // 单条约 8 万字
    for (let i = 0; i < 60; i++) appendTurn(ACTION, makeResponse({ narrative: fat }));
    const list = loadJournal();
    expect(list.length).toBeLessThan(60);
    expect(JSON.stringify(list).length).toBeLessThanOrEqual(1_600_000);
    expect(list[list.length - 1].narrative).toBe(fat);      // 最近一轮必须完整
    expect(list[0].narrative).toContain("剧情已截断");        // 早期的已让位
  });

  it("极端单条超限时也不会整个清空", () => {
    const huge = "剧情".repeat(200000);
    for (let i = 0; i < 12; i++) appendTurn(ACTION, makeResponse({ narrative: huge }));
    expect(loadJournal().length).toBeGreaterThan(0);
  });
});

describe("批次号", () => {
  it("同一批次内 sid 一致", () => {
    const [a, b] = seed();
    expect(a.sid).toBe(b.sid);
  });

  it("再入轮回换批次号，旧日志仍保留", () => {
    const [a] = seed(1);
    rotateSession();
    seed(1);
    const list = loadJournal();
    expect(list).toHaveLength(2);
    expect(list[1].sid).not.toBe(a.sid);
  });
});

describe("导出格式", () => {
  it("JSONL 每行一条且可逐行解析", () => {
    const lines = toJsonl(seed()).trim().split("\n");
    expect(lines).toHaveLength(2);
    const parsed = lines.map(l => JSON.parse(l));
    expect(parsed[0].narrative).toBe("晨光透林，你于溪畔拭剑。");
    expect(parsed[1].choices).toHaveLength(2);
  });

  it("Markdown 含轮次、境界、玩家行动、选项与剧情", () => {
    const md = toMarkdown(seed());
    expect(md).toContain("# 墨问仙途 · 对局日志");
    expect(md).toContain("## 第 7 轮");
    expect(md).toContain("潜心修行");
    expect(md).toContain("A 沿溪上行（explore / mid）");
    expect(md).toContain("B 潜心修行（cultivate / low / long）");
    expect(md).toContain("晨光透林，你于溪畔拭剑。");
    expect(md).toContain("青云子 +5");      // 道缘
  });

  it("Markdown 的数值行反映实际增减与天数", () => {
    const md = toMarkdown(seed());
    expect(md).toContain("修为 +26");
    expect(md).toContain("气血 -4");
    expect(md).toContain("天数 1800");
  });

  it("纯文本同样包含剧情与选项", () => {
    const txt = toText(seed());
    expect(txt).toContain("第 7 轮");
    expect(txt).toContain("本轮选项：A 沿溪上行");
    expect(txt).toContain("晨光透林，你于溪畔拭剑。");
  });

  it("三种格式都给出文件名与内容", () => {
    seed();
    for (const fmt of ["jsonl", "md", "txt"] as const) {
      const out = exportJournalAs(fmt);
      expect(out).not.toBeNull();
      expect(out!.filename).toMatch(/^墨问仙途-对局日志-\d{8}-\d{4}\./);
      expect(out!.content.length).toBeGreaterThan(0);
      expect(out!.mime).toBeTruthy();
    }
  });

  it("空日志不导出", () => {
    expect(exportJournalAs("md")).toBeNull();
  });

  it("带上未决之事快照，导出的 Markdown 里能看出哪条收了", () => {
    const r = makeResponse();
    (r.state as GameState).threads = [{ title: "荒泽白影", cat: "疑窦", open: 3, due: 7 }];
    r.engine_meta = { source: "ai", threads: { closed: ["素衣少女"] } } as never;
    appendTurn(ACTION, r);
    const list = loadJournal();
    expect(list[0].snapshot.threads[0]).toEqual({ title: "荒泽白影", cat: "疑窦", open: 3, due: 7 });
    const md = toMarkdown(list);
    expect(md).toContain("未决之事：荒泽白影（疑窦·第3轮起·第7轮前）");
    expect(md).toContain("素衣少女 ·已了结");
  });

  it("无变化的数值行写作「无增减」", () => {
    const r = makeResponse();
    r.delta_applied = { hp: 0, qi: 0, exp: 0, spirit_stones: 0, items_add: [], items_remove: [] };
    r.engine_meta = { source: "mock" } as never;      // 也没有天数可报
    appendTurn(ACTION, r);
    expect(toMarkdown(loadJournal())).toContain("变化：无增减");
  });
});

describe("v3.4：天数带与时序冲突必须落进导出", () => {
  it("变化行的天数后面带上所属时间带", () => {
    appendTurn(ACTION, makeResponse({
      engine_meta: { source: "ai", cultivate: { days: 143 } as never, time_band: "数月" } as never,
    }));
    expect(toMarkdown(loadJournal())).toContain("天数 143（数月）");
  });

  it("剧情与时间带打架时打标记（只记录，不重试）", () => {
    appendTurn(ACTION, makeResponse({
      engine_meta: { source: "ai", cultivate: { days: 143 } as never, time_band: "数月",
                     time_conflict: { kind: "moment_in_long_span", band: "数月", days: 143, hits: 2 } } as never,
    }));
    expect(toMarkdown(loadJournal())).toContain("剧情与时序不符");
  });

  it("不带时间带时仍只报天数（向后兼容老日志）", () => {
    appendTurn(ACTION, makeResponse({
      engine_meta: { source: "ai", cultivate: { days: 143 } as never } as never,
    }));
    expect(toMarkdown(loadJournal())).toContain("天数 143");
    expect(toMarkdown(loadJournal())).not.toContain("天数 143（");
  });
});
