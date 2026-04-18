"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Zap,
  RefreshCw,
  Brain,
  Mail,
  PlayCircle,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  getAutonomy,
  updateAutonomy,
  sendDigestNow,
  checkRebalanceNow,
  type AutonomyStatus,
} from "@/lib/api";

function toLocalTime(unixSec: number): string {
  if (!unixSec) return "never";
  return new Date(unixSec * 1000).toLocaleString();
}

export default function AutonomyPage() {
  const { data, mutate, isLoading } = useSWR<AutonomyStatus>(
    "autonomy",
    getAutonomy,
    { refreshInterval: 30_000 }
  );

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  const cfg = data?.config;

  const save = async (patch: Partial<NonNullable<typeof cfg>>) => {
    if (!cfg) return;
    setSaving(true);
    try {
      await updateAutonomy(patch);
      await mutate();
      toast.success("Settings updated");
    } catch (err) {
      toast.error("Failed to update", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSaving(false);
    }
  };

  const onDigestTest = async () => {
    setTesting("digest");
    try {
      await sendDigestNow();
      toast.success("Digest sent — check Telegram");
    } catch (err) {
      toast.error("Failed to send digest", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setTesting(null);
    }
  };

  const onRebalanceTest = async () => {
    setTesting("rebalance");
    try {
      const r = await checkRebalanceNow();
      await mutate();
      toast.success(`Rebalance check done — ${r.actions.length} action(s)`);
    } catch (err) {
      toast.error("Rebalance check failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setTesting(null);
    }
  };

  if (isLoading || !data) {
    return (
      <div className="flex h-96 items-center justify-center text-muted-foreground">
        Loading autonomy status...
      </div>
    );
  }

  if (!data.enabled) {
    return (
      <div className="mx-auto max-w-2xl">
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-8 text-center">
            <XCircle className="mx-auto mb-3 h-10 w-10 text-destructive" />
            <h2 className="text-xl font-bold text-foreground">
              Autonomy Service Not Running
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {data.summary ?? "The background service could not start."}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-foreground">
          <Zap className="h-6 w-6 text-brand" />
          Set &amp; Forget Automation
        </h1>
        <p className="text-sm text-muted-foreground">
          Turn on every loop and your bot truly runs itself — no manual
          intervention required.
        </p>
      </div>

      {/* Master status */}
      <Card className="border-profit/30 bg-profit/5 elevated">
        <CardContent className="flex items-center gap-4 p-6">
          <CheckCircle2 className="h-8 w-8 text-profit" />
          <div>
            <h3 className="text-base font-bold text-foreground">
              Autonomy service is running
            </h3>
            <p className="text-xs text-muted-foreground">
              Three background loops continuously manage your bots.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Auto-Rebalance */}
      <Card className="border-border/60 bg-card elevated">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <RefreshCw className="h-5 w-5 text-brand" />
            Auto-Rebalance Grid Range
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            When price drifts too far from the grid centre, the bot is
            automatically re-centered so it keeps trading. Prevents dead grids
            after large moves.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="reb-en" className="text-sm font-medium">
              Enable auto-rebalance
            </Label>
            <Switch
              id="reb-en"
              checked={cfg?.rebalance_enabled ?? false}
              onCheckedChange={(v) =>
                save({ rebalance_enabled: Boolean(v) })
              }
              disabled={saving}
            />
          </div>

          <div className="flex items-center justify-between">
            <Label htmlFor="reb-notify" className="text-sm font-medium">
              Notify only (don&apos;t auto-adjust)
            </Label>
            <Switch
              id="reb-notify"
              checked={cfg?.rebalance_notify_only ?? false}
              onCheckedChange={(v) =>
                save({ rebalance_notify_only: Boolean(v) })
              }
              disabled={saving}
            />
          </div>

          <div className="flex items-end gap-3">
            <div className="flex-1">
              <Label htmlFor="drift" className="text-xs uppercase tracking-wider text-muted-foreground">
                Drift threshold (%)
              </Label>
              <Input
                id="drift"
                type="number"
                min={5}
                max={50}
                value={cfg?.rebalance_drift_pct ?? 15}
                onChange={(e) =>
                  save({ rebalance_drift_pct: Number(e.target.value) })
                }
                className="mt-1"
                disabled={saving}
              />
            </div>
            <Button
              variant="outline"
              onClick={onRebalanceTest}
              disabled={testing === "rebalance"}
            >
              {testing === "rebalance" ? (
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Checking...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <PlayCircle className="h-4 w-4" />
                  Check Now
                </span>
              )}
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            Last check: <Clock className="inline h-3 w-3" /> {toLocalTime(data.last_rebalance_check)}
          </p>

          {data.rebalance_actions && data.rebalance_actions.length > 0 && (
            <div className="rounded-xl border border-border bg-muted/30 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Recent rebalance actions
              </p>
              <div className="space-y-1">
                {data.rebalance_actions.slice(-5).map((a, i) => {
                  const rec = a as Record<string, unknown>;
                  const name = String(rec.bot_name ?? "bot");
                  const drift = Number(rec.drift_pct ?? 0);
                  const applied = Boolean(rec.applied);
                  return (
                    <div
                      key={i}
                      className="flex items-center justify-between text-xs"
                    >
                      <span className="text-foreground">{name}</span>
                      <span
                        className={`${applied ? "text-profit" : "text-brand"}`}
                      >
                        drifted {drift.toFixed(1)}% {applied ? "→ applied" : "→ notified"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Weekly AI Re-evaluation */}
      <Card className="border-border/60 bg-card elevated">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Brain className="h-5 w-5 text-brand" />
            Weekly AI Re-evaluation
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Every Sunday at 06:00 UTC, the AI re-analyses markets and alerts you
            if a significantly better strategy is found for your running bots.
          </p>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <Label htmlFor="weekly-en" className="text-sm font-medium">
              Enable weekly re-evaluation
            </Label>
            <Switch
              id="weekly-en"
              checked={cfg?.weekly_reeval_enabled ?? false}
              onCheckedChange={(v) =>
                save({ weekly_reeval_enabled: Boolean(v) })
              }
              disabled={saving}
            />
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Last run: {toLocalTime(data.last_reeval_check)}
          </p>
        </CardContent>
      </Card>

      {/* Daily Digest */}
      <Card className="border-border/60 bg-card elevated">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Mail className="h-5 w-5 text-brand" />
            Daily Performance Digest
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Once a day you&apos;ll get a Telegram message with your 24-hour P&amp;L,
            trade count, and current market regime. Peace of mind without
            checking the app.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="digest-en" className="text-sm font-medium">
              Enable daily digest
            </Label>
            <Switch
              id="digest-en"
              checked={cfg?.digest_enabled ?? false}
              onCheckedChange={(v) =>
                save({ digest_enabled: Boolean(v) })
              }
              disabled={saving}
            />
          </div>

          <div className="flex items-end gap-3">
            <div className="flex-1">
              <Label htmlFor="hour" className="text-xs uppercase tracking-wider text-muted-foreground">
                Send hour (UTC)
              </Label>
              <Input
                id="hour"
                type="number"
                min={0}
                max={23}
                value={cfg?.digest_hour_utc ?? 8}
                onChange={(e) =>
                  save({ digest_hour_utc: Number(e.target.value) })
                }
                className="mt-1"
                disabled={saving}
              />
            </div>
            <Button
              variant="outline"
              onClick={onDigestTest}
              disabled={testing === "digest"}
            >
              {testing === "digest" ? (
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Sending...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <PlayCircle className="h-4 w-4" />
                  Send Test
                </span>
              )}
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            Last sent: {toLocalTime(data.last_digest_sent)}
          </p>
        </CardContent>
      </Card>

      {/* What else runs automatically */}
      <Card className="border-border/60 bg-card elevated">
        <CardHeader>
          <CardTitle className="text-base">Also running for you</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <AutoItem
            title="Market Regime Detector"
            description="Auto-pauses bots in bad markets, resumes when conditions normalize"
            active
          />
          <AutoItem
            title="Daily Database Backups"
            description="SQLite snapshots at 3AM UTC, 30-day rolling retention"
            active
          />
          <AutoItem
            title="Telegram Alerts"
            description="Pings on trades, crashes, regime changes, and rebalance actions"
            active
          />
          <AutoItem
            title="Kill Switch"
            description="One-click emergency stop from the header of every page"
            active
          />
        </CardContent>
      </Card>
    </div>
  );
}

function AutoItem({
  title,
  description,
  active,
}: {
  title: string;
  description: string;
  active: boolean;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/60 bg-muted/20 p-3">
      {active ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-profit" />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
      )}
      <div className="flex-1">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Badge
        className={
          active
            ? "border-profit/20 bg-profit/10 text-profit"
            : "bg-muted text-muted-foreground"
        }
      >
        {active ? "ACTIVE" : "OFF"}
      </Badge>
    </div>
  );
}
