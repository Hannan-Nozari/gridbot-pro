// ── Bot Types ──────────────────────────────────────────────

export type BotStatus = "idle" | "running" | "stopped" | "error";
export type BotType = "grid" | "hybrid" | "smart" | "v3";
export type TradeSide = "buy" | "sell";

export interface GridConfig {
  symbol: string;
  upper_price: number;
  lower_price: number;
  num_grids: number;
  total_investment: number;
  stop_loss?: number;
  take_profit?: number;
}

export interface HybridConfig {
  symbol: string;
  upper_price: number;
  lower_price: number;
  num_grids: number;
  total_investment: number;
  rsi_period?: number;
  rsi_overbought?: number;
  rsi_oversold?: number;
  stop_loss?: number;
  take_profit?: number;
}

export interface SmartConfig {
  symbol: string;
  total_investment: number;
  volatility_window?: number;
  rebalance_threshold?: number;
  stop_loss?: number;
  take_profit?: number;
}

export interface V3Config {
  symbol: string;
  total_investment: number;
  fee_tier: number;
  price_range_pct: number;
  rebalance_trigger_pct?: number;
  stop_loss?: number;
  take_profit?: number;
}

export type BotConfig = GridConfig | HybridConfig | SmartConfig | V3Config;

export interface Bot {
  id: string;
  name: string;
  type: BotType;
  status: BotStatus;
  paper: boolean;
  config: BotConfig;
  created_at: string;
  updated_at?: string;
  pnl: number;
  pnl_pct: number;
  total_value: number;
  num_trades: number;
  uptime?: number;
  error_message?: string;
}

// ── Trade Types ────────────────────────────────────────────

export interface Trade {
  id: string;
  bot_id: string;
  symbol: string;
  side: TradeSide;
  price: number;
  amount: number;
  fee: number;
  profit: number | null;
  timestamp: string;
}

export interface TradeQueryParams {
  bot_id?: string;
  symbol?: string;
  side?: TradeSide;
  limit?: number;
  offset?: number;
}

// ── Backtest Types ─────────────────────────────────────────

export interface EquityPoint {
  timestamp: string;
  value: number;
}

export interface BacktestTrade {
  timestamp: string;
  side: TradeSide;
  price: number;
  amount: number;
  profit: number | null;
}

export interface BacktestResult {
  id: string;
  strategy: BotType;
  symbol: string;
  start_date: string;
  end_date: string;
  pnl: number;
  pnl_pct: number;
  monthly_roi: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  num_trades: number;
  equity_curve: EquityPoint[];
  trades: BacktestTrade[];
  created_at: string;
}

export interface BacktestRequest {
  strategy: BotType;
  symbol: string;
  start_date: string;
  end_date: string;
  config: BotConfig;
  initial_capital: number;
}

// ── Portfolio / Analytics Types ────────────────────────────

export interface PortfolioSummary {
  total_value: number;
  total_pnl: number;
  pnl_pct: number;
  num_bots: number;
  num_trades: number;
  active_bots: number;
}

export interface Analytics {
  daily_pnl: EquityPoint[];
  win_rate: number;
  avg_trade_profit: number;
  best_bot: string | null;
  worst_bot: string | null;
  total_fees: number;
  volume_24h: number;
}

// ── Alert Types ────────────────────────────────────────────

export interface AlertTrigger {
  type: "pnl_threshold" | "drawdown" | "bot_stopped" | "trade_executed";
  enabled: boolean;
  value?: number;
}

export interface AlertConfig {
  email_enabled: boolean;
  email_address?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_pass?: string;
  recipient_email?: string;
  telegram_enabled: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  on_trade_executed?: boolean;
  drawdown_threshold?: number;
  profit_target?: number;
  triggers?: AlertTrigger[];
}

// ── WebSocket Message Types ────────────────────────────────

export type WSMessageType =
  | "price_update"
  | "trade_executed"
  | "bot_status_change"
  | "portfolio_update";

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  data: T;
  timestamp: string;
}

export interface PriceUpdate {
  symbol: string;
  price: number;
  change_24h: number;
}

export interface TradeExecuted {
  trade: Trade;
  bot_id: string;
}

export interface BotStatusChange {
  bot_id: string;
  old_status: BotStatus;
  new_status: BotStatus;
}

export interface PortfolioUpdate {
  total_value: number;
  total_pnl: number;
  pnl_pct: number;
}

// ── Auth Types ─────────────────────────────────────────────

export interface LoginResponse {
  token: string;
}

// ── Create Bot ─────────────────────────────────────────────

export interface CreateBotRequest {
  name: string;
  type: BotType;
  paper: boolean;
  config: BotConfig;
}
