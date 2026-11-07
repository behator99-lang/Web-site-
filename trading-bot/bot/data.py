"""Kursdaten laden: CSV (eigener Export oder MT5-Export) oder Testdaten erzeugen."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

COLS = ["open", "high", "low", "close"]


def load_csv(path: str | Path) -> pd.DataFrame:
    """Liest CSV-Kursdaten. Unterstützt:
    - eigenes Format: time,open,high,low,close[,volume]
    - MT5-Export (Strg+U → Balken → Exportieren): <DATE> <TIME> <OPEN> ... tab-getrennt
    """
    path = Path(path)
    head = path.read_text(encoding="utf-8", errors="ignore")[:500]
    sep = "\t" if "\t" in head else ("," if "," in head else ";")
    df = pd.read_csv(path, sep=sep)
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]

    if "date" in df.columns and "time" in df.columns:
        df["time"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
    elif "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    elif "date" in df.columns:
        df["time"] = pd.to_datetime(df["date"])
    else:
        raise ValueError(f"{path}: keine Zeitspalte gefunden (time oder date)")

    missing = [c for c in COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: Spalten fehlen: {missing}")
    df = df.set_index("time").sort_index()[COLS].astype(float)
    df = df[~df.index.duplicated(keep="last")].dropna()
    return df


def save_csv(df: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index_label="time")


def synthetic_gold(bars: int = 20000, seed: int = 42, start_price: float = 2000.0) -> pd.DataFrame:
    """Künstliche Gold-ähnliche H1-Kurse zum Ausprobieren (ohne Broker).

    Reiner Zufall ohne Trend: Hier DARF keine Strategie dauerhaft gewinnen.
    Das ist ein guter Plausibilitätstest für den Optimierer. Findet er auf
    Zufallsdaten einen "Vorteil", ist das Overfitting. Nur zum Testen der Technik!
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=bars * 2, freq="h")
    idx = idx[idx.dayofweek < 5][:bars]  # kein Wochenende
    # Volatilität wechselt zwischen ruhigen und unruhigen Phasen
    vol = 0.0018 * np.exp(np.cumsum(rng.normal(0, 0.03, bars)).clip(-1, 1))
    rets = rng.standard_t(4, bars) * vol / np.sqrt(2)  # reiner Zufall, kein Trend
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]])
    spread_hl = np.abs(rng.normal(0, vol, bars)) * close
    high = np.maximum(open_, close) + spread_hl
    low = np.minimum(open_, close) - spread_hl
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx).round(2)
