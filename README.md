# LernSperre

Sperrt YouTube, Instagram & Co. nach einer einstellbaren Zeit, bis du in Anki gelernt hast. Für Ubuntu mit GNOME, funktioniert mit der offiziellen Anki-App.

> LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

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

## Mehr

- **[Anleitung](docs/ANLEITUNG.md)**: Menü, Einstellungen, Ziele, alle Befehle, Probleme lösen
- **[Changelog](CHANGELOG.md)**: was sich in welcher Version geändert hat
- **[Entwicklung](docs/ENTWICKLUNG.md)**: Aufbau, ohne .deb installieren, Tests, Releases
