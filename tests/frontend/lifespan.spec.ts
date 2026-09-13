/* 时间与寿元：前端只做展示，真值全在后端 server.py。
   这里守两件事：
     1. 前端的 DAYS_PER_YEAR / ACTION_DAYS / DAY_EFF / LIFESPAN_TABLE 必须与后端逐条一致
        —— 后端调了日效率而前端没调，玩家看到的「这一轮几年」就是假的；
     2. 纯函数（stageOf / lifespanAvg / ageLevel / AGE_HINT / daysText）的兜底与分级不许错。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import {
  DAYS_PER_YEAR, START_AGE, ACTION_DAYS, DAY_EFF,
  LIFESPAN_TABLE, LIFESPAN_SAFE_RATIO,
  REST_LIFE_BONUS_EVERY, REST_LIFE_BONUS, REST_LIFE_BONUS_CAP,
  stageOf, lifespanAvg, ageLevel, AGE_HINT, daysText,
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

function parseScalar(name: string): number {
  const m = serverSrc.match(new RegExp(`^${name}\\s*=\\s*([\\d.]+)`, "m"));
  if (!m) throw new Error(`未在 server.py 中找到 ${name}`);
  return Number(m[1]);
}

/** 解析 `NAME = { "tag": (lo, hi), ... }` 形式的天数/区间字典 */
function parseRangeDict(name: string): Record<string, [number, number]> {
  const block = serverSrc.match(new RegExp(`${name}\\s*=\\s*\\{([\\s\\S]*?)\\n\\}`));
  if (!block) throw new Error(`未在 server.py 中找到 ${name}`);
  const out: Record<string, [number, number]> = {};
  for (const m of block[1].matchAll(/"([a-z_]+)":\s*\((\d+),\s*(\d+)\)/g)) {
    out[m[1]] = [Number(m[2]), Number(m[3])];
  }
  if (Object.keys(out).length === 0) throw new Error(`${name} 解析为空，正则可能已失效`);
  return out;
}

/** 解析 `NAME = { "tag": 数值, ... }` */
function parseNumDict(name: string): Record<string, number> {
  const block = serverSrc.match(new RegExp(`${name}\\s*=\\s*\\{([\\s\\S]*?)\\n\\}`));
  if (!block) throw new Error(`未在 server.py 中找到 ${name}`);
  const out: Record<string, number> = {};
  for (const m of block[1].matchAll(/"([a-z_]+)":\s*([\d.]+)/g)) out[m[1]] = Number(m[2]);
  if (Object.keys(out).length === 0) throw new Error(`${name} 解析为空，正则可能已失效`);
  return out;
}

