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
}

/** 江湖人物卡：bond 为道缘，-100 死敌 ~ 100 生死之交 */
export interface NpcEntry {
  name: string;
  title: string;
  bond: number;
  met_turn?: number;
  fired?: Record<string, number>;  // 已触发过的事件 → 轮次（gift/teach/vendetta，同类一生一次）
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
  secluded: boolean;     // 是否处于闭门造车状态
  capped: boolean;       // 是否被单轮上限截断
  base?: number;         // AI 给出的原始修为（未乘系数）
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
}

export interface ActResponse {
  ok: boolean;
  state: GameState;
  narrative: string;
  choices: Choice[];
  delta_applied: DeltaApplied;
  npc_events?: NpcEvent[];   // 本轮道缘变化（用丹/结局轮为空）
  breakthrough: { success: boolean; from: string; to: string } | null;
  near_death: boolean;
  ending: boolean;
  engine_meta: EngineMeta;
  error?: { code: string; message: string };
}

/** 本轮道缘变化事件（供飘字） */
export interface NpcEvent {
  name: string;
  delta: number;
}

export interface GameAction {
  type: "choice" | "breakthrough" | "custom" | "use_item" | "shop_buy" | "shop_sell";
  id?: string;
  text?: string;
  name?: string;
  qty?: number;  // 坊市买卖数量
  tag?: string;  // 选项标签（fight → 后端掷斗法判定）
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
