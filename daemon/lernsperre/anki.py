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
    """Erkennt beantwortete Karten, ohne Anki zu verändern.

    1. Genau: `revlog` lesen (geht, solange Anki die Datenbank nicht exklusiv sperrt).
    2. Ungefähr: Die Desktop-App von Anki sperrt ihre Datenbank exklusiv
       ("database is locked"). Dann zählt jede Änderung der WAL-Datei
       (collection.anki2-wal) als eine Antwort. Anki schreibt beim Beantworten
       einer Karte, beim bloßen Anzeigen nicht.
    """

    RETRY_DB_AFTER = 30.0  # nach "locked" so lange nicht erneut versuchen

    def __init__(self, configured: str = "", search_dirs: list[Path] | None = None):
        self.configured = configured
        self.search_dirs = search_dirs
        self.path: Path | None = None
        self.mode = ""  # "genau", "ungefähr" oder "" (keine Sammlung)
        self.last_error = ""
        self._wal_sig: tuple[int, int] | None = None
        self._changes: list[float] = []
        self._db_blocked_until = 0.0

    def _refresh_path(self) -> None:
        if self.path is None or not self.path.exists():
            self.path = find_collection(self.configured, self.search_dirs)
            self._wal_sig = None

    def _wal_signature(self) -> tuple[int, int] | None:
        assert self.path is not None
        wal = self.path.with_name(self.path.name + "-wal")
        try:
            st = wal.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def reset(self) -> None:
        """Zu Beginn einer Sperre: bisherige Änderungen vergessen, neu messen."""
        self._refresh_path()
        self._changes = []
        self._wal_sig = self._wal_signature() if self.path else None
        self._db_blocked_until = 0.0

    def _watch_wal(self, now: float) -> None:
        sig = self._wal_signature()
        if sig is not None and self._wal_sig is not None and sig != self._wal_sig:
            self._changes.append(now)
            del self._changes[:-500]
        if sig is not None:
            self._wal_sig = sig

    def poll(self, now: float, since: float) -> tuple[float | None, int | None]:
        """(Zeitpunkt der letzten Antwort, Anzahl Antworten seit `since`)."""
        self._refresh_path()
        if self.path is None:
            self.mode, self.last_error = "", "Keine Anki-Sammlung gefunden"
            return None, None
        self._watch_wal(now)
        wal_last = self._changes[-1] if self._changes else None
        if now >= self._db_blocked_until:
            try:
                con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.05)
                try:
                    last_ms, count = con.execute(
                        "SELECT max(id), (SELECT count(*) FROM revlog WHERE id >= ?) FROM revlog",
                        (int(since * 1000),),
                    ).fetchone()
                finally:
                    con.close()
                self.mode, self.last_error = "genau", ""
                values = [v for v in ((last_ms / 1000.0) if last_ms else None, wal_last) if v is not None]
                return (max(values) if values else None), int(count)
            except sqlite3.Error:
                self._db_blocked_until = now + self.RETRY_DB_AFTER
        self.mode, self.last_error = "ungefähr", ""
        return wal_last, sum(1 for t in self._changes if t >= since)

    # Kurzformen (Tests, Kommandozeile)
    def last_answer(self, now: float) -> float | None:
        return self.poll(now, now)[0]

    def cards_since(self, ts: float) -> int | None:
        import time

        return self.poll(time.time(), ts)[1]
