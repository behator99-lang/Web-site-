"""Live-Logik mit simuliertem Broker testen (läuft ohne MetaTrader 5)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from bot import live
from bot.config import Config, Instrument
from bot.risk import RiskManager


class FakeBroker:
    mt5 = SimpleNamespace(POSITION_TYPE_BUY=0, POSITION_TYPE_SELL=1)

    def __init__(self, df):
        self.df, self.pos, self.opened, self.closed = df, [], [], []

    def rates(self, count):
        return self.df.iloc[-count:]

    def account(self):
        return {"equity": 5000.0}

    def positions(self):
        return list(self.pos)

    def open(self, direction, lots, sl, tp):
        self.opened.append((direction, lots))
        self.pos.append(SimpleNamespace(ticket=len(self.opened), type=0 if direction == 1 else 1,
                                        volume=lots, profit=0.0))
        return {"ticket": len(self.opened), "price": 0, "sl": 0, "tp": 0, "lots": lots}

    def close(self, p):
        self.pos.remove(p)
        self.closed.append(p.ticket)
        return {"ticket": p.ticket, "price": 0, "profit": 0}


def strat_from(signals):
    return lambda df, p: pd.DataFrame(
        {"signal": signals[: len(df)], "sl_dist": 10.0, "tp_dist": 20.0}, index=df.index)


class TestLiveStep(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        mock.patch.object(live, "JOURNAL", tmp / "j.csv").start()
        self.addCleanup(mock.patch.stopall)
        idx = pd.date_range("2024-01-01", periods=10, freq="h")
        self.df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=idx)
        self.cfg = Config()
        self.inst = Instrument()

    def step(self, broker, signals, last=None, dry=False, rm=None):
        rm = rm or RiskManager(self.cfg.risk, peak_equity=5000)
        return live.step(broker, self.cfg, self.inst, strat_from(signals), {}, rm, last, dry), rm

    def test_uses_last_closed_bar_and_opens(self):
        b = FakeBroker(self.df)
        # Signal auf vorletzter Kerze (letzte abgeschlossene); letzte Kerze läuft noch
        bar, _ = self.step(b, [0] * 8 + [1, -1])
        self.assertEqual(bar, self.df.index[-2])
        self.assertEqual(len(b.opened), 1)
        self.assertEqual(b.opened[0][0], 1)
        self.assertAlmostEqual(b.opened[0][1], 0.04)  # 50 USD / (10*100 + 7) = 0.0496 → abgerundet

    def test_same_bar_processed_once(self):
        b = FakeBroker(self.df)
        bar, rm = self.step(b, [0] * 8 + [1, 0])
        self.step(b, [0] * 8 + [1, 0], last=bar, rm=rm)
        self.assertEqual(len(b.opened), 1)

    def test_reverse_on_opposite_signal(self):
        b = FakeBroker(self.df)
        b.open(1, 0.05, 10, 20)
        self.step(b, [0] * 8 + [-1, 0])
        self.assertEqual(b.closed, [1])
        self.assertEqual(b.opened[-1][0], -1)

    def test_no_duplicate_in_same_direction(self):
        b = FakeBroker(self.df)
        b.open(1, 0.05, 10, 20)
        self.step(b, [0] * 8 + [1, 0])
        self.assertEqual(len(b.opened), 1)

    def test_dry_run_sends_nothing(self):
        b = FakeBroker(self.df)
        self.step(b, [0] * 8 + [1, 0], dry=True)
        self.assertEqual(b.opened, [])

    def test_halted_blocks_new_trades(self):
        b = FakeBroker(self.df)
        rm = RiskManager(self.cfg.risk, peak_equity=10_000)  # Equity 5000 = 50 % Drawdown
        self.step(b, [0] * 8 + [1, 0], rm=rm)
        self.assertTrue(rm.halted)
        self.assertEqual(b.opened, [])


if __name__ == "__main__":
    unittest.main()
