/* 选项行的排版契约：徽标不许把行动句子顶到第二行

   事故回顾（v3.12.4）：行动徽标（「探索 · 25~60 天」）原本写在 .ctext 里面，
   跟着行动句子一起排版。选了「修行/探索」的选项一多，14 字以上的行动就会被
   徽标顶到第二行 —— 手机上 390px 宽时，一整列选项全是两行，且折点很丑
   （「……驿卜 / 三」）。

   修法两条，缺一不可：
   1. 徽标搬出 .ctext，成为按钮 flex 行里的独立一列（右侧信息列）；
   2. 窄屏把徽标里的类型词（「探索 · 」约 42px）收起来，只留耗时。

   这条契约用源码断言守住：一旦有人把徽标挪回句子里，测试当场红。 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const read = (p: string) => readFileSync(path.join(process.cwd(), p), "utf-8");
const choiceListSrc = read("src/components/ChoiceList.vue");
const cssSrc = read("src/style.css").replace(/\/\*[\s\S]*?\*\//g, "");

function cssRule(sel: string): string {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return cssSrc.match(new RegExp(`${esc}\\s*\\{([^}]*)\\}`, "m"))?.[1] ?? "";
}

const narrow = cssSrc.match(/@media \(max-width:480px\)\{[\s\S]*?\n\}/)?.[0] ?? "";

describe("选项行：徽标是独立一列，不参与句子换行", () => {
  it("模板里徽标排在 .ctext 之外（顺序：句子 → 提示 → 徽标）", () => {
    const tpl = choiceListSrc.slice(choiceListSrc.indexOf("<template>"));
    const textIdx = tpl.indexOf('class="ctext"');
    const tagIdx = tpl.indexOf('class="ctag"');
    expect(textIdx, "找不到 .ctext").toBeGreaterThan(-1);
    expect(tagIdx, "找不到 .ctag").toBeGreaterThan(textIdx);
    // 徽标之前，.ctext 必须已经闭合：区间内至少两个 </span>
    // （提示行 .chint 一个、.ctext 自己一个）。只有一个说明徽标还在句子里。
    const between = tpl.slice(textIdx, tagIdx);
    expect((between.match(/<\/span>/g) || []).length,
      "徽标又回到 .ctext 里了 —— 窄屏一整列选项会重新变成两行").toBeGreaterThanOrEqual(2);
  });

  it("CSS 按 flex 子项排徽标（不是行内元素）", () => {
    const body = cssRule(".ctag");
    expect(body).toContain("flex:none");
    expect(body).not.toContain("inline-block");
    expect(body).not.toContain("vertical-align");
    expect(body, "徽标要能整块不折行").toContain("white-space:nowrap");
  });

  it("窄屏徽标只留耗时（类型词让位给行动句子）", () => {
    expect(choiceListSrc, "徽标缺 ctag-kind 包裹").toContain('class="ctag-kind"');
    expect(narrow, "窄屏没把类型词收起来").toMatch(/\.ctag-kind\{[^}]*display:none/);
  });

  it("窄屏给行动句子腾了宽度（字号/内边距/间距都紧了）", () => {
    expect(narrow).toMatch(/\.choice\{[^}]*font-size:14\.5px/);
    expect(narrow).toMatch(/\.choice\{[^}]*gap:6px/);
  });
});
