/* 未决之事台账的前端契约（v3.5）

   台账的裁决全在后端，前端只负责两件事：
     ① 类型契约跟得上后端（threads / chronicle 字段存在）；
     ② 玩家看得见自己欠了什么——状态抽屉里要有「未决之事」区块，且必须有样式。
   ② 尤其不能靠眼睛发现：上次「对局日志」按钮就是只写了标签没写 CSS，
      退化成系统灰方块。所以这里照 footer.spec.ts 的规矩，把样式也写成断言。 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const typesSrc = readFileSync(path.join(process.cwd(), "src/game/types.ts"), "utf-8");
const drawerSrc = readFileSync(path.join(process.cwd(), "src/components/StatusDrawer.vue"), "utf-8");
const cssSrc = readFileSync(path.join(process.cwd(), "src/style.css"), "utf-8")
  .replace(/\/\*[\s\S]*?\*\//g, "");

function rule(sel: string): string {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = cssSrc.match(new RegExp(`${esc}\\s*\\{([^}]*)\\}`, "m"));
  return m ? m[1] : "";
}

describe("类型契约：台账字段进了 GameState", () => {
  it("GameState 带 threads 与 chronicle", () => {
    expect(typesSrc).toMatch(/threads\?:\s*ThreadEntry\[\]/);
    expect(typesSrc).toMatch(/chronicle\?:\s*string\[\]/);
  });

  it("ThreadEntry 含认线所需的字段", () => {
    expect(typesSrc).toMatch(/interface ThreadEntry/);
    for (const f of ["title", "cat", "open", "last", "due", "note"]) {
      expect(typesSrc).toMatch(new RegExp(`${f}\\??:`));
    }
  });

  it("engine_meta 带 threads 变动（导出日志要用）", () => {
    expect(typesSrc).toMatch(/threads\?:\s*\{[\s\S]*?opened\?:\s*string\[\]/);
    expect(typesSrc).toMatch(/recall_used\?:\s*boolean/);
  });
});

describe("状态抽屉：玩家看得见未决之事", () => {
  it("渲染了未决之事区块", () => {
    expect(drawerSrc).toContain("未 决 之 事");
    expect(drawerSrc).toMatch(/class="drawer-threads"/);
    expect(drawerSrc).toMatch(/v-for="t in threads"/);
  });

  it("逾期会标出来（欠得最久的那条最该被看见）", () => {
    expect(drawerSrc).toContain("isOverdue(t)");
    expect(drawerSrc).toContain("已逾期");
  });

  it("读的是 state.threads 而不是别的来源", () => {
    expect(drawerSrc).toMatch(/game\.state\?\.threads/);
  });
});

describe("台账区块的样式不能缺", () => {
  it.each([".drawer-threads", ".dt-title", ".thread-row", ".th-cat", ".th-title", ".th-when"])(
    "%s 有配套 CSS", (sel) => {
      expect(rule(sel), `${sel} 没有任何 CSS —— 会退化成默认排版`).not.toBe("");
    });

  it("逾期态有专门的颜色（否则看不出哪条该去收）", () => {
    expect(cssSrc).toMatch(/\.thread-row\.overdue\s*\.[a-z-]+\s*\{[^}]*var\(--seal\)/);
  });
});
