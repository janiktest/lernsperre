"""Kommandozeile: `lernsperre [run|status|lock|reset|reload|config]`."""

from __future__ import annotations

import argparse
import json
import logging
import sys


def _call(method: str):
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    from .service import BUS_NAME, IFACE, OBJECT_PATH

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        res = bus.call_sync(
            BUS_NAME, OBJECT_PATH, IFACE, method, None, None,
            Gio.DBusCallFlags.NO_AUTO_START, 2000, None,
        )
    except GLib.Error as e:
        print(f"LernSperre-Dienst nicht erreichbar: {e.message}", file=sys.stderr)
        print("Starten mit: systemctl --user start lernsperre", file=sys.stderr)
        sys.exit(1)
    return res.unpack() if res is not None else ()


def _fmt(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="lernsperre", description="LernSperre – Ablenkung sperren, in Anki lernen.")
    ap.add_argument(
        "command", nargs="?", default="status",
        choices=["run", "status", "lock", "reset", "reload", "config", "json"],
        help="run = Dienst starten, status = Zustand, lock = Sperre jetzt aktivieren, "
        "reset = Zähler zurücksetzen/entsperren, reload = Einstellungen neu laden, "
        "config = Pfad der Einstellungsdatei",
    )
    args = ap.parse_args(argv)

    if args.command == "run":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        from .service import Service

        Service().run()
    elif args.command == "config":
        from .config import CONFIG_FILE, load_config

        load_config()
        print(CONFIG_FILE)
    elif args.command in ("lock", "reset", "reload"):
        _call({"lock": "LockNow", "reset": "Reset", "reload": "Reload"}[args.command])
        print("OK")
    else:
        (raw,) = _call("GetState")
        s = json.loads(raw)
        if args.command == "json":
            print(json.dumps(s, indent=2, ensure_ascii=False))
            return
        print(f"LernSperre {s['version']}")
        print("Überwachung (GNOME-Erweiterung):", "aktiv" if s["monitoring"] else "MELDET SICH NICHT")
        if s["mode"] == "locked":
            state = "lernt gerade" if s["learning_active"] else "pausiert, weil Anki nicht vorne ist oder keine Karte beantwortet wird"
            print(f"GESPERRT – noch {_fmt(s['learn_remaining'])} in Anki lernen ({state})")
            if s["anki_collection"]:
                print("Anki-Sammlung:", s["anki_collection"])
            if s["anki_note"]:
                print("Hinweis:", s["anki_note"])
        else:
            print(f"Frei – noch {_fmt(s['remaining'])} von {_fmt(s['allowed'])} erlaubt")
            if s["target"]:
                print(f"Zählt gerade: {s['target']} ({s['reason']})")
        for p in s["players"]:
            print(f"Wiedergabe: {p['name']} – {'läuft' if p['playing'] else 'pausiert'} – {p['title']}")


if __name__ == "__main__":
    main()
