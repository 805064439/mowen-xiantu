/* 修炼节奏：前端只负责「把速度讲给玩家听」，真值全在后端。
   因此这里做两件事：
     1. 前端展示用的表（ACTION_INFO / STREAK_TABLE / 闭门公式）必须与 server.py 逐条一致 ——
        后端调了系数而前端没调，玩家看到的倍率就是假的；
     2. 纯函数（streakCoeff / seclusionCoeff / actionInfo）的兜底行为不许编造加成。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import {
  ACTION_INFO, actionInfo, STREAK_TABLE, STREAK_CAP, SECLUSION_STREAK,
  SECLUSION_DECAY, SECLUSION_FLOOR, streakCoeff, seclusionCoeff, coeffLabel,
  RISK_VOLATILITY, riskVolatility, riskLabel,
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

/** 解析 `NAME = { "key": 数值, ... }` 形式的字典 */
function parseNumDict(name: string): Record<string, number> {
  const block = serverSrc.match(new RegExp(`${name}\\s*=\\s*\\{([\\s\\S]*?)\\n\\}`));
  if (!block) throw new Error(`未在 server.py 中找到 ${name}`);
  const out: Record<string, number> = {};
  for (const m of block[1].matchAll(/"([a-z_]+)":\s*([\d.]+)/g)) out[m[1]] = Number(m[2]);
  if (Object.keys(out).length === 0) throw new Error(`${name} 解析为空，正则可能已失效`);
  return out;
}

/** 解析 `NAME = { "key": "中文", ... }` 形式的字典 */
function parseStrDict(name: string): Record<string, string> {
  const block = serverSrc.match(new RegExp(`${name}\\s*=\\s*\\{([\\s\\S]*?)\\n\\}`));
  if (!block) throw new Error(`未在 server.py 中找到 ${name}`);
  const out: Record<string, string> = {};
  for (const m of block[1].matchAll(/"([a-z_]+)":\s*"([^"]+)"/g)) out[m[1]] = m[2];
  if (Object.keys(out).length === 0) throw new Error(`${name} 解析为空，正则可能已失效`);
  return out;
}

/** 解析 `NAME = ((阈值, 系数), (阈值, 系数), ...)` */
function parseStreakTable(): [number, number][] {
  const block = serverSrc.match(/CULTIVATE_STREAK_TABLE\s*=\s*\(\(([\s\S]*?)\)\)/);
  if (!block) throw new Error("未在 server.py 中找到 CULTIVATE_STREAK_TABLE");
  return block[1].split("),").map(pair => {
    const nums = pair.match(/([\d.]+)\s*,\s*([\d.]+)/);
    if (!nums) throw new Error(`CULTIVATE_STREAK_TABLE 条目解析失败：${pair}`);
    return [Number(nums[1]), Number(nums[2])] as [number, number];
  });
}

function parseScalar(name: string): number {
  const m = serverSrc.match(new RegExp(`^${name}\\s*=\\s*([\\d.]+)`, "m"));
  if (!m) throw new Error(`未在 server.py 中找到 ${name}`);
  return Number(m[1]);
}

const backendCoeff = parseNumDict("ACTION_CULTIVATE_COEFF");
const backendLabel = parseStrDict("ACTION_CULTIVATE_LABEL");
const backendStreak = parseStreakTable();
const backendRisk = parseNumDict("RISK_VOLATILITY");

describe("行动系数与后端同源", () => {
  it("后端每个 tag 前端都有，系数一致", () => {
    for (const [tag, coeff] of Object.entries(backendCoeff)) {
      expect(ACTION_INFO[tag], `ACTION_INFO 缺少「${tag}」`).toBeTruthy();
      expect(ACTION_INFO[tag].coeff, `「${tag}」系数与后端不符`).toBe(coeff);
    }
  });

  it("前端不得凭空发明后端没有的行动类型", () => {
    for (const tag of Object.keys(ACTION_INFO)) {
      expect(backendCoeff[tag], `前端多出后端没有的 tag「${tag}」`).toBeTruthy();
    }
  });

  it("行动中文名与后端 ACTION_CULTIVATE_LABEL 一致", () => {
    for (const [tag, label] of Object.entries(backendLabel)) {
      expect(ACTION_INFO[tag].label, `「${tag}」中文名与后端不符`).toBe(label);
    }
  });

  it("每个行动都有取舍说明（玩家得知道选了会失去什么）", () => {
    for (const [tag, info] of Object.entries(ACTION_INFO)) {
      expect(info.note.length, `「${tag}」缺说明文案`).toBeGreaterThan(5);
    }
  });

  it("修行最快、交易最慢——系数排序不能乱", () => {
    expect(ACTION_INFO.cultivate.coeff).toBeGreaterThan(ACTION_INFO.rest.coeff);
    expect(ACTION_INFO.rest.coeff).toBeGreaterThan(ACTION_INFO.fight.coeff);
    expect(ACTION_INFO.fight.coeff).toBeGreaterThan(ACTION_INFO.explore.coeff);
    expect(ACTION_INFO.explore.coeff).toBeGreaterThan(ACTION_INFO.trade.coeff);
  });
});

