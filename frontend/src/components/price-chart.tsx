"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Line,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceDot,
} from "recharts";
import { TrendingDown, TrendingUp } from "lucide-react";
import { getCandles, getTicker, type Candle } from "@/lib/api";

interface PriceChartProps {
  symbol: string;
  timeframe?: string;
  height?: number;
  showHeader?: boolean;
  trades?: { timestamp: string | number; side: "buy" | "sell"; price: number }[];
  gridLevels?: { price: number; type: "buy" | "sell" }[];
}

export function PriceChart({
  symbol,
  timeframe = "1h",
  height = 320,
  showHeader = true,
  trades,
  gridLevels,
}: PriceChartProps) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [ticker, setTicker] = useState<{
    price: number;
    change_24h_pct: number;
    high_24h: number;
    low_24h: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [c, t] = await Promise.all([
          getCandles(symbol, timeframe, 100),
          getTicker(symbol),
        ]);
        if (!active) return;
        setCandles(c.candles);
        setTicker(t);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load chart");
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    const interval = setInterval(load, 15_000); // refresh every 15s

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [symbol, timeframe]);

  // Map trades to markers on the chart
  const tradeMarkers =
    trades?.map((t) => ({
      timestamp:
        typeof t.timestamp === "string"
          ? new Date(t.timestamp).getTime()
          : t.timestamp,
      side: t.side,
      price: t.price,
    })) ?? [];

  const up = (ticker?.change_24h_pct ?? 0) >= 0;

  return (
    <div className="w-full">
      {showHeader && (
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              {symbol} · {timeframe}
            </p>
            <div className="mt-1 flex items-center gap-3">
              <p className="text-xl font-bold tracking-tight text-foreground">
                $
                {ticker
                  ? ticker.price.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : "—"}
              </p>
              {ticker && (
                <span
                  className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                    up ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss"
                  }`}
                >
                  {up ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : (
                    <TrendingDown className="h-3 w-3" />
                  )}
                  {up ? "+" : ""}
                  {ticker.change_24h_pct.toFixed(2)}%
                </span>
              )}
            </div>
          </div>
          {ticker && (
            <div className="text-right text-xs text-muted-foreground">
              <p>
                H: ${ticker.high_24h.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
              <p>
                L: ${ticker.low_24h.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
            </div>
          )}
        </div>
      )}

      {loading && candles.length === 0 ? (
        <div
          className="flex items-center justify-center rounded-xl bg-muted/20 text-sm text-muted-foreground"
          style={{ height }}
        >
          Loading chart...
        </div>
      ) : error ? (
        <div
          className="flex items-center justify-center rounded-xl bg-loss/5 px-4 text-center text-xs text-loss"
          style={{ height }}
        >
          {error}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart
            data={candles}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={up ? "#4ade80" : "#ff4d15"}
                  stopOpacity={0.35}
                />
                <stop
                  offset="100%"
                  stopColor={up ? "#4ade80" : "#ff4d15"}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickFormatter={(v) =>
                new Date(v).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              }
              tick={{ fontSize: 10, fill: "#737373" }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis
              dataKey="close"
              domain={["auto", "auto"]}
              tick={{ fontSize: 10, fill: "#737373" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) =>
                v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(2)}`
              }
            />
            <Tooltip
              contentStyle={{
                background: "#1a1a1a",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 10,
                fontSize: 12,
              }}
              labelFormatter={(ts) => new Date(Number(ts)).toLocaleString()}
              formatter={(val: unknown, name: unknown) => [
                typeof val === "number" ? `$${val.toLocaleString()}` : String(val),
                String(name ?? "Price"),
              ]}
            />

            {/* Grid levels as horizontal lines */}
            {gridLevels?.map((lvl, i) => (
              <ReferenceDot
                key={`grid-${i}`}
                x={candles[candles.length - 1]?.timestamp ?? 0}
                y={lvl.price}
                r={0}
                label={{
                  value: `$${lvl.price.toFixed(2)}`,
                  fill: lvl.type === "buy" ? "#4ade80" : "#ff4d15",
                  fontSize: 9,
                  position: "right",
                }}
              />
            ))}

            {/* Trade markers */}
            {tradeMarkers.map((t, i) => (
              <ReferenceDot
                key={`trade-${i}`}
                x={t.timestamp}
                y={t.price}
                r={5}
                fill={t.side === "buy" ? "#4ade80" : "#ff4d15"}
                stroke="#000"
                strokeWidth={1.5}
              />
            ))}

            <Area
              type="monotone"
              dataKey="close"
              stroke={up ? "#4ade80" : "#ff4d15"}
              strokeWidth={2}
              fill="url(#priceGrad)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
