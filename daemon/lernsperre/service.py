"""Hintergrunddienst: D-Bus-Schnittstelle, MPRIS, Benachrichtigungen, Takt."""

from __future__ import annotations

import json
import logging
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import __version__  # noqa: E402
from .anki import AnkiActivity, resolve_launch  # noqa: E402
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
    <method name="Pause"><arg type="u" name="minutes" direction="in"/></method>
    <method name="Resume"/>
    <method name="Quit"/>
    <signal name="StateChanged"><arg type="s" name="state_json"/></signal>
  </interface>
</node>
"""

EXTENSION_UUID = "lernsperre@janiktest.github.io"
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
        self.cards_since_lock: int | None = None
        self.config_mtime = self._config_mtime()
        self.config_error = ""
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
        for sig in (15, 2):  # SIGTERM (systemctl stop), SIGINT: sauber beenden, Kopie löschen
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)
        log.info("LernSperre %s läuft (Einstellungen: %s)", __version__, CONFIG_FILE)
        try:
            self.loop.run()
        finally:
            self.store.save_state(self.engine.state_dict())
            self.store.close()
            self.anki.cleanup()

    def _on_signal(self) -> bool:
        self.loop.quit()
        return False

    def _on_bus_acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self.conn = conn
        node = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
        conn.register_object(OBJECT_PATH, node.interfaces[0], self._on_method_call, None, None)
        if not self.store.get("extension_auto_enabled"):
            self._enable_tries = 0
            GLib.timeout_add_seconds(5, self._try_enable_extension)

    def _try_enable_extension(self) -> bool:
        """Schaltet die GNOME-Erweiterung einmalig ein (z. B. nach Installation per .deb).

        Später respektiert LernSperre es, wenn du sie selbst wieder ausschaltest.
        """
        self._enable_tries += 1
        try:
            info = self.conn.call_sync(
                "org.gnome.Shell.Extensions", "/org/gnome/Shell", "org.gnome.Shell.Extensions",
                "GetExtensionInfo", GLib.Variant("(s)", (EXTENSION_UUID,)),
                GLib.VariantType("(a{sv})"), Gio.DBusCallFlags.NONE, 2000, None,
            ).unpack()[0]
            if info:  # GNOME kennt die Erweiterung (nach Neuanmeldung)
                ok = self.conn.call_sync(
                    "org.gnome.Shell.Extensions", "/org/gnome/Shell", "org.gnome.Shell.Extensions",
                    "EnableExtension", GLib.Variant("(s)", (EXTENSION_UUID,)),
                    GLib.VariantType("(b)"), Gio.DBusCallFlags.NONE, 2000, None,
                ).unpack()[0]
                if ok:
                    self.store.set("extension_auto_enabled", "1")
                    log.info("GNOME-Erweiterung eingeschaltet")
                    return False
        except GLib.Error as e:
            log.debug("Erweiterung einschalten: %s", e.message)
        return self._enable_tries < 30  # etwa 5 min lang versuchen

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
                self.anki.cleanup()
                invocation.return_value(None)
            elif method == "Reload":
                self._reload(force=True)
                if self.config_error:
                    invocation.return_dbus_error(f"{IFACE}.ConfigError", self.config_error)
                else:
                    invocation.return_value(None)
            elif method == "Pause":
                (minutes,) = params.unpack()
                events = self.engine.pause(time.time(), minutes)
                if not events:
                    invocation.return_dbus_error(f"{IFACE}.Error", "Während einer Sperre geht Pausieren nicht")
                    return
                self._handle(events)
                invocation.return_value(None)
            elif method == "Resume":
                self._handle(self.engine.resume())
                invocation.return_value(None)
            elif method == "Quit":
                log.info("Beendet über das Menü")
                invocation.return_value(None)
                GLib.idle_add(self.loop.quit)
            else:
                invocation.return_dbus_error(f"{IFACE}.Error", f"Unbekannte Methode {method}")
        except Exception as e:  # noqa: BLE001
            log.exception("Fehler in %s", method)
            invocation.return_dbus_error(f"{IFACE}.Error", str(e))

    # --- Einstellungen -------------------------------------------------
    @staticmethod
    def _config_mtime() -> float:
        try:
            return CONFIG_FILE.stat().st_mtime
        except OSError:
            return 0.0

    def _reload(self, force: bool = False) -> None:
        mtime = self._config_mtime()
        if not force and mtime == self.config_mtime:
            return
        self.config_mtime = mtime
        try:
            cfg = load_config()
        except Exception as e:  # noqa: BLE001
            msg = f"Fehler in {CONFIG_FILE.name}: {e}"
            if msg != self.config_error:
                self._notify("Einstellungen fehlerhaft", f"{msg}\nDie alten Einstellungen bleiben aktiv.")
            self.config_error = msg
            log.warning(msg)
            return
        self.config_error = ""
        self.config_mtime = self._config_mtime()
        self.cfg = cfg
        self.engine.cfg = cfg
        self.anki = AnkiActivity(cfg.anki_collection)
        log.info("Einstellungen neu geladen")

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
        return Signals(
            windows=windows, players=self.players, last_answer=self.last_answer,
            cards_since_lock=self.cards_since_lock,
        )

    def _tick(self) -> bool:
        now = time.time()
        mono = time.monotonic()
        dt, self.last_mono = mono - self.last_mono, mono
        try:
            if now - self.players_at >= 2:
                self._poll_players()
                self.players_at = now
            if self.ticks % 2 == 0:
                self._reload()
            if self.engine.state.mode == "locked":
                # jede Sekunde; kopiert/gelesen wird nur, wenn Anki etwas geschrieben hat
                self.last_answer, self.cards_since_lock = self.anki.poll(now, self.engine.state.lock_started)
                self.last_answer_at = now
            elif self.engine.state.mode != "locked":
                self.cards_since_lock = None
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
                self.cards_since_lock = None
                self.last_answer = None
                self.anki.reset()
                self._notify("Gesperrt", f"{self._unlock_goal()} in Anki, dann geht es weiter.")
                if self.cfg.pause_media_on_lock:
                    self._pause_players()
            elif kind == "unlocked":
                self.anki.cleanup()
                self._notify("Entsperrt", "Gut gemacht! Die erlaubte Zeit beginnt von vorn.")
            elif kind == "pause_media":
                self._pause_players()
            elif kind == "paused":
                self._notify("Pausiert", f"LernSperre zählt {ev[1]:g} min lang nicht.")
            elif kind == "resumed":
                self._notify("Pause vorbei", "LernSperre zählt wieder.")
            if kind != "pause_media":
                self.store.log(kind)
                self.store.save_state(self.engine.state_dict())
                self._emit_state()

    def _unlock_goal(self) -> str:
        c = self.cfg
        if c.unlock_mode == "cards":
            return f"Beantworte {c.min_cards} Karten"
        if c.unlock_mode == "both":
            return f"Lerne {c.learn_minutes:g} min und beantworte {c.min_cards} Karten"
        return f"Lerne {c.learn_minutes:g} min"

    def _snapshot(self) -> dict:
        snap = self.engine.snapshot()
        now = time.time()
        snap["version"] = __version__
        snap["config_path"] = str(CONFIG_FILE)
        snap["config_error"] = self.config_error
        snap["editor"] = self.cfg.editor
        snap["unlock_goal"] = self._unlock_goal()
        snap["monitoring"] = now - self.windows_at <= WINDOWS_STALE_AFTER
        snap["anki_collection"] = str(self.anki.path) if self.anki.path else ""
        snap["anki_note"] = self.anki.last_error
        snap["anki_mode"] = self.anki.mode
        try:
            snap["anki_launch_argv"] = resolve_launch(self.cfg.anki_launch)
        except ValueError as e:
            snap["anki_launch_argv"] = []
            snap["anki_note"] = str(e)
        snap["last_answer_ago"] = round(now - self.last_answer) if self.last_answer else None
        fw = self._signals(now).focused
        snap["focused_window"] = (
            {"title": fw.title, "app_id": fw.app_id, "wm_class": fw.wm_class} if fw else None
        )
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
