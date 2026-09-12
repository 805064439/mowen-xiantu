/* 道具图鉴：与后端 ITEM_TABLE 的一致性 + 文案可读性

   背景：行囊里的道具点一下就直接服用，而界面上从未写过它有什么用。
   修这个体验缺口时引入了 ITEM_INFO（前端图鉴），但图鉴本身也是一份
   「副本」—— 后端改了丹药数值、前端还写着旧功效，玩家就会按错说明吃药。
   所以这里把后端 ITEM_TABLE 当权威，逐条比对前端的 effect 文案。 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { ITEM_INFO, itemInfo, canUseItem } from "../../src/game/constants";

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

/** 解析后端 ITEM_TABLE：{ 名称 -> { hp_pct: 0.3, exp: 25, ... } } */
function parseBackendItemTable(): Record<string, Record<string, number>> {
  const block = serverSrc.match(/ITEM_TABLE\s*=\s*\{([\s\S]*?)\n\}/);
  if (!block) throw new Error("未在 server.py 中找到 ITEM_TABLE");
  const out: Record<string, Record<string, number>> = {};
  for (const m of block[1].matchAll(/"([^"]+)":\s*\{\s*"effect":\s*\{([^}]*)\}/g)) {
    const eff: Record<string, number> = {};
    for (const kv of m[2].matchAll(/"(\w+)":\s*(-?[\d.]+)/g)) {
      eff[kv[1]] = Number(kv[2]);
    }
    out[m[1]] = eff;
  }
  if (Object.keys(out).length === 0) throw new Error("ITEM_TABLE 解析结果为空，正则可能已失效");
  return out;
}

const backendItems = parseBackendItemTable();

/** 把后端 effect 结构翻译成人话（与前端 ITEM_INFO.effect 的写法对齐） */
function effectToText(eff: Record<string, number>): string {
  const parts: string[] = [];
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const num = (v: number) => (Number.isInteger(v) ? String(v) : String(v));
  if ("exp" in eff) parts.push(`修为 +${num(eff.exp)}`);
  if ("hp_pct" in eff) parts.push(`回复 ${pct(eff.hp_pct)} 气血`);
  if ("hp" in eff) parts.push(`气血 +${num(eff.hp)}`);
  if ("qi_pct" in eff) parts.push(`回复 ${pct(eff.qi_pct)} 灵力`);
  if ("qi" in eff) parts.push(`灵力 +${num(eff.qi)}`);
  return parts.join("、");
}

describe("道具图鉴与后端 ITEM_TABLE 一致", () => {
  it("后端收录的每味丹药，前端图鉴都得有，且标记为可服用", () => {
    for (const name of Object.keys(backendItems)) {
      const info = ITEM_INFO[name];
      expect(info, `图鉴缺少「${name}」`).toBeTruthy();
      expect(info.kind, `「${name}」在后端可服用，前端却不是丹药`).toBe("pill");
      expect(canUseItem(name)).toBe(true);
    }
  });

  it("功效文案与后端数值逐条吻合（后端改数值而前端没改 → 这里变红）", () => {
    for (const [name, eff] of Object.entries(backendItems)) {
      expect(ITEM_INFO[name].effect, `「${name}」功效文案与后端不符`).toBe(effectToText(eff));
    }
  });

  it("前端不得凭空发明后端没有的丹药", () => {
    for (const [name, info] of Object.entries(ITEM_INFO)) {
      if (info.kind === "pill") {
        expect(backendItems[name], `图鉴里的「${name}」后端并无此药`).toBeTruthy();
      }
    }
  });

  it("每种丹药都有说明与服用时机提示", () => {
    for (const [name, info] of Object.entries(ITEM_INFO)) {
      if (info.kind !== "pill") continue;
      expect(info.desc.length, `「${name}」缺说明`).toBeGreaterThan(6);
      expect(info.hint?.length ?? 0, `「${name}」缺服用提示`).toBeGreaterThan(6);
    }
  });
});

describe("非丹药物品", () => {
  it("材料与兵刃一律不可服用", () => {
    const notPills = Object.entries(ITEM_INFO).filter(([, i]) => i.kind !== "pill");
    expect(notPills.length).toBeGreaterThan(0);
    for (const [name] of notPills) {
      expect(canUseItem(name)).toBe(false);
    }
  });

  it("开局自带的钝剑被识别为兵刃而非杂物", () => {
    expect(ITEM_INFO["师父的钝剑"]?.kind).toBe("gear");
    expect(canUseItem("师父的钝剑")).toBe(false);
  });

  it("掉落表出现的材料都有图鉴条目", () => {
    // 后端掉落表里的物品名（server.py 的 DROP_* 元组）
    const names = new Set<string>();
    for (const m of serverSrc.matchAll(/\(\s*"([^"]+)"\s*,\s*"(?:下品|中品|上品)"\s*,\s*[\d.]+\s*\)/g)) {
      names.add(m[1]);
    }
    expect(names.size).toBeGreaterThan(0);
    for (const n of names) {
      expect(ITEM_INFO[n], `掉落物「${n}」未收录进图鉴`).toBeTruthy();
    }
  });
});

describe("兜底行为", () => {
  it("未知物品不编造功效", () => {
    const info = itemInfo("天外奇物");
    expect(info.kind).toBe("material");
    expect(canUseItem("天外奇物")).toBe(false);
    expect(info.effect).toContain("不明");
    expect(info.desc.length).toBeGreaterThan(0);
  });

  it("空名不会抛异常", () => {
    expect(() => itemInfo("")).not.toThrow();
  });
});
