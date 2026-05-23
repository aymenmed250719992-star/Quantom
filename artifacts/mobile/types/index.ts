export interface Trade {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  entry_price: number;
  exit_price: number | null;
  stop_loss_price?: number | null;
  take_profit_price?: number | null;
  quantity: number;
  pnl: number | null;
  pnl_percent?: number | null;
  status: "open" | "closed" | "cancelled";
  ai_confidence: number;
  ai_reasoning: string;
  market_condition?: string;
  pattern?: string;
  created_at: string;
  closed_at: string | null;
  // ML features
  ml_win_prob?: number | null;
  rsi_at_entry?: number | null;
  macd_hist_at_entry?: number | null;
  bb_pct_at_entry?: number | null;
}

export interface MLStatus {
  is_trained: boolean;
  n_samples: number;
  min_samples_needed: number;
  samples_until_first_train: number;
  feature_importances: [string, number][];
  algorithm: string;
}

export interface GeminiKeyInfo {
  label: string;
  provider: string;
  available: boolean;
  exhausted: boolean;
  hours_remaining: number;
  total_calls: number;
  success_calls: number;
  failed_calls: number;
}

export interface GeminiPoolStatus {
  total_keys: number;
  available_keys: number;
  active_key: string;
  active_provider: string | null;
  all_exhausted: boolean;
  keys: GeminiKeyInfo[];
  providers: Record<string, GeminiKeyInfo[]>;
}

export interface BotStatus {
  id: number;
  is_running: boolean;
  mode: "demo" | "live";
  last_scan_at: string | null;
  total_trades: number;
  win_rate: number;
  target_win_rate?: number;
  current_threshold?: number;
}

export interface BalanceInfo {
  total: number;
  free: number;
  used: number;
  currency: string;
  mode: string;
  error?: string;
}

export interface Portfolio {
  total_pnl: number;
  roi_percent: number;
  total_closed: number;
  total_open: number;
  wins: number;
  losses: number;
  win_rate: number;
  target_win_rate: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  recent_trades: Trade[];
}

export interface WsMessage {
  type: "log" | "signal" | "trade" | "error" | "lesson" | "adaptive" | "pong" | "agent";
  message?: string;
  symbol?: string;
  action?: string;
  confidence?: number;
  trade?: Trade;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  provider?: string;   // "gemini" | "openai" | "claude" | "rule-based"
  key?: string;        // e.g. "GEMINI K1"
}

export interface Settings {
  maxRiskPercent: number;
  minConfidenceScore: number;
  targetWinRate: number;
}

export interface AgentPattern {
  pattern: string;
  win_rate: number;
  total: number;
}

export interface AgentStatus {
  scan_count: number;
  goal: string;
  current_strategy: string;
  strategy_confidence: number;
  patterns_tracked: number;
  best_patterns: AgentPattern[];
  recent_thoughts: string[];
  strategy_overrides: Record<string, string>;
  trades_since_review: number;
}

export interface AgentMemory {
  strategy: string;
  strategy_confidence: number;
  goal: string;
  patterns: Record<string, { wins: number; losses: number }>;
  best_patterns: AgentPattern[];
  strategy_overrides: Record<string, string>;
  lessons: Array<{
    id: string;
    lesson: string;
    symbol: string;
    outcome: string;
    created_at: string;
    pattern?: string;
  }>;
  recent_thoughts: string[];
}
