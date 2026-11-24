# LernSperre

Sperrt YouTube, Instagram & Co. nach einer einstellbaren Zeit, bis du in Anki gelernt hast. Für Ubuntu mit GNOME, funktioniert mit der offiziellen Anki-App.

> LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

## Was die App macht

- Zählt die Zeit, wenn YouTube, Instagram, TikTok, Netflix, Reddit oder X vorne sind oder dort gerade etwas läuft. Die Ziele sind frei einstellbar.
- Nach der erlaubten Zeit (Standard 20 min) sperrt ein Vollbild-Overlay alles außer Anki.
- Entsperrt wird nach einer Lernzeit (Standard 5 min) oder einer Anzahl Karten in Anki. Danach beginnt die Zeit von vorn.
- Auf Wunsch (Schalter im Menü) bringt freiwilliges Lernen Bonuszeit, Standard 10 Karten = 5 min.
- Restzeit und Menü (Pausieren, Einstellungen, Beenden …) oben rechts in der Leiste.

## Installieren

1. `lernsperre_…_all.deb` unter **[Releases](https://github.com/janiktest/lernsperre/releases/latest)** herunterladen.
2. Installieren:
   ```bash
   sudo apt install ./Downloads/lernsperre_*_all.deb
   ```
3. **Ab- und wieder anmelden.**

Fertig. Oben rechts in der Leiste steht jetzt z. B. `⏳ 20:00`. Der Dienst und die GNOME-Erweiterung starten ab jetzt bei jeder Anmeldung von selbst.

**Prüfen, falls nichts erscheint:**

```bash
systemctl --user status lernsperre                       # Dienst läuft? Sonst: systemctl --user start lernsperre
gnome-extensions info lernsperre@janiktest.github.io     # Erweiterung an? Sonst: gnome-extensions enable lernsperre@janiktest.github.io
```

Mehrere Anki-Installationen? `lernsperre detect-ankis`, dann `lernsperre use-anki N`.

## Updaten

Neue .deb genauso installieren. Was danach nötig ist, steht bei jedem [Release](https://github.com/janiktest/lernsperre/releases) und im [Changelog](CHANGELOG.md):

- **Neu anmelden**, wenn sich die GNOME-Erweiterung geändert hat (GNOME lädt sie nur beim Anmelden neu)
- sonst reicht `systemctl --user restart lernsperre`

Deine Einstellungen bleiben erhalten.

## Entfernen

```bash
sudo apt remove lernsperre
```

## Entwickeln

```bash
git clone https://github.com/janiktest/lernsperre.git && cd lernsperre
./install.sh              # ohne .deb installieren (nur für deinen Benutzer)
cd daemon && pytest -q    # Tests
```

Aufbau, Releases und mehr: [docs/ENTWICKLUNG.md](docs/ENTWICKLUNG.md)

## Stand

- [x] Erkennung, Zeitzähler, Sperre mit Anki, .deb mit automatischen Releases
- [x] Panel-Menü, Einstellungen, Entsperren nach Zeit oder Karten, mehrere Bildschirme, Anki-Auswahl
- [ ] Browser-Erweiterung für Firefox (genaue Adresse, Ton im Tab)
- [ ] Einführung beim ersten Start, Hinweis wenn die Überwachung aus war

## Mehr

- **[Anleitung](docs/ANLEITUNG.md)**: Menü, Einstellungen, Ziele, alle Befehle, Probleme lösen
- **[Changelog](CHANGELOG.md)**: was sich in welcher Version geändert hat
