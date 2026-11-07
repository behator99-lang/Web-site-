"""Backtester: spielt eine Strategie Kerze für Kerze auf historischen Daten durch.

Realistische Annahmen:
- Einstieg zur Eröffnung der Kerze NACH dem Signal
- Spread: Long kauft zum Ask (Bid + Spread), Short verkauft zum Bid
- Kommission pro Lot
- Werden Stop-Loss und Take-Profit in derselben Kerze berührt, zählt der Stop-Loss
  (pessimistisch, weil man den Verlauf innerhalb der Kerze nicht kennt)
- Kurslücken: Öffnet der Kurs schon hinter dem Stop, wird zum Eröffnungskurs geschlossen
- Gleiches Risikomanagement wie im Live-Bot
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import Config
from .metrics import compute_metrics
from .risk import RiskManager, position_size
from .strategies import get_strategy


@dataclass
class Position:
    direction: int
    lots: float
    entry: float
    sl: float
    tp: float
    entry_time: pd.Timestamp


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series
    metrics: dict
    risk_log: list[str] = field(default_factory=list)


def run_backtest(
    df: pd.DataFrame,
    strategy: str,
    params: dict,
    cfg: Config,
    initial_balance: float | None = None,
    trade_from: pd.Timestamp | None = None,
) -> BacktestResult:
    """trade_from: Kerzen davor dienen nur zum Aufwärmen der Indikatoren."""
    inst = cfg.instrument
    cs, spread = inst.contract_size, inst.spread
    balance = float(initial_balance or cfg.backtest["initial_balance"])
    signals = get_strategy(strategy)(df, params)

    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    sig = signals["signal"].to_numpy()
    sl_d, tp_d = signals["sl_dist"].to_numpy(), signals["tp_dist"].to_numpy()
    times = df.index
    if trade_from is not None:
        sig = sig.copy()
        sig[times < trade_from] = 0

    rm = RiskManager(cfg.risk, peak_equity=balance)
    pos: Position | None = None
    trades: list[dict] = []
    equity = []
    pending = 0
    pending_i = -1

    def close(price: float, t, reason: str) -> None:
        nonlocal balance, pos
        pnl = (price - pos.entry) * pos.direction * pos.lots * cs - inst.commission_per_lot * pos.lots
        balance += pnl
        trades.append(
            dict(entry_time=pos.entry_time, exit_time=t, direction=pos.direction, lots=pos.lots,
                 entry=pos.entry, exit=price, pnl=pnl, reason=reason)
        )
        pos = None

    def unrealized(price_bid: float) -> float:
        if pos is None:
            return 0.0
        exit_px = price_bid if pos.direction == 1 else price_bid + spread
        return (exit_px - pos.entry) * pos.direction * pos.lots * cs

    for j in range(len(df)):
        t = times[j]
        rm.update(t.date(), balance + unrealized(o[j]))

        # 1) Signal der Vorkerze zur Eröffnung ausführen
        if pending != 0:
            if pos is not None and pos.direction == -pending:
                close(o[j] if pos.direction == 1 else o[j] + spread, t, "gegensignal")
            if pos is None:
                ok, why = rm.can_open(balance)
                lots = position_size(balance, sl_d[pending_i], inst, cfg.risk.risk_per_trade_pct) if ok else 0.0
                if lots > 0:
                    entry = o[j] + spread if pending == 1 else o[j]
                    pos = Position(pending, lots, entry,
                                   entry - pending * sl_d[pending_i],
                                   entry + pending * tp_d[pending_i], t)
                    rm.register_trade()
                elif not ok:
                    rm.log.append(f"{t} Signal ignoriert: {why}")
            pending = 0

        # 2) Stop-Loss / Take-Profit innerhalb der Kerze prüfen
        if pos is not None:
            if pos.direction == 1:  # Long schließt zum Bid
                if l[j] <= pos.sl:
                    close(min(o[j], pos.sl), t, "stop_loss")
                elif h[j] >= pos.tp:
                    close(max(o[j], pos.tp), t, "take_profit")
            else:  # Short schließt zum Ask
                if h[j] + spread >= pos.sl:
                    close(max(o[j] + spread, pos.sl), t, "stop_loss")
                elif l[j] + spread <= pos.tp:
                    close(min(o[j] + spread, pos.tp), t, "take_profit")

        equity.append(balance + unrealized(c[j]))
        if sig[j] != 0:
            pending, pending_i = int(sig[j]), j

    if pos is not None:
        close(c[-1] if pos.direction == 1 else c[-1] + spread, times[-1], "ende")
        equity[-1] = balance

    trades_df = pd.DataFrame(
        trades, columns=["entry_time", "exit_time", "direction", "lots", "entry", "exit", "pnl", "reason"]
    )
    equity_s = pd.Series(equity, index=times, name="equity")
    if trade_from is not None:
        equity_s = equity_s[equity_s.index >= trade_from]
    return BacktestResult(trades_df, equity_s, compute_metrics(trades_df, equity_s), rm.log)
