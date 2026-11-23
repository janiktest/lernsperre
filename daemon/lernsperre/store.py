"""Speichert Zustand und Ereignisse in SQLite (~/.local/share/lernsperre/state.db)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                ts REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
            );
            """
        )

    def load_state(self) -> dict | None:
        row = self.con.execute("SELECT value FROM kv WHERE key='state'").fetchone()
        return json.loads(row[0]) if row else None

    def save_state(self, state: dict) -> None:
        self.con.execute(
            "INSERT INTO kv(key, value) VALUES('state', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(state),),
        )
        self.con.commit()

    def log(self, kind: str, detail: str = "", ts: float | None = None) -> None:
        self.con.execute(
            "INSERT INTO events(ts, kind, detail) VALUES(?, ?, ?)",
            (ts if ts is not None else time.time(), kind, detail),
        )
        self.con.commit()

    def close(self) -> None:
        self.con.close()
