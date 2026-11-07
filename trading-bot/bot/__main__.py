"""Kommandozeile: python -m bot <befehl>"""
from __future__ import annotations

import argparse
import json
import sys

import yaml

from .config import ROOT, load_config, load_env


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m bot", description="Gold-Trading-Bot")
    ap.add_argument("--config", help="Pfad zur config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("demo-data", help="Künstliche Testdaten erzeugen (ohne Broker)")
    s.add_argument("--bars", type=int, default=20000)
    s.add_argument("--out", default=str(ROOT / "data" / "synthetic_H1.csv"))

    s = sub.add_parser("download", help="Historische Kurse aus MT5 laden (Windows)")
    s.add_argument("--bars", type=int, default=30000)

    s = sub.add_parser("backtest", help="Eine Strategie auf historischen Daten testen")
    s.add_argument("--data", required=True)
    s.add_argument("--strategy", help="Standard: aus config.yaml")
    s.add_argument("--params", help='JSON, z. B. \'{"fast":20,"slow":100}\'')
    s.add_argument("--trades", action="store_true", help="Alle Trades anzeigen")

    s = sub.add_parser("optimize", help="Walk-Forward: beste Strategie finden und ehrlich prüfen")
    s.add_argument("--data", required=True)
    s.add_argument("--strategies", nargs="*", help="Nur diese Strategien testen")

    s = sub.add_parser("run", help="Bot starten (Demo- oder Live-Konto über MT5)")
    s.add_argument("--dry-run", action="store_true", help="Nur Signale loggen, keine Orders")

    args = ap.parse_args(argv)
    load_env()
    cfg = load_config(args.config)

    if args.cmd == "demo-data":
        from .data import save_csv, synthetic_gold
        save_csv(synthetic_gold(args.bars), args.out)
        print(f"Gespeichert: {args.out} (Zufallsdaten, nur zum Testen der Technik!)")

    elif args.cmd == "download":
        from .broker import MT5Broker
        from .data import save_csv
        b = MT5Broker(cfg.symbol, cfg.timeframe)
        b.connect()
        df = b.rates(args.bars)
        b.shutdown()
        out = ROOT / "data" / f"{cfg.symbol}_{cfg.timeframe}.csv"
        save_csv(df, out)
        print(f"{len(df)} Kerzen ({df.index[0]} – {df.index[-1]}) gespeichert: {out}")

    elif args.cmd == "backtest":
        from .backtest import run_backtest
        from .data import load_csv
        from .metrics import format_metrics
        name = args.strategy or cfg.strategy["name"]
        params = json.loads(args.params) if args.params else (
            cfg.strategy.get("params", {}) if name == cfg.strategy["name"] else None)
        if params is None:
            from .strategies import iter_params
            params = next(iter_params(name))
        df = load_csv(args.data)
        res = run_backtest(df, name, params, cfg)
        print(f"\nBacktest {name} {params}\n{df.index[0]} – {df.index[-1]} ({len(df)} Kerzen)\n")
        print(format_metrics(res.metrics))
        if args.trades and len(res.trades):
            print("\n", res.trades.to_string())
        for line in res.risk_log[:10]:
            print("  Risiko:", line)

    elif args.cmd == "optimize":
        from .data import load_csv
        from .metrics import format_metrics
        from .optimize import walk_forward
        df = load_csv(args.data)
        print(f"Walk-Forward auf {len(df)} Kerzen ({df.index[0]} – {df.index[-1]})\n")
        r = walk_forward(df, cfg, args.strategies)
        print("\n=== Ergebnis NUR auf ungesehenen Daten (Out-of-Sample) ===")
        print(format_metrics(r["out_of_sample"]) if r["out_of_sample"] else "  keine Trades")
        print(f"\nUrteil: {r['verdict']}")
        rec = {"strategy": r["recommended"]}
        out = ROOT / "logs" / "optimize_result.yaml"
        out.parent.mkdir(exist_ok=True)
        out.write_text(yaml.safe_dump({**rec, "out_of_sample": r["out_of_sample"],
                                       "verdict": r["verdict"]}, allow_unicode=True, sort_keys=False))
        if not r["verdict"].startswith("VIELVERSPRECHEND"):
            print("\nHinweis: Die Empfehlung unten ist nur das beste Ergebnis der letzten Monate.\n"
                  "Laut Urteil gibt es keinen belastbaren Vorteil. Höchstens im Demo testen.")
        print(f"\nEmpfehlung für config.yaml (auch gespeichert in {out}):\n")
        print(yaml.safe_dump(rec, sort_keys=False))

    elif args.cmd == "run":
        from .live import run
        run(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
