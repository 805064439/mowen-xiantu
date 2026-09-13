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

/* -----------------------------------------------------------------------
   修炼节奏：与后端 server.py 的 ACTION_CULTIVATE_COEFF / CULTIVATE_STREAK_TABLE
   同源（数值改动须两边一起改，tests/frontend/cultivation.spec.ts 逐条盯着）。

   玩家选什么，修行就有多快——这里只负责把它翻译成人话给玩家看。
   ----------------------------------------------------------------------- */
export interface ActionInfo {
  label: string;   // 行动类型中文名
  coeff: number;   // 修炼系数
  note: string;    // 一句话取舍说明
}

export const ACTION_INFO: Record<string, ActionInfo> = {
  cultivate: { label: "潜心修行", coeff: 1.8, note: "修行最快，代价是错过外界机缘" },
  rest: { label: "静养调息", coeff: 1.3, note: "修行较快，兼顾回复气血灵力" },
  fight: { label: "斗法拼杀", coeff: 1.2, note: "修行不慢，另有战利品；但凭凶险换高期望——一轮可能大进或空手" },
  explore: { label: "外出探索", coeff: 1.0, note: "基准速度，机缘随机——常有意外之喜或落空" },
  trade: { label: "坊市交易", coeff: 0.8, note: "修行最慢，换来的是灵石" },
  other: { label: "随缘而行", coeff: 1.0, note: "不偏不倚的基准速度，既无加成也无损失" },
};

/** 高风险行动修为的随机波动幅度（±），与后端 RISK_VOLATILITY 同源。
 * 低风险行动（cultivate/rest/trade/other）不波动，保证基准线稳定。 */
export const RISK_VOLATILITY: Record<string, number> = {
  fight: 0.40,
  explore: 0.18,
};

/** 取某行动的波动幅度；未知/低风险行动返回 0（不波动） */
export function riskVolatility(tag?: string): number {
  return RISK_VOLATILITY[tag ?? ""] ?? 0;
}

/** 波动系数对应的中文标注：>1 机缘、<1 事与愿违、=1 空 */
export function riskLabel(coeff: number): string {
  if (coeff > 1.001) return "机缘";
  if (coeff < 0.999) return "事与愿违";
  return "";
}

/** 取行动说明；未知 tag 一律按「随缘而行」，不编造加成 */
export function actionInfo(tag?: string): ActionInfo {
  return ACTION_INFO[tag ?? ""] ?? ACTION_INFO.other;
}

/** 连修加成表：轮数 → 系数（与后端 CULTIVATE_STREAK_TABLE 一致） */
export const STREAK_TABLE: [number, number][] = [[0, 1.0], [2, 1.1], [3, 1.2], [5, 1.4]];
export const STREAK_CAP = 5;          // 加成封顶轮数
export const SECLUSION_STREAK = 6;    // 越此轮数起「闭门造车」，效率衰减
export const SECLUSION_DECAY = 0.8;   // v2：0.6 → 0.8（惩罚不过火）
export const SECLUSION_FLOOR = 0.6;   // v2：0.3 → 0.6（不至于彻底卡死）

/** 当前连修轮数对应的加成系数（只用于展示，真值以后端为准） */
export function streakCoeff(streak: number): number {
  let c = 1.0;
  for (const [threshold, v] of STREAK_TABLE) {
    if (streak >= threshold) c = v;
  }
  return c;
}

/** 闭门衰减系数：与后端 _seclusion_coeff 同式 */
export function seclusionCoeff(streak: number): number {
  if (streak < SECLUSION_STREAK) return 1.0;
  return Math.max(SECLUSION_FLOOR, SECLUSION_DECAY ** (streak - SECLUSION_STREAK + 1));
}

/** 把系数写成飘字用的短标签：「潜心修行 ×2.39」 */
export function coeffLabel(coeff: number): string {
  return `×${coeff.toFixed(2)}`;
}

/* -----------------------------------------------------------------------
   时间与寿元：与后端 server.py 的 DAYS_PER_YEAR / ACTION_DAYS / DAY_EFF /
   LIFESPAN_TABLE 同源（改动须两边一起改，tests/frontend/lifespan.spec.ts 盯着）。

   修为 = 天数 × 日效率 —— 时间与修为同源，所以「花三年闭关」和「逛三天坊市」
   不再等价，寿元才成为真实资源。
   ----------------------------------------------------------------------- */
export const DAYS_PER_YEAR = 360;
export const START_AGE = 16;

/** 每轮行动消耗的天数区间（闭关动辄经年，斗法不过顷刻） */
export const ACTION_DAYS: Record<string, [number, number]> = {
  cultivate: [270, 810],
  rest: [15, 45],
  explore: [3, 15],
  trade: [3, 10],
  fight: [1, 3],
  other: [5, 20],
};

/** 日效率：修为 = 天数 × 日效率 × 各项系数 */
export const DAY_EFF: Record<string, number> = {
  cultivate: 0.110,
  rest: 0.030,
  explore: 0.004,
  trade: 0.002,
  fight: 0.002,
  other: 0.005,
};

/** 寿元区间（按大境界） */
export const LIFESPAN_TABLE: [string, number, number][] = [
  ["炼气期", 140, 190],
  ["筑基期", 390, 510],
  ["金丹期", 1160, 1500],
  ["元婴期", 3400, 4400],
];
export const LIFESPAN_SAFE_RATIO = 0.72;  // 占寿元 72% 以下绝无寿终之虞
export const REST_LIFE_BONUS_EVERY = 3;   // 每 3 轮静养
export const REST_LIFE_BONUS = 3.5;       // 寿元上限 +3.5 岁（封顶 60）
export const REST_LIFE_BONUS_CAP = 60;

/** 大境界序号：每 9 层一境 */
export function stageOf(realmIndex: number): number {
  return Math.max(0, Math.min(LIFESPAN_TABLE.length - 1, Math.floor(realmIndex / 9)));
}

/** 按大境界取寿元均值（无存档时的兜底展示值） */
export function lifespanAvg(realmIndex: number): number {
  const [, lo, hi] = LIFESPAN_TABLE[stageOf(realmIndex)];
  return Math.round((lo + hi) / 2);
}

/** 占寿元比例 → 风险分级（不暴露精确概率，只给体感） */
export function ageLevel(ratio: number): "safe" | "faded" | "warn" | "dread" {
  if (ratio < LIFESPAN_SAFE_RATIO) return "safe";
  if (ratio <= 0.85) return "faded";
  if (ratio <= 1.0) return "warn";
  return "dread";
}

export const AGE_HINT: Record<string, string> = {
  safe: "",
  faded: "鬓角微霜，修为渐觉凝滞",
  warn: "气血衰败，寿元将尽——当谋续命之策",
  dread: "大限已至，每一息皆是偷生",
};

/** 天数 → 人话（叙事用，飘字「岁月流逝」） */
export function daysText(days: number): string {
  if (days >= DAYS_PER_YEAR) {
    const y = days / DAYS_PER_YEAR;
    return y >= 2 ? `过了约 ${y.toFixed(1)} 年` : "过了一年有余";
  }
  if (days >= 30) return `过了约 ${Math.round(days / 30)} 个月`;
  return `过了 ${days} 天`;
}
