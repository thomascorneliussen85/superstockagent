"""Persistent record of every AI call: tokens, cost, trigger, and the response.

Stored in SQLite (``data/copilot.db``). AI output is kept in its own table,
separate from any trade data, so it can later be evaluated against outcomes
without being mixed into the original records.
"""

from __future__ import annotations

import calendar
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms INTEGER NOT NULL,
    model TEXT NOT NULL,
    served_model TEXT,
    trigger TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL,
    error TEXT,
    stop_reason TEXT,
    request_id TEXT
);
CREATE INDEX IF NOT EXISTS ai_calls_ts ON ai_calls(ts_ms);
CREATE TABLE IF NOT EXISTS ai_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL REFERENCES ai_calls(id),
    ts_ms INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    bid REAL,
    ask REAL,
    snapshot_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    engine_version TEXT,
    prompt_version TEXT
);
"""


def month_bounds_ms(now: datetime) -> tuple[int, int]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days = calendar.monthrange(now.year, now.month)[1]
    start_ms = int(start.timestamp() * 1000)
    return start_ms, start_ms + days * 86_400_000


def day_start_ms(now: datetime) -> int:
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


class Ledger:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def record_call(self, **row: Any) -> int:
        cols = ",".join(row)
        qs = ",".join("?" for _ in row)
        with self._lock:
            cur = self._db.execute(f"INSERT INTO ai_calls ({cols}) VALUES ({qs})", tuple(row.values()))
            self._db.commit()
            return int(cur.lastrowid)

    def record_comment(
        self,
        call_id: int,
        ts_ms: int,
        symbol: str,
        bid: float | None,
        ask: float | None,
        snapshot: dict,
        response: dict,
        engine_version: str,
        prompt_version: str,
    ) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO ai_comments (call_id, ts_ms, symbol, bid, ask, snapshot_json, response_json, "
                "engine_version, prompt_version) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    call_id,
                    ts_ms,
                    symbol,
                    bid,
                    ask,
                    json.dumps(snapshot),
                    json.dumps(response),
                    engine_version,
                    prompt_version,
                ),
            )
            self._db.commit()
            return int(cur.lastrowid)

    def spent_usd(self, since_ms: int, until_ms: int | None = None) -> float:
        q = "SELECT COALESCE(SUM(cost_usd), 0) FROM ai_calls WHERE ts_ms >= ?"
        args: list[Any] = [since_ms]
        if until_ms is not None:
            q += " AND ts_ms < ?"
            args.append(until_ms)
        with self._lock:
            return float(self._db.execute(q, args).fetchone()[0])

    def calls_since(self, since_ms: int) -> int:
        with self._lock:
            return int(
                self._db.execute("SELECT COUNT(*) FROM ai_calls WHERE ts_ms >= ?", (since_ms,)).fetchone()[0]
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()


def utc_now() -> datetime:
    return datetime.now(UTC)
