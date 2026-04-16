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
