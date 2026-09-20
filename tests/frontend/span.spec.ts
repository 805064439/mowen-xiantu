/* v3.2 修行粒度三档（span）+ 场景节奏（scene_pace）

   玩家体感的病根是「时间尺度在三处不一致」：
     · 数值层：闭关真是 5 年；
     · 选项层：徽标上写的是「潜心修行 +80%」，一个字没提时间；
     · 叙事层：选项文字写「行功一个周天」，实则也是 5 年。
   v3.1 只落了 short 布尔（两档），v3.2 补上三档与场景节奏。

   这里守四件事：
     1. 前端 CULTIVATE_SPAN / SCENE_PACE 与后端逐条一致（后端改了前端没改 = 玩家看到假时间）；
     2. spanHint / actionSpanHint 的文案口径不许错（"约5年" / "约1月" / "数日" / "顷刻"）；
     3. 三档必须严格递增且不重叠——否则玩家分不出档位；
     4. ChoiceList 必须对所有行动显示耗时，而不只是 explore 与片刻修行。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import {
  CULTIVATE_SPAN, SPAN_LABEL, DEFAULT_CULTIVATE_SPAN, SCENE_PACE_LABEL,
  ACTION_DAYS, spanHint, actionSpanHint, DAYS_PER_YEAR, INIT_CHOICES,
  exploreTierOfRisk,
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

function parseBackendSpan(): Record<string, [number, number]> {
  const body = parseBlock("CULTIVATE_SPAN");
  const out: Record<string, [number, number]> = {};
  for (const m of body.matchAll(/"(short|medium|long)":\s*\((\d+),\s*(\d+)\)/g)) {
    out[m[1]] = [Number(m[2]), Number(m[3])];
  }
  if (Object.keys(out).length !== 3) throw new Error("CULTIVATE_SPAN 解析不全");
  return out;
}

const backendSpan = parseBackendSpan();

describe("方案二：三档表前后端一致", () => {
  it("三档齐备且逐条同值", () => {
    for (const k of ["short", "medium", "long"]) {
      expect(CULTIVATE_SPAN[k], `前端缺 ${k} 档`).toEqual(backendSpan[k]);
    }
  });

  it("后端 long 档与 ACTION_DAYS.cultivate 同值", () => {
    const days = serverSrc.match(/"cultivate":\s*\((\d+),\s*(\d+)\)/);
    expect(days).toBeTruthy();
    expect(backendSpan.long).toEqual([Number(days![1]), Number(days![2])]);
  });

  it("前端 long 档与 ACTION_DAYS.cultivate 同值", () => {
    expect(CULTIVATE_SPAN.long).toEqual(ACTION_DAYS.cultivate);
  });

  it("三档严格递增且不重叠", () => {
    const [, sHi] = CULTIVATE_SPAN.short;
    const [mLo, mHi] = CULTIVATE_SPAN.medium;
    const [lLo] = CULTIVATE_SPAN.long;
    expect(sHi).toBeLessThan(mLo);
    expect(mHi).toBeLessThan(lLo);
  });

  it("默认档是 long（未标记的选项仍按整段闭关，不退化）", () => {
    expect(DEFAULT_CULTIVATE_SPAN).toBe("long");
    expect(serverSrc).toMatch(/DEFAULT_CULTIVATE_SPAN\s*=\s*"long"/);
  });

  it("三档都有中文标签", () => {
    for (const k of ["short", "medium", "long"]) {
      expect(SPAN_LABEL[k], `${k} 缺中文标签`).toBeTruthy();
    }
  });
});

describe("方案一：耗时文案口径", () => {
  it("整段闭关显示「约5年」", () => {
    expect(spanHint(...CULTIVATE_SPAN.long)).toBe("约5年");
  });

  it("静养显示「约1月」", () => {
    expect(spanHint(...ACTION_DAYS.rest)).toBe("约1月");
  });

  it("坊市显示「数日」", () => {
    expect(spanHint(...ACTION_DAYS.trade)).toBe("数日");
  });

  it("斗法显示「顷刻」", () => {
    expect(spanHint(...ACTION_DAYS.fight)).toBe("顷刻");
  });

  it("年/月/日/顷刻四档分界正确", () => {
    expect(spanHint(DAYS_PER_YEAR * 2, DAYS_PER_YEAR * 2)).toBe("约2年");
    expect(spanHint(30, 60)).toBe("约2月");
    expect(spanHint(3, 10)).toBe("数日");
    expect(spanHint(1, 2)).toBe("顷刻");
  });

  it("修行按 span 取耗时：片刻 / 数月 / 多年", () => {
    expect(actionSpanHint("cultivate", "short")).toBe("片刻");
    expect(actionSpanHint("cultivate", "medium")).toMatch(/月/);
    expect(actionSpanHint("cultivate", "long")).toMatch(/年/);
  });

  it("修行未给 span 时按整段闭关显示（不得显示成片刻）", () => {
    expect(actionSpanHint("cultivate", undefined)).toMatch(/年/);
    expect(actionSpanHint("cultivate", "HACK")).toMatch(/年/);   // 非法值兜底
  });

  it("非修行行动按 ACTION_DAYS 显示", () => {
    expect(actionSpanHint("rest")).toBe("约1月");
    expect(actionSpanHint("fight")).toBe("顷刻");
    expect(actionSpanHint("不存在的tag")).toBe(spanHint(...ACTION_DAYS.other));
  });
});

describe("方案一：ChoiceList 必须把时长摆到台面上", () => {
  const choiceList = readFileSync(
    path.join(process.cwd(), "src/components/ChoiceList.vue"), "utf-8");

  it("徽标对所有行动都拼上耗时（不再只给 explore 与片刻）", () => {
    expect(choiceList).toMatch(/text:\s*`\$\{info\.label\} · \$\{actionSpanHint\(c\.tag, c\.span\)\}`/);
  });

  it("悬停说明里给出确切天数区间", () => {
    expect(choiceList).toMatch(/耗时 \$\{lo\}~\$\{hi\} 天/);
  });

  it("picker 把 span 透传给后端（不传则一次吃掉五年）", () => {
    expect(choiceList).toMatch(/span:\s*c\.span/);
  });

  it("探索徽标显示的是时长，不是档位名（v3.4）", () => {
    // 探索一档就是 25~60 天；写「远行历练」玩家点之前看不出会被推进一个月
    expect(choiceList).toMatch(/探索 · \$\{spanHint\(\.\.\.tier\.days\)\}/);
    expect(choiceList).not.toMatch(/探索 · \$\{tier\.label\}/);
  });
});

describe("v3.4：探索三档的耗时文案必须能拉开区分", () => {
  it("三档文案互不相同（撞成同一个等于没显示）", () => {
    const hints = ["low", "mid", "high"].map((r) => spanHint(...exploreTierOfRisk(r).days));
    expect(new Set(hints).size).toBe(3);
  });

  it("中档「远行历练」显示的是「约1月」量级，而不是「数日」", () => {
    expect(spanHint(...exploreTierOfRisk("mid").days)).toBe("约1月");
    expect(spanHint(...exploreTierOfRisk("low").days)).toBe("数日");
    expect(spanHint(...exploreTierOfRisk("high").days)).toBe("约4月");
  });
});

describe("v3.2.4 回归：开局静态选项（INIT_CHOICES）不得缺 span", () => {
  it("所有 cultivate 开局选项都自带显式 span（否则会落到 DEFAULT=long 显示「约5年」，与后端按文字推断的时长脱节）", () => {
    for (const c of INIT_CHOICES) {
      if (c.tag === "cultivate") {
        expect((c as any).span, `开局选项「${c.text}」缺少 span，会误显示约5年`).toBeTruthy();
        expect(["short", "medium", "long"]).toContain((c as any).span);
      }
    }
  });

  it("「打坐半日」选项显示「片刻」而非「约5年」", () => {
    const halfDay = INIT_CHOICES.find((c) => c.text.includes("打坐半日"))!;
    expect(halfDay).toBeTruthy();
    expect(halfDay.tag).toBe("cultivate");
    expect((halfDay as any).span).toBe("short");
    expect(actionSpanHint("cultivate", "short")).toBe("片刻");
  });
});

describe("方案三：场景节奏常量同源", () => {
  it("三档节奏齐备", () => {
    expect(Object.keys(SCENE_PACE_LABEL).sort()).toEqual(["action", "downtime", "resolve"]);
    for (const v of Object.values(SCENE_PACE_LABEL)) expect(v).toBeTruthy();
  });

  it("后端同样定义了三档节奏与兜底分池", () => {
    expect(serverSrc).toMatch(/SCENE_PACE\s*=\s*\("action",\s*"resolve",\s*"downtime"\)/);
    expect(serverSrc).toMatch(/FILLER_BY_PACE/);
    expect(serverSrc).toMatch(/def filler_choices/);
  });

  it("空白期的兜底池含整段闭关，事件进行中不含", () => {
    const body = parseBlock("FILLER_BY_PACE");
    const downtime = body.slice(body.indexOf('"downtime"'));
    expect(downtime).toContain('"span": "long"');
  });

  it("提示词写明了节奏铁律（action 禁 long / downtime 应给 long）", () => {
    const prompt = serverSrc.slice(serverSrc.indexOf("SYSTEM_PROMPT"));
    expect(prompt).toContain("【场景节奏】");
    expect(prompt).toMatch(/action（事件进行中）/);
    expect(prompt).toMatch(/禁止/);
  });

  it("scene_pace 进了 sanitize_state 白名单（防注入）", () => {
    expect(serverSrc).toMatch(/"scene_pace":\s*raw\.get\("scene_pace"\)/);
  });

  it("GameState 类型带 scene_pace", () => {
    const types = readFileSync(path.join(process.cwd(), "src/game/types.ts"), "utf-8");
    expect(types).toMatch(/scene_pace\?: string/);
  });
});
