"""
All Trading Strategies
-----------------------
1. Grid          — buy/sell at fixed levels (what we have)
2. DCA           — buy on schedule, sell when in profit
3. Mean Reversion — buy dips, sell rips (Bollinger/Z-score)
4. Momentum      — follow the trend, ride breakouts
5. Combined      — auto-switch based on market regime
"""

from collections import deque
import math


# ──────────────────────────────────────────────
#  Shared Indicators
# ──────────────────────────────────────────────

def calc_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def calc_std(prices, period):
    if len(prices) < period:
        return None
    mean = sum(prices[-period:]) / period
    variance = sum((p - mean) ** 2 for p in prices[-period:]) / period
    return variance ** 0.5

def calc_bollinger(prices, period=20, num_std=2.0):
    sma = calc_sma(prices, period)
    std = calc_std(prices, period)
    if sma is None or std is None or std == 0:
        return None
    return (sma - num_std * std, sma, sma + num_std * std)

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_z_score(prices, period=20):
    """How many standard deviations from mean."""
    if len(prices) < period:
        return 0
    mean = sum(prices[-period:]) / period
    std = calc_std(prices, period)
    if std is None or std == 0:
        return 0
    return (prices[-1] - mean) / std

def calc_atr(highs, lows, closes, period=14):
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

def detect_regime(closes, period=20):
    """Detect market regime: 'trending', 'mean_reverting', or 'neutral'.
    Uses efficiency ratio (direction / volatility).
    """
    if len(closes) < period + 1:
        return "neutral"
    direction = abs(closes[-1] - closes[-period])
    volatility = sum(abs(closes[i] - closes[i-1]) for i in range(-period, 0))
    if volatility == 0:
        return "neutral"
    efficiency = direction / volatility
    if efficiency > 0.4:
        return "trending"
    elif efficiency < 0.2:
        return "mean_reverting"
    return "neutral"


# ──────────────────────────────────────────────
#  Strategy 1: GRID (simplified for comparison)
# ──────────────────────────────────────────────

class GridStrategy:
    def __init__(self, lower, upper, num_grids, investment):
        self.lower = lower
        self.upper = upper
        self.num_grids = num_grids
        self.investment = investment
        self.fee_rate = 0.00075  # with BNB discount

        self.step = (upper - lower) / num_grids
        self.grid_levels = [round(lower + i * self.step, 2) for i in range(num_grids + 1)]
        self.order_size = investment / num_grids / ((lower + upper) / 2)

        self.balance_usdt = investment
        self.balance_coin = 0.0
        self.buy_orders = {}
        self.sell_orders = {}
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.num_trades = 0
        self.trades = []
        self.initialized = False

    def init(self, first_price):
        for lvl in self.grid_levels:
            if lvl < first_price:
                self.buy_orders[lvl] = self.order_size
            elif lvl > first_price:
                self.sell_orders[lvl] = self.order_size
        self.initialized = True

    def update(self, timestamp, high, low, close, volume):
        if not self.initialized:
            self.init(close)
            return

        # Buy fills
        filled = []
        for lvl, amt in list(self.buy_orders.items()):
            if low <= lvl:
                cost = amt * lvl
                fee = cost * self.fee_rate
                if self.balance_usdt >= cost + fee:
                    self.balance_usdt -= cost + fee
                    self.balance_coin += amt
                    self.total_fees += fee
                    self.num_trades += 1
                    filled.append(lvl)
                    self.trades.append({"time": timestamp, "side": "buy", "price": lvl, "amount": amt})
                    self.sell_orders[round(lvl + self.step, 2)] = amt
        for lvl in filled:
            del self.buy_orders[lvl]

        # Sell fills
        filled = []
        for lvl, amt in list(self.sell_orders.items()):
            if high >= lvl:
                if self.balance_coin >= amt:
                    revenue = amt * lvl
                    fee = revenue * self.fee_rate
                    self.balance_usdt += revenue - fee
                    self.balance_coin -= amt
                    self.total_fees += fee
                    profit = amt * self.step * (1 - self.fee_rate * 2)
                    self.total_profit += profit
                    self.num_trades += 1
                    filled.append(lvl)
                    self.trades.append({"time": timestamp, "side": "sell", "price": lvl, "amount": amt, "profit": profit})
                    self.buy_orders[round(lvl - self.step, 2)] = amt
        for lvl in filled:
            del self.sell_orders[lvl]

    def value(self, current_price):
        return self.balance_usdt + self.balance_coin * current_price


