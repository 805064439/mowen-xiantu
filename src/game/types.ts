/* 游戏数据契约：与后端 server.py 的 API 严格对应 */

export interface GameItem {
  name: string;
  qty: number;
  rarity: string;
}

export interface Reincarnation {
  realm: string;
  turn: number;
  memory: string[];
  ended?: boolean;
}

export interface GameState {
  realm_index: number;
  hp: number;
  hp_max: number;
  qi: number;
  qi_max: number;
  exp: number;
  spirit_stones: number;
  spirit_root?: string;
  items: GameItem[];
  memory: string[];
  memory_summary?: string;
  recent: { action: string; narrative: string }[];
  reincarnations?: Reincarnation[];
  npcs?: NpcEntry[];      // 江湖人物（道缘卡）
  style_echo?: string[];  // 最近开篇回声（防 AI 复读）
  pending_events?: PendingEvent[];  // 待结算天机事件（赠宝/传功/寻仇）
  fail_streak?: number;             // 连续突破失败次数（保底依据）
  cultivate_streak?: number;        // 连修轮数（连击加成；出门即断）
  last_near_death_turn?: number;    // 上次濒死轮次（冷却判定）
  turn: number;
  /* ---- 时间与寿元（v2）---- */
  days?: number;             // 累计天数（唯一权威，age 由它推导）
  age?: number;              // 当前年岁
  lifespan?: number;         // 寿元上限（突破大境界时重掷）
  life_bonus?: number;       // 静养续命累计（封顶 = 基础寿元的 12%）
  rest_count?: number;       // 累计静养轮数
  seclusion_streak?: number; // 枯坐轮数（仅 cultivate 累加，出门/静养即断）
  dead?: boolean;            // 已寿终
  /* ---- 机缘物件（v3 · 探索所得）---- */
  treasures?: Record<string, number>;  // {"residual_scroll": 3, "guard_talisman": 1, ...}
  eff_bonus?: number;                  // 闭关效率加成（由 treasures 派生）
  break_bonus?: number;                // 突破成功率加成（由 treasures 派生）
  elixir_buff?: number;                // 灵丹限时 buff 剩余轮数（服丹后 12 轮）
  scene_pace?: string;                 // 场景节奏 action|resolve|downtime（只影响给什么选项）
}

/** 寿元信息（engine_meta.age）——状态栏直接渲染 */
export interface AgeInfo {
  age: number;
  lifespan: number;
  ratio: number;      // age / lifespan
  days: number;
  stage: string;      // 炼气期 / 筑基期 …
  hint: string;       // 分级风险文案（安全线内为空）
  level: "safe" | "faded" | "warn" | "dread";
  life_bonus: number;
  dead: boolean;
}

/** 江湖人物卡：bond 为道缘，-100 死敌 ~ 100 生死之交 */
export interface NpcEntry {
  name: string;
  title: string;
  bond: number;
  met_turn?: number;
  fired?: Record<string, number>;  // 已触发过的事件 → 轮次（gift/teach/vendetta，同类一生一次）
  alias?: string[];                // 曾用名（AI 走样的写法），供后端认人，前端不展示
}

/** 天机事件：由道缘阈值触发，下一轮结算 */
export interface PendingEvent {
  type: "gift" | "teach" | "vendetta";
  npc: string;
  at: number;
}

export type Risk = "low" | "mid" | "high";

export interface Choice {
  id: string;
  text: string;
  risk: Risk;
  tag?: string;
  special?: string;
  hint?: string;   // 附带提示（如冲关成功率）
  short?: boolean; // v3.1 兼容：片刻行功（等价于 span="short"）
  span?: string; // 修行粒度 short|medium|long（v3.2）：决定这一下要过多久
}

export interface DeltaApplied {
  hp: number;
  qi: number;
  exp: number;
  spirit_stones: number;
  items_add: GameItem[];
  items_remove: GameItem[];
}

