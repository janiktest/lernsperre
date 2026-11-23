"""Einstellungen laden (~/.config/lernsperre/config.toml)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lernsperre"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lernsperre"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
# LernSperre – Einstellungen
# Nach Änderungen: `lernsperre reload` (oder den Dienst neu starten).
#
# LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.

# Erlaubte Zeit auf Zielen, bis gesperrt wird (Minuten)
allowed_minutes = 20

# So lange muss in Anki gelernt werden, um zu entsperren (Minuten)
learn_minutes = 5

# Warnung so viele Sekunden vor der Sperre (0 = aus)
warn_seconds = 60

# Lernzeit zählt nur, wenn die letzte beantwortete Karte höchstens
# so viele Sekunden her ist (sonst pausiert die Lernzeit)
idle_seconds = 60

# Während der Sperre laufende Wiedergabe (MPRIS) pausieren
pause_media_on_lock = true

# Woran das Anki-Fenster erkannt wird (App-ID / WM_CLASS, Teilstring, ohne Groß/klein)
anki_app_ids = ["net.ankiweb.Anki", "anki"]

# Desktop-Datei zum Starten von Anki
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
    learn_minutes: float = 5
    warn_seconds: float = 60
    idle_seconds: float = 60
    pause_media_on_lock: bool = True
    anki_app_ids: list[str] = field(default_factory=lambda: ["net.ankiweb.Anki", "anki"])
    anki_desktop_id: str = "net.ankiweb.Anki.desktop"
    anki_collection: str = ""
    targets: list[Target] = field(default_factory=list)

    @property
    def allowed_seconds(self) -> float:
        return max(1.0, self.allowed_minutes * 60)

    @property
    def learn_seconds(self) -> float:
        return max(1.0, self.learn_minutes * 60)


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
        "allowed_minutes",
        "learn_minutes",
        "warn_seconds",
        "idle_seconds",
        "pause_media_on_lock",
        "anki_app_ids",
        "anki_desktop_id",
        "anki_collection",
    ):
        if key in raw:
            setattr(cfg, key, raw[key])
    return cfg


def load_config(path: Path = CONFIG_FILE) -> Config:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return parse_config(path.read_text(encoding="utf-8"))
