"""Liest nur lesend, wann zuletzt in Anki eine Karte beantwortet wurde.

Es wird kein Add-on gebraucht: Jede beantwortete Karte landet in der Tabelle
`revlog` der Sammlung (id = Zeitpunkt in Millisekunden). Solange die
Anki-Desktop-App offen ist, sperrt sie ihre Datenbank; dann wird eine Kopie
in ~/.cache/lernsperre gelesen. An Ankis Dateien wird nie etwas geändert.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sqlite3
from pathlib import Path

HOME = Path.home()
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "lernsperre" / "anki-kopie"
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

    1. Direkt: `revlog` lesen (geht, wenn Anki geschlossen ist).
    2. Kopie: Die Anki-Desktop-App sperrt ihre Datenbank exklusiv
       ("database is locked"). Die Dateien selbst bleiben lesbar. Dann wird
       collection.anki2 einmal und collection.anki2-wal bei jeder Änderung
       nach CACHE_DIR kopiert und die Kopie gelesen. SQLite übernimmt dabei
       die Änderungen aus der WAL-Datei, also auch die neuesten Antworten.
       Die Kopie wird nur gelesen (nie zurückgeschrieben) und nach der
       Sperre gelöscht.
    """

    def __init__(self, configured: str = "", search_dirs: list[Path] | None = None,
                 cache_dir: Path | None = None):
        self.configured = configured
        self.search_dirs = search_dirs
        self.cache_dir = cache_dir or CACHE_DIR
        self.path: Path | None = None
        self.mode = ""  # "direkt", "kopie" oder "" (keine Sammlung)
        self.last_error = ""
        self._main_sig: tuple[int, int] | None = None  # Stand der kopierten Hauptdatei
        self._wal_sig: tuple[int, int] | None = None  # Stand der kopierten WAL-Datei
        self._cached: tuple[float | None, int | None] = (None, None)
        self._cached_since: float | None = None

    def _refresh_path(self) -> None:
        if self.path is None or not self.path.exists():
            self.path = find_collection(self.configured, self.search_dirs)
            self._main_sig = self._wal_sig = None

    @staticmethod
    def _sig(p: Path) -> tuple[int, int] | None:
        try:
            st = p.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    @staticmethod
    def _query(uri: str, since: float) -> tuple[float | None, int]:
        con = sqlite3.connect(uri, uri=True, timeout=0.05)
        try:
            last_ms, count = con.execute(
                "SELECT max(id), (SELECT count(*) FROM revlog WHERE id >= ?) FROM revlog",
                (int(since * 1000),),
            ).fetchone()
        finally:
            con.close()
        return ((last_ms / 1000.0) if last_ms else None), int(count)

    def reset(self) -> None:
        """Zu Beginn einer Sperre: Sammlung neu suchen, alte Kopie verwerfen."""
        self.cleanup()
        self.path = None
        self._refresh_path()

    def cleanup(self) -> None:
        """Kopie löschen (nach der Sperre, beim Beenden)."""
        if self.cache_dir.is_dir():
            shutil.rmtree(self.cache_dir, ignore_errors=True)
        self._main_sig = self._wal_sig = None
        self._cached, self._cached_since = (None, None), None

    def _copy(self, src: Path, dst: Path) -> None:
        tmp = dst.with_name(dst.name + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)

    def _read_copy(self, since: float) -> tuple[float | None, int | None]:
        assert self.path is not None
        wal = self.path.with_name(self.path.name + "-wal")
        main_sig, wal_sig = self._sig(self.path), self._sig(wal)
        if main_sig == self._main_sig and wal_sig == self._wal_sig and since == self._cached_since:
            return self._cached  # nichts Neues
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        dst = self.cache_dir / "collection.anki2"
        dst_wal = self.cache_dir / "collection.anki2-wal"
        for extra in (self.cache_dir / "collection.anki2-shm",):
            extra.unlink(missing_ok=True)
        if main_sig != self._main_sig or not dst.exists():
            self._copy(self.path, dst)
        if wal_sig is not None:
            self._copy(wal, dst_wal)
        else:
            dst_wal.unlink(missing_ok=True)
        if self._sig(self.path) != main_sig:
            # Anki hat genau beim Kopieren die Hauptdatei geschrieben: nächste Sekunde neu
            self._main_sig = None
            return self._cached
        # nur lesend öffnen: dann schreibt SQLite auch die Kopie nicht um
        result = self._query(f"file:{dst}?mode=ro", since)
        self._main_sig, self._wal_sig = main_sig, wal_sig
        self._cached, self._cached_since = result, since
        return result

    def poll(self, now: float, since: float) -> tuple[float | None, int | None]:
        """(Zeitpunkt der letzten Antwort, Anzahl Antworten seit `since`)."""
        self._refresh_path()
        if self.path is None:
            self.mode, self.last_error = "", "Keine Anki-Sammlung gefunden"
            return None, None
        try:
            result = self._query(f"file:{self.path}?mode=ro", since)
            self.mode, self.last_error = "direkt", ""
            return result
        except sqlite3.Error:
            pass  # Anki ist offen und sperrt die Datenbank
        try:
            result = self._read_copy(since)
            self.mode, self.last_error = "kopie", ""
            return result
        except (OSError, sqlite3.Error) as e:
            self._main_sig = None  # beim nächsten Mal alles neu kopieren
            self.mode, self.last_error = "kopie", f"Anki-Sammlung nicht lesbar: {e}"
            return self._cached

    # Kurzformen (Tests, Kommandozeile)
    def last_answer(self, now: float) -> float | None:
        return self.poll(now, now)[0]

    def cards_since(self, ts: float) -> int | None:
        import time

        return self.poll(time.time(), ts)[1]