# ──────────────────────────────────────────────
#  Strategy 2: DCA
# ──────────────────────────────────────────────

class DCAStrategy:
    def __init__(self, investment, buy_interval_hours=4, take_profit_pct=3.0, chunk_pct=2.0):
        self.investment = investment
        self.fee_rate = 0.00075
        self.buy_interval = buy_interval_hours
        self.take_profit_pct = take_profit_pct
        self.chunk = investment * (chunk_pct / 100)  # buy this much each interval

        self.balance_usdt = investment
        self.balance_coin = 0.0
        self.total_cost = 0.0  # total spent buying
        self.avg_price = 0.0
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.num_trades = 0
        self.trades = []
        self.hours_since_buy = 0

    def update(self, timestamp, high, low, close, volume):
        self.hours_since_buy += 1

        # DCA buy on schedule
        if self.hours_since_buy >= self.buy_interval and self.balance_usdt >= self.chunk:
            amount = self.chunk / close
            fee = self.chunk * self.fee_rate
            self.balance_usdt -= self.chunk + fee
            self.balance_coin += amount
            self.total_cost += self.chunk
            self.total_fees += fee
            self.num_trades += 1
            self.hours_since_buy = 0

            # Update average price
            if self.balance_coin > 0:
                self.avg_price = self.total_cost / self.balance_coin

            self.trades.append({"time": timestamp, "side": "buy", "price": close, "amount": amount})

        # Take profit: sell portion when price is X% above average
        if self.balance_coin > 0 and self.avg_price > 0:
            profit_pct = (close - self.avg_price) / self.avg_price * 100
            if profit_pct >= self.take_profit_pct:
                # Sell 50% of position
                sell_amount = self.balance_coin * 0.5
                revenue = sell_amount * close
                fee = revenue * self.fee_rate
                profit = (close - self.avg_price) * sell_amount
                self.balance_usdt += revenue - fee
                self.balance_coin -= sell_amount
                self.total_cost = self.balance_coin * self.avg_price  # adjust cost basis
                self.total_profit += profit
                self.total_fees += fee
                self.num_trades += 1
                self.trades.append({"time": timestamp, "side": "sell", "price": close, "amount": sell_amount, "profit": profit})

    def value(self, current_price):
        return self.balance_usdt + self.balance_coin * current_price


# ──────────────────────────────────────────────
#  Strategy 3: MEAN REVERSION
# ──────────────────────────────────────────────