describe("高风险波动幅度与后端同源", () => {
  it("前端 RISK_VOLATILITY 与后端逐条一致", () => {
    expect(RISK_VOLATILITY).toEqual(backendRisk);
  });

  it("只有高风险行动波动，低风险行动（cultivate/rest/trade/other）不波动", () => {
    for (const tag of ["cultivate", "rest", "trade", "other"]) {
      expect(riskVolatility(tag), `「${tag}」不应波动`).toBe(0);
    }
    expect(riskVolatility("fight")).toBe(backendRisk.fight);
    expect(riskVolatility("explore")).toBe(backendRisk.explore);
    expect(riskVolatility("unknown_tag")).toBe(0);
  });

  it("波动标注：>1 机缘、<1 事与愿违、=1 空", () => {
    expect(riskLabel(1.4)).toBe("机缘");
    expect(riskLabel(0.6)).toBe("事与愿违");
    expect(riskLabel(1.0)).toBe("");
  });
});

describe("连击与闭门公式与后端同源", () => {
  it("连击表逐条一致", () => {
    expect(STREAK_TABLE).toEqual(backendStreak);
  });

  it("连击封顶与闭门阈值一致，且封顶必须早于闭门（否则最高档永远吃不到）", () => {
    expect(STREAK_CAP).toBe(parseScalar("STREAK_CAP"));
    expect(SECLUSION_STREAK).toBe(parseScalar("SECLUSION_STREAK"));
    expect(STREAK_CAP).toBeLessThan(SECLUSION_STREAK);
  });

  it("闭门衰减参数一致", () => {
    expect(SECLUSION_DECAY).toBe(parseScalar("SECLUSION_DECAY"));
    expect(SECLUSION_FLOOR).toBe(parseScalar("SECLUSION_FLOOR"));
  });

  it("streakCoeff 覆盖到每一档，超出封顶不再增长", () => {
    expect(streakCoeff(0)).toBe(1.0);
    expect(streakCoeff(2)).toBe(1.1);
    expect(streakCoeff(3)).toBe(1.2);
    expect(streakCoeff(5)).toBe(1.4);
    expect(streakCoeff(99)).toBe(1.4);
  });

  it("seclusionCoeff 与后端 _seclusion_coeff 同式", () => {
    expect(seclusionCoeff(5)).toBe(1.0);                                  // 未越界
    expect(seclusionCoeff(6)).toBeCloseTo(0.6, 6);
    expect(seclusionCoeff(7)).toBeCloseTo(0.36, 6);
    expect(seclusionCoeff(8)).toBeCloseTo(0.3, 6);                        // 触底
    expect(seclusionCoeff(50)).toBe(0.3);
  });
});

describe("展示兜底", () => {
  it("未知 tag 按随缘而行，不编造加成", () => {
    const info = actionInfo("some_new_tag");
    expect(info.label).toBe("随缘而行");
    expect(info.coeff).toBe(1.0);
  });

  it("空 tag 不抛异常", () => {
    expect(() => actionInfo(undefined)).not.toThrow();
    expect(actionInfo("").coeff).toBe(1.0);
  });

  it("系数标签固定两位小数，读起来不抖", () => {
    expect(coeffLabel(2.39)).toBe("×2.39");
    expect(coeffLabel(1)).toBe("×1.00");
  });
});

describe("修为飘字的数据契约", () => {
  const typesSrc = readFileSync(path.join(process.cwd(), "src/game/types.ts"), "utf-8");

  it("CultivateInfo 覆盖后端 detail 的全部字段（漏字段 = 前端静默丢信息）", () => {
    const detailBlock = serverSrc.match(/detail\s*=\s*\{([\s\S]*?)\n    \}/);
    if (!detailBlock) throw new Error("未在 server.py 中找到 detail 明细块");
    const backendKeys = [...detailBlock[1].matchAll(/"(\w+)":/g)].map(m => m[1]);
    expect(backendKeys.length).toBeGreaterThan(5);
    const iface = typesSrc.match(/interface CultivateInfo\s*\{([\s\S]*?)\n\}/);
    if (!iface) throw new Error("未在 types.ts 中找到 CultivateInfo");
    for (const key of backendKeys) {
      expect(iface[1], `CultivateInfo 缺字段 ${key}`).toContain(key);
    }
  });

  it("Choice 支持 hint（冲关成功率提示）", () => {
    const iface = typesSrc.match(/interface Choice\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1]).toContain("hint");
  });

  it("GameState 支持 cultivate_streak（连修轮数随存档往返）", () => {
    const iface = typesSrc.match(/interface GameState\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1]).toContain("cultivate_streak");
  });
});
