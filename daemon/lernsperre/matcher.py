"""Prüft, ob ein Fenster oder eine Wiedergabe zu einem Ziel passt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .config import Config, Target


@dataclass
class Window:
    title: str = ""
    wm_class: str = ""
    app_id: str = ""
    focused: bool = False
    minimized: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Window":
        return cls(
            title=str(d.get("title") or ""),
            wm_class=str(d.get("wm_class") or ""),
            app_id=str(d.get("app_id") or ""),
            focused=bool(d.get("focused")),
            minimized=bool(d.get("minimized")),
        )

    @property
    def ids(self) -> str:
        return f"{self.app_id}\n{self.wm_class}".lower()


@dataclass
class Player:
    """Ein MPRIS-Player (z. B. Firefox, VLC, Spotify)."""

    bus_name: str
    playing: bool = False
    identity: str = ""
    desktop_entry: str = ""
    title: str = ""
    url: str = ""

    @property
    def app_key(self) -> str:
        """Kurzname für die Zuordnung zu Fenstern, z. B. 'firefox'."""
        if self.desktop_entry:
            return self.desktop_entry.lower().removesuffix(".desktop")
        # org.mpris.MediaPlayer2.firefox.instance_1_23 -> firefox
        rest = self.bus_name.removeprefix("org.mpris.MediaPlayer2.")
        return rest.split(".")[0].lower()


@lru_cache(maxsize=256)
def _regex(pattern: str) -> re.Pattern | None:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def title_matches(title: str, patterns: list[str]) -> bool:
    if not title:
        return False
    low = title.lower()
    for p in patterns:
        if not p:
            continue
        if p.startswith("re:"):
            rx = _regex(p[3:])
            if rx and rx.search(title):
                return True
        elif p.lower() in low:
            return True
    return False


def url_matches(url: str, patterns: list[str]) -> bool:
    if not url:
        return False
    m = re.match(r"^[a-z][a-z0-9+.-]*://([^/:?#]+)", url.lower())
    host = m.group(1) if m else url.lower()
    for p in patterns:
        p = p.lower().strip()
        if p and (host == p or host.endswith("." + p)):
            return True
    return False


def target_for_window(cfg: Config, w: Window) -> Target | None:
    for t in cfg.targets:
        if title_matches(w.title, t.titles):
            return t
        if any(a and a.lower() in w.ids for a in t.apps):
            return t
    return None


def target_for_player(cfg: Config, p: Player) -> Target | None:
    for t in cfg.targets:
        if url_matches(p.url, t.urls) or title_matches(p.title, t.titles):
            return t
        if any(a and (a.lower() in p.app_key or a.lower() in p.identity.lower()) for a in t.apps):
            return t
    return None


def is_anki(cfg: Config, w: Window | None) -> bool:
    if w is None:
        return False
    return any(a and a.lower() in w.ids for a in cfg.anki_app_ids)


def window_belongs_to_player(w: Window, p: Player) -> bool:
    key = p.app_key
    return bool(key) and key in w.ids
