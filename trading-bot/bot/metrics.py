"""Kennzahlen zur Bewertung einer Strategie."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, equity: pd.Series) -> dict:
    start, end = float(equity.iloc[0]), float(equity.iloc[-1])
    if len(trades):
        start = end - float(trades["pnl"].sum())
    peak = equity.cummax()
    max_dd = float(((peak - equity) / peak).max() * 100) if len(equity) else 0.0

    daily = equity.resample("1D").last().dropna()
    rets = daily.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if len(rets) > 2 and rets.std() > 0 else 0.0

    n = len(trades)
    wins = trades[trades["pnl"] > 0]["pnl"] if n else pd.Series(dtype=float)
    losses = trades[trades["pnl"] <= 0]["pnl"] if n else pd.Series(dtype=float)
    gross_loss = -losses.sum()
    if gross_loss > 0:
        pf = float(wins.sum() / gross_loss)
    else:
        pf = float("inf") if len(wins) else 0.0

    return {
        "start_balance": round(start, 2),
        "end_balance": round(end, 2),
        "return_pct": round((end / start - 1) * 100, 2) if start else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "trades": n,
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else 0.0,
        "profit_factor": round(pf, 2) if np.isfinite(pf) else pf,
        "avg_trade": round(float(trades["pnl"].mean()), 2) if n else 0.0,
    }


def score(m: dict, min_trades: int) -> float:
    """Eine Zahl für "wie gut": Sharpe, bestraft durch Drawdown. Zu wenige Trades = ungültig."""
    if m["trades"] < min_trades:
        return -math.inf
    return m["sharpe"] - m["max_drawdown_pct"] / 20


def format_metrics(m: dict) -> str:
    labels = {
        "start_balance": "Startkapital",
        "end_balance": "Endkapital",
        "return_pct": "Rendite %",
        "max_drawdown_pct": "Max. Drawdown %",
        "sharpe": "Sharpe Ratio",
        "trades": "Anzahl Trades",
        "win_rate_pct": "Trefferquote %",
        "profit_factor": "Profit-Faktor",
        "avg_trade": "Ø Gewinn/Trade",
    }
    return "\n".join(f"  {labels[k]:<18} {v}" for k, v in m.items() if k in labels)
