/* §6 修复 + v3.1 地基修复的「前端接线」守卫。

   前端在这两件事里只做一件事：**别把信息弄丢**——
     · 灵丹从「掉落即涨修为」变成「入背包 → 玩家主动服用 → 限时效率 buff」，
       所以状态栏必须真的有服用入口，否则这枚丹进了背包就再也用不掉；
     · 「行功一个周天」这类片刻工夫必须把 short 标记透传给后端，
       否则点一下会被推进整整五年（§6 的那个 bug 会原地复活）。

   这两条都藏在组件里，没有 @vue/test-utils 无法 mount，故与 treasure.spec.ts
   一样改用源码级断言：它们守的是「接线存在」，不是「像素长什么样」。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

function findUp(name: string): string {
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    const candidate = path.join(dir, name);
    if (existsSync(candidate)) return candidate;
    dir = path.dirname(dir);
  }
  throw new Error(`未能在 ${process.cwd()} 及其上级目录中找到 ${name}`);
}

const src = (p: string) => readFileSync(path.join(process.cwd(), p), "utf-8");

const serverSrc = readFileSync(findUp("server.py"), "utf-8");
const choiceListSrc = src("src/components/ChoiceList.vue");
const statusPanelSrc = src("src/components/StatusPanel.vue");
const typesSrc = src("src/game/types.ts");
const constantsSrc = src("src/game/constants.ts");

describe("§6 短修行：前端必须把 short 透传给后端", () => {
  it("Choice 类型带 short 字段", () => {
    const iface = typesSrc.match(/interface Choice\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1], "Choice 缺 short").toContain("short");
  });

  it("GameAction 带 short 字段（否则请求体里会丢）", () => {
    const iface = typesSrc.match(/interface GameAction\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1], "GameAction 缺 short").toContain("short");
  });

  it("ChoiceList 的 pick() 原样带上 c.short", () => {
    expect(choiceListSrc).toMatch(/short:\s*c\.short/);
  });

  it("短修行选项在徽标上有可感知的区分（否则玩家以为修行变弱了）", () => {
    expect(choiceListSrc).toMatch(/c\.tag === "cultivate" && c\.short/);
  });
});

describe("v3.1 灵丹：前端必须提供服用入口", () => {
  it("StatusPanel 会派发 use_elixir 动作", () => {
    expect(statusPanelSrc).toContain('type: "use_elixir"');
  });

  it("服用按钮只在持有灵丹时出现，且受输入锁约束", () => {
    expect(statusPanelSrc).toMatch(/v-if="elixirQty > 0"/);
    expect(statusPanelSrc).toMatch(/game\.loading \|\| game\.inputLocked/);
  });

  it("丹力剩余轮数常驻可见（只给 buff 的机制必须让玩家看到倒计时）", () => {
    expect(statusPanelSrc).toMatch(/elixir_buff/);
    expect(statusPanelSrc).toMatch(/elixirBuff > 0/);
  });

  it("前端文案不再宣称灵丹「直接给修为」", () => {
    const elixirDesc = constantsSrc.match(/elixir:\s*\{[^}]*\}/)?.[0] ?? "";
    expect(elixirDesc).not.toContain("即时修为");
    expect(elixirDesc).not.toContain("直长修为");
    expect(elixirDesc).not.toContain("唯一直接给修为");
  });
});

describe("v3.1 地基：后端常量与实现口径", () => {
  it("奇遇表已清空（非闭关行动不得有脱离天数的修为）", () => {
    const m = serverSrc.match(/^FORTUNE_EXP\s*=\s*\{\}/m);
    expect(m, "FORTUNE_EXP 必须为空表").toBeTruthy();
  });

  it("灵丹在 TREASURE 里只有效率 buff，没有 exp 区间", () => {
    const elixir = serverSrc.match(/"elixir":\s*\{[^}]*\}/)?.[0] ?? "";
    expect(elixir).toContain("eff_buff");
    expect(elixir).toContain("buff_rounds");
    expect(elixir).not.toContain('"exp"');
  });

  it("灵丹 buff 只在修行回合倒计时（探索不消耗）", () => {
    expect(serverSrc).toMatch(/action_tag in TREASURE_EFF_TAGS:[\s\S]{0,200}elixir_buff/);
  });

  it("服务端对 elixir_buff 做了白名单钳制（防注入 9999 轮）", () => {
    expect(serverSrc).toMatch(/"elixir_buff":\s*_int\(raw\.get\("elixir_buff"\),\s*0,\s*ELIXIR_BUFF_ROUNDS/);
  });
});

describe("§6 短修行：后端跨度与关键词兜底", () => {
  it("SHORT_CULTIVATE_DAYS 是一个远小于闭关跨度的正区间", () => {
    const m = serverSrc.match(/SHORT_CULTIVATE_DAYS\s*=\s*\((\d+),\s*(\d+)\)/);
    expect(m, "未找到 SHORT_CULTIVATE_DAYS").toBeTruthy();
    const lo = Number(m![1]);
    const hi = Number(m![2]);
    expect(lo).toBeGreaterThanOrEqual(1);
    expect(hi).toBeGreaterThanOrEqual(lo);
    expect(hi).toBeLessThan(30);           // 必须远小于一次闭关（1260~2340 天）
  });

  it("关键词兜底覆盖「周天」等叙事写法", () => {
    const m = serverSrc.match(/SHORT_CULTIVATE_HINTS\s*=\s*\(([\s\S]*?)\)/);
    expect(m, "未找到 SHORT_CULTIVATE_HINTS").toBeTruthy();
    expect(m![1]).toContain("周天");
  });

  it("normalize_choices 保留 short（丢了等于修复失效）", () => {
    expect(serverSrc).toMatch(/"short":\s*bool\(c\.get\("short"\)\)/);
  });

  it("两处路由都透传了 short（/api/act 与 /api/act/stream 不得分叉）", () => {
    const hits = [...serverSrc.matchAll(/short\s*=\s*is_short_cultivate\(action\)/g)];
    expect(hits.length, "short 必须在两路端点都被解出").toBe(2);
    const passes = [...serverSrc.matchAll(/_postprocess_turn\([^)]*short=short/g)];
    expect(passes.length).toBeGreaterThanOrEqual(2);
  });

  it("演武数据里的「周天」选项带 short 标记", () => {
    const hits = [...serverSrc.matchAll(/"text":\s*"[^"]*周天[^"]*"[^}]*"short":\s*True/g)];
    expect(hits.length).toBeGreaterThanOrEqual(2);
  });

  it("提示词教会模型 short 契约", () => {
    const prompt = serverSrc.slice(serverSrc.indexOf("SYSTEM_PROMPT"));
    expect(prompt).toContain('"short": true');
    expect(prompt).toContain("周天");
  });
});
