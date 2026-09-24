/* 世界常量：自身结构 + 与后端 server.py 的跨语言一致性

   前端这套常量只是「展示用的副本」，真正的权威在后端 REALM_TABLE。
   两边一旦漂移，玩家会在进度条上看到与实际门槛不符的数字，
   而这类偏差在构建期、运行期都不报错 —— 只能靠这里的红叉发现。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { REALMS, EXP_MAX, INIT_STATE, OPENING, INIT_CHOICES, VERSION } from "../../src/game/constants";

/** 向上寻找后端源码（不依赖 cwd），把它作为「数值权威」来比对 */
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

/** 从后端源码里解出 REALM_TABLE，避免拿 shadow copy 做基准 */
function parseBackendRealmTable() {
  const block = serverSrc.match(/REALM_TABLE\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("未在 server.py 中找到 REALM_TABLE");
  const rows = [...block[1].matchAll(/\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/g)];
  if (rows.length === 0) throw new Error("REALM_TABLE 解析结果为空，正则可能已失效");
  return rows.map((r) => ({ name: r[1], exp: Number(r[2]), rate: Number(r[3]) }));
}

const backendTable = parseBackendRealmTable();

describe("境界常量自身结构", () => {
  it("境界名从炼气一层排到筑基初期", () => {
    expect(REALMS[0]).toBe("炼气一层");
    expect(REALMS[REALMS.length - 1]).toBe("筑基初期");
    expect(REALMS).toHaveLength(10);
  });

  it("EXP_MAX 与境界一一对应且严格递增", () => {
    expect(EXP_MAX).toHaveLength(REALMS.length);
    for (let i = 1; i < EXP_MAX.length; i++) {
      expect(EXP_MAX[i]).toBeGreaterThan(EXP_MAX[i - 1]);
    }
  });

  it("最后一层为不可突破的天花板", () => {
    expect(EXP_MAX[EXP_MAX.length - 1]).toBeGreaterThan(10 ** 3);
  });
});

describe("前后端常量一致性", () => {
  it("境界名与后端完全一致", () => {
    expect(REALMS.slice(0, backendTable.length)).toEqual(backendTable.map((r) => r.name));
  });

  it("每层修为上限与后端 REALM_TABLE 完全一致", () => {
    expect(EXP_MAX.slice(0, backendTable.length)).toEqual(backendTable.map((r) => r.exp));
  });

  it("后端每个境界的升级门槛都通向正确的下一境界", () => {
    backendTable.forEach((row, i) => {
      if (i + 1 < backendTable.length) {
        expect(EXP_MAX[i]).toBe(row.exp);
        expect(REALMS[i + 1]).toBe(backendTable[i + 1].name);
      }
    });
  });

  it("后端筑基之上的修为上限与前端一致", () => {
    const foundationMax = Number(/MAX_REALM_INDEX\s*=\s*(\d+)/.exec(serverSrc)?.[1]);
    expect(foundationMax).toBe(REALMS.length - 1);
  });
});

describe("版本号", () => {
  it("形如 x.y.z", () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("与后端 VERSION 完全一致", () => {
    const backend = /^VERSION\s*=\s*"([^"]+)"/m.exec(serverSrc)?.[1];
    expect(backend, "未在 server.py 中找到 VERSION").toBeTruthy();
    expect(VERSION).toBe(backend);
  });

  it("后端 /api/health 会把版本吐出去", () => {
    // 用 indexOf 切片而非多行正则：server.py 在 Windows 下检出是 CRLF，
    // `\n\n\n` 这类字面量匹配会静默失效（正则能跑，只是抓不到）。
    const at = serverSrc.indexOf("def health():");
    const tail = at >= 0 ? serverSrc.slice(at, at + 400) : "";
    const nextDef = tail.indexOf("\ndef ", 4);
    const fn = nextDef > 0 ? tail.slice(0, nextDef) : tail;
    expect(fn, "未在 server.py 中定位到 health()").toContain("VERSION");
  });

  it("界面确实把它渲染出来了（页脚 #ver）", () => {
    const app = readFileSync(path.join(process.cwd(), "src/App.vue"), "utf-8");
    expect(app).toContain('id="ver"');
    expect(app).toMatch(/v\{\{\s*VERSION\s*\}\}/);
  });
});

describe("开局数据", () => {
  it("开局状态字段齐备且均为合法数值", () => {
    expect(INIT_STATE.hp).toBeGreaterThan(0);
    expect(INIT_STATE.hp).toBeLessThanOrEqual(INIT_STATE.hp_max);
    expect(INIT_STATE.qi).toBeGreaterThan(0);
    expect(INIT_STATE.qi).toBeLessThanOrEqual(INIT_STATE.qi_max);
    expect(INIT_STATE.exp).toBeLessThan(EXP_MAX[0]);
    expect(INIT_STATE.spirit_stones).toBeGreaterThanOrEqual(0);
    expect(INIT_STATE.realm_index).toBe(0);
    expect(INIT_STATE.turn).toBe(0);
  });

  it("开局自带物品数量合法", () => {
    INIT_STATE.items.forEach((it) => {
      expect(it.qty).toBeGreaterThan(0);
      expect(["下品", "中品", "上品"]).toContain(it.rarity);
      expect(it.name.length).toBeGreaterThan(0);
    });
  });

  it("开局灵根为空 —— 由天道在首轮掷定", () => {
    expect((INIT_STATE as Record<string, unknown>).spirit_root).toBeUndefined();
  });

  it("开局三个选项齐备，含稳妥选项", () => {
    expect(INIT_CHOICES).toHaveLength(3);
    expect(INIT_CHOICES.map((c) => c.id)).toEqual(["A", "B", "C"]);
    expect(INIT_CHOICES.some((c) => c.risk === "low")).toBe(true);
    INIT_CHOICES.forEach((c) => expect(c.text.length).toBeLessThanOrEqual(24));
  });

  it("序章文案非空且具备开场钩子", () => {
    expect(OPENING.length).toBeGreaterThan(50);
    expect(OPENING).toContain("青牛山");
  });
});
