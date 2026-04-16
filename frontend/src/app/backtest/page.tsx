"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { FlaskConical, Play, TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { runBacktest } from "@/lib/api";
import type { BacktestResult } from "@/types";

const STRATEGIES = ["Grid", "Hybrid", "Smart", "V3"] as const;

function ResultStatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: "profit" | "loss" | "default";
}) {
  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-1 text-lg font-bold ${
          color === "profit"
            ? "text-profit"
            : color === "loss"
            ? "text-loss"
            : "text-foreground"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

export default function BacktestPage() {
  const [strategy, setStrategy] = useState("Grid");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [days, setDays] = useState("30");
  const [investment, setInvestment] = useState("10000");
  const [numGrids, setNumGrids] = useState("10");
  const [lowerPrice, setLowerPrice] = useState("");
  const [upperPrice, setUpperPrice] = useState("");
  // Hybrid-specific
  const [rsiPeriod, setRsiPeriod] = useState("14");
  const [overbought, setOverbought] = useState("70");
  const [oversold, setOversold] = useState("30");
  // Smart-specific
  const [atrPeriod, setAtrPeriod] = useState("14");
  const [sensitivity, setSensitivity] = useState("1.5");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setResult(null);
    try {
      const params: Record<string, unknown> = {
        strategy,
        symbol,
        days: parseInt(days, 10),
        investment: parseFloat(investment),
        num_grids: parseInt(numGrids, 10),
        lower_price: lowerPrice ? parseFloat(lowerPrice) : undefined,
        upper_price: upperPrice ? parseFloat(upperPrice) : undefined,
      };

      if (strategy === "Hybrid") {
        params.rsi_period = parseInt(rsiPeriod, 10);
        params.overbought = parseInt(overbought, 10);
        params.oversold = parseInt(oversold, 10);
      }
      if (strategy === "Smart") {
        params.atr_period = parseInt(atrPeriod, 10);
        params.sensitivity = parseFloat(sensitivity);
      }

      const data = await runBacktest(params as unknown as import("@/types").BacktestRequest);
      setResult(data);
      toast.success("Backtest completed");
    } catch {
      toast.error("Backtest failed. Check parameters and try again.");
    } finally {
      setLoading(false);
    }
  };

  const returnPct = result?.pnl_pct ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Backtester
        </h2>
        <p className="text-sm text-muted-foreground">
          Test strategies against historical data
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Panel: Form */}
        <Card className="border-border/50 bg-card lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FlaskConical className="h-4 w-4 text-primary" />
              Parameters
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <Label>Strategy</Label>
              <Select value={strategy} onValueChange={(v) => v !== null && setStrategy(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STRATEGIES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="bt-symbol">Symbol</Label>
              <Input
                id="bt-symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="BTC/USDT"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="bt-days">Days</Label>
                <Input
                  id="bt-days"
                  type="number"
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="bt-investment">Investment</Label>
                <Input
                  id="bt-investment"
                  type="number"
                  value={investment}
                  onChange={(e) => setInvestment(e.target.value)}
                />
              </div>
            </div>

            <Separator />

            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="bt-lower">Lower</Label>
                <Input
                  id="bt-lower"
                  type="number"
                  value={lowerPrice}
                  onChange={(e) => setLowerPrice(e.target.value)}
                  placeholder="Auto"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="bt-upper">Upper</Label>
                <Input
                  id="bt-upper"
                  type="number"
                  value={upperPrice}
                  onChange={(e) => setUpperPrice(e.target.value)}
                  placeholder="Auto"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="bt-grids">Grids</Label>
                <Input
                  id="bt-grids"
                  type="number"
                  value={numGrids}
                  onChange={(e) => setNumGrids(e.target.value)}
                />
              </div>
            </div>

            {strategy === "Hybrid" && (
              <>
                <Separator />
                <p className="text-xs font-medium text-muted-foreground">
                  RSI Parameters
                </p>
                <div className="grid grid-cols-3 gap-3">
                  <div className="grid gap-2">
                    <Label htmlFor="bt-rsi">RSI Period</Label>
                    <Input
                      id="bt-rsi"
                      type="number"
                      value={rsiPeriod}
                      onChange={(e) => setRsiPeriod(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="bt-ob">Overbought</Label>
                    <Input
                      id="bt-ob"
                      type="number"
                      value={overbought}
                      onChange={(e) => setOverbought(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="bt-os">Oversold</Label>
                    <Input
                      id="bt-os"
                      type="number"
                      value={oversold}
                      onChange={(e) => setOversold(e.target.value)}
                    />
                  </div>
                </div>
              </>
            )}

            {strategy === "Smart" && (
              <>
                <Separator />
                <p className="text-xs font-medium text-muted-foreground">
                  Volatility Parameters
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-2">
                    <Label htmlFor="bt-atr">ATR Period</Label>
                    <Input
                      id="bt-atr"
                      type="number"
                      value={atrPeriod}
                      onChange={(e) => setAtrPeriod(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="bt-sens">Sensitivity</Label>
                    <Input
                      id="bt-sens"
                      type="number"
                      step="0.1"
                      value={sensitivity}
                      onChange={(e) => setSensitivity(e.target.value)}
                    />
                  </div>
                </div>
              </>
            )}

            <Button
              className="mt-2 w-full"
              onClick={handleRun}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Running Backtest...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Play className="h-4 w-4" />
                  Run Backtest
                </span>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Right Panel: Results */}
        <div className="space-y-6 lg:col-span-2">
          {!result && !loading ? (
            <Card className="border-border/50 bg-card">
              <CardContent className="flex flex-col items-center justify-center py-20">
                <FlaskConical className="mb-4 h-12 w-12 text-muted-foreground/30" />
                <p className="text-lg font-medium text-foreground">
                  No Results Yet
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Configure parameters and run a backtest to see results
                </p>
              </CardContent>
            </Card>
          ) : loading ? (
            <Card className="border-border/50 bg-card">
              <CardContent className="flex flex-col items-center justify-center py-20">
                <div className="mb-4 h-10 w-10 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <p className="text-sm text-muted-foreground">
                  Running backtest simulation...
                </p>
              </CardContent>
            </Card>
          ) : result ? (
            <>
              {/* Stat Cards */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
                <ResultStatCard
                  label="Return"
                  value={`${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%`}
                  color={returnPct >= 0 ? "profit" : "loss"}
                />
                <ResultStatCard
                  label="Sharpe"
                  value={(result.sharpe ?? 0).toFixed(2)}
                />
                <ResultStatCard
                  label="Max DD"
                  value={`${(result.max_drawdown ?? 0).toFixed(2)}%`}
                  color="loss"
                />
                <ResultStatCard
                  label="Win Rate"
                  value={`${(result.win_rate ?? 0).toFixed(1)}%`}
                />
                <ResultStatCard
                  label="Profit Factor"
                  value={(result.profit_factor ?? 0).toFixed(2)}
                />
                <ResultStatCard
                  label="Trades"
                  value={String(result.num_trades ?? 0)}
                />
                <ResultStatCard
                  label="Monthly ROI"
                  value={`${(result.monthly_roi ?? 0).toFixed(2)}%`}
                />
              </div>

              {/* Equity Curve */}
              <Card className="border-border/50 bg-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    {returnPct >= 0 ? (
                      <TrendingUp className="h-4 w-4 text-profit" />
                    ) : (
                      <TrendingDown className="h-4 w-4 text-loss" />
                    )}
                    Equity Curve
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart
                      data={result.equity_curve ?? []}
                      margin={{ top: 5, right: 5, left: 5, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="timestamp"
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
                      />
                      <Tooltip
                        formatter={(value) => [
                          `$${Number(value).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}`,
                          "Equity",
                        ]}
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke={returnPct >= 0 ? "#22c55e" : "#ef4444"}
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              {/* Trade List */}
              {result.trades && result.trades.length > 0 && (
                <Card className="border-border/50 bg-card">
                  <CardHeader>
                    <CardTitle className="text-base">Trade List</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="max-h-[400px] overflow-y-auto">
                      <Table>
                        <TableHeader>
                          <TableRow className="border-border/50 hover:bg-transparent">
                            <TableHead className="text-xs">Date</TableHead>
                            <TableHead className="text-xs">Side</TableHead>
                            <TableHead className="text-right text-xs">
                              Price
                            </TableHead>
                            <TableHead className="text-right text-xs">
                              Amount
                            </TableHead>
                            <TableHead className="text-right text-xs">
                              Profit
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {result.trades.map((trade, i) => (
                            <TableRow key={i} className="border-border/50">
                              <TableCell className="text-xs text-muted-foreground">
                                {new Date(trade.timestamp).toLocaleDateString()}
                              </TableCell>
                              <TableCell>
                                <span
                                  className={`text-xs font-medium ${
                                    trade.side === "buy"
                                      ? "text-profit"
                                      : "text-loss"
                                  }`}
                                >
                                  {trade.side.toUpperCase()}
                                </span>
                              </TableCell>
                              <TableCell className="text-right text-xs">
                                ${trade.price.toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}
                              </TableCell>
                              <TableCell className="text-right text-xs">
                                {trade.amount?.toFixed(6) ?? "-"}
                              </TableCell>
                              <TableCell className="text-right">
                                <span
                                  className={`text-xs font-medium ${
                                    (trade.profit ?? 0) >= 0
                                      ? "text-profit"
                                      : "text-loss"
                                  }`}
                                >
                                  {(trade.profit ?? 0) >= 0 ? "+" : ""}$
                                  {Math.abs(trade.profit ?? 0).toFixed(2)}
                                </span>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
