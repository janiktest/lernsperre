"""Kommandozeile: `lernsperre [run|status|lock|reset|reload|config]`."""

from __future__ import annotations

import argparse
import json
import logging
import sys


HELP = """\
LernSperre – Befehle

  lernsperre                 Zustand anzeigen (wie: lernsperre status)
  lernsperre status          verbleibende Zeit, was gerade zählt, Sperre
  lernsperre lock            Sperre jetzt aktivieren
  lernsperre pause [MIN]     Zählen für MIN Minuten pausieren (Standard 30, nicht während einer Sperre)
  lernsperre resume          Pause beenden
  lernsperre reset           Zähler zurücksetzen bzw. Sperre aufheben (Notfall)
  lernsperre edit            Einstellungen im Texteditor öffnen
  lernsperre config          Pfad der Einstellungsdatei ausgeben
  lernsperre reload          Einstellungen sofort neu laden (passiert sonst automatisch)
  lernsperre quit            LernSperre beenden (bis zur nächsten Anmeldung)
  lernsperre start           LernSperre wieder starten
  lernsperre json            Zustand als JSON
  lernsperre run             Dienst im Vordergrund starten (zum Testen)
  lernsperre hilfe           diese Übersicht

Anleitung: https://github.com/janiktest/lernsperre/blob/main/docs/ANLEITUNG.md
GitHub:    https://github.com/janiktest/lernsperre

LernSperre ist ein unabhängiges Projekt und nicht mit Anki oder Ankitects verbunden.
"""


def _call(method: str, args=None):
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    from .service import BUS_NAME, IFACE, OBJECT_PATH

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        res = bus.call_sync(
            BUS_NAME, OBJECT_PATH, IFACE, method, args, None,
            Gio.DBusCallFlags.NO_AUTO_START, 2000, None,
        )
    except GLib.Error as e:
        if "ServiceUnknown" in e.message or "NameHasNoOwner" in e.message:
            print("LernSperre läuft nicht. Starten mit: lernsperre start", file=sys.stderr)
        else:
            msg = e.message.split(": ", 1)[1] if e.message.startswith("GDBus.Error:") and ": " in e.message else e.message
            print(f"Fehler: {msg}", file=sys.stderr)
        sys.exit(1)
    return res.unpack() if res is not None else ()


def _fmt(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="lernsperre", description="LernSperre – Ablenkung sperren, in Anki lernen.",
        epilog="Alle Befehle: lernsperre hilfe",
    )
    ap.add_argument(
        "command", nargs="?", default="status",
        choices=["run", "status", "lock", "pause", "resume", "reset", "reload", "edit",
                 "config", "quit", "start", "json", "hilfe", "help"],
    )
    ap.add_argument("minutes", nargs="?", type=int, default=30, help="Minuten für pause")
    args = ap.parse_args(argv)

    if args.command in ("hilfe", "help"):
        print(HELP, end="")
    elif args.command == "start":
        import subprocess

        sys.exit(subprocess.call(["systemctl", "--user", "start", "lernsperre.service"]))
    elif args.command == "edit":
        import shutil
        import subprocess

        from .config import CONFIG_FILE, load_config

        cfg = load_config()
        for cmd in ([cfg.editor] if cfg.editor else []) + ["gnome-text-editor", "gedit", "xdg-open"]:
            if shutil.which(cmd.split()[0]):
                subprocess.Popen(cmd.split() + [str(CONFIG_FILE)])
                break
        else:
            print(CONFIG_FILE)
    elif args.command == "pause":
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        _call("Pause", GLib.Variant("(u)", (max(1, args.minutes),)))
        print(f"Pausiert für {args.minutes} min")
    elif args.command in ("resume", "quit"):
        _call({"resume": "Resume", "quit": "Quit"}[args.command])
        print("OK")
    elif args.command == "run":
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
        if s.get("config_error"):
            print("EINSTELLUNGEN FEHLERHAFT:", s["config_error"])
        if s["mode"] == "locked":
            print(f"GESPERRT – Ziel: {s['unlock_goal']}")
            if s["unlock_mode"] in ("time", "both"):
                state = "läuft" if s["learning_active"] else "wartet, bis Anki vorne ist und du Karten beantwortest"
                print(f"  Lernzeit: noch {_fmt(s['learn_remaining'])} ({state})")
            if s["unlock_mode"] in ("cards", "both"):
                print(f"  Karten: {s['cards_done']} von {s['min_cards']}")
            if s["anki_collection"]:
                print("Anki-Sammlung:", s["anki_collection"])
            if s["anki_note"]:
                print("Hinweis:", s["anki_note"])
        elif s["paused"]:
            print(f"Pausiert – noch {_fmt(s['paused_remaining'])}, danach noch {_fmt(s['remaining'])} erlaubt")
        else:
            print(f"Frei – noch {_fmt(s['remaining'])} von {_fmt(s['allowed'])} erlaubt")
            if s["target"]:
                print(f"Zählt gerade: {s['target']} ({s['reason']})")
        fw = s.get("focused_window")
        if fw:
            print(f"Vorderes Fenster: {fw['title']} (App-ID: {fw['app_id'] or '–'}, WM_CLASS: {fw['wm_class'] or '–'})")
        for p in s["players"]:
            print(f"Wiedergabe: {p['name']} – {'läuft' if p['playing'] else 'pausiert'} – {p['title']}")


if __name__ == "__main__":
    main()
