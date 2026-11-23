"""Die eigentliche Logik: Zeit zählen, sperren, Lernzeit in Anki zählen.

Ohne D-Bus und ohne Uhr, damit sie sich leicht testen lässt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import Config
from .matcher import (
    Player,
    Window,
    is_anki,
    target_for_player,
    target_for_window,
    window_belongs_to_player,
)

MAX_TICK = 5.0  # größere Sprünge (z. B. Standby) zählen nicht


@dataclass
class Signals:
    windows: list[Window] | None = None  # None = GNOME-Erweiterung meldet sich nicht
    players: list[Player] = field(default_factory=list)
    last_answer: float | None = None  # Unix-Sekunden der letzten Anki-Antwort
    cards_since_lock: int | None = None  # beantwortete Karten seit Beginn der Sperre

    @property
    def focused(self) -> Window | None:
        for w in self.windows or []:
            if w.focused:
                return w
        return None


@dataclass
class State:
    mode: str = "free"  # "free" oder "locked"
    used: float = 0.0  # gezählte Sekunden auf Zielen seit dem letzten Entsperren
    learned: float = 0.0  # gezählte Lernsekunden in der aktuellen Sperre
    warned: bool = False
    lock_started: float = 0.0
    cards_done: int = 0  # beantwortete Karten in der aktuellen Sperre
    paused_until: float = 0.0
    unmonitored: float = 0.0  # Sekunden ohne Meldung der GNOME-Erweiterung (gesamt)

    @classmethod
    def from_dict(cls, d: dict | None) -> "State":
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


@dataclass
class Activity:
    target: str | None = None
    reason: str = ""  # "vorne", "Wiedergabe", "Wiedergabe im Hintergrund"


def detect_activity(cfg: Config, sig: Signals) -> Activity:
    focused = sig.focused
    if focused is not None:
        t = target_for_window(cfg, focused)
        if t:
            return Activity(t.name, "vorne")
    playing = [p for p in sig.players if p.playing]
    for p in playing:
        t = target_for_player(cfg, p)
        if t:
            return Activity(t.name, "Wiedergabe")
    # Wiedergabe in einem Browser, dessen (Hintergrund-)Fenster ein Ziel zeigt,
    # z. B. YouTube-Tab läuft weiter, während ein anderes Fenster vorne ist.
    for p in playing:
        for w in sig.windows or []:
            if window_belongs_to_player(w, p):
                t = target_for_window(cfg, w)
                if t:
                    return Activity(t.name, "Wiedergabe im Hintergrund")
    return Activity()


class Engine:
    def __init__(self, cfg: Config, state: State | None = None):
        self.cfg = cfg
        self.state = state or State()
        self.activity = Activity()
        self.learning_active = False
        self.anki_focused = False
        self.now = 0.0

    # --- Aktionen -------------------------------------------------------
    def lock(self, now: float) -> list[tuple]:
        if self.state.mode == "locked":
            return []
        self.state.mode = "locked"
        self.state.learned = 0.0
        self.state.cards_done = 0
        self.state.lock_started = now
        self.state.paused_until = 0.0
        return [("locked",)]

    def unlock(self) -> list[tuple]:
        self.state.mode = "free"
        self.state.used = 0.0
        self.state.learned = 0.0
        self.state.cards_done = 0
        self.state.warned = False
        return [("unlocked",)]

    def pause(self, now: float, minutes: float) -> list[tuple]:
        """Pausiert das Zählen. Während einer Sperre nicht möglich."""
        if self.state.mode == "locked" or minutes <= 0:
            return []
        self.state.paused_until = now + minutes * 60
        return [("paused", minutes)]

    def resume(self) -> list[tuple]:
        if self.state.paused_until == 0:
            return []
        self.state.paused_until = 0.0
        return [("resumed",)]

    def is_paused(self, now: float) -> bool:
        return self.state.mode == "free" and now < self.state.paused_until

    def unlock_reached(self) -> bool:
        st, cfg = self.state, self.cfg
        time_ok = st.learned >= cfg.learn_seconds
        cards_ok = st.cards_done >= cfg.min_cards
        if cfg.unlock_mode == "cards":
            return cards_ok
        if cfg.unlock_mode == "both":
            return time_ok and cards_ok
        return time_ok

    def reset(self) -> list[tuple]:
        was_locked = self.state.mode == "locked"
        self.unlock()
        return [("unlocked",)] if was_locked else [("reset",)]

    # --- Takt -----------------------------------------------------------
    def tick(self, now: float, dt: float, sig: Signals) -> list[tuple]:
        events: list[tuple] = []
        dt = dt if 0 < dt <= MAX_TICK else 0.0
        st = self.state
        if sig.windows is None:
            st.unmonitored += dt

        self.anki_focused = is_anki(self.cfg, sig.focused)

        self.now = now
        if st.mode == "free" and st.paused_until and now >= st.paused_until:
            st.paused_until = 0.0
            events.append(("resumed",))
        if st.mode == "free" and self.is_paused(now):
            self.learning_active = False
            self.activity = Activity()
        elif st.mode == "free":
            self.learning_active = False
            self.activity = detect_activity(self.cfg, sig)
            if self.activity.target:
                st.used += dt
            remaining = self.cfg.allowed_seconds - st.used
            if (
                self.cfg.warn_seconds > 0
                and not st.warned
                and 0 < remaining <= self.cfg.warn_seconds
            ):
                st.warned = True
                events.append(("warn", remaining))
            if remaining <= 0:
                events += self.lock(now)
        else:
            self.activity = Activity()
            la = sig.last_answer
            self.learning_active = (
                self.anki_focused
                and la is not None
                and la >= st.lock_started
                and now - la <= self.cfg.idle_seconds
            )
            if self.learning_active:
                st.learned += dt
            if sig.cards_since_lock is not None:
                st.cards_done = max(st.cards_done, sig.cards_since_lock)
            if self.unlock_reached():
                events += self.unlock()
            elif self.cfg.pause_media_on_lock and any(p.playing for p in sig.players):
                events.append(("pause_media",))
        return events

    # --- Anzeige --------------------------------------------------------
    def snapshot(self) -> dict:
        st = self.state
        return {
            "mode": st.mode,
            "allowed": self.cfg.allowed_seconds,
            "used": round(st.used, 1),
            "remaining": round(max(0.0, self.cfg.allowed_seconds - st.used), 1),
            "learn_required": self.cfg.learn_seconds,
            "learned": round(st.learned, 1),
            "learn_remaining": round(max(0.0, self.cfg.learn_seconds - st.learned), 1),
            "learning_active": self.learning_active,
            "unlock_mode": self.cfg.unlock_mode,
            "min_cards": self.cfg.min_cards,
            "cards_done": st.cards_done,
            "paused": self.is_paused(self.now),
            "paused_remaining": round(max(0.0, st.paused_until - self.now)) if self.is_paused(self.now) else 0,
            "pause_minutes": list(self.cfg.pause_minutes),
            "icons": {
                "free": self.cfg.icon_free,
                "locked": self.cfg.icon_locked,
                "paused": self.cfg.icon_paused,
                "learning": self.cfg.icon_learning,
                "learning_paused": self.cfg.icon_learning_paused,
            },
            "show_time": bool(self.cfg.show_time),
            "anki_focused": self.anki_focused,
            "target": self.activity.target,
            "reason": self.activity.reason,
            "anki_app_ids": list(self.cfg.anki_app_ids),
            "anki_desktop_id": self.cfg.anki_desktop_id,
            "idle_seconds": self.cfg.idle_seconds,
        }

    def state_dict(self) -> dict:
        return asdict(self.state)
