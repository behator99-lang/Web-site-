"""Anbindung an MetaTrader 5.

Das offizielle Python-Paket "MetaTrader5" läuft NUR unter Windows und braucht
ein installiertes, eingeloggtes MT5-Terminal auf demselben Rechner.
"""
from __future__ import annotations

import os

import pandas as pd

from .config import Instrument

MAGIC = 20261107  # Kennzeichnet Orders dieses Bots. Fremde Positionen werden nie angefasst.


class BrokerError(RuntimeError):
    pass


def _mt5():
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError as e:
        raise BrokerError(
            "Paket 'MetaTrader5' nicht gefunden. Es läuft nur unter Windows: "
            "pip install MetaTrader5 (und das MT5-Terminal installieren)."
        ) from e
    return mt5


class MT5Broker:
    def __init__(self, symbol: str, timeframe: str):
        self.mt5 = _mt5()
        self.symbol = symbol
        tf = getattr(self.mt5, f"TIMEFRAME_{timeframe}", None)
        if tf is None:
            raise BrokerError(f"Unbekannter Zeitrahmen {timeframe!r}")
        self.timeframe = tf

    # --- Verbindung -------------------------------------------------------
    def connect(self) -> None:
        kwargs = {}
        if os.environ.get("MT5_PATH"):
            kwargs["path"] = os.environ["MT5_PATH"]
        if os.environ.get("MT5_LOGIN"):
            kwargs.update(
                login=int(os.environ["MT5_LOGIN"]),
                password=os.environ.get("MT5_PASSWORD", ""),
                server=os.environ.get("MT5_SERVER", ""),
            )
        if not self.mt5.initialize(**kwargs):
            raise BrokerError(f"MT5-Verbindung fehlgeschlagen: {self.mt5.last_error()}")
        if not self.mt5.symbol_select(self.symbol, True):
            raise BrokerError(f"Symbol {self.symbol} nicht verfügbar. Heißt es bei deinem Broker anders?")

    def shutdown(self) -> None:
        self.mt5.shutdown()

    def is_real_account(self) -> bool:
        return self.mt5.account_info().trade_mode == self.mt5.ACCOUNT_TRADE_MODE_REAL

    def account(self) -> dict:
        a = self.mt5.account_info()
        return {"login": a.login, "server": a.server, "balance": a.balance,
                "equity": a.equity, "currency": a.currency}

    def instrument(self, spread_fallback: float, commission: float) -> Instrument:
        s = self.mt5.symbol_info(self.symbol)
        return Instrument(
            contract_size=s.trade_contract_size, lot_step=s.volume_step,
            min_lot=s.volume_min, max_lot=s.volume_max,
            spread=(s.spread * s.point) or spread_fallback, commission_per_lot=commission,
        )

    # --- Daten ------------------------------------------------------------
    def rates(self, count: int) -> pd.DataFrame:
        r = self.mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, count)
        if r is None or len(r) == 0:
            raise BrokerError(f"Keine Kursdaten: {self.mt5.last_error()}")
        df = pd.DataFrame(r)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df.set_index("time")[["open", "high", "low", "close"]].astype(float)

    # --- Orders -----------------------------------------------------------
    def positions(self) -> list:
        return [p for p in (self.mt5.positions_get(symbol=self.symbol) or []) if p.magic == MAGIC]

    def _filling(self) -> int:
        fm = self.mt5.symbol_info(self.symbol).filling_mode
        if fm & 1:
            return self.mt5.ORDER_FILLING_FOK
        if fm & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def _send(self, request: dict):
        res = self.mt5.order_send(request)
        if res is None or res.retcode != self.mt5.TRADE_RETCODE_DONE:
            code = getattr(res, "retcode", None)
            comment = getattr(res, "comment", self.mt5.last_error())
            raise BrokerError(f"Order abgelehnt ({code}): {comment}")
        return res

    def open(self, direction: int, lots: float, sl_dist: float, tp_dist: float) -> dict:
        mt5 = self.mt5
        info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        price = tick.ask if direction == 1 else tick.bid
        # Broker verlangen oft einen Mindestabstand für SL/TP
        min_dist = info.trade_stops_level * info.point
        sl_dist, tp_dist = max(sl_dist, min_dist), max(tp_dist, min_dist)
        sl = round(price - direction * sl_dist, info.digits)
        tp = round(price + direction * tp_dist, info.digits)
        res = self._send({
            "action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": lots,
            "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
            "price": price, "sl": sl, "tp": tp, "deviation": 30, "magic": MAGIC,
            "comment": "goldbot", "type_time": mt5.ORDER_TIME_GTC, "type_filling": self._filling(),
        })
        return {"ticket": res.order, "price": res.price, "sl": sl, "tp": tp, "lots": lots}

    def close(self, position) -> dict:
        mt5 = self.mt5
        tick = mt5.symbol_info_tick(self.symbol)
        is_buy = position.type == mt5.POSITION_TYPE_BUY
        res = self._send({
            "action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "position": position.ticket, "price": tick.bid if is_buy else tick.ask,
            "deviation": 30, "magic": MAGIC, "comment": "goldbot close",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": self._filling(),
        })
        return {"ticket": position.ticket, "price": res.price, "profit": position.profit}
