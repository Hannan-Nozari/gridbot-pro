"use client";

import { useMemo } from "react";
import useSWR from "swr";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  TrendingUp,
  Bot as BotIcon,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Wallet,
  Flame,
  Play,
  Pause,
  MoreHorizontal,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getPortfolioSummary, getEquityCurve, getBots, getTrades } from "@/lib/api";
import type { Bot as BotType, Trade, PortfolioSummary } from "@/types";

// ── Helpers ─────────────────────────────────────────────────

function formatUsd(n: number, decimals = 2) {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatCompact(n: number) {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
  return n.toFixed(2);
}

// ── Mock sparkline data for demo (replaces stubs when real data unavailable) ─
const mockSpark = (base: number, vol = 0.1, n = 20) =>
  Array.from({ length: n }, (_, i) => ({
    i,
    v: base * (1 + (Math.sin(i * 0.5) + Math.random() * 0.5 - 0.25) * vol),
  }));

// ── Hero Portfolio Card ─────────────────────────────────────

function HeroPortfolioCard({
  value,
  pnl,
  pnlPct,
  data,
}: {
  value: number;
  pnl: number;
  pnlPct: number;
  data: { timestamp: string; value: number }[];
}) {
  const isProfit = pnl >= 0;

  return (
    <Card className="relative col-span-1 overflow-hidden border-border/60 bg-card lg:col-span-2 elevated">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Wallet className="h-4 w-4 text-brand" />
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Total Portfolio
              </span>
            </div>
            <p className="text-3xl font-bold tracking-tight text-foreground">
              ${formatUsd(value)}
            </p>
            <div className="flex items-center gap-2">
              <div
                className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                  isProfit
                    ? "bg-profit/10 text-profit"
                    : "bg-loss/10 text-loss"
                }`}
              >
                {isProfit ? (
                  <ArrowUpRight className="h-3 w-3" />
                ) : (
                  <ArrowDownRight className="h-3 w-3" />
                )}
                {isProfit ? "+" : ""}
                {pnlPct.toFixed(2)}%
              </div>
              <span className="text-xs text-muted-foreground">
                {isProfit ? "+" : ""}${formatUsd(Math.abs(pnl))} today
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {["1D", "1W", "1M", "ALL"].map((label, i) => (
              <button
                key={label}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  i === 1
                    ? "bg-brand-muted text-brand"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Chart */}
        <div className="mt-6 h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={
                data && data.length > 0
                  ? data
                  : mockSpark(value || 1000, 0.08, 30).map((p) => ({
                      timestamp: String(p.i),
                      value: p.v,
                    }))
              }
              margin={{ top: 5, right: 0, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="heroGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff4d15" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#ff4d15" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Tooltip
                contentStyle={{
                  background: "#1a1a1a",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                }}
                formatter={(v) => [`$${formatUsd(Number(v))}`, "Value"]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#ff4d15"
                strokeWidth={2.5}
                fill="url(#heroGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Small Stat Card with Sparkline ──────────────────────────

function SparkStatCard({
  label,
  value,
  change,
  icon: Icon,
  spark,
  color = "#ff4d15",
}: {
  label: string;
  value: string;
  change?: { value: string; positive: boolean };
  icon: React.ElementType;
  spark: { i: number; v: number }[];
  color?: string;
}) {
  return (
    <Card className="stat-card border-border/60 bg-card elevated">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-muted">
            <Icon className="h-4 w-4 text-brand" strokeWidth={2.5} />
          </div>
          {change && (
            <Badge
              variant="outline"
              className={`border-0 text-[11px] font-semibold ${
                change.positive
                  ? "bg-profit/10 text-profit"
                  : "bg-loss/10 text-loss"
              }`}
            >
              {change.positive ? "↑" : "↓"} {change.value}
            </Badge>
          )}
        </div>

        <div className="mt-4 space-y-1">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <p className="text-2xl font-bold tracking-tight text-foreground">
            {value}
          </p>
        </div>

        <div className="mt-3 h-[40px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={spark}>
              <Line
                type="monotone"
                dataKey="v"
                stroke={color}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Main Chart Card (Bar) ───────────────────────────────────

function StatisticsCard({ trades }: { trades: Trade[] | undefined }) {
  // Group trades by day for last 7 days
  const data = useMemo(() => {
    if (!trades || trades.length === 0) {
      // Demo data
      return [
        { day: "Mon", buy: 12, sell: 8 },
        { day: "Tue", buy: 18, sell: 14 },
        { day: "Wed", buy: 9, sell: 15 },
        { day: "Thu", buy: 22, sell: 19 },
        { day: "Fri", buy: 15, sell: 11 },
        { day: "Sat", buy: 28, sell: 22 },
        { day: "Sun", buy: 19, sell: 24 },
      ];
    }

    const days: Record<string, { buy: number; sell: number }> = {};
    const now = Date.now();
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now - i * 86400000);
      const key = d.toLocaleDateString("en-US", { weekday: "short" });
      days[key] = { buy: 0, sell: 0 };
    }
    trades.forEach((t) => {
      const key = new Date(t.timestamp).toLocaleDateString("en-US", {
        weekday: "short",
      });
      if (days[key]) {
        if (t.side === "buy") days[key].buy++;
        else days[key].sell++;
      }
    });
    return Object.entries(days).map(([day, v]) => ({ day, ...v }));
  }, [trades]);

  return (
    <Card className="col-span-1 border-border/60 bg-card elevated lg:col-span-2">
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-foreground">Trade Activity</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Buy vs sell volume over 7 days
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-brand" />
              <span className="text-muted-foreground">Buys</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-white/20" />
              <span className="text-muted-foreground">Sells</span>
            </span>
          </div>
        </div>

        <div className="mt-6 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} barCategoryGap="20%">
              <XAxis
                dataKey="day"
                tick={{ fontSize: 11, fill: "#737373" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#737373" }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a1a1a",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                }}
                cursor={{ fill: "rgba(255,77,21,0.05)" }}
              />
              <Bar dataKey="buy" fill="#ff4d15" radius={[6, 6, 0, 0]} />
              <Bar dataKey="sell" fill="rgba(255,255,255,0.18)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Strategy Donut ──────────────────────────────────────────

function StrategyDonut({ bots }: { bots: BotType[] | undefined }) {
  const data = useMemo(() => {
    if (!bots || bots.length === 0) {
      return [
        { name: "Grid", value: 45, color: "#ff4d15" },
        { name: "Hybrid", value: 25, color: "#ffa06b" },
        { name: "Smart", value: 20, color: "#4ade80" },
        { name: "V3", value: 10, color: "#60a5fa" },
      ];
    }
    const counts: Record<string, number> = {};
    bots.forEach((b) => {
      counts[b.type] = (counts[b.type] ?? 0) + 1;
    });
    const palette = ["#ff4d15", "#ffa06b", "#4ade80", "#60a5fa"];
    return Object.entries(counts).map(([name, value], i) => ({
      name,
      value,
      color: palette[i % palette.length],
    }));
  }, [bots]);

  const total = data.reduce((s, d) => s + d.value, 0);

  return (
    <Card className="border-border/60 bg-card elevated">
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-foreground">Strategy Mix</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">Bots by type</p>
          </div>
          <button className="rounded-lg p-1 hover:bg-muted">
            <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        <div className="relative mt-4 h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                innerRadius={55}
                outerRadius={80}
                paddingAngle={3}
                strokeWidth={0}
              >
                {data.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#1a1a1a",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Total
            </p>
            <p className="text-2xl font-bold text-foreground">{total}</p>
          </div>
        </div>

        <div className="mt-4 space-y-2">
          {data.map((d) => (
            <div
              key={d.name}
              className="flex items-center justify-between text-xs"
            >
              <span className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: d.color }}
                />
                <span className="text-muted-foreground">{d.name}</span>
              </span>
              <span className="font-semibold text-foreground">
                {total > 0 ? Math.round((d.value / total) * 100) : 0}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Active Bots "Best Rent Cars" style ──────────────────────

function ActiveBotsSection({ bots }: { bots: BotType[] | undefined }) {
  const running = bots?.filter((b) => b.status === "running") ?? [];

  const displayBots: (BotType | null)[] =
    running.length > 0
      ? running.slice(0, 4)
      : [null, null, null, null];

  return (
    <Card className="border-border/60 bg-card elevated">
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-foreground">
              Top Performing Bots
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Highest P&L in the last 24 hours
            </p>
          </div>
          <button className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
            View All
          </button>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {displayBots.map((bot, i) =>
            bot ? (
              <div
                key={bot.id}
                className="group relative overflow-hidden rounded-2xl border border-border/60 bg-muted/20 p-4 transition-all hover:border-brand/40 hover:bg-muted/40"
              >
                <div className="flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-muted">
                    <BotIcon className="h-5 w-5 text-brand" />
                  </div>
                  <Badge
                    variant="outline"
                    className="border-profit/20 bg-profit/10 text-[10px] font-semibold text-profit"
                  >
                    <span className="mr-1 h-1.5 w-1.5 rounded-full bg-profit" />
                    LIVE
                  </Badge>
                </div>
                <p className="mt-3 truncate text-sm font-bold text-foreground">
                  {bot.name}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {bot.config?.symbol ?? "—"} · {bot.type}
                </p>
                <div className="mt-3 flex items-end justify-between">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      P&L
                    </p>
                    <p
                      className={`text-base font-bold ${
                        (bot.pnl ?? 0) >= 0 ? "text-profit" : "text-loss"
                      }`}
                    >
                      {(bot.pnl ?? 0) >= 0 ? "+" : ""}$
                      {formatUsd(Math.abs(bot.pnl ?? 0))}
                    </p>
                  </div>
                  <button className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white opacity-0 transition-opacity group-hover:opacity-100">
                    <Pause className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ) : (
              <div
                key={i}
                className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/10 p-4 text-center"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted/40">
                  <Play className="h-4 w-4 text-muted-foreground" />
                </div>
                <p className="mt-3 text-xs text-muted-foreground">No bot</p>
                <p className="text-[10px] text-muted-foreground/60">
                  Create to start
                </p>
              </div>
            )
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Recent Trades Table ─────────────────────────────────────

function RecentTradesTable({ trades }: { trades: Trade[] | undefined }) {
  return (
    <Card className="border-border/60 bg-card elevated">
      <CardContent className="p-0">
        <div className="flex items-center justify-between p-6 pb-4">
          <div>
            <h3 className="text-base font-bold text-foreground">Recent Trades</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Latest executions across all bots
            </p>
          </div>
          <button className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
            View All
          </button>
        </div>

        <Table>
          <TableHeader>
            <TableRow className="border-border/60 hover:bg-transparent">
              <TableHead className="pl-6 text-[11px] uppercase tracking-wider text-muted-foreground">
                Time
              </TableHead>
              <TableHead className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Pair
              </TableHead>
              <TableHead className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Side
              </TableHead>
              <TableHead className="text-right text-[11px] uppercase tracking-wider text-muted-foreground">
                Price
              </TableHead>
              <TableHead className="text-right text-[11px] uppercase tracking-wider text-muted-foreground">
                Amount
              </TableHead>
              <TableHead className="pr-6 text-right text-[11px] uppercase tracking-wider text-muted-foreground">
                Profit
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!trades || trades.length === 0 ? (
              <TableRow className="border-border/60 hover:bg-transparent">
                <TableCell
                  colSpan={6}
                  className="py-10 text-center text-sm text-muted-foreground"
                >
                  No recent trades
                </TableCell>
              </TableRow>
            ) : (
              trades.slice(0, 8).map((t, i) => (
                <TableRow
                  key={t.id ?? i}
                  className="border-border/40 hover:bg-muted/30"
                >
                  <TableCell className="pl-6 text-xs text-muted-foreground">
                    {new Date(t.timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </TableCell>
                  <TableCell className="text-sm font-semibold">
                    {t.symbol}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={`border-0 text-[11px] font-bold ${
                        t.side === "buy"
                          ? "bg-profit/10 text-profit"
                          : "bg-loss/10 text-loss"
                      }`}
                    >
                      {t.side.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right text-sm font-medium tabular-nums">
                    ${formatUsd(t.price)}
                  </TableCell>
                  <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                    {t.amount.toFixed(6)}
                  </TableCell>
                  <TableCell className="pr-6 text-right">
                    <span
                      className={`text-sm font-semibold tabular-nums ${
                        (t.profit ?? 0) >= 0 ? "text-profit" : "text-loss"
                      }`}
                    >
                      {(t.profit ?? 0) >= 0 ? "+" : ""}$
                      {formatUsd(Math.abs(t.profit ?? 0))}
                    </span>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ── Main Dashboard Page ─────────────────────────────────────

export default function DashboardPage() {
  const { data: portfolio } = useSWR<PortfolioSummary>(
    "portfolio",
    getPortfolioSummary,
    { refreshInterval: 10000 }
  );
  const { data: equityCurve } = useSWR<{ timestamp: string; value: number }[]>(
    "equity-curve",
    getEquityCurve,
    { refreshInterval: 30000 }
  );
  const { data: bots } = useSWR<BotType[]>("bots", getBots, {
    refreshInterval: 10000,
  });
  const { data: trades } = useSWR<Trade[]>(
    "trades",
    () => getTrades({ limit: 10 }),
    { refreshInterval: 10000 }
  );

  const activeBots = useMemo(
    () => bots?.filter((b) => b.status === "running") ?? [],
    [bots]
  );

  const totalValue = portfolio?.total_value ?? 0;
  const pnl = portfolio?.total_pnl ?? 0;
  const pnlPct = portfolio?.pnl_pct ?? 0;

  return (
    <div className="space-y-6">
      {/* Top Row: Hero + 2 Stat Cards */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-4">
        <HeroPortfolioCard
          value={totalValue}
          pnl={pnl}
          pnlPct={pnlPct}
          data={equityCurve ?? []}
        />

        <SparkStatCard
          label="Active Bots"
          value={String(activeBots.length)}
          change={{
            value: `${bots?.length ?? 0} total`,
            positive: activeBots.length > 0,
          }}
          icon={BotIcon}
          spark={mockSpark(activeBots.length || 1, 0.3)}
        />

        <SparkStatCard
          label="Total Trades"
          value={formatCompact(portfolio?.num_trades ?? 0)}
          change={{ value: "24h", positive: true }}
          icon={Activity}
          spark={mockSpark(portfolio?.num_trades || 10, 0.2)}
        />
      </div>

      {/* Middle Row: Statistics (bar) + Strategy Mix (donut) */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <StatisticsCard trades={trades} />
        <StrategyDonut bots={bots} />
      </div>

      {/* Active Bots (card row) */}
      <ActiveBotsSection bots={bots} />

      {/* Recent Trades */}
      <RecentTradesTable trades={trades} />
    </div>
  );
}