/** 本轮修炼系数明细（engine_meta.cultivate）——把"速度"摆给玩家看 */
export interface CultivateInfo {
  coeff: number;         // 综合系数
  action: string;        // 生效的行动 tag
  action_label: string;  // 行动中文名（潜心修行…）
  action_coeff: number;  // 行动系数
  streak: number;        // 结算时已攒的连修轮数
  streak_coeff: number;  // 连击系数
  seclusion: number;     // 闭门衰减系数（1.0 = 未衰减）
  vitality: number;      // 状态修正
  risk: number;          // 风险波动系数（高风险行动 ± 宽幅，均值 1.0）
  risk_label: string;    // 波动标注：机缘 / 事与愿违 / 空
  secluded: boolean;     // 是否处于闭门造车状态
  capped: boolean;       // 是否被单轮上限截断
  base?: number;         // 本轮基础修为 = 天数 × 日效率（+ 奇遇）
  days?: number;         // 本轮流逝天数
  day_exp?: number;      // 本轮「时间沉淀」修为（未含奇遇与系数）
  fortune?: boolean;     // 本轮是否触发奇遇
  ai_exp?: number;       // AI 提议的修为（仅叙事参考，权重 0 时不入账）
  eff?: number;          // 机缘效率乘数（1.0 = 无加成）
  eff_bonus?: number;    // 机缘效率加成（功法/秘籍/真诀 + 灵丹 buff）
  elixir_buff?: number;  // 灵丹 buff 剩余轮数（0 = 未服丹）
  span?: string;         // 本轮修行粒度（short/medium/long）
  short?: boolean;       // v3.1 兼容：本轮是否为「片刻行功」（只过了一两天，不是五年）
  tier?: string;         // 探索档位（low/mid/high，仅 explore）
  tier_label?: string;   // 探索档位中文名（寻常走动/远行历练/秘境探险）
}

/** 突破动画数据：跨大境界时附带寿元增量 */
export interface Breakthrough {
  success: boolean;
  from: string;
  to: string;
  lifespan_gain?: number;  // 寿元上限增加（跨大境界重掷）
  guard_talisman?: boolean; // 本次失败由护道符免除修为折损
}

export interface EngineMeta {
  source: string;
  model?: string;
  elapsed_ms?: number;
  retries?: number;
  tokens_in?: number;
  tokens_out?: number;
  memory_compressed?: boolean;
  cultivate?: CultivateInfo;   // 本轮修炼节奏明细
  disturbance?: boolean;       // 本轮是否触发了「闭门造车·外界打扰」事件
  age?: AgeInfo;               // 本轮年岁/寿元/风险分级
  life_extended?: number;      // 本轮静养续命增加的寿元
  lifespan_death?: boolean;    // 本轮寿终
  treasure?: { key: string; name: string; qty?: number };  // 本轮探索所得机缘（一律入背包）
  explore?: { tier: string; label: string };   // 本轮探索档位
  explore_death?: boolean;     // 本轮探索陨落
  elixir?: { buff: number; eff: number };      // 本轮服丹：buff 轮数与效率加成
  elixir_buff_left?: number;   // 回合末灵丹 buff 剩余轮数
}

export interface ActResponse {
  ok: boolean;
  state: GameState;
  narrative: string;
  choices: Choice[];
  delta_applied: DeltaApplied;
  npc_events?: NpcEvent[];   // 本轮道缘变化（用丹/结局轮为空）
  breakthrough: Breakthrough | null;
  near_death: boolean;
  ending: boolean;
  dead?: boolean;            // 本轮寿终（寿元耗尽 或 探索陨落）
  engine_meta: EngineMeta;
  error?: { code: string; message: string };
}

/** 本轮道缘变化事件（供飘字） */
export interface NpcEvent {
  name: string;
  delta: number;
}

export interface GameAction {
  type: "choice" | "breakthrough" | "custom" | "use_item" | "use_elixir" | "shop_buy" | "shop_sell";
  id?: string;
  text?: string;
  name?: string;
  qty?: number;  // 坊市买卖数量
  tag?: string;  // 选项标签（fight → 后端掷斗法判定）
  risk?: Risk;   // 风险档（explore 时即探索档位：low/mid/high）
  short?: boolean;  // v3.1 兼容：片刻行功标记（周天/小坐）：不传则后端一次吃五年
  span?: string;    // 修行粒度（short|medium|long）：不传则后端按整段闭关算
}

/** 叙事区的一个段落（一段剧情） */
export interface ScenePara {
  id: number;
  text: string;
}

/** 飘字条目 */
export interface FloatItem {
  id: number;
  text: string;
  cls: string;
}
