/* 探索三档 + 机缘物件：前端只负责「把风险和回报讲给玩家听」，真值全在后端 server.py。
   因此这里守三件事：
     1. EXPLORE_TIERS / TREASURE_INFO 与后端逐条一致 —— 后端调了掉率而前端没调，
        玩家看到的「这次出门有多险」就是假的；
     2. 纯函数（exploreTierOfRisk / treasureEffBonus / treasureBreakBonus / treasureSummary）
        的兜底与口径不许错；
     3. types.ts 的数据契约要覆盖后端新回传的字段（漏字段 = 前端静默丢信息）。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import {
  EXPLORE_TIERS, exploreTierOfRisk,
  TREASURE_INFO, treasureEffBonus, treasureBreakBonus, treasureSummary,
} from "../../src/game/constants";

function findServerPy(): string {
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    const candidate = path.join(dir, "server.py");
    if (existsSync(candidate)) return candidate;
    dir = path.dirname(dir);
  }
  throw new Error(`未能在 ${process.cwd()} 及其上级目录中找到 server.py`);
}

const serverSrc = readFileSync(findServerPy(), "utf-8");

/** 解析 `NAME = { ... }` 的块体：按花括号配平截取，兼容单行 / 多行两种写法。 */
function parseBlock(name: string): string {
  const m = new RegExp(`${name}\\s*=\\s*\\{`).exec(serverSrc);
  if (!m) throw new Error(`未在 server.py 中找到 ${name}`);
  const open = serverSrc.indexOf("{", m.index);
  let depth = 0;
  for (let j = open; j < serverSrc.length; j++) {
    const ch = serverSrc[j];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return serverSrc.slice(open + 1, j);
    }
  }
  throw new Error(`${name} 的花括号不闭合`);
}

interface BackendTier { days: [number, number]; death: number; drop: number; fortune: number; rare: boolean; label: string; }

function parseExploreTiers(): Record<string, BackendTier> {
  const body = parseBlock("EXPLORE_TIERS");
  const out: Record<string, BackendTier> = {};
  for (const m of body.matchAll(/"(low|mid|high)":\s*\{([^}]*)\}/g)) {
    const inner = m[2];
    const days = inner.match(/"days":\s*\((\d+),\s*(\d+)\)/);
    const death = inner.match(/"death":\s*([\d.]+)/);
    const drop = inner.match(/"drop":\s*([\d.]+)/);
    const fortune = inner.match(/"fortune":\s*([\d.]+)/);
    const rare = inner.match(/"rare":\s*(True|False)/);
    const label = inner.match(/"label":\s*"([^"]+)"/);
    if (!days || !death || !drop || !fortune || !rare || !label) {
      throw new Error(`EXPLORE_TIERS.${m[1]} 解析失败`);
    }
    out[m[1]] = {
      days: [Number(days[1]), Number(days[2])],
      death: Number(death[1]), drop: Number(drop[1]), fortune: Number(fortune[1]),
      rare: rare[1] === "True", label: label[1],
    };
  }
  if (Object.keys(out).length !== 3) throw new Error("EXPLORE_TIERS 解析不全");
  return out;
}

interface BackendTreasure { name: string; eff: number; bp: number; prot: boolean; rare: boolean; exp?: [number, number]; }

function parseTreasure(): Record<string, BackendTreasure> {
  const body = parseBlock("TREASURE");
  const out: Record<string, BackendTreasure> = {};
  for (const m of body.matchAll(/"([a-z_]+)":\s*\{([^}]*)\}/g)) {
    const inner = m[2];
    const name = inner.match(/"name":\s*"([^"]+)"/);
    const eff = inner.match(/"eff":\s*([\d.]+)/);
    const bp = inner.match(/"bp":\s*([\d.]+)/);
    const prot = inner.match(/"prot":\s*([\d.]+)/);
    const rare = inner.match(/"rare":\s*(True|False)/);
    const exp = inner.match(/"exp":\s*\((\d+),\s*(\d+)\)/);
    if (!name || !eff || !bp || !prot || !rare) throw new Error(`TREASURE.${m[1]} 解析失败`);
    out[m[1]] = {
      name: name[1], eff: Number(eff[1]), bp: Number(bp[1]),
      prot: Number(prot[1]) > 0, rare: rare[1] === "True",
      exp: exp ? [Number(exp[1]), Number(exp[2])] : undefined,
    };
  }
  if (Object.keys(out).length !== 6) throw new Error("TREASURE 解析不全");
  return out;
}

