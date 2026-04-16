"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Save, Settings } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

function GridConfigForm() {
  const [pair, setPair] = useState("BTC/USDT");
  const [lowerPrice, setLowerPrice] = useState("25000");
  const [upperPrice, setUpperPrice] = useState("35000");
  const [numGrids, setNumGrids] = useState("10");
  const [investment, setInvestment] = useState("10000");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { saveConfig } = await import("@/lib/api");
      await saveConfig("grid", {
        pair,
        lower_price: parseFloat(lowerPrice),
        upper_price: parseFloat(upperPrice),
        num_grids: parseInt(numGrids, 10),
        investment: parseFloat(investment),
      });
      toast.success("Grid configuration saved");
    } catch {
      toast.error("Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
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
        <div className="grid gap-2">
          <Label htmlFor="g-investment">Investment (USDT)</Label>
          <Input
            id="g-investment"
            type="number"
            value={investment}
            onChange={(e) => setInvestment(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="g-lower">Lower Price</Label>
          <Input
            id="g-lower"
            type="number"
            value={lowerPrice}
            onChange={(e) => setLowerPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="g-upper">Upper Price</Label>
          <Input
            id="g-upper"
            type="number"
            value={upperPrice}
            onChange={(e) => setUpperPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="g-grids">Number of Grids</Label>
          <Input
            id="g-grids"
            type="number"
            value={numGrids}
            onChange={(e) => setNumGrids(e.target.value)}
          />
        </div>
      </div>

      <Button onClick={handleSave} disabled={saving}>
        <Save className="mr-2 h-4 w-4" />
        {saving ? "Saving..." : "Save Grid Config"}
      </Button>
    </div>
  );
}

function HybridConfigForm() {
  const [pair, setPair] = useState("BTC/USDT");
  const [lowerPrice, setLowerPrice] = useState("25000");
  const [upperPrice, setUpperPrice] = useState("35000");
  const [numGrids, setNumGrids] = useState("10");
  const [investment, setInvestment] = useState("10000");
  const [rsiPeriod, setRsiPeriod] = useState("14");
  const [overbought, setOverbought] = useState("70");
  const [oversold, setOversold] = useState("30");
  const [trailingStop, setTrailingStop] = useState("2.0");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { saveConfig } = await import("@/lib/api");
      await saveConfig("hybrid", {
        pair,
        lower_price: parseFloat(lowerPrice),
        upper_price: parseFloat(upperPrice),
        num_grids: parseInt(numGrids, 10),
        investment: parseFloat(investment),
        rsi_period: parseInt(rsiPeriod, 10),
        overbought: parseInt(overbought, 10),
        oversold: parseInt(oversold, 10),
        trailing_stop_pct: parseFloat(trailingStop),
      });
      toast.success("Hybrid configuration saved");
    } catch {
      toast.error("Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
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
        <div className="grid gap-2">
          <Label htmlFor="h-investment">Investment (USDT)</Label>
          <Input
            id="h-investment"
            type="number"
            value={investment}
            onChange={(e) => setInvestment(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="h-lower">Lower Price</Label>
          <Input
            id="h-lower"
            type="number"
            value={lowerPrice}
            onChange={(e) => setLowerPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="h-upper">Upper Price</Label>
          <Input
            id="h-upper"
            type="number"
            value={upperPrice}
            onChange={(e) => setUpperPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="h-grids">Number of Grids</Label>
          <Input
            id="h-grids"
            type="number"
            value={numGrids}
            onChange={(e) => setNumGrids(e.target.value)}
          />
        </div>
      </div>

      <Separator />
      <p className="text-sm font-medium text-foreground">RSI Parameters</p>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="h-rsi">RSI Period</Label>
          <Input
            id="h-rsi"
            type="number"
            value={rsiPeriod}
            onChange={(e) => setRsiPeriod(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="h-ob">Overbought Threshold</Label>
          <Input
            id="h-ob"
            type="number"
            value={overbought}
            onChange={(e) => setOverbought(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="h-os">Oversold Threshold</Label>
          <Input
            id="h-os"
            type="number"
            value={oversold}
            onChange={(e) => setOversold(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-2 sm:max-w-xs">
        <Label htmlFor="h-trail">Trailing Stop (%)</Label>
        <Input
          id="h-trail"
          type="number"
          step="0.1"
          value={trailingStop}
          onChange={(e) => setTrailingStop(e.target.value)}
        />
      </div>

      <Button onClick={handleSave} disabled={saving}>
        <Save className="mr-2 h-4 w-4" />
        {saving ? "Saving..." : "Save Hybrid Config"}
      </Button>
    </div>
  );
}

function SmartConfigForm() {
  const [pair, setPair] = useState("BTC/USDT");
  const [lowerPrice, setLowerPrice] = useState("25000");
  const [upperPrice, setUpperPrice] = useState("35000");
  const [numGrids, setNumGrids] = useState("10");
  const [investment, setInvestment] = useState("10000");
  const [atrPeriod, setAtrPeriod] = useState("14");
  const [sensitivity, setSensitivity] = useState("1.5");
  const [trendFilter, setTrendFilter] = useState(true);
  const [volumeFilter, setVolumeFilter] = useState(true);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { saveConfig } = await import("@/lib/api");
      await saveConfig("smart", {
        pair,
        lower_price: parseFloat(lowerPrice),
        upper_price: parseFloat(upperPrice),
        num_grids: parseInt(numGrids, 10),
        investment: parseFloat(investment),
        atr_period: parseInt(atrPeriod, 10),
        sensitivity: parseFloat(sensitivity),
        trend_filter: trendFilter,
        volume_filter: volumeFilter,
      });
      toast.success("Smart configuration saved");
    } catch {
      toast.error("Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
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
        <div className="grid gap-2">
          <Label htmlFor="s-investment">Investment (USDT)</Label>
          <Input
            id="s-investment"
            type="number"
            value={investment}
            onChange={(e) => setInvestment(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="s-lower">Lower Price</Label>
          <Input
            id="s-lower"
            type="number"
            value={lowerPrice}
            onChange={(e) => setLowerPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="s-upper">Upper Price</Label>
          <Input
            id="s-upper"
            type="number"
            value={upperPrice}
            onChange={(e) => setUpperPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="s-grids">Number of Grids</Label>
          <Input
            id="s-grids"
            type="number"
            value={numGrids}
            onChange={(e) => setNumGrids(e.target.value)}
          />
        </div>
      </div>

      <Separator />
      <p className="text-sm font-medium text-foreground">
        Volatility Parameters
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="s-atr">ATR Period</Label>
          <Input
            id="s-atr"
            type="number"
            value={atrPeriod}
            onChange={(e) => setAtrPeriod(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="s-sens">Sensitivity</Label>
          <Input
            id="s-sens"
            type="number"
            step="0.1"
            value={sensitivity}
            onChange={(e) => setSensitivity(e.target.value)}
          />
        </div>
      </div>

      <Separator />
      <p className="text-sm font-medium text-foreground">Filters</p>

      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-lg border border-border/50 p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Trend Filter</p>
            <p className="text-xs text-muted-foreground">
              Only trade in the direction of the trend
            </p>
          </div>
          <Switch checked={trendFilter} onCheckedChange={setTrendFilter} />
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border/50 p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Volume Filter</p>
            <p className="text-xs text-muted-foreground">
              Require sufficient volume before placing orders
            </p>
          </div>
          <Switch checked={volumeFilter} onCheckedChange={setVolumeFilter} />
        </div>
      </div>

      <Button onClick={handleSave} disabled={saving}>
        <Save className="mr-2 h-4 w-4" />
        {saving ? "Saving..." : "Save Smart Config"}
      </Button>
    </div>
  );
}

function V3ConfigForm() {
  const [pair, setPair] = useState("BTC/USDT");
  const [lowerPrice, setLowerPrice] = useState("25000");
  const [upperPrice, setUpperPrice] = useState("35000");
  const [numGrids, setNumGrids] = useState("10");
  const [investment, setInvestment] = useState("10000");

  // 10 layers
  const [volatilityAdj, setVolatilityAdj] = useState(true);
  const [volAtrPeriod, setVolAtrPeriod] = useState("14");
  const [volMultiplier, setVolMultiplier] = useState("1.5");

  const [trendFollow, setTrendFollow] = useState(true);
  const [trendEmaPeriod, setTrendEmaPeriod] = useState("50");

  const [meanReversion, setMeanReversion] = useState(true);
  const [mrBbPeriod, setMrBbPeriod] = useState("20");
  const [mrBbStddev, setMrBbStddev] = useState("2.0");

  const [momentumFilter, setMomentumFilter] = useState(true);
  const [momRsiPeriod, setMomRsiPeriod] = useState("14");

  const [volumeProfile, setVolumeProfile] = useState(true);
  const [vpLookback, setVpLookback] = useState("24");

  const [dynamicSpacing, setDynamicSpacing] = useState(true);
  const [dsMethod, setDsMethod] = useState("geometric");

  const [riskManagement, setRiskManagement] = useState(true);
  const [rmMaxDrawdown, setRmMaxDrawdown] = useState("15");
  const [rmPositionLimit, setRmPositionLimit] = useState("50");

  const [orderOptimization, setOrderOptimization] = useState(true);
  const [ooSlippage, setOoSlippage] = useState("0.1");

  const [trailingProfit, setTrailingProfit] = useState(true);
  const [tpActivation, setTpActivation] = useState("2.0");
  const [tpCallback, setTpCallback] = useState("0.5");

  const [antiManipulation, setAntiManipulation] = useState(false);
  const [amSpoofDetect, setAmSpoofDetect] = useState(true);

  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { saveConfig } = await import("@/lib/api");
      await saveConfig("v3", {
        pair,
        lower_price: parseFloat(lowerPrice),
        upper_price: parseFloat(upperPrice),
        num_grids: parseInt(numGrids, 10),
        investment: parseFloat(investment),
        layers: {
          volatility_adjustment: {
            enabled: volatilityAdj,
            atr_period: parseInt(volAtrPeriod, 10),
            multiplier: parseFloat(volMultiplier),
          },
          trend_following: {
            enabled: trendFollow,
            ema_period: parseInt(trendEmaPeriod, 10),
          },
          mean_reversion: {
            enabled: meanReversion,
            bb_period: parseInt(mrBbPeriod, 10),
            bb_stddev: parseFloat(mrBbStddev),
          },
          momentum_filter: {
            enabled: momentumFilter,
            rsi_period: parseInt(momRsiPeriod, 10),
          },
          volume_profile: {
            enabled: volumeProfile,
            lookback_hours: parseInt(vpLookback, 10),
          },
          dynamic_spacing: {
            enabled: dynamicSpacing,
            method: dsMethod,
          },
          risk_management: {
            enabled: riskManagement,
            max_drawdown_pct: parseFloat(rmMaxDrawdown),
            position_limit_pct: parseFloat(rmPositionLimit),
          },
          order_optimization: {
            enabled: orderOptimization,
            max_slippage_pct: parseFloat(ooSlippage),
          },
          trailing_profit: {
            enabled: trailingProfit,
            activation_pct: parseFloat(tpActivation),
            callback_pct: parseFloat(tpCallback),
          },
          anti_manipulation: {
            enabled: antiManipulation,
            spoof_detection: amSpoofDetect,
          },
        },
      });
      toast.success("V3 configuration saved");
    } catch {
      toast.error("Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
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
        <div className="grid gap-2">
          <Label htmlFor="v3-investment">Investment (USDT)</Label>
          <Input
            id="v3-investment"
            type="number"
            value={investment}
            onChange={(e) => setInvestment(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="v3-lower">Lower Price</Label>
          <Input
            id="v3-lower"
            type="number"
            value={lowerPrice}
            onChange={(e) => setLowerPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="v3-upper">Upper Price</Label>
          <Input
            id="v3-upper"
            type="number"
            value={upperPrice}
            onChange={(e) => setUpperPrice(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="v3-grids">Number of Grids</Label>
          <Input
            id="v3-grids"
            type="number"
            value={numGrids}
            onChange={(e) => setNumGrids(e.target.value)}
          />
        </div>
      </div>

      <Separator />
      <p className="text-base font-semibold text-foreground">
        Strategy Layers
      </p>

      {/* Layer 1: Volatility Adjustment */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              1. Volatility Adjustment
            </p>
            <p className="text-xs text-muted-foreground">
              Dynamically adjust grid spacing based on ATR
            </p>
          </div>
          <Switch checked={volatilityAdj} onCheckedChange={setVolatilityAdj} />
        </div>
        {volatilityAdj && (
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="grid gap-1">
              <Label className="text-xs">ATR Period</Label>
              <Input type="number" value={volAtrPeriod} onChange={(e) => setVolAtrPeriod(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">Multiplier</Label>
              <Input type="number" step="0.1" value={volMultiplier} onChange={(e) => setVolMultiplier(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 2: Trend Following */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              2. Trend Following
            </p>
            <p className="text-xs text-muted-foreground">
              Bias grid placement based on EMA direction
            </p>
          </div>
          <Switch checked={trendFollow} onCheckedChange={setTrendFollow} />
        </div>
        {trendFollow && (
          <div className="grid grid-cols-1 gap-3 pt-2 sm:max-w-xs">
            <div className="grid gap-1">
              <Label className="text-xs">EMA Period</Label>
              <Input type="number" value={trendEmaPeriod} onChange={(e) => setTrendEmaPeriod(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 3: Mean Reversion */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              3. Mean Reversion
            </p>
            <p className="text-xs text-muted-foreground">
              Use Bollinger Bands for entry/exit signals
            </p>
          </div>
          <Switch checked={meanReversion} onCheckedChange={setMeanReversion} />
        </div>
        {meanReversion && (
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="grid gap-1">
              <Label className="text-xs">BB Period</Label>
              <Input type="number" value={mrBbPeriod} onChange={(e) => setMrBbPeriod(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">BB Std Dev</Label>
              <Input type="number" step="0.1" value={mrBbStddev} onChange={(e) => setMrBbStddev(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 4: Momentum Filter */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              4. Momentum Filter
            </p>
            <p className="text-xs text-muted-foreground">
              RSI-based momentum gating for trade execution
            </p>
          </div>
          <Switch checked={momentumFilter} onCheckedChange={setMomentumFilter} />
        </div>
        {momentumFilter && (
          <div className="grid grid-cols-1 gap-3 pt-2 sm:max-w-xs">
            <div className="grid gap-1">
              <Label className="text-xs">RSI Period</Label>
              <Input type="number" value={momRsiPeriod} onChange={(e) => setMomRsiPeriod(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 5: Volume Profile */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              5. Volume Profile
            </p>
            <p className="text-xs text-muted-foreground">
              Place grids at high-volume price levels
            </p>
          </div>
          <Switch checked={volumeProfile} onCheckedChange={setVolumeProfile} />
        </div>
        {volumeProfile && (
          <div className="grid grid-cols-1 gap-3 pt-2 sm:max-w-xs">
            <div className="grid gap-1">
              <Label className="text-xs">Lookback (hours)</Label>
              <Input type="number" value={vpLookback} onChange={(e) => setVpLookback(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 6: Dynamic Spacing */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              6. Dynamic Spacing
            </p>
            <p className="text-xs text-muted-foreground">
              Use geometric or adaptive grid spacing
            </p>
          </div>
          <Switch checked={dynamicSpacing} onCheckedChange={setDynamicSpacing} />
        </div>
        {dynamicSpacing && (
          <div className="grid grid-cols-1 gap-3 pt-2 sm:max-w-xs">
            <div className="grid gap-1">
              <Label className="text-xs">Method</Label>
              <Select value={dsMethod} onValueChange={(v) => v !== null && setDsMethod(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="geometric">Geometric</SelectItem>
                  <SelectItem value="arithmetic">Arithmetic</SelectItem>
                  <SelectItem value="adaptive">Adaptive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        )}
      </div>

      {/* Layer 7: Risk Management */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              7. Risk Management
            </p>
            <p className="text-xs text-muted-foreground">
              Auto-stop on max drawdown or position limits
            </p>
          </div>
          <Switch checked={riskManagement} onCheckedChange={setRiskManagement} />
        </div>
        {riskManagement && (
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="grid gap-1">
              <Label className="text-xs">Max Drawdown (%)</Label>
              <Input type="number" value={rmMaxDrawdown} onChange={(e) => setRmMaxDrawdown(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">Position Limit (%)</Label>
              <Input type="number" value={rmPositionLimit} onChange={(e) => setRmPositionLimit(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 8: Order Optimization */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              8. Order Optimization
            </p>
            <p className="text-xs text-muted-foreground">
              Minimize slippage with smart order placement
            </p>
          </div>
          <Switch checked={orderOptimization} onCheckedChange={setOrderOptimization} />
        </div>
        {orderOptimization && (
          <div className="grid grid-cols-1 gap-3 pt-2 sm:max-w-xs">
            <div className="grid gap-1">
              <Label className="text-xs">Max Slippage (%)</Label>
              <Input type="number" step="0.01" value={ooSlippage} onChange={(e) => setOoSlippage(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 9: Trailing Profit */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              9. Trailing Profit
            </p>
            <p className="text-xs text-muted-foreground">
              Lock in profits with trailing stop mechanism
            </p>
          </div>
          <Switch checked={trailingProfit} onCheckedChange={setTrailingProfit} />
        </div>
        {trailingProfit && (
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div className="grid gap-1">
              <Label className="text-xs">Activation (%)</Label>
              <Input type="number" step="0.1" value={tpActivation} onChange={(e) => setTpActivation(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">Callback (%)</Label>
              <Input type="number" step="0.1" value={tpCallback} onChange={(e) => setTpCallback(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Layer 10: Anti-Manipulation */}
      <div className="rounded-lg border border-border/50 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">
              10. Anti-Manipulation
            </p>
            <p className="text-xs text-muted-foreground">
              Detect and avoid spoofing and wash trading
            </p>
          </div>
          <Switch checked={antiManipulation} onCheckedChange={setAntiManipulation} />
        </div>
        {antiManipulation && (
          <div className="flex items-center justify-between pt-2">
            <p className="text-xs text-muted-foreground">
              Spoof Detection
            </p>
            <Switch checked={amSpoofDetect} onCheckedChange={setAmSpoofDetect} />
          </div>
        )}
      </div>

      <Button onClick={handleSave} disabled={saving}>
        <Save className="mr-2 h-4 w-4" />
        {saving ? "Saving..." : "Save V3 Config"}
      </Button>
    </div>
  );
}

export default function ConfigPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Configuration
        </h2>
        <p className="text-sm text-muted-foreground">
          Configure default parameters for each strategy type
        </p>
      </div>

      <Card className="border-border/50 bg-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings className="h-4 w-4 text-primary" />
            Strategy Configuration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="grid">
            <TabsList className="mb-6">
              <TabsTrigger value="grid">Grid</TabsTrigger>
              <TabsTrigger value="hybrid">Hybrid</TabsTrigger>
              <TabsTrigger value="smart">Smart</TabsTrigger>
              <TabsTrigger value="v3">V3</TabsTrigger>
            </TabsList>

            <TabsContent value="grid">
              <GridConfigForm />
            </TabsContent>
            <TabsContent value="hybrid">
              <HybridConfigForm />
            </TabsContent>
            <TabsContent value="smart">
              <SmartConfigForm />
            </TabsContent>
            <TabsContent value="v3">
              <V3ConfigForm />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
