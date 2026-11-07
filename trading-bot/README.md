# Gold-Trading-Bot (XAUUSD, MetaTrader 5)

Ein Bot, der Strategien für Gold auf historischen Daten testet, die beste davon
ehrlich prüft (Walk-Forward) und sie dann automatisch über MetaTrader 5 handelt:
zuerst auf einem Demo-Konto, später, wenn die Zahlen stimmen, mit echtem Geld.

> **Kein Finanzrat.** Die meisten automatischen Strategien verlieren auf Dauer Geld.
> Setze nur Geld ein, dessen Verlust du verkraften kannst.

## Fahrplan

| Phase | Dauer | Was passiert | Weiter, wenn … |
|---|---|---|---|
| 1. Backtest & Walk-Forward | 1–2 Wochen | Echte Gold-Daten laden, `optimize` laufen lassen | Urteil „VIELVERSPRECHEND“ |
| 2. Demo-Konto | 3–6 Monate | `run` auf dem MT5-Demo-Konto, rund um die Uhr | Demo-Ergebnis ähnelt dem Backtest, mind. 50 Trades, Drawdown im Rahmen |
| 3. Echtgeld klein | 3 Monate | `mode: live`, kleines Konto, 0,5 % Risiko pro Trade | Ergebnis ähnelt dem Demo-Ergebnis |
| 4. Hochskalieren | danach | Kapital langsam erhöhen | – |

Wenn eine Phase schlecht läuft: zurück zu Phase 1. Das ist normal und kein Scheitern.

## Ordner

```
bot/
  strategies.py   Strategien (EMA-Trend, Donchian-Ausbruch, RSI-Rücksetzer) + Suchraum
  backtest.py     Backtester mit Spread, Kommission, Kurslücken
  optimize.py     Walk-Forward: findet die beste Strategie und prüft sie auf ungesehenen Daten
  risk.py         Positionsgröße, Tagesverlust-Limit, Not-Aus
  broker.py       MetaTrader-5-Anbindung
  live.py         Demo-/Live-Betrieb
  data.py         CSV laden, Testdaten erzeugen
tests/            Automatische Tests
config.example.yaml   Einstellungen (kopieren nach config.yaml)
.env.example          Zugangsdaten (kopieren nach .env)
```

## Einrichtung

**Wichtig:** Das MT5-Python-Paket läuft **nur unter Windows**. Backtests und
Optimierung laufen überall (Windows, Mac, Linux). Für den Dauerbetrieb brauchst
du einen Windows-Rechner, der rund um die Uhr läuft, oder einen Windows-VPS
(ca. 10–20 €/Monat, viele Broker bieten einen kostenlos an).

1. **Python 3.11+** installieren (python.org, bei der Installation „Add to PATH“ anhaken)
2. **MetaTrader 5** installieren und ein **Demo-Konto** bei deinem Broker eröffnen.
   Im Terminal: *Extras → Optionen → Expert Advisors → „Algorithmischen Handel erlauben“*
3. Im Ordner `trading-bot`:
   ```bash
   pip install -r requirements.txt
   copy config.example.yaml config.yaml      # Mac/Linux: cp
   copy .env.example .env
   ```
4. `.env` mit Login, Passwort und Server des **Demo-Kontos** ausfüllen
5. In `config.yaml` prüfen, wie Gold bei deinem Broker heißt (`XAUUSD`, `GOLD`, `XAUUSD.m` …)

## Benutzung

```bash
# Ohne Broker ausprobieren (Zufallsdaten, nur zum Testen der Technik)
python -m bot demo-data
python -m bot backtest --data data/synthetic_H1.csv

# Echte Gold-Historie aus MT5 laden (ca. 30 000 Stundenkerzen ≈ 5 Jahre)
python -m bot download --bars 30000

# Eine Strategie testen
python -m bot backtest --data data/XAUUSD_H1.csv --strategy donchian_breakout

# Beste Strategie suchen und ehrlich prüfen (dauert einige Minuten)
python -m bot optimize --data data/XAUUSD_H1.csv

# Empfehlung in config.yaml übernehmen, dann:
python -m bot run --dry-run     # nur Signale anzeigen, keine Orders
python -m bot run               # handelt auf dem Demo-Konto

# Tests
python -m unittest discover tests
```

Logs landen in `logs/bot.log`, jede Aktion in `logs/journal.csv`.

## Wie der Bot „die richtige Strategie findet“

`optimize` macht eine **Walk-Forward-Analyse**:

1. Nimm 6 Monate Daten, teste alle Strategien mit allen Parametern, wähle die beste.
2. Handle damit die **nächsten 2 Monate**, die bei der Auswahl nicht sichtbar waren.
3. Schiebe das Fenster um 2 Monate weiter und wiederhole.

Bewertet wird **nur** das Ergebnis aus Schritt 2. Das simuliert genau das, was
der Bot später live tut: auf der Vergangenheit lernen und auf der Zukunft handeln.
Ein normaler Backtest mit den besten Parametern sieht fast immer toll aus und sagt fast nichts.

Plausibilitätstest: Auf den Zufallsdaten (`demo-data`) urteilt der Optimierer
„NICHT LIVE GEHEN“. So soll es sein.

## Sicherheit

- `mode: demo` (Standard): Der Bot **verweigert** den Start auf einem Echtgeld-Konto.
- Für Echtgeld braucht es **beides**: `mode: live` in `config.yaml` **und**
  `CONFIRM_LIVE_TRADING=JA_ICH_HANDLE_MIT_ECHTEM_GELD` in `.env`.
- Jede Order hat Stop-Loss und Take-Profit beim Broker. Auch wenn der Bot
  abstürzt, ist der Verlust begrenzt.
- Max. 1 % Risiko pro Trade, max. 3 % Verlust pro Tag, Not-Aus bei 15 % Drawdown
  (alles in `config.yaml` einstellbar). Der Not-Aus bleibt nach einem Neustart
  aktiv, bis du `logs/state.json` bewusst löschst.
- Der Bot fasst nur eigene Positionen an (Magic Number), keine manuellen Trades.

## Startkapital

Gold-CFD bei MT5: 1 Lot = 100 Unzen, kleinste Größe 0,01 Lot = 1 Unze.
Bewegt sich Gold um 1 USD, sind das bei 0,01 Lot 1 USD Gewinn oder Verlust.

Ein typischer Stop-Loss auf dem Stundenchart liegt bei 15–40 USD Kursabstand,
also 15–40 USD Risiko schon bei der kleinsten Lotgröße. Bei 1 % Risiko pro
Trade braucht man dafür **ca. 1 500–4 000 €**. Bei weniger lässt der Bot Trades
aus, statt das Risikolimit zu überschreiten.

- **Demo-Konto:** mit genau dem Betrag eröffnen, den du später real einsetzen willst,
  nicht mit 100 000 €, sonst sind die Ergebnisse unrealistisch.
- **Echtgeld-Start:** 2 000–3 000 €, wenn man das Geld komplett verlieren könnte.
  Mit weniger Geld geht es nur mit höherem Risiko pro Trade (nicht empfohlen) oder bei einem Broker, der kleinere Kontrakte anbietet.
