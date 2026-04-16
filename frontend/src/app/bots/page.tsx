"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  Plus,
  Play,
  Square,
  Trash2,
  MoreVertical,
  Bot as BotIcon,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useBots } from "@/hooks/useBots";
import { createBot, startBot, stopBot, deleteBot } from "@/lib/api";
import type { Bot } from "@/types";

const STRATEGY_TYPES = ["Grid", "Hybrid", "Smart", "V3"] as const;
const PAIRS = [
  "BTC/USDT",
  "ETH/USDT",
  "BNB/USDT",
  "SOL/USDT",
  "XRP/USDT",
  "ADA/USDT",
  "DOGE/USDT",
  "AVAX/USDT",
];

function BotCard({
  bot,
  onAction,
}: {
  bot: Bot;
  onAction: () => void;
}) {
  const [actionLoading, setActionLoading] = useState(false);
  const isRunning = bot.status === "running";

  const handleStart = async () => {
    setActionLoading(true);
    try {
      await startBot(bot.id);
      toast.success(`Bot "${bot.name}" started`);
      onAction();
    } catch {
      toast.error("Failed to start bot");
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    try {
      await stopBot(bot.id);
      toast.success(`Bot "${bot.name}" stopped`);
      onAction();
    } catch {
      toast.error("Failed to stop bot");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    setActionLoading(true);
    try {
      await deleteBot(bot.id);
      toast.success(`Bot "${bot.name}" deleted`);
      onAction();
    } catch {
      toast.error("Failed to delete bot");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <Card className="border-border/50 bg-card transition-colors hover:border-border">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                isRunning ? "bg-profit/10" : "bg-muted"
              }`}
            >
              <BotIcon
                className={`h-5 w-5 ${
                  isRunning ? "text-profit" : "text-muted-foreground"
                }`}
              />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">{bot.name}</p>
              <p className="text-xs text-muted-foreground">{bot.config.symbol}</p>
            </div>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger className="flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent">
              <MoreVertical className="h-4 w-4 text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {isRunning ? (
                <DropdownMenuItem onClick={handleStop} disabled={actionLoading}>
                  <Square className="mr-2 h-4 w-4" />
                  Stop Bot
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onClick={handleStart} disabled={actionLoading}>
                  <Play className="mr-2 h-4 w-4" />
                  Start Bot
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={handleDelete}
                disabled={actionLoading}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete Bot
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {bot.type}
          </Badge>
          <Badge
            variant="outline"
            className={`text-xs ${
              isRunning
                ? "border-profit/30 bg-profit/10 text-profit"
                : "border-muted-foreground/30 bg-muted text-muted-foreground"
            }`}
          >
            {isRunning ? "Running" : "Stopped"}
          </Badge>
          {bot.paper && (
            <Badge variant="outline" className="border-chart-3/30 bg-chart-3/10 text-xs text-chart-3">
              Paper
            </Badge>
          )}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-border/50 pt-4">
          <div>
            <p className="text-xs text-muted-foreground">P&L</p>
            <p
              className={`text-lg font-bold ${
                (bot.pnl ?? 0) >= 0 ? "text-profit" : "text-loss"
              }`}
            >
              {(bot.pnl ?? 0) >= 0 ? "+" : ""}$
              {Math.abs(bot.pnl ?? 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </p>
          </div>
          <Button
            variant={isRunning ? "destructive" : "default"}
            size="sm"
            onClick={isRunning ? handleStop : handleStart}
            disabled={actionLoading}
          >
            {isRunning ? (
              <>
                <Square className="mr-1 h-3 w-3" /> Stop
              </>
            ) : (
              <>
                <Play className="mr-1 h-3 w-3" /> Start
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CreateBotDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");
  const [strategyType, setStrategyType] = useState<string>("Grid");
  const [pair, setPair] = useState<string>("BTC/USDT");
  const [investment, setInvestment] = useState("1000");
  const [paperTrading, setPaperTrading] = useState(true);
  const [lowerPrice, setLowerPrice] = useState("");
  const [upperPrice, setUpperPrice] = useState("");
  const [numGrids, setNumGrids] = useState("10");

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error("Please enter a bot name");
      return;
    }
    setLoading(true);
    try {
      await createBot({
        name: name.trim(),
        type: strategyType.toLowerCase() as import("@/types").BotType,
        paper: paperTrading,
        config: {
          symbol: pair,
          total_investment: parseFloat(investment),
          lower_price: lowerPrice ? parseFloat(lowerPrice) : 0,
          upper_price: upperPrice ? parseFloat(upperPrice) : 0,
          num_grids: parseInt(numGrids, 10),
        },
      });
      toast.success(`Bot "${name}" created`);
      setOpen(false);
      resetForm();
      onCreated();
    } catch {
      toast.error("Failed to create bot");
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setName("");
    setStrategyType("Grid");
    setPair("BTC/USDT");
    setInvestment("1000");
    setPaperTrading(true);
    setLowerPrice("");
    setUpperPrice("");
    setNumGrids("10");
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <Plus className="mr-2 h-4 w-4" />
        Create New Bot
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create New Bot</DialogTitle>
          <DialogDescription>
            Configure a new grid trading bot. Set your parameters and start trading.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="bot-name">Bot Name</Label>
            <Input
              id="bot-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Grid Bot"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Strategy Type</Label>
              <Select value={strategyType} onValueChange={(v) => v !== null && setStrategyType(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STRATEGY_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Trading Pair</Label>
              <Select value={pair} onValueChange={(v) => v !== null && setPair(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAIRS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="investment">Investment Amount (USDT)</Label>
            <Input
              id="investment"
              type="number"
              value={investment}
              onChange={(e) => setInvestment(e.target.value)}
              placeholder="1000"
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border/50 p-3">
            <div>
              <p className="text-sm font-medium">Paper Trading</p>
              <p className="text-xs text-muted-foreground">
                Simulate trades without real funds
              </p>
            </div>
            <Switch
              checked={paperTrading}
              onCheckedChange={setPaperTrading}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="lower-price">Lower Price</Label>
              <Input
                id="lower-price"
                type="number"
                value={lowerPrice}
                onChange={(e) => setLowerPrice(e.target.value)}
                placeholder="Auto"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="upper-price">Upper Price</Label>
              <Input
                id="upper-price"
                type="number"
                value={upperPrice}
                onChange={(e) => setUpperPrice(e.target.value)}
                placeholder="Auto"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="num-grids">Grids</Label>
              <Input
                id="num-grids"
                type="number"
                value={numGrids}
                onChange={(e) => setNumGrids(e.target.value)}
                placeholder="10"
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button onClick={handleCreate} disabled={loading}>
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Creating...
              </span>
            ) : (
              "Create Bot"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function BotsPage() {
  const { bots, isLoading, mutate } = useBots();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Bot Management
          </h2>
          <p className="text-sm text-muted-foreground">
            Create, configure, and manage your grid trading bots
          </p>
        </div>
        <CreateBotDialog onCreated={() => mutate()} />
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="border-border/50 bg-card">
              <CardContent className="p-5">
                <div className="animate-pulse space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-muted" />
                    <div className="space-y-2">
                      <div className="h-4 w-24 rounded bg-muted" />
                      <div className="h-3 w-16 rounded bg-muted" />
                    </div>
                  </div>
                  <div className="h-8 w-full rounded bg-muted" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !bots || bots.length === 0 ? (
        <Card className="border-border/50 bg-card">
          <CardContent className="flex flex-col items-center justify-center py-16">
            <BotIcon className="mb-4 h-12 w-12 text-muted-foreground/50" />
            <p className="text-lg font-medium text-foreground">No bots yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Create your first grid trading bot to get started
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {bots.map((bot) => (
            <BotCard key={bot.id} bot={bot} onAction={() => mutate()} />
          ))}
        </div>
      )}
    </div>
  );
}
