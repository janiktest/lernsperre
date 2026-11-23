"""Einstellungen laden (~/.config/lernsperre/config.toml)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lernsperre"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lernsperre"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
# LernSperre – Einstellungen
# Änderungen werden nach dem Speichern automatisch übernommen.
# Anleitung: https://github.com/janiktest/lernsperre/blob/main/docs/ANLEITUNG.md
#
# LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

# --- Zeit zum Schauen -------------------------------------------------------

# Erlaubte Zeit auf Zielen, bis gesperrt wird (Minuten)
allowed_minutes = 20

# Warnung so viele Sekunden vor der Sperre (0 = aus)
warn_seconds = 60

# --- Entsperren durch Lernen in Anki -----------------------------------------

# Es zählt, was hier NICHT auskommentiert ist (# davor = aus):
#   nur learn_minutes  -> entsperrt nach der Lernzeit
#   nur min_cards      -> entsperrt nach so vielen beantworteten Karten, ohne Zeitvorgabe
#   beide              -> entsperrt erst, wenn beides erreicht ist
#   keins von beiden   -> Standard: 5 Minuten Lernzeit
learn_minutes = 5      # Lernzeit in Minuten
# min_cards = 20       # Mindestanzahl beantworteter Karten

# Lernzeit zählt nur, wenn Anki vorne ist und die letzte beantwortete Karte
# höchstens so viele Sekunden her ist (sonst pausiert die Lernzeit)
idle_seconds = 60

# Während der Sperre laufende Wiedergabe (Video/Musik) pausieren
pause_media_on_lock = true

# --- Pausieren ---------------------------------------------------------------

# Auswahl im Menü „Pausieren“ (Minuten). Während einer Sperre geht Pausieren nicht.
pause_minutes = [15, 30, 60]

# --- Anzeige oben im Panel ---------------------------------------------------

icon_free = "⏳"              # normal, mit verbleibender Zeit
icon_locked = "🔒"            # Sperre aktiv
icon_paused = "☕"            # pausiert
icon_learning = "▶"           # Lernzeit läuft gerade
icon_learning_paused = "⏸"    # Lernzeit wartet (Anki nicht vorne / keine Antwort)
show_time = true              # Zeit neben dem Emoji anzeigen

# --- Sonstiges ---------------------------------------------------------------

# Programm zum Öffnen dieser Datei über „Einstellungen“, z. B. "gedit"
# oder "gnome-text-editor". Leer = Standard-Texteditor.
editor = ""

# Woran das Anki-Fenster erkannt wird (App-ID / WM_CLASS, Teilstring, ohne Groß/klein)
anki_app_ids = ["net.ankiweb.Anki", "anki"]

# Welches Anki gestartet wird. Alle Installationen zeigt `lernsperre detect-ankis`,
# auswählen mit `lernsperre use-anki N`.
# Leer = über anki_desktop_id. Sonst ein Befehl (z. B. "flatpak run net.ankiweb.Anki"),
# ein Programm (z. B. "/usr/local/bin/anki") oder ein Ordner, in dem Anki liegt.
anki_launch = ""

# Desktop-Datei zum Starten von Anki (wenn anki_launch leer ist)
anki_desktop_id = "net.ankiweb.Anki.desktop"

# Pfad zu collection.anki2. Leer = automatisch suchen (Flatpak und normale Installation)
anki_collection = ""

# Ziele: ein Ziel passt, wenn der Fenstertitel einen der `titles` enthält,
# die App-ID / WM_CLASS einen der `apps` enthält oder die Adresse eine der `urls`.
# Titel mit "re:" am Anfang sind reguläre Ausdrücke.

[[targets]]
name = "YouTube"
titles = ["YouTube"]
urls = ["youtube.com", "youtu.be"]

[[targets]]
name = "Instagram"
titles = ["Instagram"]
urls = ["instagram.com"]

[[targets]]
name = "TikTok"
titles = ["TikTok"]
urls = ["tiktok.com"]

[[targets]]
name = "Netflix"
titles = ["Netflix"]
urls = ["netflix.com"]

[[targets]]
name = "Reddit"
titles = ["Reddit"]
urls = ["reddit.com"]

[[targets]]
name = "X/Twitter"
titles = ["re:/ X( [—-] |$)", "re:\\bTwitter\\b"]
urls = ["x.com", "twitter.com"]
"""


@dataclass
class Target:
    name: str
    titles: list[str] = field(default_factory=list)
    apps: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)


@dataclass
class Config:
    allowed_minutes: float = 20
    learn_minutes: float | None = 5  # None = Lernzeit zählt nicht
    warn_seconds: float = 60
    idle_seconds: float = 60
    pause_media_on_lock: bool = True
    min_cards: int | None = None  # None = Kartenzahl zählt nicht
    pause_minutes: list[int] = field(default_factory=lambda: [15, 30, 60])
    icon_free: str = "⏳"
    icon_locked: str = "🔒"
    icon_paused: str = "☕"
    icon_learning: str = "▶"
    icon_learning_paused: str = "⏸"
    show_time: bool = True
    editor: str = ""
    anki_app_ids: list[str] = field(default_factory=lambda: ["net.ankiweb.Anki", "anki"])
    anki_desktop_id: str = "net.ankiweb.Anki.desktop"
    anki_launch: str = ""
    anki_collection: str = ""
    targets: list[Target] = field(default_factory=list)

    @property
    def allowed_seconds(self) -> float:
        return max(1.0, self.allowed_minutes * 60)

    @property
    def learn_seconds(self) -> float:
        return max(1.0, self.learn_minutes * 60) if self.learn_minutes is not None else 0.0

    @property
    def unlock_mode(self) -> str:
        """"time", "cards" oder "both" – je nachdem, was in der Datei steht."""
        if self.learn_minutes is not None and self.min_cards is not None:
            return "both"
        return "cards" if self.min_cards is not None else "time"