class MeanReversionStrategy:
    def __init__(self, investment, bb_period=20, bb_std=2.0, z_entry=2.0, z_exit=0.5, position_pct=10.0):
        self.investment = investment
        self.fee_rate = 0.00075
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.z_entry = z_entry      # enter when Z-score exceeds this
        self.z_exit = z_exit        # exit when Z-score returns to this
        self.position_pct = position_pct / 100  # % of balance per trade

        self.balance_usdt = investment
        self.balance_coin = 0.0
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.num_trades = 0
        self.trades = []
        self.closes = deque(maxlen=200)
        self.entry_price = 0
        self.in_position = False
        self.position_side = None  # 'long' or 'short_proxy' (sell existing)

    def update(self, timestamp, high, low, close, volume):
        self.closes.append(close)
        if len(self.closes) < self.bb_period:
            return

        z = calc_z_score(list(self.closes), self.bb_period)
        bb = calc_bollinger(list(self.closes), self.bb_period, self.bb_std)
        if bb is None:
            return

        bb_lower, bb_mid, bb_upper = bb

        if not self.in_position:
            # BUY: price far below mean (oversold)
            if z <= -self.z_entry and low <= bb_lower:
                trade_usdt = self.balance_usdt * self.position_pct
                if trade_usdt > 1:
                    amount = trade_usdt / close
                    fee = trade_usdt * self.fee_rate
                    self.balance_usdt -= trade_usdt + fee
                    self.balance_coin += amount
                    self.total_fees += fee
                    self.num_trades += 1
                    self.entry_price = close
                    self.in_position = True
                    self.position_side = "long"
                    self.trades.append({"time": timestamp, "side": "buy", "price": close, "amount": amount})

            # SELL: price far above mean (overbought) — sell if we have coins
            elif z >= self.z_entry and high >= bb_upper and self.balance_coin > 0:
                sell_amt = self.balance_coin * self.position_pct
                if sell_amt * close > 1:
                    revenue = sell_amt * close
                    fee = revenue * self.fee_rate
                    self.balance_usdt += revenue - fee
                    self.balance_coin -= sell_amt
                    self.total_fees += fee
                    self.num_trades += 1
                    self.trades.append({"time": timestamp, "side": "sell", "price": close, "amount": sell_amt})

        else:
            # Exit long: price returned to mean
            if self.position_side == "long" and abs(z) <= self.z_exit:
                if self.balance_coin > 0:
                    sell_amt = self.balance_coin
                    revenue = sell_amt * close
                    fee = revenue * self.fee_rate
                    profit = (close - self.entry_price) * sell_amt
                    self.balance_usdt += revenue - fee
                    self.balance_coin -= sell_amt
                    self.total_profit += profit
                    self.total_fees += fee
                    self.num_trades += 1
                    self.in_position = False
                    self.trades.append({"time": timestamp, "side": "sell", "price": close, "amount": sell_amt, "profit": profit})

    def value(self, current_price):
        return self.balance_usdt + self.balance_coin * current_price


# ──────────────────────────────────────────────
#  Strategy 4: MOMENTUM / TREND FOLLOWING
# ──────────────────────────────────────────────

class MomentumStrategy:
    def __init__(self, investment, fast_ema=12, slow_ema=26, atr_period=14,
                 atr_stop_mult=2.0, position_pct=30.0):
        self.investment = investment
        self.fee_rate = 0.00075
        self.fast_period = fast_ema
        self.slow_period = slow_ema
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.position_pct = position_pct / 100

        self.balance_usdt = investment
        self.balance_coin = 0.0
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.num_trades = 0
        self.trades = []

        self.closes = deque(maxlen=200)
        self.highs = deque(maxlen=200)
        self.lows = deque(maxlen=200)

        self.in_position = False
        self.entry_price = 0
        self.stop_loss = 0
        self.trailing_high = 0

    def update(self, timestamp, high, low, close, volume):
        self.closes.append(close)
        self.highs.append(high)
        self.lows.append(low)

        if len(self.closes) < self.slow_period + 1:
            return

        fast_ema = calc_ema(list(self.closes), self.fast_period)
        slow_ema = calc_ema(list(self.closes), self.slow_period)
        atr = calc_atr(list(self.highs), list(self.lows), list(self.closes), self.atr_period)

        if fast_ema is None or slow_ema is None or atr is None:
            return

        rsi = calc_rsi(list(self.closes), 14)

        if not self.in_position:
            # BUY signal: fast EMA crosses above slow + RSI not overbought
            if fast_ema > slow_ema and rsi < 70:
                trade_usdt = self.balance_usdt * self.position_pct
                if trade_usdt > 1:
                    amount = trade_usdt / close
                    fee = trade_usdt * self.fee_rate
                    self.balance_usdt -= trade_usdt + fee
                    self.balance_coin += amount
                    self.total_fees += fee
                    self.num_trades += 1
                    self.entry_price = close
                    self.stop_loss = close - atr * self.atr_stop_mult
                    self.trailing_high = close
                    self.in_position = True
                    self.trades.append({"time": timestamp, "side": "buy", "price": close, "amount": amount})

        else:
            # Update trailing stop
            if close > self.trailing_high:
                self.trailing_high = close
                self.stop_loss = close - atr * self.atr_stop_mult

            # EXIT: trailing stop hit OR fast crosses below slow
            should_exit = False
            if low <= self.stop_loss:
                should_exit = True
            elif fast_ema < slow_ema and rsi > 30:
                should_exit = True

            if should_exit and self.balance_coin > 0:
                sell_amt = self.balance_coin
                exit_price = max(low, self.stop_loss) if low <= self.stop_loss else close
                revenue = sell_amt * exit_price
                fee = revenue * self.fee_rate
                profit = (exit_price - self.entry_price) * sell_amt
                self.balance_usdt += revenue - fee
                self.balance_coin -= sell_amt
                self.total_profit += profit
                self.total_fees += fee
                self.num_trades += 1
                self.in_position = False
                self.trades.append({"time": timestamp, "side": "sell", "price": exit_price, "amount": sell_amt, "profit": profit})

    def value(self, current_price):
        return self.balance_usdt + self.balance_coin * current_price


