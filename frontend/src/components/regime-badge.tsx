"use client";

import useSWR from "swr";
import { Activity, AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { getRegime, type RegimeStatus } from "@/lib/api";

const REGIME_CONFIG = {
  good: {
    label: "Market: GOOD",
    icon: CheckCircle2,
    classes:
      "border-profit/30 bg-profit/10 text-profit hover:border-profit/50 hover:bg-profit/15",
    dotClass: "bg-profit",
  },
  caution: {
    label: "Market: CAUTION",
    icon: AlertTriangle,
    classes:
      "border-brand/30 bg-brand/10 text-brand hover:border-brand/50 hover:bg-brand/15",
    dotClass: "bg-brand",
  },
  bad: {
    label: "Market: BAD",
    icon: XCircle,
    classes:
      "border-loss/30 bg-loss/10 text-loss hover:border-loss/50 hover:bg-loss/15",
    dotClass: "bg-loss",
  },
  unknown: {
    label: "Market: ...",
    icon: HelpCircle,
    classes:
      "border-border bg-muted/30 text-muted-foreground hover:border-border/80",
    dotClass: "bg-muted-foreground",
  },
};

function formatPct(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function RegimeBadge() {
  const { data, error } = useSWR<RegimeStatus>("regime", getRegime, {
    refreshInterval: 60_000, // poll every minute
    revalidateOnFocus: false,
  });

  const regime = (data?.regime ?? "unknown") as keyof typeof REGIME_CONFIG;
  const config = REGIME_CONFIG[regime];
  const Icon = config.icon;

  return (
    <Dialog>
      <DialogTrigger>
        <button
          type="button"
          className={`flex h-9 items-center gap-2 rounded-xl border px-3 text-xs font-semibold transition-colors ${config.classes}`}
          title="Click for market regime details"
        >
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${config.dotClass}`} />
            <span className={`relative inline-flex h-2 w-2 rounded-full ${config.dotClass}`} />
          </span>
          <Icon className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{config.label}</span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon className="h-5 w-5" />
            {config.label}
          </DialogTitle>
          <DialogDescription>
            {data?.summary ?? "Loading market regime..."}
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p className="rounded-lg border border-loss/30 bg-loss/5 p-3 text-sm text-loss">
            Could not fetch regime: {String(error)}
          </p>
        ) : !data ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <div className="space-y-4">
            {/* Reasons */}
            <div className="rounded-xl border border-border bg-muted/30 p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Why this regime?
              </p>
              <ul className="space-y-1 text-sm">
                {data.reasons.map((r, i) => (
                  <li key={i} className="text-foreground">
                    {r}
                  </li>
                ))}
              </ul>
            </div>

            {/* Signals */}
            <div className="grid grid-cols-2 gap-3">
              <SignalStat
                label="BTC Price"
                value={`$${data.signals.btc_price.toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                })}`}
              />
              <SignalStat
                label="BTC 1h"
                value={formatPct(data.signals.btc_1h_pct)}
                positive={data.signals.btc_1h_pct >= 0}
                colored
              />
              <SignalStat
                label="BTC 24h"
                value={formatPct(data.signals.btc_24h_pct)}
                positive={data.signals.btc_24h_pct >= 0}
                colored
              />
              <SignalStat
                label="Volatility"
                value={`${data.signals.volatility_pct.toFixed(2)}%`}
              />
              <SignalStat
                label="Trend Strength"
                value={`${data.signals.trend_strength_pct.toFixed(2)}%`}
              />
              <SignalStat
                label="Drawdown"
                value={`${data.signals.drawdown_pct.toFixed(2)}%`}
                positive={data.signals.drawdown_pct < 5}
                colored
              />
            </div>

            {/* Info */}
            <div className="rounded-xl border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
              <div className="flex items-center justify-between">
                <span>Auto-pause / resume</span>
                <span className="font-semibold text-foreground">
                  {data.enabled ? "Active" : "Disabled"}
                </span>
              </div>
              {(data.bots_paused_by_regime ?? 0) > 0 && (
                <div className="mt-2 flex items-center gap-2 rounded-lg bg-loss/10 px-2 py-1.5 text-loss">
                  <Activity className="h-3 w-3" />
                  {data.bots_paused_by_regime} bot(s) currently paused
                </div>
              )}
              <p className="mt-2 text-[11px] text-muted-foreground/80">
                Checked every minute. Auto-resumes after conditions stay GOOD
                for the cooldown period.
              </p>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SignalStat({
  label,
  value,
  positive,
  colored,
}: {
  label: string;
  value: string;
  positive?: boolean;
  colored?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
      <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p
        className={`mt-1 text-sm font-bold tabular-nums ${
          colored
            ? positive
              ? "text-profit"
              : "text-loss"
            : "text-foreground"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
