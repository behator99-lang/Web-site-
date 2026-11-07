"""Handelsstrategien.

Jede Strategie bekommt OHLC-Daten und liefert pro Kerze:
  signal   +1 = Long-Einstieg, -1 = Short-Einstieg, 0 = nichts tun
  sl_dist  Abstand Stop-Loss in USD (Preis-Einheiten)
  tp_dist  Abstand Take-Profit in USD

Ein Signal entsteht am SCHLUSS einer Kerze und wird erst zur Eröffnung der
nächsten Kerze ausgeführt. So kann die Strategie nicht "in die Zukunft schauen".
"""
from __future__ import annotations

from itertools import product
from typing import Callable

import numpy as np
import pandas as pd

from .indicators import atr, donchian, ema, rsi


def _finish(df: pd.DataFrame, long_: pd.Series, short_: pd.Series, p: dict) -> pd.DataFrame:
    a = atr(df, p.get("atr_period", 14))
    out = pd.DataFrame(index=df.index)
    out["signal"] = np.where(long_, 1, np.where(short_, -1, 0))
    out["sl_dist"] = a * p.get("sl_atr", 2.0)
    out["tp_dist"] = a * p.get("tp_atr", 3.0)
    out.loc[a.isna(), "signal"] = 0
    return out


def ema_trend(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Trendfolge: schneller EMA kreuzt langsamen EMA."""
    fast, slow = ema(df["close"], p["fast"]), ema(df["close"], p["slow"])
    above = fast > slow
    prev = above.shift(1, fill_value=False)
    valid = slow.notna() & slow.shift(1).notna()
    return _finish(df, valid & above & ~prev, valid & ~above & prev, p)


def donchian_breakout(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Ausbruch über das Hoch / unter das Tief der letzten N Kerzen, nur in Trendrichtung."""
    upper, lower = donchian(df, p["channel"])
    trend = ema(df["close"], p["trend"])
    close, prev_close = df["close"], df["close"].shift(1)
    long_ = (close > upper) & (prev_close <= upper.shift(1)) & (close > trend)
    short_ = (close < lower) & (prev_close >= lower.shift(1)) & (close < trend)
    return _finish(df, long_.fillna(False), short_.fillna(False), p)


def rsi_reversion(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Rücksetzer im Trend kaufen: RSI dreht aus überverkauft/überkauft zurück."""
    r = rsi(df["close"], p["rsi_period"])
    trend = ema(df["close"], p["trend"])
    lo, hi = p["oversold"], 100 - p["oversold"]
    long_ = (r > lo) & (r.shift(1) <= lo) & (df["close"] > trend)
    short_ = (r < hi) & (r.shift(1) >= hi) & (df["close"] < trend)
    return _finish(df, long_.fillna(False), short_.fillna(False), p)


STRATEGIES: dict[str, Callable[[pd.DataFrame, dict], pd.DataFrame]] = {
    "ema_trend": ema_trend,
    "donchian_breakout": donchian_breakout,
    "rsi_reversion": rsi_reversion,
}

# Suchraum für die Optimierung. Bewusst klein gehalten: je mehr Kombinationen,
# desto größer die Gefahr, zufällig gute Parameter zu finden (Overfitting).
PARAM_GRIDS: dict[str, dict[str, list]] = {
    "ema_trend": {
        "fast": [10, 20, 50],
        "slow": [100, 200],
        "sl_atr": [1.5, 2.5],
        "tp_atr": [2.0, 4.0],
    },
    "donchian_breakout": {
        "channel": [20, 55],
        "trend": [100, 200],
        "sl_atr": [1.5, 2.5],
        "tp_atr": [2.0, 4.0],
    },
    "rsi_reversion": {
        "rsi_period": [7, 14],
        "oversold": [25, 30],
        "trend": [100, 200],
        "sl_atr": [1.5, 2.5],
        "tp_atr": [1.5, 3.0],
    },
}


def get_strategy(name: str) -> Callable[[pd.DataFrame, dict], pd.DataFrame]:
    if name not in STRATEGIES:
        raise KeyError(f"Unbekannte Strategie {name!r}. Verfügbar: {', '.join(STRATEGIES)}")
    return STRATEGIES[name]


def iter_params(name: str):
    grid = PARAM_GRIDS[name]
    keys = list(grid)
    for values in product(*(grid[k] for k in keys)):
        p = dict(zip(keys, values))
        if name == "ema_trend" and p["fast"] >= p["slow"]:
            continue
        yield p
