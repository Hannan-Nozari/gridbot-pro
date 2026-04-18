import type {
  AlertConfig,
  Analytics,
  BacktestRequest,
  BacktestResult,
  Bot,
  CreateBotRequest,
  EquityPoint,
  LoginResponse,
  PortfolioSummary,
  Trade,
  TradeQueryParams,
} from "@/types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ── Core fetch wrapper ─────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let message: string;
    try {
      const body = await res.json();
      message = body.detail ?? body.message ?? res.statusText;
    } catch {
      message = res.statusText;
    }
    throw new ApiError(res.status, message);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

// ── Auth ───────────────────────────────────────────────────

export function login(password: string) {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

// ── Bots ───────────────────────────────────────────────────

export function getBots() {
  return apiFetch<Bot[]>("/bots");
}

export function getBotDetail(id: string) {
  return apiFetch<Bot>(`/bots/${id}`);
}

export function createBot(data: CreateBotRequest) {
  return apiFetch<Bot>("/bots", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function startBot(id: string) {
  return apiFetch<Bot>(`/bots/${id}/start`, { method: "POST" });
}

export function stopBot(id: string) {
  return apiFetch<Bot>(`/bots/${id}/stop`, { method: "POST" });
}

export function deleteBot(id: string) {
  return apiFetch<void>(`/bots/${id}`, { method: "DELETE" });
}

export function killSwitch() {
  return apiFetch<{
    success: boolean;
    message: string;
    bots_stopped: { id: string; name: string }[];
    errors: { id: string; name: string; error: string }[];
  }>(`/bots/kill-switch`, { method: "POST" });
}

// ── Trades ─────────────────────────────────────────────────

export function getTrades(params?: TradeQueryParams) {
  const searchParams = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) searchParams.set(key, String(value));
    }
  }
  const qs = searchParams.toString();
  return apiFetch<Trade[]>(`/trades${qs ? `?${qs}` : ""}`);
}

// ── Backtesting ────────────────────────────────────────────

export function runBacktest(data: BacktestRequest) {
  return apiFetch<BacktestResult>("/backtest", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getBacktestResults() {
  return apiFetch<BacktestResult[]>("/backtest");
}

// ── Config ────────────────────────────────────────────────

export function saveConfig(strategyType: string, config: Record<string, unknown>) {
  return apiFetch<void>(`/config/${strategyType}`, {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

// ── Portfolio & Analytics ──────────────────────────────────

export function getPortfolioSummary() {
  return apiFetch<PortfolioSummary>("/portfolio/summary");
}

export function getEquityCurve(period: string = "7d") {
  return apiFetch<EquityPoint[]>(`/portfolio/equity?period=${period}`);
}

export function getAnalytics() {
  return apiFetch<Analytics>("/analytics");
}

// ── Alerts ─────────────────────────────────────────────────

export function getAlertConfig() {
  return apiFetch<AlertConfig>("/alerts/config");
}

export function updateAlertConfig(config: Partial<AlertConfig>) {
  return apiFetch<AlertConfig>("/alerts/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export function testEmail() {
  return apiFetch<{ success: boolean }>("/alerts/test/email", {
    method: "POST",
  });
}

export function testTelegram() {
  return apiFetch<{ success: boolean }>("/alerts/test/telegram", {
    method: "POST",
  });
}

// ── AI Auto-Pilot ──────────────────────────────────────────

export interface AIStrategyResult {
  pair: string;
  strategy: string;
  pnl: number;
  pnl_pct: number;
  monthly_roi: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  num_trades: number;
  score: number;
  config: Record<string, unknown>;
}

export interface AIAnalyzeResponse {
  investment: number;
  days: number;
  results_30d: AIStrategyResult[];
  results_90d: AIStrategyResult[];
  recommendation: AIStrategyResult;
  alternative?: AIStrategyResult;
  confidence: "high" | "medium" | "low";
  risk_level: "low" | "medium" | "high";
  expected_monthly_return_usd: number;
  expected_monthly_return_pct: number;
}

export function aiAnalyze(investment: number) {
  return apiFetch<AIAnalyzeResponse>("/ai/analyze", {
    method: "POST",
    body: JSON.stringify({ investment, days: 90 }),
  });
}

export function aiDeploy(body: {
  investment: number;
  pair: string;
  strategy: string;
  config: Record<string, unknown>;
  paper: boolean;
  name?: string;
}) {
  return apiFetch<{
    bot_id: string;
    name: string;
    status: string;
    message: string;
  }>("/ai/deploy", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Market Data ────────────────────────────────────────────

export interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function getCandles(symbol: string, timeframe = "1h", limit = 100) {
  const enc = encodeURIComponent(symbol);
  return apiFetch<{ symbol: string; timeframe: string; candles: Candle[] }>(
    `/market/candles/${enc}?timeframe=${timeframe}&limit=${limit}`
  );
}

export function getTicker(symbol: string) {
  const enc = encodeURIComponent(symbol);
  return apiFetch<{
    symbol: string;
    price: number;
    change_24h_pct: number;
    high_24h: number;
    low_24h: number;
    volume_24h: number;
    timestamp: number;
  }>(`/market/ticker/${enc}`);
}

// ── Market Regime ──────────────────────────────────────────

export type Regime = "good" | "caution" | "bad" | "unknown";

export interface RegimeSignals {
  btc_1h_pct: number;
  btc_24h_pct: number;
  volatility_pct: number;
  trend_strength_pct: number;
  drawdown_pct: number;
  btc_price: number;
}

export interface RegimeStatus {
  regime: Regime;
  action: "run" | "hold" | "pause";
  signals: RegimeSignals;
  reasons: string[];
  bad_count: number;
  caution_count: number;
  timestamp: string;
  summary: string;
  enabled: boolean;
  thresholds?: Record<string, number | boolean>;
  bots_paused_by_regime?: number;
}

export function getRegime() {
  return apiFetch<RegimeStatus>("/regime/status");
}

export function forceRegimeAnalysis() {
  return apiFetch<RegimeStatus>("/regime/analyze-now", { method: "POST" });
}

export function getRegimeHistory(limit = 50) {
  return apiFetch<{
    history: {
      id: number;
      timestamp: string;
      regime: string;
      action: string;
      signals: RegimeSignals;
      reasons: string[];
      summary: string;
    }[];
  }>(`/regime/history?limit=${limit}`);
}

export function updateRegimeThresholds(body: Record<string, number | boolean>) {
  return apiFetch<{ thresholds: Record<string, number | boolean> }>(
    "/regime/thresholds",
    { method: "PUT", body: JSON.stringify(body) }
  );
}
