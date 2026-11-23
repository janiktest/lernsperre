# LernSperre

Desktop-App für Ubuntu (GNOME): LernSperre zählt, wie lange du auf YouTube, Instagram, TikTok, Netflix, Reddit oder X/Twitter bist. Nach einer einstellbaren Zeit (Standard 20 min) wird gesperrt, und du musst erst eine Weile (Standard 5 min) in Anki lernen, bevor es weitergeht.

Funktioniert mit Anki-Decks über die offizielle Anki-App (getestet für das Flatpak `net.ankiweb.Anki`). Es wird kein Anki-Add-on gebraucht.

> LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

Es ist eine Selbstdisziplin-Sperre, keine Kindersicherung. Wer die Erweiterung oder den Dienst abschaltet, kommt drum herum.

## So funktioniert es

| Teil | Aufgabe |
| --- | --- |
| GNOME-Shell-Erweiterung | meldet alle Fenster (Titel, App-ID, WM_CLASS, Fokus) an den Dienst, zeigt die Restzeit im Panel und legt bei einer Sperre ein Vollbild-Overlay über alles |
| Hintergrunddienst (Python, systemd-User-Dienst) | zählt die Zeit, liest MPRIS (was gerade abgespielt wird), sperrt und entsperrt, speichert den Zustand in SQLite |
| Anki (Flatpak) | zum Lernen. Der Dienst liest nur lesend die Sammlung, um zu sehen, wann zuletzt eine Karte beantwortet wurde |

**Zeit zählt**, wenn ein Ziel-Fenster vorne ist oder gerade etwas von einem Ziel abgespielt wird (z. B. YouTube-Tab im Hintergrund, über MPRIS und den Titel des Browserfensters).

**Während der Sperre** ist nur Anki erlaubt. Jedes andere Fenster wird vom Overlay verdeckt, laufende Wiedergabe wird pausiert. Die Lernzeit zählt nur, solange Anki vorne ist **und** du Karten beantwortest (Pause nach 60 s ohne Antwort). Ist die Lernzeit erreicht, wird entsperrt und der Zähler beginnt von vorn.

1 min vor der Sperre kommt eine Benachrichtigung.

## Installation

Voraussetzungen: Ubuntu mit GNOME (Wayland), `python3-gi` (Standard auf Ubuntu), Anki als Flatpak.

```bash
git clone https://github.com/janiktest/lernsperre.git
cd lernsperre
./install.sh
```

Auf Wayland erkennt GNOME eine neu installierte Erweiterung erst nach dem nächsten Anmelden. Danach einmal:

```bash
gnome-extensions enable lernsperre@janiktest.github.io
```

Entfernen: `./uninstall.sh`

## Bedienung

```bash
lernsperre status   # Restzeit, was gerade zählt, Zustand der Überwachung
lernsperre lock     # Sperre jetzt aktivieren (z. B. zum Ausprobieren)
lernsperre reset    # Zähler zurücksetzen / Sperre aufheben (Notfall)
lernsperre config   # Pfad der Einstellungsdatei
lernsperre reload   # Einstellungen neu laden
```

Im Panel oben steht `⏳ 12:34` (verbleibende Zeit) bzw. während der Sperre `🔒 4:12 ▶` (Lernzeit läuft) oder `⏸` (pausiert). Das Menü dahinter hat „Anki öffnen“, „Sperre jetzt aktivieren“ und „Zähler zurücksetzen“.

Notfall: Auf dem Sperrbildschirm gibt es unten „Notfall: Sperre aufheben“ (zweimal klicken). Ohne Overlay geht `lernsperre reset` im Terminal.

## Einstellungen

`~/.config/lernsperre/config.toml` (wird beim ersten Start angelegt):

- `allowed_minutes` – erlaubte Zeit bis zur Sperre (20)
- `learn_minutes` – Lernzeit zum Entsperren (5)
- `warn_seconds` – Warnung vor der Sperre (60, 0 = aus)
- `idle_seconds` – Lernzeit pausiert, wenn so lange keine Karte beantwortet wurde (60)
- `pause_media_on_lock` – Wiedergabe bei Sperre pausieren (true)
- `anki_collection` – Pfad zu `collection.anki2`, leer = automatisch
- `[[targets]]` – Ziele mit `titles` (Fenstertitel, `re:` für reguläre Ausdrücke), `apps` (App-ID / WM_CLASS, z. B. für native Apps) und `urls` (für die spätere Browser-Erweiterung)

## Entwicklung

```bash
cd daemon && pytest -q
```

## Stand

- [x] Schritt 1: Erkennung (Fenster + MPRIS), Zeitzähler, Panel, Warnung, Sperre mit Anki, Installationsskript
- [ ] Browser-Erweiterung für Firefox (genaue Adresse, Ton im Tab)
- [ ] Einstellungsfenster und Einführung beim ersten Start, Hinweis wenn die Überwachung aus war, .deb und Releases
