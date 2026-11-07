"""Lädt config.yaml und .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Instrument:
    contract_size: float = 100.0
    lot_step: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 1.0
    spread: float = 0.30
    commission_per_lot: float = 7.0


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 15.0
    max_trades_per_day: int = 4


@dataclass
class Config:
    mode: str = "demo"
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    instrument: Instrument = field(default_factory=Instrument)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: dict = field(default_factory=lambda: {"name": "ema_trend", "params": {}})
    backtest: dict = field(default_factory=lambda: {"initial_balance": 2000})
    walk_forward: dict = field(
        default_factory=lambda: {"train_bars": 3000, "test_bars": 1000, "min_trades": 15}
    )


def load_env(path: Path | None = None) -> None:
    """Minimaler .env-Parser (ohne Zusatzpaket). Vorhandene Variablen gewinnen."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else ROOT / "config.yaml"
    if not path.exists():
        path = ROOT / "config.example.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = Config(
        mode=raw.get("mode", "demo"),
        symbol=raw.get("symbol", "XAUUSD"),
        timeframe=raw.get("timeframe", "H1"),
        instrument=Instrument(**raw.get("instrument", {})),
        risk=RiskConfig(**raw.get("risk", {})),
        strategy=raw.get("strategy", Config().strategy),
        backtest={**Config().backtest, **raw.get("backtest", {})},
        walk_forward={**Config().walk_forward, **raw.get("walk_forward", {})},
    )
    if cfg.mode not in ("demo", "live"):
        raise ValueError(f"mode muss 'demo' oder 'live' sein, nicht {cfg.mode!r}")
    return cfg
