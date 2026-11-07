"""Tests: python -m unittest discover tests"""
import os
import unittest

import pandas as pd

from bot.backtest import run_backtest
from bot.config import Config, Instrument, RiskConfig
from bot.data import synthetic_gold
from bot.live import LIVE_CONFIRMATION, check_account_allowed
from bot.risk import RiskManager, position_size
from bot.strategies import STRATEGIES, PARAM_GRIDS, iter_params


def bars(rows, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(rows), freq="h")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)


class TestPositionSize(unittest.TestCase):
    inst = Instrument(contract_size=100, lot_step=0.01, min_lot=0.01, max_lot=1.0, commission_per_lot=0)

    def test_risk_one_percent(self):
        # 2000 USD, 1 % = 20 USD Risiko, Stop 10 USD → 20 / (10 * 100) = 0.02 Lot
        self.assertAlmostEqual(position_size(2000, 10, self.inst, 1.0), 0.02)

    def test_too_small_account_skips_trade(self):
        # 500 USD, 1 % = 5 USD, Stop 10 USD bräuchte 0.005 Lot < Minimum → 0
        self.assertEqual(position_size(500, 10, self.inst, 1.0), 0.0)

    def test_max_lot_cap(self):
        self.assertEqual(position_size(10_000_000, 1, self.inst, 1.0), 1.0)

    def test_never_exceeds_risk(self):
        for eq in (800, 1500, 2345, 9999):
            for sl in (3.7, 8.2, 21.5):
                lots = position_size(eq, sl, self.inst, 1.0)
                self.assertLessEqual(lots * sl * 100, eq * 0.01 + 1e-9)


class TestRiskManager(unittest.TestCase):
    def test_daily_loss_and_kill_switch(self):
        rm = RiskManager(RiskConfig(max_daily_loss_pct=3, max_drawdown_pct=10), peak_equity=1000)
        d = pd.Timestamp("2024-01-01").date()
        rm.update(d, 1000)
        self.assertTrue(rm.can_open(1000)[0])
        self.assertFalse(rm.can_open(965)[0])  # 3.5 % Tagesverlust
        rm.update(d, 890)  # 11 % unter Höchststand
        self.assertTrue(rm.halted)
        rm.update(pd.Timestamp("2024-01-02").date(), 890)
        self.assertFalse(rm.can_open(890)[0])  # Not-Aus bleibt aktiv


class TestBacktest(unittest.TestCase):
    def cfg(self, spread=0.0, commission=0.0):
        c = Config()
        c.instrument = Instrument(contract_size=100, spread=spread, commission_per_lot=commission)
        c.risk = RiskConfig(risk_per_trade_pct=1.0, max_trades_per_day=99)
        return c

    def run_forced(self, df, signals, cfg):
        """Backtest mit fest vorgegebenen Signalen statt einer echten Strategie."""
        name = "_test"
        STRATEGIES[name] = lambda d, p: pd.DataFrame(
            {"signal": signals, "sl_dist": 10.0, "tp_dist": 20.0}, index=d.index)
        try:
            return run_backtest(df, name, {}, cfg, initial_balance=10_000)
        finally:
            del STRATEGIES[name]

    def test_entry_next_open_and_take_profit(self):
        df = bars([[100, 101, 99, 100], [100, 105, 99, 104], [104, 125, 103, 120], [120, 121, 119, 120]])
        r = self.run_forced(df, [1, 0, 0, 0], self.cfg())
        t = r.trades.iloc[0]
        self.assertEqual(t.entry, 100)  # Eröffnung der 2. Kerze, nicht Schluss der 1.
        self.assertEqual(t.entry_time, df.index[1])
        self.assertEqual(t.reason, "take_profit")
        self.assertEqual(t.exit, 120)
        # 1 % von 10 000 = 100 USD Risiko / (10 * 100) = 0.1 Lot → 20 USD * 100 * 0.1 = 200
        self.assertAlmostEqual(t.pnl, 200)

    def test_stop_loss_wins_when_both_hit(self):
        df = bars([[100, 100, 100, 100], [100, 130, 80, 100], [100, 100, 100, 100]])
        r = self.run_forced(df, [1, 0, 0], self.cfg())
        self.assertEqual(r.trades.iloc[0].reason, "stop_loss")
        self.assertAlmostEqual(r.trades.iloc[0].pnl, -100)

    def test_gap_through_stop_fills_at_open(self):
        df = bars([[100, 100, 100, 100], [100, 101, 99, 100], [80, 82, 78, 81]])
        r = self.run_forced(df, [1, 0, 0], self.cfg())
        self.assertEqual(r.trades.iloc[0].exit, 80)  # nicht 90: Kurslücke

    def test_spread_and_commission_cost(self):
        df = bars([[100, 100, 100, 100], [100, 101, 99, 100], [100, 101, 99, 100]])
        r = self.run_forced(df, [-1, 0, 0], self.cfg(spread=0.5, commission=7))
        t = r.trades.iloc[0]
        self.assertEqual(t.entry, 100)       # Short verkauft zum Bid
        self.assertEqual(t.exit, 100.5)      # schließt zum Ask
        self.assertAlmostEqual(t.pnl, -0.5 * 100 * t.lots - 7 * t.lots)

    def test_no_lookahead(self):
        """Signale dürfen sich nicht ändern, wenn zukünftige Kerzen fehlen."""
        df = synthetic_gold(3000, seed=1)
        for name in STRATEGIES:
            p = next(iter_params(name))
            full = STRATEGIES[name](df, p)["signal"]
            cut = STRATEGIES[name](df.iloc[:2000], p)["signal"]
            pd.testing.assert_series_equal(full.iloc[:2000], cut, check_names=False)

    def test_all_strategies_run(self):
        df = synthetic_gold(3000, seed=2)
        for name in PARAM_GRIDS:
            r = run_backtest(df, name, next(iter_params(name)), Config())
            self.assertGreater(r.metrics["trades"], 0, name)


class TestLiveSafety(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CONFIRM_LIVE_TRADING", None)

    def test_demo_account_always_ok(self):
        check_account_allowed(Config(mode="demo"), is_real=False)

    def test_real_account_blocked_in_demo_mode(self):
        with self.assertRaises(SystemExit):
            check_account_allowed(Config(mode="demo"), is_real=True)

    def test_real_account_needs_confirmation(self):
        with self.assertRaises(SystemExit):
            check_account_allowed(Config(mode="live"), is_real=True)
        os.environ["CONFIRM_LIVE_TRADING"] = LIVE_CONFIRMATION
        check_account_allowed(Config(mode="live"), is_real=True)


if __name__ == "__main__":
    unittest.main()
