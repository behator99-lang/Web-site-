"""Walk-Forward-Optimierung: der Teil, in dem der Bot "die richtige Strategie findet".

Ablauf (wiederholt über die ganze Historie):
  1. Trainingsfenster (z. B. 6 Monate): alle Strategien × alle Parameter testen,
     die beste Kombination auswählen.
  2. Testfenster (die 2 Monate DANACH): genau diese Kombination handeln.
     Diese Daten hat die Auswahl nie gesehen.
  3. Fenster weiterschieben, wiederholen.

Nur die Ergebnisse aus den Testfenstern zählen. Sie zeigen, wie gut das
Auswahlverfahren in der Zukunft funktioniert hätte, nicht wie gut es in die
Vergangenheit passt.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .backtest import run_backtest
from .config import Config
from .metrics import compute_metrics, score
from .strategies import STRATEGIES, iter_params

WARMUP_BARS = 300  # genug für EMA 200 + Puffer


@dataclass
class WindowResult:
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    strategy: str
    params: dict
    train_score: float
    test_metrics: dict


def best_on(df: pd.DataFrame, cfg: Config, strategies: list[str]) -> tuple[str, dict, float, dict]:
    best = (None, None, float("-inf"), None)
    for name in strategies:
        for params in iter_params(name):
            m = run_backtest(df, name, params, cfg).metrics
            s = score(m, cfg.walk_forward["min_trades"])
            if s > best[2]:
                best = (name, params, s, m)
    return best


def walk_forward(
    df: pd.DataFrame, cfg: Config, strategies: list[str] | None = None, verbose: bool = True
) -> dict:
    strategies = strategies or list(STRATEGIES)
    train, test = cfg.walk_forward["train_bars"], cfg.walk_forward["test_bars"]
    if len(df) < train + test:
        raise ValueError(f"Zu wenig Daten: {len(df)} Kerzen, nötig sind mindestens {train + test}.")

    balance = float(cfg.backtest["initial_balance"])
    windows: list[WindowResult] = []
    all_trades, all_equity = [], []

    start = 0
    while start + train + test <= len(df):
        train_df = df.iloc[start : start + train]
        name, params, s, _ = best_on(train_df, cfg, strategies)
        test_start_i = start + train
        test_end_i = test_start_i + test
        test_from = df.index[test_start_i]

        if name is None:
            if verbose:
                print(f"  {test_from.date()}: keine Strategie mit genug Trades, Fenster ausgesetzt")
            start += test
            continue

        test_df = df.iloc[max(0, test_start_i - WARMUP_BARS) : test_end_i]
        res = run_backtest(test_df, name, params, cfg, initial_balance=balance, trade_from=test_from)
        balance = float(res.equity.iloc[-1])
        all_trades.append(res.trades)
        all_equity.append(res.equity)
        windows.append(WindowResult(df.index[start], test_from, df.index[test_end_i - 1],
                                    name, params, s, res.metrics))
        if verbose:
            print(f"  Test {test_from.date()} – {df.index[test_end_i - 1].date()}: "
                  f"{name} {params} → {res.metrics['return_pct']:+.2f} % "
                  f"({res.metrics['trades']} Trades)")
        start += test

    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame(columns=["pnl"])
    equity = pd.concat(all_equity) if all_equity else pd.Series(dtype=float)
    oos = compute_metrics(trades, equity) if len(equity) else {}

    # Empfehlung für den Demo-Betrieb: beste Kombination auf den jüngsten Daten
    latest_name, latest_params, _, _ = best_on(df.iloc[-train:], cfg, strategies)
    return {
        "windows": windows,
        "out_of_sample": oos,
        "trades": trades,
        "equity": equity,
        "recommended": {"name": latest_name, "params": latest_params},
        "verdict": verdict(oos),
    }


def verdict(m: dict) -> str:
    if not m or m.get("trades", 0) < 30:
        return "ZU WENIG DATEN: weniger als 30 Out-of-Sample-Trades, keine Aussage möglich."
    pf = m["profit_factor"]
    if m["return_pct"] <= 0 or pf < 1.1:
        return "NICHT LIVE GEHEN: Out-of-Sample kein belastbarer Vorteil."
    if m["max_drawdown_pct"] > 25 or m["sharpe"] < 0.5:
        return "VORSICHT: profitabel, aber zu schwankungsanfällig. Weiter im Demo testen."
    return "VIELVERSPRECHEND: jetzt mehrere Monate im Demo-Konto bestätigen lassen."
