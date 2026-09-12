/* 世界常量：与后端 REALM_TABLE 保持一致（前端仅做展示） */

export const REALMS = [
  "炼气一层", "炼气二层", "炼气三层", "炼气四层", "炼气五层",
  "炼气六层", "炼气七层", "炼气八层", "炼气九层", "筑基初期",
];

export const EXP_MAX = [100, 130, 170, 260, 330, 400, 580, 680, 800, 9999];

export const INIT_STATE = {
  realm_index: 0, hp: 100, hp_max: 100, qi: 50, qi_max: 50,
  exp: 10, spirit_stones: 30,
  items: [
    { name: "回气丹", qty: 2, rarity: "下品" },
    { name: "师父的钝剑", qty: 1, rarity: "下品" },
  ],
  memory: ["独守青牛山破庙三年，师父云游未归", "昨夜炼气入体，初入炼气一层"],
  recent: [], turn: 0,
};

export const OPENING =
  "庆元十七年，秋。\n\n青牛山下的破庙里，你睁开眼。师父走了三年，留下半袋米、一柄钝剑，" +
  "和一句\"灵根如此，好自为之\"。昨夜，你终于炼气入体。\n\n山外妖兽近年频繁出没，坊市灵石价格一日三涨，" +
  "传闻北边荒泽又现秘境。米缸将尽——是时候下山了。";

export const INIT_CHOICES = [
  { id: "A", text: "下山，赶往青牛镇", risk: "mid", tag: "explore" },
  { id: "B", text: "在破庙再打坐半日，巩固境界", risk: "low", tag: "cultivate" },
  { id: "C", text: "翻检师父遗物，看看还有何可用", risk: "low", tag: "explore" },
] as const;

/* -----------------------------------------------------------------------
   道具图鉴：与后端 server.py 的 ITEM_TABLE 同源（数值改动须两边一起改，
   tests/frontend/constants.spec.ts 有专门用例盯着，漂移了会变红）。

   kind:
     pill     丹药 —— 可服用，effect 描述的是真实结算结果
     material 材料 —— 炼器/炼丹所用，当前版本不可服用
     gear     兵刃 —— 随身之物，不可服用
   ----------------------------------------------------------------------- */
export interface ItemInfo {
  kind: "pill" | "material" | "gear";
  effect: string;   // 一句话功效，进道具 chip 的 title 与详情弹窗
  desc: string;     // 风味说明
  hint?: string;    // 服用时机建议（仅丹药）
}

export const ITEM_INFO: Record<string, ItemInfo> = {
  "回气丹": {
    kind: "pill", effect: "回复 30% 气血",
    desc: "青牛镇药铺最常见的伤药，药性温厚，止血生肌。",
    hint: "伤重时服用最划算——回的是当前气血上限的比例，血少时吃等于浪费。",
  },
  "疗伤丹": {
    kind: "pill", effect: "回复 15% 气血",
    desc: "药力微涩，胜在价廉，走江湖的散修常揣一把在怀里。",
    hint: "回血量只有回气丹一半，适合小伤收尾。",
  },
  "凝气丹": {
    kind: "pill", effect: "修为 +25",
    desc: "将灵药精华凝作一丸，服之可省数日打坐之功。",
    hint: "直接长修为，不占回合的苦修。卡在圆满线附近时最有用。",
  },
  "清心丹": {
    kind: "pill", effect: "回复 50% 灵力",
    desc: "性凉，入喉如含薄冰，最能压制灵力枯竭时的躁气。",
    hint: "灵力见底、又要接连斗法或冲关时，比回气丹更对路。",
  },
  "辟谷丹": {
    kind: "pill", effect: "气血 +10、灵力 +10",
    desc: "粗陋的充饥之物，修士服之可百日不食五谷。",
    hint: "数值是固定的，越到后期越不值；前期聊胜于无。",
  },
  "碎星石": {
    kind: "material", effect: "炼器材料",
    desc: "陨铁中所出的奇异矿石，触手生寒，是打造法器的上佳之材。",
  },
  "引灵符": {
    kind: "material", effect: "符箓 · 暂不可直接使用",
    desc: "朱砂画就的空符，尚未注入灵力。待符道传承现世，方知用法。",
  },
  "铁背蜥甲": {
    kind: "material", effect: "炼器材料",
    desc: "自铁背蜥身上剥下的硬甲，坚逾寻常铁皮。",
  },
  "师父的钝剑": {
    kind: "gear", effect: "随身兵刃",
    desc: "师父留下的旧剑，刃口早已卷了。剑身刻着两个模糊的小字，看不真切。",
  },
};

/** 取道具说明；未收录的物品给出保守兜底（宁可说不知道，也不编造功效） */
export function itemInfo(name: string): ItemInfo {
  return ITEM_INFO[name] ?? {
    kind: "material",
    effect: "来历不明之物",
    desc: "这件东西你也叫不出名目，暂且收在行囊里。",
  };
}

/** 能否服用 —— 只有丹药可以 */
export function canUseItem(name: string): boolean {
  return ITEM_INFO[name]?.kind === "pill";
}
