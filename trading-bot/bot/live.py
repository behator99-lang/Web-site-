"""Live-/Demo-Betrieb: wartet auf jede neue abgeschlossene Kerze und handelt.

Sicherheitsregeln:
- mode: demo → Start auf einem Echtgeld-Konto wird verweigert.
- mode: live → zusätzlich CONFIRM_LIVE_TRADING=JA_ICH_HANDLE_MIT_ECHTEM_GELD in .env nötig.
- Not-Aus-Status und Höchststand werden in logs/state.json gespeichert und
  überleben einen Neustart. Zum Zurücksetzen die Datei bewusst löschen.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from datetime import datetime

from .broker import BrokerError, MT5Broker
from .config import ROOT, Config
from .risk import RiskManager, position_size
from .strategies import get_strategy

LIVE_CONFIRMATION = "JA_ICH_HANDLE_MIT_ECHTEM_GELD"
STATE_FILE = ROOT / "logs" / "state.json"
JOURNAL = ROOT / "logs" / "journal.csv"

log = logging.getLogger("goldbot")


def setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(ROOT / "logs" / "bot.log", encoding="utf-8"), logging.StreamHandler()],
    )


def journal(event: str, **data) -> None:
    new = not JOURNAL.exists()
    with JOURNAL.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["zeit", "ereignis", "daten"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), event, json.dumps(data, default=str)])


def check_account_allowed(cfg: Config, is_real: bool) -> None:
    if not is_real:
        return
    if cfg.mode != "live":
        raise SystemExit("ABBRUCH: Echtgeld-Konto erkannt, aber mode ist 'demo'. Es wird nicht gehandelt.")
    if os.environ.get("CONFIRM_LIVE_TRADING") != LIVE_CONFIRMATION:
        raise SystemExit(f"ABBRUCH: Für Echtgeld muss CONFIRM_LIVE_TRADING={LIVE_CONFIRMATION} in .env stehen.")


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(rm: RiskManager) -> None:
    STATE_FILE.write_text(json.dumps(
        {"peak_equity": rm.peak_equity, "halted": rm.halted, "halt_reason": rm.halt_reason}, indent=2))


def run(cfg: Config, dry_run: bool = False, poll_seconds: int = 20) -> None:
    setup_logging()
    broker = MT5Broker(cfg.symbol, cfg.timeframe)
    broker.connect()
    real = broker.is_real_account()
    check_account_allowed(cfg, real)

    acc = broker.account()
    inst = broker.instrument(cfg.instrument.spread, cfg.instrument.commission_per_lot)
    strat = get_strategy(cfg.strategy["name"])
    params = cfg.strategy.get("params", {})
    log.info("Verbunden: Konto %s (%s) %s | %s %s | Equity %.2f %s",
             acc["login"], acc["server"], "ECHTGELD" if real else "DEMO",
             cfg.symbol, cfg.timeframe, acc["equity"], acc["currency"])
    log.info("Strategie %s %s | Kontrakt %s, Lots %s–%s%s", cfg.strategy["name"], params,
             inst.contract_size, inst.min_lot, inst.max_lot, " | DRY-RUN (keine Orders)" if dry_run else "")

    state = load_state()
    rm = RiskManager(cfg.risk, peak_equity=max(state.get("peak_equity", 0), acc["equity"]))
    rm.halted, rm.halt_reason = state.get("halted", False), state.get("halt_reason", "")
    journal("start", konto=acc["login"], echtgeld=real, strategie=cfg.strategy, dry_run=dry_run)

    last_bar = None
    try:
        while True:
            try:
                last_bar = step(broker, cfg, inst, strat, params, rm, last_bar, dry_run)
                save_state(rm)
            except BrokerError as e:
                log.error("Broker-Fehler: %s", e)
                journal("fehler", text=str(e))
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        log.info("Beendet (Strg+C). Offene Positionen bleiben mit SL/TP beim Broker bestehen.")
    finally:
        broker.shutdown()


def step(broker, cfg, inst, strat, params, rm, last_bar, dry_run):
    df = broker.rates(600).iloc[:-1]  # letzte Kerze ist noch nicht abgeschlossen
    bar_time = df.index[-1]
    if bar_time == last_bar:
        return last_bar

    equity = broker.account()["equity"]
    rm.update(bar_time.date(), equity)
    sig = strat(df, params).iloc[-1]
    signal = int(sig["signal"])
    log.info("Neue Kerze %s close=%.2f equity=%.2f signal=%+d", bar_time, df["close"].iloc[-1], equity, signal)
    if rm.halted:
        log.warning("%s. Keine neuen Trades. logs/state.json löschen, um fortzufahren.", rm.halt_reason)
    if signal == 0:
        return bar_time

    def direction(p):
        return 1 if p.type == broker.mt5.POSITION_TYPE_BUY else -1

    for p in broker.positions():
        if direction(p) == -signal:
            log.info("Gegensignal: schließe Position %s", p.ticket)
            if not dry_run:
                journal("close", **broker.close(p))
    if any(direction(p) == signal for p in broker.positions()):
        return bar_time  # schon in Signalrichtung investiert

    ok, why = rm.can_open(equity)
    if not ok:
        log.info("Signal ignoriert: %s", why)
        journal("ignoriert", grund=why, signal=signal)
        return bar_time
    lots = position_size(equity, float(sig["sl_dist"]), inst, cfg.risk.risk_per_trade_pct)
    if lots <= 0:
        msg = "Konto zu klein für Mindest-Lotgröße bei diesem Stop-Abstand"
        log.warning("Signal ignoriert: %s", msg)
        journal("ignoriert", grund=msg, signal=signal)
        return bar_time

    log.info("%s %.2f Lots, SL-Abstand %.2f, TP-Abstand %.2f", "KAUF" if signal == 1 else "VERKAUF",
             lots, sig["sl_dist"], sig["tp_dist"])
    if not dry_run:
        order = broker.open(signal, lots, float(sig["sl_dist"]), float(sig["tp_dist"]))
        rm.register_trade()
        journal("open", richtung=signal, **order)
    return bar_time
