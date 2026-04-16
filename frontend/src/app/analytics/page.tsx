"use client";

import useSWR from "swr";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { getAnalytics, getBots } from "@/lib/api";
import type { Bot } from "@/types";

// Analytics response from the backend — richer than PortfolioSummary
interface AnalyticsData {
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  profit_factor: number;
  win_rate: number;
  drawdown_curve: { timestamp: string; value: number }[];
  monthly_returns: { month: string; return_pct: number }[];
  [key: string]: unknown;
}

function MetricCard({
  label,
  value,
  description,
  color,
}: {
  label: string;
  value: string;
  description?: string;
  color?: "profit" | "loss" | "default";
}) {
  return (
    <Card className="border-border/50 bg-card">
      <CardContent className="p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p
          className={`mt-1 text-2xl font-bold ${
            color === "profit"
              ? "text-profit"
              : color === "loss"
              ? "text-loss"
              : "text-foreground"
          }`}
        >
          {value}
        </p>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const { data: portfolio, isLoading } = useSWR<AnalyticsData>(
    "portfolio-analytics",
    getAnalytics as unknown as () => Promise<AnalyticsData>,
    { refreshInterval: 30000 }
  );

  const { data: bots } = useSWR<Bot[]>("bots-analytics", getBots, {
    refreshInterval: 30000,
  });

  const drawdownData = portfolio?.drawdown_curve ?? [];
  const monthlyReturns = portfolio?.monthly_returns ?? [];

  const sharpe = portfolio?.sharpe_ratio ?? 0;
  const sortino = portfolio?.sortino_ratio ?? 0;
  const maxDrawdown = portfolio?.max_drawdown ?? 0;
  const profitFactor = portfolio?.profit_factor ?? 0;
  const winRate = portfolio?.win_rate ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Portfolio Analytics
        </h2>
        <p className="text-sm text-muted-foreground">
          Advanced risk metrics and performance analysis
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[1, 2, 3, 4, 5].map((i) => (
            <Card key={i} className="border-border/50 bg-card">
              <CardContent className="p-5">
                <div className="animate-pulse space-y-3">
                  <div className="h-3 w-20 rounded bg-muted" />
                  <div className="h-7 w-16 rounded bg-muted" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <>
          {/* Metric Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard
              label="Sharpe Ratio"
              value={sharpe.toFixed(2)}
              description={
                sharpe >= 2 ? "Excellent" : sharpe >= 1 ? "Good" : "Below average"
              }
              color={sharpe >= 1 ? "profit" : "loss"}
            />
            <MetricCard
              label="Sortino Ratio"
              value={sortino.toFixed(2)}
              description="Downside risk adjusted"
              color={sortino >= 1 ? "profit" : "loss"}
            />
            <MetricCard
              label="Max Drawdown"
              value={`${maxDrawdown.toFixed(2)}%`}
              description="Peak to trough decline"
              color="loss"
            />
            <MetricCard
              label="Profit Factor"
              value={profitFactor.toFixed(2)}
              description="Gross profit / Gross loss"
              color={profitFactor >= 1.5 ? "profit" : "default"}
            />
            <MetricCard
              label="Win Rate"
              value={`${winRate.toFixed(1)}%`}
              description="Profitable trades"
              color={winRate >= 50 ? "profit" : "loss"}
            />
          </div>

          {/* Drawdown Chart */}
          <Card className="border-border/50 bg-card">
            <CardHeader>
              <CardTitle className="text-base font-semibold text-foreground">
                Drawdown
              </CardTitle>
            </CardHeader>
            <CardContent>
              {drawdownData.length === 0 ? (
                <div className="flex h-[250px] items-center justify-center text-sm text-muted-foreground">
                  No drawdown data available
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={250}>
                  <AreaChart
                    data={drawdownData}
                    margin={{ top: 5, right: 5, left: 5, bottom: 5 }}
                  >
                    <defs>
                      <linearGradient
                        id="drawdownGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      reversed
                      tickFormatter={(v) => `${v.toFixed(1)}%`}
                    />
                    <Tooltip
                      formatter={(value: unknown) => [
                        `${Number(value).toFixed(2)}%`,
                        "Drawdown",
                      ]}
                    />
                    <Area
                      type="monotone"
                      dataKey="drawdown"
                      stroke="#ef4444"
                      strokeWidth={2}
                      fill="url(#drawdownGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Monthly Returns */}
          <Card className="border-border/50 bg-card">
            <CardHeader>
              <CardTitle className="text-base font-semibold text-foreground">
                Monthly Returns
              </CardTitle>
            </CardHeader>
            <CardContent>
              {monthlyReturns.length === 0 ? (
                <div className="flex h-[250px] items-center justify-center text-sm text-muted-foreground">
                  No monthly return data available
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart
                    data={monthlyReturns}
                    margin={{ top: 5, right: 5, left: 5, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="month"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v) => `${v.toFixed(0)}%`}
                    />
                    <Tooltip
                      formatter={(value: unknown) => [
                        `${Number(value).toFixed(2)}%`,
                        "Return",
                      ]}
                    />
                    <Bar
                      dataKey="return_pct"
                      radius={[4, 4, 0, 0]}
                      fill="#3b82f6"
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Strategy Comparison */}
          {bots && bots.length > 1 && (
            <Card className="border-border/50 bg-card">
              <CardHeader>
                <CardTitle className="text-base font-semibold text-foreground">
                  Strategy Comparison
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow className="border-border/50 hover:bg-transparent">
                      <TableHead className="text-xs">Bot</TableHead>
                      <TableHead className="text-xs">Strategy</TableHead>
                      <TableHead className="text-xs">Pair</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-right text-xs">P&L</TableHead>
                      <TableHead className="text-right text-xs">Trades</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bots.map((bot) => (
                      <TableRow key={bot.id} className="border-border/50">
                        <TableCell className="text-sm font-medium">
                          {bot.name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs">
                            {bot.type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">{(bot.config as { symbol?: string })?.symbol ?? "—"}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={`text-xs ${
                              bot.status === "running"
                                ? "border-profit/30 bg-profit/10 text-profit"
                                : "text-muted-foreground"
                            }`}
                          >
                            {bot.status === "running" ? "Running" : "Stopped"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span
                            className={`text-sm font-semibold ${
                              (bot.pnl ?? 0) >= 0 ? "text-profit" : "text-loss"
                            }`}
                          >
                            {(bot.pnl ?? 0) >= 0 ? "+" : ""}$
                            {Math.abs(bot.pnl ?? 0).toFixed(2)}
                          </span>
                        </TableCell>
                        <TableCell className="text-right text-sm">
                          {bot.num_trades ?? 0}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
