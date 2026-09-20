/* 页脚按钮的「样式到位」契约

   事故回顾：v3.3.3 新增「对局日志」入口时，只在 App.vue 里加了一个
   `<button id="btn-journal">`，忘了在 style.css 里配样式 —— 旁边三个按钮
   （坊市 / 仙缘令 / 再入轮回）都各有水墨描边 + hover 反色，唯独它是浏览器
   默认的系统灰方块，字体也掉了队。

   这类问题测试不该靠眼睛发现：页脚按钮是纯静态列表，把「每个按钮都得有
   配套 CSS」写成断言，下次再加按钮忘了样式就会当场红。 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const appSrc = readFileSync(path.join(process.cwd(), "src/App.vue"), "utf-8");
const cssSrc = readFileSync(path.join(process.cwd(), "src/style.css"), "utf-8")
  .replace(/\/\*[\s\S]*?\*\//g, "");   // 剥注释：注释里提到的旧写法不算生效声明

/** 页脚里出现的所有按钮 id（模板顺序即视觉顺序） */
const footer = appSrc.match(/<footer>[\s\S]*?<\/footer>/);
if (!footer) throw new Error("App.vue 里没找到 <footer>");
const ids = [...footer[0].matchAll(/id="(btn-[a-z]+)"/g)].map((m) => m[1]);

function rule(sel: string): string {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = cssSrc.match(new RegExp(`${esc}\\s*\\{([^}]*)\\}`, "m"));
  return m ? m[1] : "";
}

describe("页脚按钮：每个都得有配套样式", () => {
  it("解析出了一组按钮（否则下面的断言只是空跑）", () => {
    expect(ids.length).toBeGreaterThanOrEqual(4);
    for (const id of ["btn-shop", "btn-journal", "btn-savecode", "btn-restart"]) {
      expect(ids).toContain(id);
    }
  });

  it.each(ids)("%s 在 style.css 中有规则", (id) => {
    const body = rule(`#${id}`);
    expect(body, `#${id} 没有任何 CSS —— 会退化成浏览器默认按钮`).not.toBe("");
    // 水墨风统一用衬线字体；不继承会掉成系统 UI 字体，和整页不搭
    expect(body).toContain("font-family:inherit");
    expect(body).toContain("cursor:pointer");
    expect(body).toContain("border-radius");
  });

  it.each(ids)("%s 有 hover 反馈（与其余按钮手感一致）", (id) => {
    expect(rule(`#${id}:hover`), `#${id} 缺 hover 样式`).not.toBe("");
  });

  it("按钮成组排布，间距一致", () => {
    expect(appSrc).toContain('class="foot-btns"');
    const g = rule(".foot-btns");
    expect(g).toContain("display:flex");
    expect(g).toContain("gap:");
  });
});
