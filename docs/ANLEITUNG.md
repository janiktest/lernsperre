# LernSperre – Anleitung

LernSperre zählt, wie lange du auf YouTube, Instagram, TikTok, Netflix, Reddit oder X/Twitter bist. Ist die erlaubte Zeit um, wird der Bildschirm gesperrt, bis du in Anki gelernt hast. Danach beginnt die erlaubte Zeit von vorn.

> LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

GitHub: <https://github.com/janiktest/lernsperre>

---

## 1. Installieren

1. Die neueste `lernsperre_…_all.deb` unter [Releases](https://github.com/janiktest/lernsperre/releases/latest) herunterladen.
2. Per Doppelklick installieren oder im Terminal:
   ```bash
   sudo apt install ./Downloads/lernsperre_*_all.deb
   ```
3. **Einmal ab- und wieder anmelden.** GNOME lädt neue Erweiterungen erst bei der nächsten Anmeldung. Danach startet LernSperre bei jeder Anmeldung von selbst.

Voraussetzungen: Ubuntu mit GNOME (ab GNOME 48, z. B. Ubuntu 26.04) und Anki als Flatpak (`net.ankiweb.Anki`). Eine normale Anki-Installation (`~/.local/share/Anki2`) wird auch gefunden.

**Update:** die neue .deb genauso installieren. Ob du dich danach neu anmelden musst oder `systemctl --user restart lernsperre` reicht, steht bei jedem [Release](https://github.com/janiktest/lernsperre/releases) und im [Changelog](../CHANGELOG.md). Deine Einstellungen bleiben erhalten, neue Optionen werden automatisch in deine Einstellungsdatei eingefügt.

**Entfernen:** `sudo apt remove lernsperre`

---

## 2. Das Panel-Symbol

Oben rechts in der GNOME-Leiste, links neben WLAN, Lautstärke und Akku, steht LernSperre:

| Anzeige | Bedeutung |
| --- | --- |
| `⏳ 12:34` | noch 12 min 34 s erlaubt (gelb ab der letzten Minute) |
| `☕ 9:59` | pausiert, noch 9:59 Pause |
| `🔒 4:12 ▶` | gesperrt, Lernzeit läuft gerade |
| `🔒 4:12 ⏸` | gesperrt, Lernzeit wartet (Anki nicht vorne oder keine Karte beantwortet) |
| `🔒 7/20` | gesperrt, 7 von 20 Karten beantwortet (Karten-Modus) |
| `LS –` | LernSperre läuft nicht |

Die Emojis kannst du in den Einstellungen ändern.

### Menü (auf das Symbol klicken)

| Eintrag | Was passiert |
| --- | --- |
| Statuszeile | was gerade zählt und wie viel Zeit noch übrig ist |
| Anki öffnen | holt Anki nach vorne oder startet es |
| Sperre jetzt aktivieren | sperrt sofort, z. B. wenn du gleich lernen willst |
| Pausieren ▸ 15 / 30 / 60 Minuten | in dieser Zeit wird nichts gezählt (nicht während einer Sperre) |
| Pause beenden | zählt sofort wieder |
| Bonuszeit durch Lernen | Schalter: Ist er an, bringen freiwillig beantwortete Karten mehr erlaubte Zeit (siehe unten) |
| Zähler zurücksetzen | die erlaubte Zeit beginnt von vorn |
| Einstellungen | öffnet die Einstellungsdatei im Texteditor |
| Anleitung | diese Seite |
| GitHub-Seite | das Projekt auf GitHub |
| LernSperre beenden | beendet LernSperre bis zur nächsten Anmeldung (nicht während einer Sperre) |
| LernSperre starten | erscheint, wenn LernSperre nicht läuft |
| Dienst neu starten | führt `systemctl --user restart lernsperre` aus, z. B. nach einem Update ohne Änderung an der Erweiterung |
| Erweiterung neu laden | führt `gnome-extensions disable …` und `enable …` aus, z. B. wenn die Sperre hängt. Neuen Code nach einem Update lädt GNOME trotzdem erst beim Anmelden |

Bei den Einträgen, die einen Befehl ausführen, zeigt das Menü den Befehl an, wenn du mit der Maus darüberfährst.

---

## 3. Was gezählt wird

Die Zeit läuft, wenn

- ein **Ziel-Fenster vorne** ist (z. B. ein Firefox-Fenster mit „YouTube“ im Titel, oder eine App wie die Netflix-App), oder
- gerade **Video oder Ton von einem Ziel läuft**, auch wenn ein anderes Fenster vorne ist (z. B. YouTube-Musik im Hintergrund). Das erkennt LernSperre über MPRIS, die Wiedergabe-Schnittstelle, die auch die Medientasten benutzen.

Eine Minute vor der Sperre kommt eine Benachrichtigung.

Hinweis: Firefox zeigt im Fenstertitel nur den **aktiven Tab**. Ein YouTube-Tab im Hintergrund ohne Ton zählt nicht.

---

## 4. Die Sperre

- Ein Vollbild-Overlay liegt über allem, bei mehreren Bildschirmen über allen. Text und Knöpfe stehen nur auf dem Hauptbildschirm, die anderen werden abgedunkelt. **Nur Anki ist erlaubt.** Wechselst du zu einem anderen Fenster, kommt das Overlay sofort zurück.
- Laufende Wiedergabe (Video, Musik) wird pausiert.
- Mit **„Anki öffnen“** kommst du zu Anki. Läuft Anki schon, wird nur das Fenster nach vorne geholt. Das Deck wählst du in Anki selbst.
- Welches Anki gestartet wird, stellst du mit `anki_launch` ein (siehe [Welches Anki?](#welches-anki)).

### Wie du entsperrst

In den Einstellungen stehen `learn_minutes` und `min_cards` direkt untereinander. **Es zählt, was nicht auskommentiert ist** (`#` am Zeilenanfang = aus):

```toml
learn_minutes = 5      # Lernzeit in Minuten
# min_cards = 20       # Mindestanzahl beantworteter Karten
```

| In der Datei aktiv | Entsperrt, wenn … |
| --- | --- |
| nur `learn_minutes` (Standard) | du so lange gelernt hast. Die Lernzeit läuft nur, solange Anki vorne ist und du Karten beantwortest. Nach `idle_seconds` (60 s) ohne Antwort wartet sie. |
| nur `min_cards` | du so viele Karten beantwortet hast, egal wie lange es dauert. Antworten vom Handy (AnkiDroid/AnkiMobile) zählen auch, sobald sie synchronisiert sind. |
| beide | beides erreicht ist |
| keins von beiden | Standard: 5 Minuten Lernzeit |

Gezählt wird nur, was nach Beginn der Sperre beantwortet wurde. LernSperre liest dafür nur lesend in deiner Anki-Sammlung (Tabelle `revlog`). Es wird kein Anki-Add-on gebraucht und nichts in Anki verändert.

Während einer Sperre prüft LernSperre jede Sekunde. Solange die Anki-Desktop-App offen ist, sperrt sie ihre Datenbank. Dann kopiert LernSperre sie nach `~/.cache/lernsperre` (die große Datei einmal, die kleine `collection.anki2-wal` bei jeder Änderung) und liest die Kopie. Dort stehen auch deine neuesten Antworten, denn Anki schreibt jede Antwort zuerst in die WAL-Datei. Die Kopie wird nur gelesen, nie zurückgeschrieben und nach der Sperre gelöscht. Ankis Dateien und die Synchronisierung bleiben unberührt.

### Bonuszeit durch freiwilliges Lernen

Im Menü gibt es den Schalter **„Bonuszeit durch Lernen“** (oder `lernsperre bonus an` / `aus`). Ist er an, bringen je `bonus_cards` Karten (Standard 10), die du außerhalb einer Sperre in Anki beantwortest, `bonus_minutes` (Standard 5) mehr erlaubte Zeit. Es zählen nur Karten ab dem Einschalten bzw. ab dem letzten Entsperren. Die Restzeit kann dadurch auch über `allowed_minutes` steigen. Den Fortschritt zeigt die erste Zeile im Menü.

Nur solange der Schalter an ist, liest LernSperre auch außerhalb einer Sperre in Anki mit (über die Kopie in `~/.cache/lernsperre`). Ist er aus, passiert das nur während einer Sperre.

### Notfall

Unten auf dem Overlay ist **„Notfall: Sperre aufheben“**. Zweimal klicken hebt die Sperre auf, z. B. wenn Anki nicht startet. Ohne Overlay geht im Terminal `lernsperre reset`.

---

## 5. Einstellungen

Menü → **Einstellungen** öffnet `~/.config/lernsperre/config.toml` im Texteditor (oder im Terminal: `lernsperre edit`). **Nach dem Speichern werden die Änderungen automatisch übernommen**, ein Neustart ist nicht nötig. Ist die Datei fehlerhaft, gibt es eine Benachrichtigung, und die alten Einstellungen bleiben aktiv.

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `allowed_minutes` | `20` | erlaubte Zeit auf Zielen bis zur Sperre |
| `warn_seconds` | `60` | Warnung so viele Sekunden vorher (`0` = aus) |
| `learn_minutes` | `5` | Lernzeit zum Entsperren (auskommentieren = zählt nicht, siehe oben) |
| `min_cards` | auskommentiert | Mindestanzahl Karten zum Entsperren (aktiv = zählt) |
| `idle_seconds` | `60` | Lernzeit wartet, wenn so lange keine Karte beantwortet wurde |
| `pause_media_on_lock` | `true` | Wiedergabe bei der Sperre pausieren |
| `pause_minutes` | `[15, 30, 60]` | Auswahl im Menü „Pausieren“ |
| `bonus_cards` | `10` | so viele Karten bringen Bonuszeit (wenn der Schalter an ist) |
| `bonus_minutes` | `5` | so viele Minuten Bonuszeit |
| `icon_free` | `"⏳"` | Panel-Emoji normal |
| `icon_locked` | `"🔒"` | Panel-Emoji bei Sperre |
| `icon_paused` | `"☕"` | Panel-Emoji bei Pause |
| `icon_learning` | `"▶"` | Lernzeit läuft |
| `icon_learning_paused` | `"⏸"` | Lernzeit wartet |
| `show_time` | `true` | Zeit neben dem Emoji anzeigen |
| `editor` | `""` | Programm für „Einstellungen“, z. B. `"gedit"`. Leer = Standard-Texteditor |
| `anki_app_ids` | `["net.ankiweb.Anki", "anki"]` | woran das Anki-Fenster erkannt wird |
| `anki_launch` | `""` | welches Anki gestartet wird: Befehl, Programm oder Ordner (siehe unten). Leer = über `anki_desktop_id` |
| `anki_desktop_id` | `"net.ankiweb.Anki.desktop"` | Desktop-Datei zum Starten, wenn `anki_launch` leer ist |
| `anki_collection` | `""` | Pfad zu `collection.anki2`, leer = automatisch (neuestes Profil) |

### Einstellungen zurücksetzen oder aufräumen

Nach ein paar Updates kann die Datei unübersichtlich werden, weil neue Optionen unten angehängt werden.

```bash
lernsperre reset-config --behalten   # neu und übersichtlich, deine Werte und Ziele bleiben
lernsperre reset-config              # alles auf Standard
```

Die alte Datei wird vorher als `~/.config/lernsperre/config.toml.bak-<Datum>` gesichert. Kommentare, die du selbst geschrieben hast, übernimmt `--behalten` nicht, die stehen aber im Backup.

### Welches Anki?

Hast du mehrere Anki-Installationen (z. B. Flatpak und den Installer von ankiweb.net), kann LernSperre das falsche starten. So stellst du das richtige ein:

```bash
lernsperre detect-ankis     # listet alle gefundenen Installationen mit Nummer
lernsperre use-anki 2       # Nummer 2 benutzen
```

`detect-ankis` sucht Flatpak, Snap, deb-Pakete, den Installer bzw. Launcher von ankiweb.net (`/usr/local/bin/anki`, `~/.local/share/AnkiProgramFiles`), `/opt/anki*`, pip/uv (`~/.local/bin/anki`) und AppImages in `~/Applications`, `~/Downloads` und `~`. Zu jeder Installation zeigt es den Datenordner und die Profile.

`use-anki` trägt `anki_launch` und `anki_collection` (zuletzt benutztes Profil) in deine Einstellungen ein. Von Hand geht es auch:

```toml
anki_launch = "flatpak run net.ankiweb.Anki"   # ein Befehl
anki_launch = "/usr/local/bin/anki"            # ein Programm
anki_launch = "~/Programme/anki-25.02"         # ein Ordner, in dem Anki liegt
```

### Ziele bearbeiten

Jedes Ziel ist ein `[[targets]]`-Block. Ein Ziel passt, wenn

- der **Fenstertitel** einen Eintrag aus `titles` enthält (Groß/klein egal; mit `re:` davor ein regulärer Ausdruck),
- die **App-ID oder WM_CLASS** einen Eintrag aus `apps` enthält (für native Apps), oder
- die **Adresse** zu `urls` passt (für eine spätere Browser-Erweiterung und Player, die ihre Adresse melden).

Beispiele:

```toml
[[targets]]
name = "Twitch"
titles = ["Twitch"]
urls = ["twitch.tv"]

[[targets]]
name = "Spotify"
apps = ["spotify"]
```

Ein Ziel entfernen: den ganzen Block löschen.

Titel, App-ID und WM_CLASS des Fensters, das gerade vorne ist, zeigt `lernsperre status` (Zeile „Vorderes Fenster“).

---

## 6. Befehle im Terminal

Tipp: `lernsperre ` tippen und zweimal **Tab** drücken, dann werden alle Befehle vorgeschlagen.

```text
lernsperre                 Zustand anzeigen
lernsperre status          verbleibende Zeit, was gerade zählt, Sperre
lernsperre lock            Sperre jetzt aktivieren
lernsperre pause [MIN]     MIN Minuten pausieren (Standard 30, nicht während einer Sperre)
lernsperre resume          Pause beenden
lernsperre bonus an|aus    Bonuszeit durch freiwilliges Lernen an- oder ausschalten
lernsperre reset           Zähler zurücksetzen bzw. Sperre aufheben (Notfall)
lernsperre edit            Einstellungen im Texteditor öffnen
lernsperre detect-ankis    alle Anki-Installationen suchen
lernsperre use-anki N      Installation Nr. N aus detect-ankis einstellen
lernsperre config          Pfad der Einstellungsdatei ausgeben
lernsperre reset-config    Einstellungen auf Standard zurücksetzen (Backup als config.toml.bak-…)
lernsperre reset-config --behalten
                           Datei neu und übersichtlich schreiben, deine Werte und Ziele bleiben
lernsperre reload          Einstellungen sofort neu laden (passiert sonst automatisch)
lernsperre quit            LernSperre beenden (bis zur nächsten Anmeldung)
lernsperre start           LernSperre wieder starten
lernsperre json            Zustand als JSON (zur Fehlersuche)
lernsperre run             im Vordergrund starten (zum Testen, vorher `lernsperre quit`)
lernsperre hilfe           Übersicht aller Befehle
```

Weitere nützliche Befehle:

```bash
journalctl --user -u lernsperre -f                          # Protokoll des Dienstes
systemctl --user status lernsperre                          # läuft der Dienst?
gnome-extensions info lernsperre@janiktest.github.io        # ist die Erweiterung an?
gnome-extensions enable lernsperre@janiktest.github.io      # Erweiterung einschalten
```

---

## 7. Wo liegt was?

| Pfad | Inhalt |
| --- | --- |
| `~/.config/lernsperre/config.toml` | deine Einstellungen |
| `~/.local/share/lernsperre/state.db` | Zähler und Ereignisse (SQLite) |
| `/usr/lib/lernsperre/` | Programm |
| `/usr/share/gnome-shell/extensions/lernsperre@janiktest.github.io/` | GNOME-Erweiterung |
| `/usr/lib/systemd/user/lernsperre.service` | Autostart beim Anmelden |

---

## 8. Probleme

| Problem | Lösung |
| --- | --- |
| Kein Symbol oben rechts | einmal ab- und wieder anmelden; dann `gnome-extensions enable lernsperre@janiktest.github.io` |
| Symbol zeigt `LS –` | Menü → „LernSperre starten“ oder `lernsperre start` |
| Falsches Anki wird geöffnet | `lernsperre detect-ankis`, dann `lernsperre use-anki N` |
| Lernzeit läuft nicht, obwohl ich lerne | Anki muss vorne sein. `lernsperre status` zeigt, ob die Anki-Sammlung gefunden wurde; sonst in den Einstellungen `anki_collection` setzen |
| Eine Seite wird nicht erkannt | als Ziel mit einem Wort aus dem Fenstertitel eintragen |
| Etwas wird fälschlich gezählt | `lernsperre status` zeigt, welches Ziel zählt; den passenden Eintrag in `titles` genauer machen |

---

## Ehrlich gesagt

LernSperre ist eine **Selbstdisziplin-Sperre**, keine Kindersicherung. Wer die Erweiterung abschaltet, LernSperre beendet oder den Notausgang nimmt, kommt drum herum.
