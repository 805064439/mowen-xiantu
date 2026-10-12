/* v3.13 舆图 + NPC 详情卡的「到位」契约

   背景：M1/N2/N3 新增了三个前端入口（舆图弹窗、NPC 详情卡、页脚舆图按钮），
   这类「加了 Vue 组件但忘了挂载/忘了样式/地名漂移」的问题不该靠眼睛发现。
   用静态断言把它们钉住：
     1. 页脚有「舆图」按钮（btn-map）
     2. App.vue 挂载了 MapModal 与 NpcDetail
     3. 前端 PLACES 与后端 server.py 的 LOCATIONS 键名完全一致（地名漂移是高压线）
     4. 详情卡把四种往来操作 + 三种结契都摆在按钮上
     5. types.ts 的 NpcEntry 有 pact / op_cd 字段（与后端 sanitize 对齐） */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const cwd = process.cwd();
const appSrc = readFileSync(path.join(cwd, "src/App.vue"), "utf-8");
const mapSrc = readFileSync(path.join(cwd, "src/components/MapModal.vue"), "utf-8");
const npcSrc = readFileSync(path.join(cwd, "src/components/NpcDetail.vue"), "utf-8");
const constSrc = readFileSync(path.join(cwd, "src/game/constants.ts"), "utf-8");
const typesSrc = readFileSync(path.join(cwd, "src/game/types.ts"), "utf-8");
const serverSrc = readFileSync(path.join(cwd, "server.py"), "utf-8");

describe("舆图（M1）", () => {
  it("页脚有舆图按钮，且挂载了 MapModal", () => {
    expect(appSrc).toContain('id="btn-map"');
    expect(appSrc).toContain("MapModal");
    expect(appSrc).toContain("<MapModal");
  });

  it("前端地点表与后端 LOCATIONS 键名一一对应（地名漂移是高压线）", () => {
    const backendBlock = serverSrc.match(/LOCATIONS = \{([\s\S]*?)\n\}/);
    if (!backendBlock) throw new Error("server.py 未找到 LOCATIONS");
    const backendKeys = [...backendBlock[1].matchAll(/"(\w+)":\s*\{/g)].map(m => m[1]).sort();
    const placesBlock = constSrc.match(/export const PLACES[^=]*=\s*\[([\s\S]*?)\n\];/);
    if (!placesBlock) throw new Error("constants.ts 未找到 PLACES");
    const frontendKeys = [...placesBlock[1].matchAll(/\{ key: "(\w+)",\s+name:/g)].map(m => m[1]).sort();
    expect(frontendKeys).toEqual(backendKeys);
  });

  it("舆图只展示、不给瞬移按钮（移动走叙事，不绕耗时风险）", () => {
    expect(mapSrc).not.toContain("npcAct");
    expect(mapSrc).not.toContain("shopAct");
  });

  it("每个地点都有 flavor 与 fauna（v3.13.1 点开看风土人情/出没妖兽）", () => {
    const placesBlock = constSrc.match(/export const PLACES[^=]*=\s*\[([\s\S]*?)\n\];/);
    if (!placesBlock) throw new Error("constants.ts 未找到 PLACES");
    const entries = placesBlock[1].match(/\{ key:/g) || [];
    expect(entries).toHaveLength(8);
    expect((placesBlock[1].match(/flavor:/g) || []).length).toBe(8);
    expect((placesBlock[1].match(/fauna:/g) || []).length).toBe(8);
  });

  it("点地点看风土人情 / 出没妖兽 / 可访故人三块（M2 前半）", () => {
    expect(mapSrc).toContain("md-flavor");
    expect(mapSrc).toContain("md-fauna");
    expect(mapSrc).toContain("md-residents");
  });
});

describe("NPC 详情卡（N1/N2/N3）", () => {
  it("App.vue 挂载了 NpcDetail", () => {
    expect(appSrc).toContain("NpcDetail");
    expect(appSrc).toContain("<NpcDetail");
  });

  it("详情卡摆出四种往来操作（赠礼/论道/打听/切磋）", () => {
    for (const op of ["npc_gift", "npc_talk", "npc_ask", "npc_spar"]) {
      expect(npcSrc, `缺操作 ${op}`).toContain(op);
    }
  });

  it("详情卡摆出三种结契（结拜/师徒/道侣）", () => {
    for (const p of ["sworn", "master", "companion"]) {
      expect(npcSrc, `缺结契 ${p}`).toContain(p);
    }
  });

  it("结契门槛写死在 90（bond≥90 才能结）", () => {
    expect(npcSrc).toContain("90");
  });

  it("NpcEntry 类型对齐后端 sanitize（pact + op_cd + location）", () => {
    const iface = typesSrc.match(/interface NpcEntry\s*\{([\s\S]*?)\n\}/);
    expect(iface?.[1]).toContain("pact");
    expect(iface?.[1]).toContain("op_cd");
    expect(iface?.[1]).toContain("location");   // v3.13.1：现居地（可访故人）
  });

  it("GameState 有 location 字段（舆图当前位置）", () => {
    expect(typesSrc).toContain("location?: string");
  });
});
