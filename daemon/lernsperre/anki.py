"""Liest nur lesend, wann zuletzt in Anki eine Karte beantwortet wurde.

Es wird kein Add-on gebraucht: Jede beantwortete Karte landet in der Tabelle
`revlog` der Sammlung (id = Zeitpunkt in Millisekunden). Falls die Datenbank
gerade nicht lesbar ist, dient die Änderungszeit der WAL-Datei als Ersatz,
denn Anki schreibt bei jeder Antwort in die WAL-Datei, beim bloßen Anzeigen
einer Karte aber nicht.
"""

from __future__ import annotations

import os
import shlex
import sqlite3
from pathlib import Path

HOME = Path.home()
SEARCH_DIRS = [
    HOME / ".var/app/net.ankiweb.Anki/data/Anki2",  # Flatpak
    HOME / ".local/share/Anki2",  # normale Installation
]


def resolve_launch(spec: str) -> list[str]:
    """Wandelt anki_launch (Befehl, Programm oder Ordner) in eine Befehlszeile um."""
    spec = spec.strip()
    if not spec:
        return []
    path = Path(spec).expanduser()
    if path.is_dir():
        for rel in ("anki", "bin/anki", ".venv/bin/anki", "AppRun"):
            exe = path / rel
            if exe.is_file() and os.access(exe, os.X_OK):
                return [str(exe)]
        images = sorted(path.glob("*.AppImage"))
        if images:
            return [str(images[0])]
        raise ValueError(f"In {path} wurde kein Anki-Programm gefunden")
    if path.is_file():
        return [str(path)]
    return shlex.split(spec)


def find_collection(configured: str = "", search_dirs: list[Path] | None = None) -> Path | None:
    if configured:
        p = Path(configured).expanduser()
        return p if p.exists() else None
    candidates: list[Path] = []
    dirs = list(search_dirs or SEARCH_DIRS)
    if search_dirs is None:
        dirs += list(HOME.glob("snap/*/*/.local/share/Anki2"))  # Snap
    for d in dirs:
        if d.is_dir():
            candidates.extend(d.glob("*/collection.anki2"))
    if not candidates:
        return None

    def mtime(p: Path) -> float:
        wal = p.with_name(p.name + "-wal")
        return max(p.stat().st_mtime, wal.stat().st_mtime if wal.exists() else 0)

    return max(candidates, key=mtime)


class AnkiActivity:
    def __init__(self, configured: str = "", search_dirs: list[Path] | None = None):
        self.configured = configured
        self.search_dirs = search_dirs
        self.path: Path | None = None
        self._last_wal_mtime: float | None = None
        self._wal_change_at: float | None = None
        self.last_error: str = ""

    def _refresh_path(self) -> None:
        if self.path is None or not self.path.exists():
            self.path = find_collection(self.configured, self.search_dirs)

    def _revlog_last(self) -> float | None:
        assert self.path is not None
        uri = f"file:{self.path}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=0.2)
        try:
            row = con.execute("SELECT max(id) FROM revlog").fetchone()
        finally:
            con.close()
        return (row[0] / 1000.0) if row and row[0] else None

    def _wal_last(self, now: float) -> float | None:
        assert self.path is not None
        wal = self.path.with_name(self.path.name + "-wal")
        if not wal.exists():
            return self._wal_change_at
        m = wal.stat().st_mtime
        if self._last_wal_mtime is not None and m != self._last_wal_mtime:
            self._wal_change_at = min(m, now)
        self._last_wal_mtime = m
        return self._wal_change_at

    def cards_since(self, ts: float) -> int | None:
        """Anzahl beantworteter Karten seit ts (Unix-Sekunden), None wenn nicht lesbar.

        Auch Antworten vom Handy zählen, sobald sie synchronisiert sind.
        """
        self._refresh_path()
        if self.path is None:
            return None
        try:
            con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.2)
            try:
                row = con.execute("SELECT count(*) FROM revlog WHERE id >= ?", (int(ts * 1000),)).fetchone()
            finally:
                con.close()
        except sqlite3.Error as e:
            self.last_error = f"Karten nicht zählbar ({e})"
            return None
        return int(row[0])

    def last_answer(self, now: float) -> float | None:
        """Zeitpunkt (Unix-Sekunden) der letzten Antwort, sonst None."""
        self._refresh_path()
        if self.path is None:
            self.last_error = "Keine Anki-Sammlung gefunden"
            return None
        wal = self._wal_last(now)
        try:
            rev = self._revlog_last()
            self.last_error = ""
        except sqlite3.Error as e:
            self.last_error = f"revlog nicht lesbar ({e}), nutze WAL-Zeit"
            rev = None
        values = [v for v in (rev, wal) if v is not None]
        return max(values) if values else None