def parse_config(text: str) -> Config:
    raw = tomllib.loads(text)
    targets = [
        Target(
            name=str(t.get("name", "?")),
            titles=[str(x) for x in t.get("titles", [])],
            apps=[str(x) for x in t.get("apps", [])],
            urls=[str(x) for x in t.get("urls", [])],
        )
        for t in raw.get("targets", [])
    ]
    cfg = Config(targets=targets)
    for key in (
        "allowed_minutes", "learn_minutes", "warn_seconds", "idle_seconds",
        "pause_media_on_lock", "pause_minutes",
        "icon_free", "icon_locked", "icon_paused", "icon_learning",
        "icon_learning_paused", "show_time", "editor",
        "anki_app_ids", "anki_desktop_id", "anki_collection", "anki_launch",
    ):
        if key in raw:
            setattr(cfg, key, raw[key])
    # Entsperren: was in der Datei steht, zählt. Steht keins von beiden da: 5 min.
    cfg.learn_minutes = float(raw["learn_minutes"]) if "learn_minutes" in raw else None
    cfg.min_cards = max(1, int(raw["min_cards"])) if "min_cards" in raw else None
    if cfg.learn_minutes is None and cfg.min_cards is None:
        cfg.learn_minutes = 5.0
    cfg.pause_minutes = [int(m) for m in cfg.pause_minutes if int(m) > 0]
    return cfg


def add_missing_options(text: str) -> str:
    """Ergänzt in einer älteren Einstellungsdatei neue Optionen mit Standardwert.

    Die Zeilen kommen vor die erste Tabelle ([[targets]]), damit sie in TOML
    nicht zu einem Ziel gehören. Eigene Werte bleiben unverändert.
    """
    # learn_minutes/min_cards darf man absichtlich auskommentieren
    present = set(tomllib.loads(text)) | {"learn_minutes", "min_cards"}
    default_lines = DEFAULT_CONFIG.split("[[targets]]")[0].splitlines()
    missing = []
    for i, line in enumerate(default_lines):
        key = line.split("=")[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key and key not in present:
            comments = []
            j = i - 1
            while j >= 0 and default_lines[j].startswith("#") and not default_lines[j].startswith("# ---"):
                comments.insert(0, default_lines[j])
                j -= 1
            missing += comments + [line, ""]
    if not missing:
        return text
    block = "# --- Neu hinzugekommene Einstellungen ---\n" + "\n".join(missing) + "\n"
    lines = text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("["):
            return "".join(lines[:idx]) + block + "".join(lines[idx:])
    return text.rstrip("\n") + "\n\n" + block


_OLD_UNLOCK_COMMENTS = {
    "# Wie wird entsperrt?",
    '#   "time"  = nach einer Lernzeit (learn_minutes)',
    '#   "cards" = nach einer Anzahl beantworteter Karten (min_cards), ohne Zeitvorgabe',
    '#   "both"  = erst wenn beides erreicht ist',
    '# Lernzeit zum Entsperren (Minuten), gilt bei "time" und "both"',
    '# Mindestanzahl beantworteter Karten, gilt bei "cards" und "both"',
}
UNLOCK_HELP = [line for line in DEFAULT_CONFIG.splitlines() if line.startswith("#")
               and ("NICHT auskommentiert" in line or "->" in line)]


def migrate_unlock_mode(text: str) -> str:
    """Wandelt das alte `unlock_mode` (0.2.0) um: Nicht benutztes wird auskommentiert."""
    raw = tomllib.loads(text)
    if "unlock_mode" not in raw:
        return text
    mode = raw["unlock_mode"]
    off = {"time": "min_cards", "cards": "learn_minutes"}.get(mode)
    out: list[str] = []
    inserted = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^unlock_mode\s*=", stripped) or stripped in _OLD_UNLOCK_COMMENTS:
            continue
        key = re.match(r"^#?\s*(learn_minutes|min_cards)\s*=", stripped)
        if key and not inserted:
            out += UNLOCK_HELP
            inserted = True
        if key and key.group(1) == off and not stripped.startswith("#"):
            line = "# " + line
        if key and out and out[-1] == "" and re.match(r"^#?\s*(learn_minutes|min_cards)\s*=", out[-2] if len(out) > 1 else ""):
            out.pop()  # beide direkt untereinander
        out.append(line)
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out)) + "\n"
    return result


def load_config(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    cfg = parse_config(text)  # Fehler erst melden, bevor etwas geändert wird
    updated = add_missing_options(migrate_unlock_mode(text))
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        cfg = parse_config(updated)
    return cfg
