# Changelog

Jede Version hat eine Zeile **Nach dem Update**: was du nach dem Installieren der neuen .deb tun musst.

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