# ──────────────────────────────────────────────
#  Strategy 5: COMBINED (auto-switches)
# ──────────────────────────────────────────────

class CombinedStrategy:
    """Runs all strategies but allocates capital based on market regime."""

    def __init__(self, investment, grid_lower, grid_upper, grid_num=10):
        self.investment = investment

        # Split capital: allocate to each strategy
        self.grid_alloc = 0.35
        self.dca_alloc = 0.20
        self.mr_alloc = 0.20
        self.mom_alloc = 0.25

        self.grid = GridStrategy(grid_lower, grid_upper, grid_num,
                                 investment * self.grid_alloc)
        self.dca = DCAStrategy(investment * self.dca_alloc,
                               buy_interval_hours=6, take_profit_pct=3.0, chunk_pct=1.5)
        self.mr = MeanReversionStrategy(investment * self.mr_alloc,
                                        bb_period=20, z_entry=1.8, z_exit=0.3, position_pct=15)
        self.mom = MomentumStrategy(investment * self.mom_alloc,
                                    fast_ema=12, slow_ema=26, position_pct=40)

        self.closes = deque(maxlen=100)
        self.regime = "neutral"
        self.regime_hours = 0

        # Active flags — all start active
        self.grid_active = True
        self.dca_active = True
        self.mr_active = True
        self.mom_active = True

    def update(self, timestamp, high, low, close, volume):
        self.closes.append(close)
        self.regime_hours += 1

        # Detect regime every 4 hours
        if self.regime_hours >= 4 and len(self.closes) >= 25:
            self.regime = detect_regime(list(self.closes), 20)
            self.regime_hours = 0

            # Adjust which strategies are active
            if self.regime == "trending":
                self.grid_active = False     # grid loses in trends
                self.mr_active = False       # mean reversion loses in trends
                self.mom_active = True       # momentum shines
                self.dca_active = True       # DCA always runs
            elif self.regime == "mean_reverting":
                self.grid_active = True      # grid loves chop
                self.mr_active = True        # mean reversion loves chop
                self.mom_active = False      # momentum gets whipsawed
                self.dca_active = True
            else:  # neutral
                self.grid_active = True
                self.mr_active = True
                self.mom_active = True
                self.dca_active = True

        # Run active strategies
        if self.grid_active:
            self.grid.update(timestamp, high, low, close, volume)
        if self.dca_active:
            self.dca.update(timestamp, high, low, close, volume)
        if self.mr_active:
            self.mr.update(timestamp, high, low, close, volume)
        if self.mom_active:
            self.mom.update(timestamp, high, low, close, volume)

    def value(self, current_price):
        return (self.grid.value(current_price) +
                self.dca.value(current_price) +
                self.mr.value(current_price) +
                self.mom.value(current_price))

    @property
    def total_profit(self):
        return self.grid.total_profit + self.dca.total_profit + self.mr.total_profit + self.mom.total_profit

    @property
    def total_fees(self):
        return self.grid.total_fees + self.dca.total_fees + self.mr.total_fees + self.mom.total_fees

    @property
    def num_trades(self):
        return self.grid.num_trades + self.dca.num_trades + self.mr.num_trades + self.mom.num_trades

    @property
    def trades(self):
        all_t = []
        for s, name in [(self.grid, "grid"), (self.dca, "dca"), (self.mr, "mr"), (self.mom, "mom")]:
            for t in s.trades:
                t["strategy"] = name
                all_t.append(t)
        return sorted(all_t, key=lambda x: x.get("time", ""))
