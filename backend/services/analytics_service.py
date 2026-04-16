"""
Analytics Service
------------------
Computes performance metrics for backtests and live trading.

Ported and extended from deep_analysis.py ``compute_metrics``.
"""

import math
import logging
from typing import Any, Dict, List, Union

import numpy as np

logger = logging.getLogger(__name__)


def compute_metrics(
    equity_curve: List[float],
    trades: List[dict],
    investment: float,
    days: float,
    hourly_prices: Union[List[float], np.ndarray],
) -> Dict[str, Any]:
    """Compute comprehensive performance metrics.

    Parameters
    ----------
    equity_curve:
        Portfolio value at each time step (one entry per candle).
    trades:
        List of trade dicts.  Sell trades should contain a ``"profit"``
        key; buy trades need only ``"side": "buy"``.
    investment:
        Initial capital deployed.
    days:
        Duration of the period in calendar days.
    hourly_prices:
        Raw close prices at each time step (used for HODL comparison).

    Returns
    -------
    dict
        A flat dictionary of all computed metrics.
    """
    equity = np.asarray(equity_curve, dtype=np.float64)
    hourly = np.asarray(hourly_prices, dtype=np.float64)
    months = max(days / 30.0, 1.0)

    # ── Basic P&L ──────────────────────────────────────────────────────
    final_value = float(equity[-1]) if len(equity) > 0 else investment
    pnl = final_value - investment
    pnl_pct = (pnl / investment) * 100.0 if investment else 0.0
    monthly_roi = pnl_pct / months
    annual_roi_est = monthly_roi * 12.0

    # ── Trade analysis ─────────────────────────────────────────────────
    sell_trades = [t for t in trades if t.get("profit") is not None]
    buy_trades = [t for t in trades if t.get("side") == "buy"]
    profits = [t["profit"] for t in sell_trades]

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]

    win_rate = (len(wins) / len(profits) * 100.0) if profits else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(abs(np.mean(losses))) if losses else 0.0
    avg_profit_per_trade = float(np.mean(profits)) if profits else 0.0
    max_single_profit = float(max(profits)) if profits else 0.0
    max_single_loss = float(min(profits)) if profits else 0.0

    total_wins = sum(wins) if wins else 0.0
    total_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = (
        (total_wins / total_losses) if total_losses > 0 else float("inf")
    )

    # ── Consecutive wins / losses ──────────────────────────────────────
    max_consec_wins = 0
    max_consec_losses = 0
    curr_wins = 0
    curr_losses = 0
    for p in profits:
        if p > 0:
            curr_wins += 1
            curr_losses = 0
            max_consec_wins = max(max_consec_wins, curr_wins)
        else:
            curr_losses += 1
            curr_wins = 0
            max_consec_losses = max(max_consec_losses, curr_losses)

    # ── Drawdown analysis ──────────────────────────────────────────────
    max_dd = 0.0
    max_dd_pct = 0.0
    max_dd_duration = 0
    peak = equity[0] if len(equity) > 0 else investment
    in_dd = False
    curr_dd_start = 0

    for i, val in enumerate(equity):
        if val > peak:
            peak = val
            if in_dd:
                dd_duration = i - curr_dd_start
                max_dd_duration = max(max_dd_duration, dd_duration)
                in_dd = False
        dd = peak - val
        dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
        if dd > 0 and not in_dd:
            in_dd = True
            curr_dd_start = i
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = dd

    # Close any open drawdown at the end
    if in_dd and len(equity) > 0:
        dd_duration = len(equity) - 1 - curr_dd_start
        max_dd_duration = max(max_dd_duration, dd_duration)

    # ── Risk-adjusted returns (Sharpe / Sortino) ───────────────────────
    sharpe = 0.0
    sortino = 0.0

    if len(equity) > 1:
        returns = np.diff(equity) / equity[:-1]
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

        if len(returns) > 1 and np.std(returns) > 0:
            # Annualised assuming hourly candles (8760 hours / year)
            sharpe = float(
                (np.mean(returns) / np.std(returns)) * np.sqrt(8760)
            )
            downside = returns[returns < 0]
            downside_std = (
                float(np.std(downside)) if len(downside) > 0 else 1e-10
            )
            sortino = float(
                (np.mean(returns) / downside_std) * np.sqrt(8760)
            )

    # ── Calmar ratio ───────────────────────────────────────────────────
    annual_return = pnl_pct * (365.0 / days) if days > 0 else 0.0
    calmar = (
        annual_return / max_dd_pct if max_dd_pct > 0 else float("inf")
    )

    # ── HODL comparison ────────────────────────────────────────────────
    hodl_return = 0.0
    alpha_vs_hodl = 0.0
    if len(hourly) >= 2 and hourly[0] > 0:
        hodl_return = ((hourly[-1] - hourly[0]) / hourly[0]) * 100.0
        alpha_vs_hodl = pnl_pct - hodl_return

    # ── Total fees (summed from trades) ────────────────────────────────
    total_fees = sum(
        t.get("fee", 0.0) for t in trades
    )
    # If individual trade fees aren't recorded, fall back to zero
    # (the caller may provide a pre-computed total_fees separately).

    fee_pct_of_profit = (
        (total_fees / max(total_wins, 0.01)) * 100.0
    )

    return {
        "pnl": round(pnl, 4),
        "pnl_pct": round(pnl_pct, 4),
        "monthly_roi": round(monthly_roi, 4),
        "annual_roi_est": round(annual_roi_est, 4),
        "num_trades": len(trades),
        "num_sells": len(sell_trades),
        "num_buys": len(buy_trades),
        "win_rate": round(win_rate, 2),
        "avg_profit_per_trade": round(avg_profit_per_trade, 6),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else float("inf"),
        "max_single_profit": round(max_single_profit, 6),
        "max_single_loss": round(max_single_loss, 6),
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "max_drawdown_pct": round(max_dd_pct, 4),
        "max_drawdown_usd": round(max_dd, 4),
        "max_dd_duration_hours": max_dd_duration,
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "calmar_ratio": round(calmar, 4) if calmar != float("inf") else float("inf"),
        "total_fees": round(total_fees, 6),
        "fee_pct_of_profit": round(fee_pct_of_profit, 2),
        "hodl_return": round(hodl_return, 4),
        "alpha_vs_hodl": round(alpha_vs_hodl, 4),
    }
