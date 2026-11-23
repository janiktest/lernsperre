"""Hintergrunddienst: D-Bus-Schnittstelle, MPRIS, Benachrichtigungen, Takt."""

from __future__ import annotations

import json
import logging
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import __version__  # noqa: E402
from .anki import AnkiActivity  # noqa: E402
from .config import CONFIG_FILE, DATA_DIR, load_config  # noqa: E402
from .engine import Engine, Signals, State  # noqa: E402
from .matcher import Player, Window  # noqa: E402
from .store import Store  # noqa: E402

log = logging.getLogger("lernsperre")

BUS_NAME = "io.github.janiktest.LernSperre"
OBJECT_PATH = "/io/github/janiktest/LernSperre"
IFACE = "io.github.janiktest.LernSperre"
IFACE_XML = f"""
<node>
  <interface name="{IFACE}">
    <method name="ReportWindows"><arg type="s" name="windows_json" direction="in"/></method>
    <method name="GetState"><arg type="s" name="state_json" direction="out"/></method>
    <method name="LockNow"/>
    <method name="Reset"/>
    <method name="Reload"/>
    <signal name="StateChanged"><arg type="s" name="state_json"/></signal>
  </interface>
</node>
"""

WINDOWS_STALE_AFTER = 15.0  # Sekunden ohne Meldung der GNOME-Erweiterung
MPRIS_PREFIX = "org.mpris.MediaPlayer2."


