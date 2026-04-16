"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import { Download, ChevronLeft, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
import { getTrades, getBots } from "@/lib/api";
import type { Trade, Bot } from "@/types";

const PAGE_SIZE = 20;

export default function TradesPage() {
  const [page, setPage] = useState(1);
  const [botFilter, setBotFilter] = useState("all");
  const [symbolFilter, setSymbolFilter] = useState("all");
  const [sideFilter, setSideFilter] = useState("all");

  const { data: bots } = useSWR<Bot[]>("trades-bots", getBots);

  const queryKey = `trades-${page}-${botFilter}-${symbolFilter}-${sideFilter}`;
  const { data: allTrades, isLoading } = useSWR<Trade[]>(queryKey, () =>
    getTrades({
      bot_id: botFilter !== "all" ? botFilter : undefined,
      symbol: symbolFilter !== "all" ? symbolFilter : undefined,
      side: (sideFilter !== "all" ? sideFilter : undefined) as import("@/types").TradeSide | undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
  );

  const trades = allTrades ?? [];
  const totalTrades = trades.length;
  const totalPages = Math.max(1, Math.ceil(totalTrades / PAGE_SIZE));

  const symbols = Array.from(
    new Set(bots?.map((b) => b.config.symbol).filter(Boolean) ?? [])
  );

  const exportCsv = useCallback(() => {
    if (!trades.length) return;
    const headers = [
      "Time",
      "Bot",
      "Symbol",
      "Side",
      "Price",
      "Amount",
      "Fee",
      "Profit",
    ];
    const rows = trades.map((t) => [
      new Date(t.timestamp).toISOString(),
      t.bot_id ?? "",
      t.symbol,
      t.side,
      t.price,
      t.amount ?? "",
      t.fee ?? "",
      t.profit ?? "",
    ]);
    const csv = [headers, ...rows].map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trades-export-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [trades]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Trade History
          </h2>
          <p className="text-sm text-muted-foreground">
            Complete log of all executed trades
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={exportCsv}>
          <Download className="mr-2 h-4 w-4" />
          Export CSV
        </Button>
      </div>

      {/* Filters */}
      <Card className="border-border/50 bg-card">
        <CardContent className="flex flex-wrap items-center gap-4 p-4">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Bot:</span>
            <Select value={botFilter} onValueChange={(v) => { if (v !== null) { setBotFilter(v); setPage(1); } }}>
              <SelectTrigger className="w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Bots</SelectItem>
                {bots?.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Symbol:
            </span>
            <Select value={symbolFilter} onValueChange={(v) => { if (v !== null) { setSymbolFilter(v); setPage(1); } }}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Symbols</SelectItem>
                {symbols.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Side:</span>
            <Select value={sideFilter} onValueChange={(v) => { if (v !== null) { setSideFilter(v); setPage(1); } }}>
              <SelectTrigger className="w-[120px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="buy">Buy</SelectItem>
                <SelectItem value="sell">Sell</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="ml-auto text-xs text-muted-foreground">
            {totalTrades.toLocaleString()} total trades
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="border-border/50 bg-card">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : trades.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20">
              <p className="text-sm text-muted-foreground">No trades found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-border/50 hover:bg-transparent">
                    <TableHead className="text-xs">Time</TableHead>
                    <TableHead className="text-xs">Bot</TableHead>
                    <TableHead className="text-xs">Symbol</TableHead>
                    <TableHead className="text-xs">Side</TableHead>
                    <TableHead className="text-right text-xs">Price</TableHead>
                    <TableHead className="text-right text-xs">Amount</TableHead>
                    <TableHead className="text-right text-xs">Fee</TableHead>
                    <TableHead className="text-right text-xs">Profit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {trades.map((trade, i) => (
                    <TableRow key={trade.id ?? i} className="border-border/50">
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(trade.timestamp).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-xs font-medium">
                        {trade.bot_id ?? "-"}
                      </TableCell>
                      <TableCell className="text-xs font-medium">
                        {trade.symbol}
                      </TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold ${
                            trade.side === "buy"
                              ? "bg-profit/10 text-profit"
                              : "bg-loss/10 text-loss"
                          }`}
                        >
                          {trade.side.toUpperCase()}
                        </span>
                      </TableCell>
                      <TableCell className="text-right text-xs">
                        $
                        {trade.price.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </TableCell>
                      <TableCell className="text-right text-xs">
                        {trade.amount?.toFixed(6) ?? "-"}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        ${(trade.fee ?? 0).toFixed(4)}
                      </TableCell>
                      <TableCell className="text-right">
                        <span
                          className={`text-xs font-semibold ${
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
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
