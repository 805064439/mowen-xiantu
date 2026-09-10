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
  turn: number;
}

export type Risk = "low" | "mid" | "high";

export interface Choice {
  id: string;
  text: string;
  risk: Risk;
  tag?: string;
  special?: string;
}

export interface DeltaApplied {
  hp: number;
  qi: number;
  exp: number;
  spirit_stones: number;
  items_add: GameItem[];
  items_remove: GameItem[];
}

export interface EngineMeta {
  source: string;
  model?: string;
  elapsed_ms?: number;
  retries?: number;
  tokens_in?: number;
  tokens_out?: number;
  memory_compressed?: boolean;
}

export interface ActResponse {
  ok: boolean;
  state: GameState;
  narrative: string;
  choices: Choice[];
  delta_applied: DeltaApplied;
  breakthrough: { success: boolean; from: string; to: string } | null;
  near_death: boolean;
  ending: boolean;
  engine_meta: EngineMeta;
  error?: { code: string; message: string };
}

export interface GameAction {
  type: "choice" | "breakthrough" | "custom" | "use_item";
  id?: string;
  text?: string;
  name?: string;
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