function parseTreasureCaps(): Record<string, number> {
  const body = parseBlock("TREASURE_CAP");
  const out: Record<string, number> = {};
  for (const m of body.matchAll(/"([a-z_]+)":\s*(\d+)/g)) out[m[1]] = Number(m[2]);
  return out;
}

const backendTiers = parseExploreTiers();
const backendTreasure = parseTreasure();
const backendCaps = parseTreasureCaps();

describe("探索三档与后端同源", () => {
  it("三档齐备且前端不得凭空发明档位", () => {
    expect(Object.keys(EXPLORE_TIERS).sort()).toEqual(Object.keys(backendTiers).sort());
  });

  it("每档的天数 / 死亡率 / 掉率 / 奇遇率 / 稀有 / 中文名逐条一致", () => {
    for (const [key, b] of Object.entries(backendTiers)) {
      const f = EXPLORE_TIERS[key];
      expect(f, `EXPLORE_TIERS 缺少「${key}」`).toBeTruthy();
      expect(f.label).toBe(b.label);
      expect(f.days[0]).toBe(b.days[0]);
      expect(f.days[1]).toBe(b.days[1]);
      expect(f.death).toBeCloseTo(b.death, 6);
      expect(f.drop).toBeCloseTo(b.drop, 6);
      expect(f.fortune).toBeCloseTo(b.fortune, 6);
      expect(f.rare).toBe(b.rare);
    }
  });

  it("耗时 / 风险 / 掉落随档位单调递增（档位语义不能乱）", () => {
    const keys = ["low", "mid", "high"] as const;
    for (let i = 0; i + 1 < keys.length; i++) {
      expect(EXPLORE_TIERS[keys[i]].days[1]).toBeLessThan(EXPLORE_TIERS[keys[i + 1]].days[1]);
      expect(EXPLORE_TIERS[keys[i]].death).toBeLessThan(EXPLORE_TIERS[keys[i + 1]].death);
      expect(EXPLORE_TIERS[keys[i]].drop).toBeLessThan(EXPLORE_TIERS[keys[i + 1]].drop);
    }
  });

  it("只有秘境档可出稀有物件", () => {
    expect(EXPLORE_TIERS.high.rare).toBe(true);
    expect(EXPLORE_TIERS.mid.rare).toBe(false);
    expect(EXPLORE_TIERS.low.rare).toBe(false);
  });

  it("每档都有给玩家看的取舍说明", () => {
    for (const t of Object.values(EXPLORE_TIERS)) {
      expect(t.note.length).toBeGreaterThan(8);
    }
  });
});

describe("风险档 → 档位的兜底", () => {
  it("合法档位原样返回", () => {
    expect(exploreTierOfRisk("low").key).toBe("low");
    expect(exploreTierOfRisk("mid").key).toBe("mid");
    expect(exploreTierOfRisk("high").key).toBe("high");
  });

  it("未知 / 空值回落到中档（与后端 DEFAULT_EXPLORE_TIER 同义）", () => {
    expect(exploreTierOfRisk("").key).toBe("mid");
    expect(exploreTierOfRisk(undefined).key).toBe("mid");
    expect(exploreTierOfRisk("bogus").key).toBe("mid");
  });
});

describe("机缘物件与后端同源", () => {
  it("物件键集合一致（前端不得凭空发明物件）", () => {
    expect(Object.keys(TREASURE_INFO).sort()).toEqual(Object.keys(backendTreasure).sort());
  });

  it("名称 / 效率 / 突破加成 / 护道标记逐条一致", () => {
    for (const [key, b] of Object.entries(backendTreasure)) {
      const f = TREASURE_INFO[key];
      expect(f, `TREASURE_INFO 缺少「${key}」`).toBeTruthy();
      expect(f.name).toBe(b.name);
      expect(f.eff).toBeCloseTo(b.eff, 6);
      expect(f.bp).toBeCloseTo(b.bp, 6);
      expect(f.prot).toBe(b.prot);
    }
  });

  it("灵丹是唯一即时给修为的物件，且区间一致", () => {
    const b = backendTreasure.elixir;
    expect(TREASURE_INFO.elixir.exp).toEqual(b.exp);
    const givers = Object.values(TREASURE_INFO).filter((t) => t.exp);
    expect(givers).toHaveLength(1);
    expect(givers[0].key).toBe("elixir");
  });

  it("叠加上限与后端 TREASURE_CAP 一致", () => {
    for (const [key, cap] of Object.entries(backendCaps)) {
      expect(TREASURE_INFO[key], `TREASURE_INFO 缺少「${key}」`).toBeTruthy();
      expect(TREASURE_INFO[key].cap).toBe(cap);
    }
  });

  it("每个物件都有给玩家看的说明", () => {
    for (const t of Object.values(TREASURE_INFO)) {
      expect(t.desc.length).toBeGreaterThan(8);
    }
  });
});

