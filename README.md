# Framewerk Studio – Website

One-Page-Website für ein fiktives Videoproduktions-Studio. Reines HTML, CSS und JavaScript, ohne Framework und ohne Build-Schritt.

## Dateien

```
index.html          Die komplette One-Page (alle Texte)
impressum.html      Platzhalterseite Impressum
datenschutz.html    Platzhalterseite Datenschutz
css/style.css       Design: Farben, Schriften, Layout, Animationen
js/main.js          Menü, Scroll-Animationen, Video-Popup, Formular
assets/videos/      Hier kommen deine Videos hin
assets/images/      Hier kommen deine Bilder hin
```

## Lokal öffnen

**Einfach:** `index.html` doppelklicken. Die Seite öffnet sich im Browser.

**Besser** (Videos laden damit zuverlässiger): im Projektordner einen kleinen Server starten

```bash
python3 -m http.server 8000
```

und dann im Browser `http://localhost:8000` öffnen. Alternative in VS Code: die Erweiterung „Live Server“.

## Anpassen

| Was | Wo |
|---|---|
| Texte (Slogan, Leistungen, Ablauf, Über uns …) | `index.html`. Jede Sektion ist mit einem Kommentar wie `<!-- 2. LEISTUNGEN -->` markiert |
| Akzentfarbe, Hintergrund, Schriftfarben | `css/style.css`, ganz oben im Block `:root`. Für eine andere Akzentfarbe `--accent` und `--accent-rgb` (dieselbe Farbe als RGB-Werte) ändern |
| Schriftarten | Google-Fonts-Link im `<head>` von `index.html` und `--font-display` / `--font-body` in `:root` |
| Hero-Video | Datei als `assets/videos/hero.mp4` ablegen. Ohne Datei läuft automatisch ein animierter Farbverlauf |
| Portfolio-Videos | In `index.html` beim jeweiligen `<button class="work" …>` das Attribut `data-video` füllen: `assets/videos/projekt-1.mp4` **oder** ein YouTube-/Vimeo-Link |
| Portfolio-Vorschaubilder | In `<div class="work-thumb" …>` ein Bild einsetzen: `<div class="work-thumb"><img src="assets/images/projekt-1.jpg" alt=""></div>`. Ohne Bild bleibt der Farbverlauf (Farbton über `--hue`) |
| Teamfoto | Bei „Über uns“ das `<div class="image-placeholder">…</div>` ersetzen durch `<img src="assets/images/team.jpg" alt="Unser Team">` |
| Instagram / TikTok / E-Mail | Im Kontaktbereich von `index.html` die `href`-Links anpassen |

**Tipps für Videos:** Hero-Video als MP4 (H.264), möglichst unter 10 MB, 10–20 Sekunden, ohne Ton. Es läuft stumm und in Schleife.

## Kontaktformular

Das Formular prüft die Eingaben, verschickt aber noch **nichts** (Demo). Für echten Versand eignet sich z. B. [Formspree](https://formspree.io): Dort ein Formular anlegen und in `js/main.js` an der markierten Stelle die Daten per `fetch()` an die Formspree-Adresse senden.

## Vor dem Livegang

- Testimonials sind erfundene Beispieltexte und als solche markiert. Durch echte Stimmen ersetzen oder entfernen.
- Impressum und Datenschutz mit echten, rechtlich geprüften Angaben füllen.
- Google Fonts für die DSGVO am besten lokal einbinden.
