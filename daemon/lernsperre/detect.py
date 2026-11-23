"""Sucht Anki-Installationen (Flatpak, Snap, deb, Installer/Launcher, pip, AppImage).

Wird von `lernsperre detect-ankis` und `lernsperre use-anki N` benutzt.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HOME = Path.home()
FLATPAK_ID = "net.ankiweb.Anki"
SHARED_DATA = HOME / ".local/share/Anki2"  # alle Nicht-Sandbox-Varianten teilen sich diesen Ordner


@dataclass
class Profile:
    name: str
    collection: Path
    modified: float


@dataclass
class Install:
    kind: str
    detail: str
    launch: str  # Befehl zum Starten
    desktop_id: str = ""
    data_dir: Path | None = None
    profiles: list[Profile] = field(default_factory=list)

    @property
    def newest_collection(self) -> Path | None:
        return max(self.profiles, key=lambda p: p.modified).collection if self.profiles else None


def _run(cmd: list[str]) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def profiles_in(data_dir: Path | None) -> list[Profile]:
    if not data_dir or not data_dir.is_dir():
        return []
    result = []
    for col in data_dir.glob("*/collection.anki2"):
        wal = col.with_name(col.name + "-wal")
        mtime = max(col.stat().st_mtime, wal.stat().st_mtime if wal.exists() else 0)
        result.append(Profile(col.parent.name, col, mtime))
    return sorted(result, key=lambda p: -p.modified)


def snap_data_dirs(name: str) -> list[Path]:
    base = HOME / "snap" / name
    return [p for p in base.glob("*/.local/share/Anki2") if p.is_dir()] if base.is_dir() else []


def _desktop_files() -> dict[str, str]:
    """desktop-id -> Exec-Zeile, für alle .desktop-Dateien mit 'Anki' im Namen."""
    dirs = [HOME / ".local/share"] + [
        Path(d) for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if d
    ]
    dirs += [HOME / ".local/share/flatpak/exports/share", Path("/var/lib/flatpak/exports/share"),
             Path("/var/lib/snapd/desktop")]
    found: dict[str, str] = {}
    for d in dirs:
        appdir = d / "applications"
        if not appdir.is_dir():
            continue
        for f in appdir.glob("*.desktop"):
            if f.name in found or "lernsperre" in f.name.lower():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            name = re.search(r"^Name=(.*)$", text, re.M)
            exec_ = re.search(r"^Exec=(.*)$", text, re.M)
            if name and "anki" in name.group(1).lower() and exec_:
                found[f.name] = exec_.group(1)
    return found


def detect() -> list[Install]:
    installs: list[Install] = []
    seen_exec: set[str] = set()
    desktops = _desktop_files()

    # Flatpak
    for line in _run(["flatpak", "list", "--app", "--columns=application,version,installation"]).splitlines():
        parts = line.split("\t")
        if parts and "anki" in parts[0].lower():
            app_id = parts[0].strip()
            version = parts[1].strip() if len(parts) > 1 else ""
            where = parts[2].strip() if len(parts) > 2 else ""
            data = HOME / ".var/app" / app_id / "data/Anki2"
            installs.append(Install(
                "Flatpak", f"{app_id} {version} ({where})".strip(), f"flatpak run {app_id}",
                f"{app_id}.desktop" if f"{app_id}.desktop" in desktops else "", data, profiles_in(data),
            ))

    # Snap
    for line in _run(["snap", "list"]).splitlines()[1:]:
        parts = line.split()
        if parts and "anki" in parts[0].lower():
            name, version = parts[0], parts[1] if len(parts) > 1 else ""
            desktop = next((d for d in desktops if d.startswith(f"{name}_")), "")
            dirs = snap_data_dirs(name)
            data = dirs[0] if dirs else None
            installs.append(Install("Snap", f"{name} {version}", f"snap run {name}", desktop, data, profiles_in(data)))
            seen_exec.add(f"/snap/bin/{name}")

    # deb-Pakete
    deb_pkgs = {}
    for line in _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"]).splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and "anki" in parts[0].lower() and parts[2].endswith(" installed"):
            deb_pkgs[parts[0]] = parts[1]

    # Programme auf der Platte
    candidates = [
        Path("/usr/bin/anki"),
        Path("/usr/local/bin/anki"),
        HOME / ".local/bin/anki",
        HOME / ".local/share/AnkiProgramFiles/.venv/bin/anki",
    ]
    candidates += sorted(Path("/opt").glob("anki*/anki")) + sorted(Path("/opt").glob("anki*/bin/anki"))
    which = shutil.which("anki")
    if which:
        candidates.append(Path(which))
    for appdir in (HOME / "Applications", HOME / "Downloads", HOME / "Programme", HOME):
        if appdir.is_dir():
            candidates += [p for p in appdir.glob("*.AppImage") if "anki" in p.name.lower()]
    for c in candidates:
        if not c.exists() or not os.access(c, os.X_OK):
            continue
        real = str(c.resolve())
        if real in seen_exec or str(c) in seen_exec or real.startswith("/snap/"):
            continue
        seen_exec.update({real, str(c)})
        s = str(c)
        if s.endswith(".AppImage"):
            kind, detail = "AppImage", s
        elif "AnkiProgramFiles" in real:
            kind, detail = "Anki-Launcher (ankiweb.net)", s
        elif s.startswith("/usr/bin/") and deb_pkgs:
            pkg = "anki" if "anki" in deb_pkgs else next(iter(deb_pkgs))
            kind, detail = "deb-Paket", f"{pkg} {deb_pkgs[pkg]} – {s}"
        elif s.startswith("/usr/local/") or s.startswith("/opt/"):
            kind, detail = "Installer (ankiweb.net)", s
        elif s.startswith(str(HOME / ".local/bin")):
            kind, detail = "pip/uv", s
        else:
            kind, detail = "Programm", s
        desktop = next((d for d, ex in desktops.items() if shlex.split(ex or "x")[0] in (s, real, c.name)), "")
        installs.append(Install(kind, detail, shlex.quote(s), desktop, SHARED_DATA, profiles_in(SHARED_DATA)))
    return installs


def _short(p: Path | None) -> str:
    if p is None:
        return "–"
    s = str(p)
    return "~" + s[len(str(HOME)):] if s.startswith(str(HOME)) else s


def format_installs(installs: list[Install]) -> str:
    if not installs:
        return "Keine Anki-Installation gefunden.\n"
    out = ["Gefundene Anki-Installationen:", ""]
    for i, inst in enumerate(installs, 1):
        detail = inst.detail.replace(str(HOME), "~")
        out.append(f"[{i}] {inst.kind}: {detail}")
        out.append(f"    Starten:  {inst.launch}")
        if inst.desktop_id:
            out.append(f"    Desktop:  {inst.desktop_id}")
        out.append(f"    Daten:    {_short(inst.data_dir)}")
        for p in inst.profiles:
            when = datetime.fromtimestamp(p.modified).strftime("%d.%m.%Y %H:%M")
            out.append(f"              Profil „{p.name}“, zuletzt geändert {when}")
        out.append("")
    return "\n".join(out) + "\n"


def set_options(text: str, values: dict[str, str]) -> str:
    """Setzt Top-Level-Optionen in der Einstellungsdatei, Kommentare bleiben erhalten."""
    first_table = re.search(r"^\s*\[", text, re.M)
    head, tail = (text[: first_table.start()], text[first_table.start():]) if first_table else (text, "")
    for key, value in values.items():
        line = f"{key} = {value}"
        pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.M)
        if pattern.search(head):
            head = pattern.sub(lambda _m: line, head, count=1)
        else:
            head = head.rstrip("\n") + f"\n{line}\n\n"
    return head + tail


def toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