describe("加成汇总函数", () => {
  it("效率加成按数量求和", () => {
    expect(treasureEffBonus({ residual_scroll: 3 })).toBeCloseTo(0.09, 6);
    expect(treasureEffBonus({ residual_scroll: 3, immortal_art: 1 })).toBeCloseTo(0.21, 6);
  });

  it("突破加成只认悟道石", () => {
    expect(treasureBreakBonus({ enlight_stone: 2 })).toBeCloseTo(0.06, 6);
    expect(treasureBreakBonus({ guard_talisman: 1 })).toBe(0);
    expect(treasureBreakBonus({ immortal_art: 2 })).toBe(0);
  });

  it("空值 / 未知键一律按 0 处理，不编造加成", () => {
    expect(treasureEffBonus(undefined)).toBe(0);
    expect(treasureEffBonus({})).toBe(0);
    expect(treasureEffBonus({ 不存在的物件: 9 })).toBe(0);
    expect(treasureBreakBonus(undefined)).toBe(0);
  });

  it("摘要文案：数量 > 1 才带 ×N，未知键直接忽略", () => {
    expect(treasureSummary({ residual_scroll: 2, guard_talisman: 1 })).toBe("功法残卷×2 · 护道符");
    expect(treasureSummary({ 未知: 1 })).toBe("");
    expect(treasureSummary(undefined)).toBe("");
  });
});

describe("后天加成只作用于修行（防滚雪球的口径）", () => {
  it("后端 TREASURE_EFF_TAGS 只含 cultivate / rest，绝不含 explore", () => {
    const m = serverSrc.match(/TREASURE_EFF_TAGS\s*=\s*\(([^)]*)\)/);
    if (!m) throw new Error("未在 server.py 中找到 TREASURE_EFF_TAGS");
    const tags = [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
    expect(tags).toContain("cultivate");
    expect(tags).toContain("rest");
    expect(tags).not.toContain("explore");
  });
});

describe("P1 数据契约（types.ts）", () => {
  const typesSrc = readFileSync(path.join(process.cwd(), "src/game/types.ts"), "utf-8");

  it("GameState 覆盖后端 sanitize_state 新增的机缘字段", () => {
    const iface = typesSrc.match(/interface GameState\s*\{([\s\S]*?)\n\}/);
    if (!iface) throw new Error("未在 types.ts 中找到 GameState");
    for (const key of ["treasures", "eff_bonus", "break_bonus"]) {
      expect(iface[1], `GameState 缺字段 ${key}`).toContain(key);
    }
  });

  it("CultivateInfo 带机缘效率明细", () => {
    const iface = typesSrc.match(/interface CultivateInfo\s*\{([\s\S]*?)\n\}/);
    if (!iface) throw new Error("未在 types.ts 中找到 CultivateInfo");
    for (const key of ["eff", "eff_bonus", "tier", "tier_label"]) {
      expect(iface[1], `CultivateInfo 缺字段 ${key}`).toContain(key);
    }
  });

  it("Breakthrough 带护道符标记、EngineMeta 带探索明细", () => {
    expect(typesSrc).toMatch(/interface Breakthrough\s*\{[\s\S]*?guard_talisman/);
    expect(typesSrc).toMatch(/interface EngineMeta\s*\{[\s\S]*?treasure\?/);
    expect(typesSrc).toMatch(/interface EngineMeta\s*\{[\s\S]*?explore\?/);
  });

  it("GameAction 支持 risk 档位（探索三档的入口）", () => {
    const iface = typesSrc.match(/interface GameAction\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1]).toContain("risk");
  });
});