class Service:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.store = Store(DATA_DIR / "state.db")
        self.engine = Engine(self.cfg, State.from_dict(self.store.load_state()))
        self.anki = AnkiActivity(self.cfg.anki_collection)
        self.conn: Gio.DBusConnection | None = None
        self.windows: list[Window] = []
        self.windows_at = 0.0
        self.players: list[Player] = []
        self.players_at = 0.0
        self.last_answer: float | None = None
        self.last_answer_at = 0.0
        self.last_mono = time.monotonic()
        self.ticks = 0
        self.loop = GLib.MainLoop()

    # --- Start ----------------------------------------------------------
    def run(self) -> None:
        Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )
        GLib.timeout_add(1000, self._tick)
        log.info("LernSperre %s läuft (Einstellungen: %s)", __version__, CONFIG_FILE)
        try:
            self.loop.run()
        finally:
            self.store.save_state(self.engine.state_dict())
            self.store.close()

    def _on_bus_acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self.conn = conn
        node = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
        conn.register_object(OBJECT_PATH, node.interfaces[0], self._on_method_call, None, None)

    def _on_name_lost(self, conn, name) -> None:
        log.error("D-Bus-Name %s nicht verfügbar (läuft LernSperre schon?)", name)
        self.loop.quit()

    # --- D-Bus-Methoden -------------------------------------------------
    def _on_method_call(self, conn, sender, path, iface, method, params, invocation) -> None:
        try:
            if method == "ReportWindows":
                (raw,) = params.unpack()
                self.windows = [Window.from_dict(d) for d in json.loads(raw)]
                self.windows_at = time.time()
                invocation.return_value(None)
            elif method == "GetState":
                invocation.return_value(GLib.Variant("(s)", (json.dumps(self._snapshot()),)))
            elif method == "LockNow":
                self._handle(self.engine.lock(time.time()))
                invocation.return_value(None)
            elif method == "Reset":
                self._handle(self.engine.reset())
                invocation.return_value(None)
            elif method == "Reload":
                self.cfg = load_config()
                self.engine.cfg = self.cfg
                self.anki = AnkiActivity(self.cfg.anki_collection)
                log.info("Einstellungen neu geladen")
                invocation.return_value(None)
            else:
                invocation.return_dbus_error(f"{IFACE}.Error", f"Unbekannte Methode {method}")
        except Exception as e:  # noqa: BLE001
            log.exception("Fehler in %s", method)
            invocation.return_dbus_error(f"{IFACE}.Error", str(e))

    # --- Signale sammeln ------------------------------------------------
    def _poll_players(self) -> None:
        if self.conn is None:
            return
        players: list[Player] = []
        try:
            names = self.conn.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                "ListNames", None, GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, 500, None,
            ).unpack()[0]
        except GLib.Error as e:
            log.warning("ListNames fehlgeschlagen: %s", e.message)
            return
        for name in names:
            if not name.startswith(MPRIS_PREFIX):
                continue
            try:
                player = self._get_all(name, "org.mpris.MediaPlayer2.Player")
                root = self._get_all(name, "org.mpris.MediaPlayer2")
            except GLib.Error:
                continue
            meta = player.get("Metadata") or {}
            players.append(
                Player(
                    bus_name=name,
                    playing=player.get("PlaybackStatus") == "Playing",
                    identity=str(root.get("Identity") or ""),
                    desktop_entry=str(root.get("DesktopEntry") or ""),
                    title=str(meta.get("xesam:title") or ""),
                    url=str(meta.get("xesam:url") or ""),
                )
            )
        self.players = players

    def _get_all(self, name: str, iface: str) -> dict:
        assert self.conn is not None
        res = self.conn.call_sync(
            name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "GetAll",
            GLib.Variant("(s)", (iface,)), GLib.VariantType("(a{sv})"),
            Gio.DBusCallFlags.NONE, 300, None,
        )
        return res.unpack()[0]

    def _pause_players(self) -> None:
        if self.conn is None:
            return
        for p in self.players:
            if p.playing:
                self.conn.call(
                    p.bus_name, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player",
                    "Pause", None, None, Gio.DBusCallFlags.NONE, 500, None, None,
                )
                p.playing = False

    def _notify(self, summary: str, body: str, replace_id: int = 0) -> None:
        if self.conn is None:
            return
        self.conn.call(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications", "Notify",
            GLib.Variant(
                "(susssasa{sv}i)",
                ("LernSperre", replace_id, "alarm-symbolic", summary, body, [], {}, 8000),
            ),
            None, Gio.DBusCallFlags.NONE, 1000, None, None,
        )

    # --- Takt -----------------------------------------------------------
    def _signals(self, now: float) -> Signals:
        windows = self.windows if now - self.windows_at <= WINDOWS_STALE_AFTER else None
        return Signals(windows=windows, players=self.players, last_answer=self.last_answer)

    def _tick(self) -> bool:
        now = time.time()
        mono = time.monotonic()
        dt, self.last_mono = mono - self.last_mono, mono
        try:
            if now - self.players_at >= 2:
                self._poll_players()
                self.players_at = now
            if self.engine.state.mode == "locked" and now - self.last_answer_at >= 2:
                self.last_answer = self.anki.last_answer(now)
                self.last_answer_at = now
            self._handle(self.engine.tick(now, dt, self._signals(now)))
            self.ticks += 1
            if self.ticks % 10 == 0:
                self.store.save_state(self.engine.state_dict())
            self._emit_state()
        except Exception:  # noqa: BLE001
            log.exception("Fehler im Takt")
        return True

    def _handle(self, events: list[tuple]) -> None:
        for ev in events:
            kind = ev[0]
            if kind == "warn":
                secs = int(round(ev[1]))
                self._notify("Gleich wird gesperrt", f"Noch {secs} Sekunden, dann ist Lernen in Anki dran.")
            elif kind == "locked":
                mins = self.cfg.learn_minutes
                self._notify("Gesperrt", f"Lerne {mins:g} min in Anki, dann geht es weiter.")
                if self.cfg.pause_media_on_lock:
                    self._pause_players()
            elif kind == "unlocked":
                self._notify("Entsperrt", "Gut gemacht! Die erlaubte Zeit beginnt von vorn.")
            elif kind == "pause_media":
                self._pause_players()
            if kind != "pause_media":
                self.store.log(kind)
                self.store.save_state(self.engine.state_dict())
                self._emit_state()

    def _snapshot(self) -> dict:
        snap = self.engine.snapshot()
        now = time.time()
        snap["version"] = __version__
        snap["monitoring"] = now - self.windows_at <= WINDOWS_STALE_AFTER
        snap["anki_collection"] = str(self.anki.path) if self.anki.path else ""
        snap["anki_note"] = self.anki.last_error
        snap["last_answer_ago"] = round(now - self.last_answer) if self.last_answer else None
        snap["players"] = [
            {"name": p.identity or p.app_key, "playing": p.playing, "title": p.title}
            for p in self.players
        ]
        return snap

    def _emit_state(self) -> None:
        if self.conn is None:
            return
        self.conn.emit_signal(
            None, OBJECT_PATH, IFACE, "StateChanged",
            GLib.Variant("(s)", (json.dumps(self._snapshot()),)),
        )
