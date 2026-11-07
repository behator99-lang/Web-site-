"""Risikomanagement: Positionsgröße, Tagesverlust-Limit, Not-Aus.

Wird vom Backtester UND vom Live-Bot genutzt, damit beide gleich handeln.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .config import Instrument, RiskConfig


def position_size(equity: float, sl_dist: float, inst: Instrument, risk_pct: float) -> float:
    """Lots so wählen, dass ein Stop-Loss höchstens risk_pct % vom Konto kostet.

    Gibt 0 zurück, wenn selbst die kleinste Lotgröße zu viel Risiko wäre.
    Dann wird der Trade ausgelassen statt das Limit zu überschreiten.
    """
    if sl_dist <= 0 or equity <= 0:
        return 0.0
    risk_money = equity * risk_pct / 100
    loss_per_lot = sl_dist * inst.contract_size + inst.commission_per_lot
    lots = math.floor(risk_money / loss_per_lot / inst.lot_step + 1e-9) * inst.lot_step
    lots = min(round(lots, 8), inst.max_lot)
    return lots if lots >= inst.min_lot else 0.0


@dataclass
class RiskManager:
    cfg: RiskConfig
    peak_equity: float
    day: date | None = None
    day_start_equity: float = 0.0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str = ""
    log: list[str] = field(default_factory=list)

    def update(self, today: date, equity: float) -> None:
        if today != self.day:
            self.day, self.day_start_equity, self.trades_today = today, equity, 0
        self.peak_equity = max(self.peak_equity, equity)
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if not self.halted and dd >= self.cfg.max_drawdown_pct:
            self.halted = True
            self.halt_reason = f"Not-Aus: Drawdown {dd:.1f} % >= {self.cfg.max_drawdown_pct} %"
            self.log.append(f"{today} {self.halt_reason}")

    def can_open(self, equity: float) -> tuple[bool, str]:
        if self.halted:
            return False, self.halt_reason
        day_loss = (self.day_start_equity - equity) / self.day_start_equity * 100
        if day_loss >= self.cfg.max_daily_loss_pct:
            return False, f"Tagesverlust {day_loss:.1f} % erreicht"
        if self.trades_today >= self.cfg.max_trades_per_day:
            return False, "Max. Trades pro Tag erreicht"
        return True, ""

    def register_trade(self) -> None:
        self.trades_today += 1
