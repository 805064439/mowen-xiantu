/* 全状态抽屉的「可关闭性」契约

   事故回顾：抽屉原本是 position:absolute + bottom:0 且**没有高度上限**。
   物品多 / 江湖人物多时内容会把抽屉向上撑出视口 ✕ 被顶到屏幕外，
   遮罩又被抽屉完全盖住 —— 实测 iPhone SE(375×667) 下抽屉高 779px、
   top = -112px，✕ 中心点 elementFromPoint 返回 none，再也收不回来。

   这里不去模拟渲染（DOM 高度要真浏览器才有意义），而是锁住**能推导出正确布局的结构事实**：
   抽屉有高度上限 + 存在唯一的可滚动容器 + 内容都在这个容器里 + 关闭出口不止一处。
   任何一项被改坏，都意味着「抽屉可能又一次关不掉」。 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const _rawCss = readFileSync(path.join(process.cwd(), "src/style.css"), "utf-8");
// 剥掉注释再解析：注释里提到旧实现的 `max-height:32vh` 不该被当成仍在生效的声明
const cssSrc = _rawCss.replace(/\/\*[\s\S]*?\*\//g, "");
const vueSrc = readFileSync(path.join(process.cwd(), "src/components/StatusDrawer.vue"), "utf-8");

/** 取出某个选择器的 CSS 声明块（不含嵌套花括号，本项目 style.css 无嵌套） */
function rule(selector: string): string {
  const esc = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = cssSrc.match(new RegExp(`${esc}\\s*\\{([^}]*)\\}`, "m"));
  if (!m) throw new Error(`未在 style.css 中找到规则 ${selector}`);
  return m[1];
}

function declAfter(selector: string, prop: string): string {
  const m = rule(selector).match(new RegExp(`${prop}\\s*:\\s*([^;]+);`));
  return m ? m[1].trim() : "";
}

describe("状态抽屉：高度必须封顶", () => {
  it("抽屉有 max-height，且不到满屏（给遮罩留出可点区域）", () => {
    const mh = declAfter(".drawer", "max-height");
    expect(mh, ".drawer 缺少 max-height —— 内容会撑爆视口，✕ 与遮罩都将被顶出屏幕").not.toBe("");
    const pct = Number(mh.replace("vh", ""));
    expect(pct).toBeGreaterThan(0);
    expect(pct).toBeLessThan(100);   // 100vh 在手机浏览器会因地址栏溢出，必须留余量
  });

  it("抽屉自身不滚动（overflow 交给内容区，否则 flex 撑高与滚动冲突）", () => {
    expect(declAfter(".drawer", "overflow")).toBe("hidden");
  });
});

describe("状态抽屉：可滚动内容区 .drawer-body", () => {
  it("存在且可竖向滚动", () => {
    expect(declAfter(".drawer-body", "overflow-y")).toBe("auto");
    // flex 子项要能滚动必须有 min-height:0，否则会被内容撑成全高、滚动失效
    expect(declAfter(".drawer-body", "min-height")).toBe("0");
  });

  it("与漫画/Android 浏览器的滚动传递隔离（overscroll-behavior: contain）", () => {
    expect(declAfter(".drawer-body", "overscroll-behavior")).toBe("contain");
  });

  it("所有内容区块都被包进 .drawer-body（不在滚动区外撑高抽屉）", () => {
    const open = vueSrc.indexOf('<div class="drawer-body">');
    expect(open, "StatusDrawer.vue 缺少 .drawer-body 容器").toBeGreaterThan(-1);
    for (const block of ["drawer-head", "drawer-bars", "drawer-age", "drawer-stones",
                         "drawer-items", "drawer-npcs", "drawer-foot"]) {
      const at = vueSrc.indexOf(`class="${block}"`);
      expect(at, `模板里没找到 ${block}`).toBeGreaterThan(-1);
      expect(at, `${block} 跑到滚动区外了，会把抽屉撑高`).toBeGreaterThan(open);
    }
  });

  it("物品区不再自带滚动坑（旧实现 max-height:32vh 造成嵌套滚动）", () => {
    expect(declAfter(".drawer-items", "max-height")).toBe("");
    expect(declAfter(".drawer-items", "overflow-y")).not.toBe("auto");
  });
});

describe("状态抽屉：关闭出口必须冗余", () => {
  it("✕ 按钮、抓取条、遮罩点击三者在位", () => {
    expect(vueSrc).toContain('class="drawer-close"');
    expect(vueSrc).toContain('class="drawer-grip"');
    expect(vueSrc).toContain('@click="close"');
  });

  it("ESC 也能收起（桌面端保底）", () => {
    expect(vueSrc).toContain('key === "Escape"');
  });

  it("关闭时要解开 body 的滚动锁", () => {
    expect(vueSrc).toContain('classList.remove("no-scroll")');
  });
});