/** 解析 `LIFESPAN_TABLE = [("名", lo, hi), ...]` */
function parseLifespanTable(): [string, number, number][] {
  const block = serverSrc.match(/LIFESPAN_TABLE\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("未在 server.py 中找到 LIFESPAN_TABLE");
  const out: [string, number, number][] = [];
  for (const m of block[1].matchAll(/\("([^"]+)",\s*(\d+),\s*(\d+)\)/g)) {
    out.push([m[1], Number(m[2]), Number(m[3])]);
  }
  if (out.length === 0) throw new Error("LIFESPAN_TABLE 解析为空，正则可能已失效");
  return out;
}

const backendDays = parseRangeDict("ACTION_DAYS");
const backendEff = parseNumDict("DAY_EFF");

describe("时间常量与后端同源", () => {
  it("一年天数与起始年岁一致", () => {
    expect(DAYS_PER_YEAR).toBe(parseScalar("DAYS_PER_YEAR"));
    expect(START_AGE).toBe(parseScalar("START_AGE"));
    expect(DAYS_PER_YEAR).toBe(360);
    expect(START_AGE).toBe(16);
  });

  it("每种行动的天数区间逐条一致", () => {
    expect(Object.keys(ACTION_DAYS).sort()).toEqual(Object.keys(backendDays).sort());
    for (const [tag, [lo, hi]] of Object.entries(backendDays)) {
      expect(ACTION_DAYS[tag], `ACTION_DAYS 缺少「${tag}」`).toBeTruthy();
      expect(ACTION_DAYS[tag][0], `「${tag}」天数下限不符`).toBe(lo);
      expect(ACTION_DAYS[tag][1], `「${tag}」天数上限不符`).toBe(hi);
    }
  });

  it("日效率逐条一致，且闭关最高、坊市最低", () => {
    expect(DAY_EFF).toEqual(backendEff);
    expect(DAY_EFF.cultivate).toBeGreaterThan(DAY_EFF.rest);
    expect(DAY_EFF.rest).toBeGreaterThan(DAY_EFF.explore);
    expect(DAY_EFF.explore).toBeGreaterThan(DAY_EFF.trade);
  });

  it("寿元表与安全线一致", () => {
    expect(LIFESPAN_TABLE).toEqual(parseLifespanTable());
    expect(LIFESPAN_SAFE_RATIO).toBe(parseScalar("LIFESPAN_SAFE_RATIO"));
    expect(LIFESPAN_SAFE_RATIO).toBe(0.72);
  });

  it("静养续命参数一致", () => {
    expect(REST_LIFE_BONUS_EVERY).toBe(parseScalar("REST_LIFE_BONUS_EVERY"));
    expect(REST_LIFE_BONUS).toBe(parseScalar("REST_LIFE_BONUS"));
    expect(REST_LIFE_BONUS_CAP).toBe(parseScalar("REST_LIFE_BONUS_CAP"));
  });
});

describe("大境界与寿元推导", () => {
  it("每 9 层一境", () => {
    expect(stageOf(0)).toBe(0);
    expect(stageOf(8)).toBe(0);
    expect(stageOf(9)).toBe(1);
    expect(stageOf(17)).toBe(1);
    expect(stageOf(18)).toBe(2);
  });

  it("越界层级钳在表内，不抛异常", () => {
    expect(stageOf(-5)).toBe(0);
    expect(stageOf(9999)).toBe(LIFESPAN_TABLE.length - 1);
  });

  it("寿元均值取区间中点", () => {
    expect(lifespanAvg(0)).toBe(165);    // 140~190
    expect(lifespanAvg(9)).toBe(450);    // 390~510
  });
});

describe("风险分级：只给体感，不给概率", () => {
  it("分级边界正确", () => {
    expect(ageLevel(0.5)).toBe("safe");
    expect(ageLevel(0.719)).toBe("safe");
    expect(ageLevel(0.72)).toBe("faded");
    expect(ageLevel(0.85)).toBe("faded");
    expect(ageLevel(0.86)).toBe("warn");
    expect(ageLevel(1.0)).toBe("warn");
    expect(ageLevel(1.01)).toBe("dread");
  });

  it("安全线内无文案，越线逐级加重", () => {
    expect(AGE_HINT.safe).toBe("");
    expect(AGE_HINT.faded.length).toBeGreaterThan(0);
    expect(AGE_HINT.warn).toContain("续命");
    expect(AGE_HINT.dread.length).toBeGreaterThan(0);
  });
});

describe("天数人话化（飘字用）", () => {
  it("按量级切换单位", () => {
    expect(daysText(3)).toContain("天");
    expect(daysText(60)).toContain("个月");
    expect(daysText(400)).toContain("年");
    expect(daysText(1080)).toContain("年");
  });

  it("边界不抛异常", () => {
    expect(() => daysText(0)).not.toThrow();
    expect(() => daysText(-10)).not.toThrow();
  });
});

describe("寿元字段的数据契约", () => {
  const typesSrc = readFileSync(path.join(process.cwd(), "src/game/types.ts"), "utf-8");

  it("GameState 覆盖后端 sanitize_state 新增的六个字段", () => {
    const iface = typesSrc.match(/interface GameState\s*\{([\s\S]*?)\n\}/);
    if (!iface) throw new Error("未在 types.ts 中找到 GameState");
    for (const key of ["days", "age", "lifespan", "life_bonus", "rest_count",
                       "seclusion_streak", "dead"]) {
      expect(iface[1], `GameState 缺字段 ${key}`).toContain(key);
    }
  });

  it("EngineMeta 带 age 明细（状态栏据此渲染）", () => {
    const iface = typesSrc.match(/interface EngineMeta\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1]).toContain("age?: AgeInfo");
    expect(iface?.[1]).toContain("life_extended");
    expect(iface?.[1]).toContain("lifespan_death");
  });

  it("ActResponse 带 dead（寿终后前端要收掉选项）", () => {
    const iface = typesSrc.match(/interface ActResponse\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1]).toContain("dead");
  });
});
