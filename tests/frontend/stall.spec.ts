/* 追索停滞的前端契约（v3.6）

   裁决全在后端：连追同一件事数轮 → 第 3 轮起逼结果 → 第 5 轮由天道自行划去。
   前端只负责两件事：
     ① 类型契约跟得上后端（state.stall / state.dry，engine_meta.stall 供日志导出）；
     ② 玩家看得见自己在原地打转——抽屉里要有「久 追 未 果」区块，且必须有样式。
   ② 尤其不能靠眼睛发现：上次「对局日志」按钮就是只写了标签没写 CSS，
      退化成系统灰方块。所以这里照 footer.spec.ts 的规矩，把样式也写成断言。 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { STALL_FORCE_TURNS, STALL_TAKEOVER_TURNS, STALL_HOP_MAX } from "../../src/game/constants";

const typesSrc = readFileSync(path.join(process.cwd(), "src/game/types.ts"), "utf-8");
const drawerSrc = readFileSync(path.join(process.cwd(), "src/components/StatusDrawer.vue"), "utf-8");
const serverSrc = readFileSync(path.join(process.cwd(), "server.py"), "utf-8");
const cssSrc = readFileSync(path.join(process.cwd(), "src/style.css"), "utf-8")
  .replace(/\/\*[\s\S]*?\*\//g, "");

function rule(sel: string): string {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = cssSrc.match(new RegExp(`${esc}\\s*\\{([^}]*)\\}`, "m"));
  return m ? m[1] : "";
}

/** 从 server.py 里取同名常量——前后端阈值一旦分家，抽屉上的提示就会骗人。 */
function backendConst(name: string): number {
  const m = serverSrc.match(new RegExp(`^${name}\\s*=\\s*(\\d+)`, "m"));
  return m ? Number(m[1]) : NaN;
}

describe("阈值：前后端必须同值", () => {
  it("逼结果的轮次一致", () => {
    expect(backendConst("STALL_FORCE_TURNS")).toBe(STALL_FORCE_TURNS);
  });

  it("天道接管的轮次一致", () => {
    expect(backendConst("STALL_TAKEOVER_TURNS")).toBe(STALL_TAKEOVER_TURNS);
  });

  it("换乘上限一致（v3.8）", () => {
    expect(backendConst("STALL_HOP_MAX")).toBe(STALL_HOP_MAX);
  });

  it("先给 AI 几轮机会，再谈接管", () => {
    expect(STALL_FORCE_TURNS).toBeLessThan(STALL_TAKEOVER_TURNS);
  });
});

describe("类型契约：追索计数进了 GameState", () => {
  it("GameState 带 stall 与 dry", () => {
    expect(typesSrc).toMatch(/stall\?:\s*\{[^}]*count\?:\s*number/);
    expect(typesSrc).toMatch(/dry\?:\s*number/);
  });

  it("GameState 带换乘次数 hop（v3.8）", () => {
    expect(typesSrc).toMatch(/hop\?:\s*number/);
  });

  it("engine_meta 带 stall 明细（导出日志要用）", () => {
    expect(typesSrc).toMatch(/stall\?:\s*\{[\s\S]*?takeover\?:\s*boolean/);
  });

  it("台账变动里也记了「换了罢手选项」", () => {
    expect(typesSrc).toMatch(/resolve_used\?:\s*boolean/);
  });
});

describe("状态抽屉：玩家看得见自己在原地打转", () => {
  it("渲染了久追未果区块", () => {
    expect(drawerSrc).toContain("久 追 未 果");
    expect(drawerSrc).toMatch(/class="drawer-stall"/);
  });

  it("读的是 state.stall 而不是别的来源", () => {
    expect(drawerSrc).toMatch(/game\.state\?\.stall\?\.count/);
  });

  it("未达阈值不显示（别拿鸡毛当令箭）", () => {
    expect(drawerSrc).toMatch(/stallShown/);
    expect(drawerSrc).toMatch(/stallCount\.value\s*>=\s*STALL_FORCE_TURNS/);
  });

  it("写明了再拖下去的后果", () => {
    expect(drawerSrc).toMatch(/天道将落下结果|本轮必须了结/);
  });

  it("换乘也要显示出来（v3.8：被搬了几站比连点几轮更要命）", () => {
    expect(drawerSrc).toMatch(/game\.state\?\.hop/);
    expect(drawerSrc).toContain("已换 {{ stallHop }} 处落脚");
    expect(drawerSrc).toMatch(/STALL_HOP_MAX/);
  });
});

describe("久追未果区块的样式不能缺", () => {
  it.each([".drawer-stall", ".stall-row", ".st-label", ".st-count", ".st-warn",
           ".st-relay", ".st-hop"])(
    "%s 有配套 CSS", (sel) => {
      expect(rule(sel), `${sel} 没有任何 CSS —— 会退化成默认排版`).not.toBe("");
    });

  it("用了警示色（否则混在一堆灰字里没人看得见）", () => {
    expect(rule(".st-label")).toContain("var(--seal)");
  });
});
