"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  Sparkles,
  TrendingUp,
  Shield,
  Rocket,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  ChevronLeft,
  DollarSign,
  Target,
  Brain,
  Zap,
  Activity,
  ArrowDownUp,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { PriceChart } from "@/components/price-chart";
import {
  aiAnalyze,
  aiDeploy,
  type AIAnalyzeResponse,
  type AIStrategyResult,
} from "@/lib/api";
import type { Bot } from "@/types";
import { getBots, getTrades } from "@/lib/api";
import type { Trade } from "@/types";

// ─── Helpers ───────────────────────────────────────────────

function usd(n: number, decimals = 2) {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

const PRESETS = [100, 500, 1000, 2500, 5000, 10000];

// ─── Step 1: Deposit amount ────────────────────────────────

function StepDeposit({
  amount,
  onChange,
  onNext,
}: {
  amount: number;
  onChange: (n: number) => void;
  onNext: () => void;
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl brand-gradient brand-glow">
          <DollarSign className="h-8 w-8 text-white" strokeWidth={2.5} />
        </div>
        <h2 className="text-3xl font-bold tracking-tight text-foreground">
          How much do you want to invest?
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          AI will analyse markets, pick the best strategy, and trade it for you.
        </p>
      </div>

      <Card className="border-border/60 bg-card elevated">
        <CardContent className="space-y-6 p-8">
          <div>
            <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Investment Amount (USDT)
            </Label>
            <div className="relative mt-2">
              <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-2xl font-bold text-muted-foreground">
                $
              </span>
              <input
                type="number"
                min={50}
                max={1000000}
                value={amount || ""}
                onChange={(e) => onChange(Number(e.target.value))}
                className="h-16 w-full rounded-xl border border-border bg-muted/30 pl-10 pr-4 text-3xl font-bold text-foreground focus:border-brand/50 focus:outline-none focus:ring-2 focus:ring-brand/20"
                placeholder="1000"
              />
            </div>
          </div>

          <div>
            <p className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Quick presets
            </p>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => onChange(p)}
                  className={`rounded-xl border py-3 text-sm font-semibold transition-all ${
                    amount === p
                      ? "border-brand bg-brand-muted text-brand"
                      : "border-border bg-muted/30 text-muted-foreground hover:border-border/80 hover:text-foreground"
                  }`}
                >
                  ${p >= 1000 ? `${p / 1000}K` : p}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">
              <strong className="text-foreground">Paper trading</strong> is on by default
              — no real money is moved until you explicitly switch to live mode.
            </p>
          </div>

          <Button
            type="button"
            onClick={onNext}
            disabled={!amount || amount < 50}
            className="h-14 w-full brand-gradient text-base font-semibold text-white hover:opacity-90"
          >
            <Brain className="mr-2 h-5 w-5" />
            Analyse Markets with AI
            <ChevronRight className="ml-2 h-5 w-5" />
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Step 2: Analyzing (loading) ───────────────────────────

function StepAnalyzing({
  progress,
  stage,
}: {
  progress: number;
  stage: string;
}) {
  const stages = [
    "Fetching market data...",
    "Running 30-day backtests...",
    "Running 90-day backtests...",
    "Computing risk metrics...",
    "Ranking strategies...",
    "Preparing recommendation...",
  ];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Card className="border-border/60 bg-card elevated">
        <CardContent className="space-y-8 p-12 text-center">
          <div className="relative mx-auto h-24 w-24">
            <div className="absolute inset-0 animate-ping rounded-full bg-brand/30" />
            <div className="relative flex h-full w-full items-center justify-center rounded-full brand-gradient brand-glow">
              <Brain className="h-10 w-10 text-white" strokeWidth={2.5} />
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-bold text-foreground">
              AI is analysing the markets...
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Testing multiple strategies across popular pairs
            </p>
          </div>

          {/* Progress bar */}
          <div className="space-y-2">
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full brand-gradient transition-all duration-500 ease-out"
                style={{ width: `${Math.min(100, progress)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">{stage}</p>
          </div>

          {/* Stage list */}
          <div className="space-y-2 text-left">
            {stages.map((s, i) => {
              const thresh = ((i + 1) / stages.length) * 100;
              const done = progress >= thresh;
              const active = !done && progress >= (i / stages.length) * 100;
              return (
                <div
                  key={s}
                  className={`flex items-center gap-3 text-xs transition-opacity ${
                    done ? "text-profit" : active ? "text-brand" : "opacity-40 text-muted-foreground"
                  }`}
                >
                  {done ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : active ? (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <span className="h-4 w-4 rounded-full border border-current" />
                  )}
                  <span>{s}</span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Step 3: Results (backtest charts + recommendation) ────

function ResultsChart({
  title,
  results,
  limit = 6,
}: {
  title: string;
  results: AIStrategyResult[];
  limit?: number;
}) {
  const data = results.slice(0, limit).map((r) => ({
    label: `${r.pair.split("/")[0]} · ${r.strategy}`,
    pnl: Number(r.pnl_pct.toFixed(2)),
    score: r.score,
  }));

  return (
    <Card className="border-border/60 bg-card elevated">
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-foreground">{title}</h3>
          <Badge variant="outline" className="border-border text-[10px] text-muted-foreground">
            {results.length} strategies tested
          </Badge>
        </div>
        <div className="mt-4 h-[200px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 0, right: 20 }}>
              <XAxis
                type="number"
                tick={{ fontSize: 10, fill: "#737373" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}%`}
              />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 10, fill: "#a3a3a3" }}
                tickLine={false}
                axisLine={false}
                width={110}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a1a1a",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  fontSize: 11,
                }}
                formatter={(v: unknown) => [`${v}%`, "Return"]}
              />
              <Bar dataKey="pnl" radius={[0, 6, 6, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? "#ff4d15" : "rgba(255,255,255,0.2)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationCard({
  rec,
  confidence,
  riskLevel,
  monthlyUsd,
  monthlyPct,
  investment,
}: {
  rec: AIStrategyResult;
  confidence: string;
  riskLevel: string;
  monthlyUsd: number;
  monthlyPct: number;
  investment: number;
}) {
  const confColor = {
    high: "text-profit bg-profit/10",
    medium: "text-brand bg-brand/10",
    low: "text-loss bg-loss/10",
  }[confidence] ?? "text-muted-foreground bg-muted";

  const riskColor = {
    low: "text-profit bg-profit/10",
    medium: "text-brand bg-brand/10",
    high: "text-loss bg-loss/10",
  }[riskLevel] ?? "text-muted-foreground bg-muted";

  return (
    <Card className="relative overflow-hidden border-brand/30 bg-card elevated brand-glow">
      <div className="absolute inset-0 opacity-20" style={{
        background: "radial-gradient(ellipse at top right, rgba(255,77,21,0.25), transparent 60%)",
      }} />

      <CardContent className="relative p-8">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl brand-gradient">
              <Sparkles className="h-6 w-6 text-white" strokeWidth={2.5} />
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-brand">
                AI Recommendation
              </p>
              <h3 className="text-2xl font-bold text-foreground">
                {rec.strategy.charAt(0).toUpperCase() + rec.strategy.slice(1)} · {rec.pair}
              </h3>
            </div>
          </div>

          <div className="flex flex-col items-end gap-1">
            <Badge className={`${confColor} border-0 text-[10px] font-bold uppercase tracking-wider`}>
              {confidence} confidence
            </Badge>
            <Badge className={`${riskColor} border-0 text-[10px] font-bold uppercase tracking-wider`}>
              {riskLevel} risk
            </Badge>
          </div>
        </div>

        {/* Key stats */}
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-xl bg-muted/30 p-4">
            <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              <TrendingUp className="h-3 w-3" /> 90d Return
            </p>
            <p className={`mt-1 text-xl font-bold ${rec.pnl_pct >= 0 ? "text-profit" : "text-loss"}`}>
              {rec.pnl_pct >= 0 ? "+" : ""}
              {rec.pnl_pct.toFixed(1)}%
            </p>
          </div>

          <div className="rounded-xl bg-muted/30 p-4">
            <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              <Target className="h-3 w-3" /> Monthly Est.
            </p>
            <p className="mt-1 text-xl font-bold text-foreground">
              {monthlyPct >= 0 ? "+" : ""}
              {monthlyPct.toFixed(1)}%
            </p>
          </div>

          <div className="rounded-xl bg-muted/30 p-4">
            <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              <Shield className="h-3 w-3" /> Max Drawdown
            </p>
            <p className="mt-1 text-xl font-bold text-foreground">
              {Math.abs(rec.max_drawdown).toFixed(1)}%
            </p>
          </div>

          <div className="rounded-xl bg-muted/30 p-4">
            <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              <ArrowDownUp className="h-3 w-3" /> Trades
            </p>
            <p className="mt-1 text-xl font-bold text-foreground">
              {rec.num_trades}
            </p>
          </div>
        </div>

        {/* Projection */}
        <div className="mt-6 rounded-2xl border border-profit/20 bg-profit/5 p-5">
          <p className="text-xs font-medium uppercase tracking-widest text-profit">
            Projected earnings
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <p className="text-3xl font-bold text-foreground">
              +${usd(monthlyUsd)}
            </p>
            <p className="text-sm text-muted-foreground">per month (estimate)</p>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            On ${usd(investment)} investment, based on {rec.num_trades} trades in 90-day backtest
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function StepResults({
  result,
  paper,
  onPaperChange,
  onDeploy,
  onBack,
  loading,
}: {
  result: AIAnalyzeResponse;
  paper: boolean;
  onPaperChange: (v: boolean) => void;
  onDeploy: () => void;
  onBack: () => void;
  loading: boolean;
}) {
  const rec = result.recommendation;

  return (
    <div className="space-y-6">
      <RecommendationCard
        rec={rec}
        confidence={result.confidence}
        riskLevel={result.risk_level}
        monthlyUsd={result.expected_monthly_return_usd}
        monthlyPct={result.expected_monthly_return_pct}
        investment={result.investment}
      />

      {/* Price chart for recommended pair */}
      <Card className="border-border/60 bg-card elevated">
        <CardContent className="p-6">
          <PriceChart symbol={rec.pair} timeframe="1h" height={280} />
        </CardContent>
      </Card>

      {/* Backtest comparison charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ResultsChart title="30-day Backtest · Top 6" results={result.results_30d} />
        <ResultsChart title="90-day Backtest · Top 6" results={result.results_90d} />
      </div>

      {/* Deploy section */}
      <Card className="border-border/60 bg-card elevated">
        <CardContent className="space-y-4 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Switch
                id="paper-mode"
                checked={paper}
                onCheckedChange={(v) => onPaperChange(Boolean(v))}
              />
              <Label htmlFor="paper-mode" className="cursor-pointer">
                <p className="text-sm font-semibold text-foreground">
                  {paper ? "🧪 Paper Trading" : "💸 LIVE Trading"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {paper
                    ? "Simulated with fake money — recommended to start here"
                    : "Will trade with your real Binance balance — use caution!"}
                </p>
              </Label>
            </div>
          </div>

          {!paper && (
            <div className="flex items-start gap-2 rounded-xl border border-loss/30 bg-loss/5 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-loss" />
              <p className="text-xs text-loss">
                <strong>LIVE mode:</strong> Real money will be traded on your Binance account.
                Make sure your API keys are set and you&apos;ve tested in paper mode first.
              </p>
            </div>
          )}

          <div className="flex gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={onBack}
              className="flex-1"
              disabled={loading}
            >
              <ChevronLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
            <Button
              type="button"
              onClick={onDeploy}
              disabled={loading}
              className="flex-[2] brand-gradient font-semibold text-white hover:opacity-90"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Deploying...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Rocket className="h-4 w-4" />
                  Deploy AI Bot
                </span>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Step 4: Running (live monitoring) ─────────────────────

function StepRunning({
  botId,
  symbol,
  investment,
  gridLevels,
}: {
  botId: string;
  symbol: string;
  investment: number;
  gridLevels?: { price: number; type: "buy" | "sell" }[];
}) {
  const { data: bots } = useSWR<Bot[]>("bots-autopilot", getBots, {
    refreshInterval: 5_000,
  });
  const { data: trades } = useSWR<Trade[]>(
    ["trades-autopilot", botId],
    () => getTrades({ bot_id: botId, limit: 50 }),
    { refreshInterval: 5_000 }
  );

  const bot = bots?.find((b) => b.id === botId);
  const pnl = bot?.pnl ?? 0;
  const totalValue = bot?.total_value ?? investment;
  const pnlPct = investment > 0 ? (pnl / investment) * 100 : 0;

  const tradeMarkers = useMemo(
    () =>
      trades?.map((t) => ({
        timestamp: t.timestamp,
        side: t.side,
        price: t.price,
      })) ?? [],
    [trades]
  );

  return (
    <div className="space-y-6">
      {/* Success banner */}
      <Card className="border-profit/30 bg-card elevated">
        <CardContent className="flex items-center gap-4 p-6">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-profit/10">
            <CheckCircle2 className="h-7 w-7 text-profit" strokeWidth={2.5} />
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-foreground">
              🎉 Your AI bot is live!
            </h2>
            <p className="text-sm text-muted-foreground">
              {bot?.name ?? "Auto-Pilot bot"} is now monitoring {symbol} and will execute trades automatically.
            </p>
          </div>
          <Badge className="bg-profit/10 text-profit border-0">
            <span className="relative mr-1.5 flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-profit opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-profit" />
            </span>
            RUNNING
          </Badge>
        </CardContent>
      </Card>

      {/* P&L stat row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <StatCard
          label="Invested"
          value={`$${usd(investment)}`}
          icon={DollarSign}
        />
        <StatCard
          label="Current Value"
          value={`$${usd(totalValue)}`}
          icon={Activity}
        />
        <StatCard
          label="P&L"
          value={`${pnl >= 0 ? "+" : ""}$${usd(Math.abs(pnl))}`}
          change={`${pnl >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`}
          positive={pnl >= 0}
          icon={TrendingUp}
        />
        <StatCard
          label="Trades"
          value={String(trades?.length ?? 0)}
          icon={ArrowDownUp}
        />
      </div>

      {/* Live chart with trade markers */}
      <Card className="border-border/60 bg-card elevated">
        <CardContent className="p-6">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
                Live Chart · Auto-updates every 15s
              </p>
              <h3 className="mt-1 text-lg font-bold text-foreground">
                Buy/sell markers show your bot&apos;s trades
              </h3>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-profit" />
                <span className="text-muted-foreground">Buy</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-brand" />
                <span className="text-muted-foreground">Sell</span>
              </span>
            </div>
          </div>
          <PriceChart
            symbol={symbol}
            timeframe="1h"
            height={380}
            showHeader={false}
            trades={tradeMarkers}
            gridLevels={gridLevels}
          />
        </CardContent>
      </Card>

      {/* Trade log */}
      <Card className="border-border/60 bg-card elevated">
        <CardContent className="p-6">
          <h3 className="mb-4 text-lg font-bold text-foreground">Trade Log</h3>
          {trades && trades.length > 0 ? (
            <div className="space-y-2">
              {trades.slice(0, 12).map((t, i) => (
                <div
                  key={t.id ?? i}
                  className="flex items-center justify-between rounded-xl border border-border/40 bg-muted/20 p-3"
                >
                  <div className="flex items-center gap-3">
                    <Badge
                      variant="outline"
                      className={`border-0 text-[10px] font-bold ${
                        t.side === "buy"
                          ? "bg-profit/10 text-profit"
                          : "bg-brand/10 text-brand"
                      }`}
                    >
                      {t.side.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {new Date(t.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold tabular-nums text-foreground">
                      ${usd(t.price)}
                    </p>
                    {t.profit !== null && t.profit !== undefined && (
                      <p
                        className={`text-xs tabular-nums ${
                          t.profit >= 0 ? "text-profit" : "text-loss"
                        }`}
                      >
                        {t.profit >= 0 ? "+" : ""}${usd(Math.abs(t.profit))}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border/60 bg-muted/10 p-8 text-center">
              <p className="text-sm text-muted-foreground">
                Waiting for first trade...
              </p>
              <p className="mt-1 text-xs text-muted-foreground/70">
                The bot places orders when price crosses grid levels. First trade
                may take a few minutes to hours depending on market volatility.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
  change,
  positive,
  icon: Icon,
}: {
  label: string;
  value: string;
  change?: string;
  positive?: boolean;
  icon: React.ElementType;
}) {
  return (
    <Card className="border-border/60 bg-card elevated">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-muted">
            <Icon className="h-4 w-4 text-brand" strokeWidth={2.5} />
          </div>
          {change && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                positive ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss"
              }`}
            >
              {change}
            </span>
          )}
        </div>
        <p className="mt-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          {label}
        </p>
        <p className="mt-1 text-xl font-bold tracking-tight text-foreground">
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

// ─── Main page ─────────────────────────────────────────────

type Step = "deposit" | "analyzing" | "results" | "running";

export default function AutopilotPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("deposit");
  const [investment, setInvestment] = useState(1000);
  const [result, setResult] = useState<AIAnalyzeResponse | null>(null);
  const [paper, setPaper] = useState(true);
  const [deploying, setDeploying] = useState(false);
  const [deployedBotId, setDeployedBotId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("Starting analysis...");

  // Simulated progress while backend runs
  useEffect(() => {
    if (step !== "analyzing") return;
    let pct = 0;
    const stages = [
      "Fetching market data...",
      "Running 30-day backtests...",
      "Running 90-day backtests...",
      "Computing risk metrics...",
      "Ranking strategies...",
      "Preparing recommendation...",
    ];
    let i = 0;
    setStage(stages[0]);
    const tick = setInterval(() => {
      pct = Math.min(95, pct + 2);
      setProgress(pct);
      const target = Math.floor((pct / 100) * stages.length);
      if (target !== i && target < stages.length) {
        i = target;
        setStage(stages[i]);
      }
    }, 600);
    return () => clearInterval(tick);
  }, [step]);

  const handleAnalyze = async () => {
    setStep("analyzing");
    setProgress(0);
    try {
      const res = await aiAnalyze(investment);
      setResult(res);
      setProgress(100);
      setTimeout(() => setStep("results"), 400);
    } catch (err) {
      toast.error("Analysis failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      setStep("deposit");
    }
  };

  const handleDeploy = async () => {
    if (!result) return;
    setDeploying(true);
    try {
      const res = await aiDeploy({
        investment: result.investment,
        pair: result.recommendation.pair,
        strategy: result.recommendation.strategy,
        config: result.recommendation.config,
        paper,
      });
      setDeployedBotId(res.bot_id);
      toast.success("Bot deployed!", { description: res.message });
      setStep("running");
    } catch (err) {
      toast.error("Deploy failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setDeploying(false);
    }
  };

  const gridLevels = useMemo(() => {
    if (!result) return undefined;
    const cfg = result.recommendation.config as Record<string, number>;
    const lower = Number(cfg.lower_price);
    const upper = Number(cfg.upper_price);
    const num = Number(cfg.num_grids);
    if (!lower || !upper || !num) return undefined;
    const step = (upper - lower) / num;
    const levels: { price: number; type: "buy" | "sell" }[] = [];
    for (let i = 0; i <= num; i++) {
      const p = lower + step * i;
      const isBuy = p < (lower + upper) / 2;
      levels.push({ price: Number(p.toFixed(2)), type: isBuy ? "buy" : "sell" });
    }
    return levels;
  }, [result]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-foreground">
            <Zap className="h-6 w-6 text-brand" />
            AI Auto-Pilot
          </h1>
          <p className="text-sm text-muted-foreground">
            Deposit, analyse, deploy — all in under 2 minutes
          </p>
        </div>

        {/* Step indicator */}
        <div className="hidden items-center gap-2 sm:flex">
          {["deposit", "analyzing", "results", "running"].map((s, i) => {
            const steps: Step[] = ["deposit", "analyzing", "results", "running"];
            const currentIdx = steps.indexOf(step);
            const active = currentIdx === i;
            const done = currentIdx > i;
            return (
              <div key={s} className="flex items-center">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-bold transition-all ${
                    done
                      ? "border-profit bg-profit text-white"
                      : active
                      ? "border-brand bg-brand text-white"
                      : "border-border bg-muted text-muted-foreground"
                  }`}
                >
                  {done ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
                </div>
                {i < 3 && (
                  <div
                    className={`h-px w-8 transition-colors ${
                      done ? "bg-profit" : "bg-border"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Step content */}
      {step === "deposit" && (
        <StepDeposit
          amount={investment}
          onChange={setInvestment}
          onNext={handleAnalyze}
        />
      )}

      {step === "analyzing" && <StepAnalyzing progress={progress} stage={stage} />}

      {step === "results" && result && (
        <StepResults
          result={result}
          paper={paper}
          onPaperChange={setPaper}
          onDeploy={handleDeploy}
          onBack={() => setStep("deposit")}
          loading={deploying}
        />
      )}

      {step === "running" && deployedBotId && result && (
        <StepRunning
          botId={deployedBotId}
          symbol={result.recommendation.pair}
          investment={result.investment}
          gridLevels={gridLevels}
        />
      )}
    </div>
  );
}
