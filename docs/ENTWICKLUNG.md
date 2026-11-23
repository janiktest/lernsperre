# Entwicklung

## Aufbau

| Teil | Ort | Aufgabe |
| --- | --- | --- |
| GNOME-Shell-Erweiterung | `gnome-extension/` | meldet alle Fenster (Titel, App-ID, WM_CLASS, Fokus) per D-Bus an den Dienst, zeigt das Panel-Menü und legt bei einer Sperre das Overlay über alles |
| Hintergrunddienst | `daemon/lernsperre/` | Python + PyGObject, läuft als systemd-User-Dienst. Zählt die Zeit, liest MPRIS (was gerade abgespielt wird), sperrt und entsperrt, speichert den Zustand in SQLite |
| Anki | – | zum Lernen. Der Dienst liest nur lesend `revlog` in der Sammlung, um Antworten zu erkennen. Kein Add-on |

D-Bus-Name: `io.github.janiktest.LernSperre`, Objekt `/io/github/janiktest/LernSperre`. Die Erweiterung ruft `ReportWindows` auf, der Dienst sendet jede Sekunde `StateChanged` mit dem Zustand als JSON.

Wichtige Dateien im Dienst:

- `engine.py` – die Logik (Zählen, Sperren, Entsperren, Pause), ohne D-Bus, gut testbar
- `service.py` – D-Bus, MPRIS, Benachrichtigungen, Takt
- `anki.py` – lesender Zugriff auf die Anki-Sammlung
- `detect.py` – `detect-ankis` / `use-anki`
- `config.py` – Einstellungen und Standardwerte

## Ohne .deb installieren

```bash
git clone https://github.com/janiktest/lernsperre.git
cd lernsperre
./install.sh       # nur für deinen Benutzer, nach ~/.local
./uninstall.sh
```

Nicht gleichzeitig mit dem .deb installieren.

## Tests

```bash
cd daemon && pytest -q
```

Die GNOME-Erweiterung lässt sich nur in einer echten GNOME-Sitzung testen. Protokolle:

```bash
journalctl --user -u lernsperre -f          # Dienst
journalctl -f /usr/bin/gnome-shell          # Erweiterung
```

## Releases

1. Version in `daemon/lernsperre/__init__.py` erhöhen (und in `gnome-extension/…/metadata.json` → `version-name`).
2. Abschnitt in `CHANGELOG.md` mit Zeile **Nach dem Update** schreiben.
3. Nach `main` mergen. GitHub Actions baut das .deb, erstellt das Release `v<Version>` und nimmt den Changelog-Abschnitt als Beschreibung.

Lokal bauen: `./packaging/build-deb.sh` → `dist/lernsperre_<version>_all.deb`.

## Ehrlich gesagt

LernSperre ist eine Selbstdisziplin-Sperre, keine Kindersicherung. Wer die Erweiterung abschaltet oder den Dienst beendet, kommt drum herum.
