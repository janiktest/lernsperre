# Changelog

Jede Version hat eine Zeile **Nach dem Update**: was du nach dem Installieren der neuen .deb tun musst.

## 0.2.3 – 23.11.2026

**Nach dem Update:** `systemctl --user restart lernsperre` reicht (oder im Panel-Menü „Dienst neu starten“), kein Ab- und Anmelden nötig.

- Karten werden wieder genau gezählt, auch wenn Anki offen ist. Ein Deck öffnen zählt nicht mehr mit, Rückgängig zieht eine Antwort wieder ab. Dafür liest LernSperre während der Sperre eine Kopie der Anki-Sammlung in `~/.cache/lernsperre`. Die Kopie wird nie zurückgeschrieben und nach der Sperre gelöscht, Ankis Dateien und die Synchronisierung bleiben unberührt.

## 0.2.2 – 23.11.2026

**Nach dem Update:** `systemctl --user restart lernsperre` reicht (oder im Panel-Menü „Dienst neu starten“), kein Ab- und Anmelden nötig.

- Behoben: Karten in der Anki-Desktop-App wurden nicht gezählt, die Sperre zeigte „database is locked“. Anki sperrt seine Datenbank, solange es offen ist. LernSperre erkennt Antworten dann an Änderungen der Datei `collection.anki2-wal`. Die Kartenzahl ist in diesem Fall ungefähr (z. B. kann auch Rückgängig mitzählen).
- Während einer Sperre wird jede Sekunde geprüft.
- `lernsperre status` zeigt, ob genau oder ungefähr gezählt wird, und wann die letzte Antwort war.

## 0.2.1 – 23.11.2026

**Nach dem Update:** ab- und wieder anmelden (GNOME-Erweiterung geändert).

- Panel-Menü: „Dienst neu starten“ (`systemctl --user restart lernsperre`) und „Erweiterung neu laden“ (`gnome-extensions disable/enable`). Fährst du mit der Maus drüber, wird der Befehl angezeigt.
- Entsperren einfacher einstellen: `unlock_mode` fällt weg. Es zählt, was von `learn_minutes` und `min_cards` nicht auskommentiert ist (beide = beides nötig, keins = 5 min). Deine Datei wird automatisch umgestellt, ohne dass sich etwas ändert.
- `lernsperre reset-config` setzt die Einstellungen zurück, `lernsperre reset-config --behalten` schreibt sie neu und übersichtlich mit deinen Werten. Die alte Datei wird als `.bak` gesichert.
- Behoben: Das X/Twitter-Ziel hat „Twitter“ im Fenstertitel nicht erkannt.
- Tab-Vervollständigung im Terminal: `lernsperre ` und zweimal Tab zeigt alle Befehle (Bash und Zsh, ggf. neues Terminal öffnen)

## 0.2.0 – 23.11.2026

**Nach dem Update:** ab- und wieder anmelden (GNOME-Erweiterung geändert).

- Panel-Menü: Pausieren (15 / 30 / 60 min), Pause beenden, Einstellungen, Anleitung, GitHub-Seite, Beenden/Starten
- Entsperren nach Lernzeit, nach Anzahl Karten oder beidem (`unlock_mode`, `min_cards`)
- Emojis im Panel einstellbar
- Einstellungen werden nach dem Speichern automatisch übernommen, neue Optionen werden in deine Datei eingefügt
- Mehrere Bildschirme: Text der Sperre nur auf dem Hauptbildschirm, die anderen werden abgedunkelt
- Anki wählbar mit `anki_launch`; `lernsperre detect-ankis` und `lernsperre use-anki N`
- Neue Befehle: `pause`, `resume`, `edit`, `quit`, `start`, `hilfe`
- Anleitung in `docs/ANLEITUNG.md`

## 0.1.0 – 23.11.2026

**Nach der Installation:** ab- und wieder anmelden.

- Erste Version: Zeit auf YouTube, Instagram, TikTok, Netflix, Reddit und X/Twitter zählen, Warnung 1 min vorher, Sperre bis zum Lernen in Anki
- Restzeit oben im Panel
- .deb-Paket mit Autostart
