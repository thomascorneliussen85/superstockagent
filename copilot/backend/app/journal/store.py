"""SQLite storage for the trading journal.

Layout (one database, ``data/copilot.db``):

* ``deals_raw``       - MT5 deals exactly as imported. Insert-only, keyed by the
                        MT5 deal ticket, so re-imports never create duplicates.
* ``position_levels`` - initial SL/TP per position (from the entry order or the
                        first time the live monitor saw the position).
* ``trades``          - round-trip trades *derived* from deals_raw. Can be
                        rebuilt at any time; never edited by hand.
* ``trade_context``   - deterministic market conditions at entry.
* ``trade_notes``     - your notes, setup tag, tags and screenshots.
* ``trade_eval``      - generated evaluations (coach feedback, AI links).

Original data, user input and generated evaluations live in separate tables.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals_raw (
    ticket INTEGER PRIMARY KEY,
    position_id INTEGER NOT NULL,
    order_ticket INTEGER,
    time_ms INTEGER NOT NULL,
    type INTEGER NOT NULL,
    entry INTEGER NOT NULL,
    reason INTEGER,
    symbol TEXT NOT NULL,
    volume REAL NOT NULL,
    price REAL NOT NULL,
    profit REAL NOT NULL,
    commission REAL NOT NULL,
    swap REAL NOT NULL,
    fee REAL NOT NULL,
    magic INTEGER,
    comment TEXT,
    imported_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS deals_pos ON deals_raw(position_id);
CREATE INDEX IF NOT EXISTS deals_time ON deals_raw(time_ms);

CREATE TABLE IF NOT EXISTS position_levels (
    position_id INTEGER PRIMARY KEY,
    sl REAL, tp REAL,
    source TEXT NOT NULL,
    seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    position_id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    open_ms INTEGER NOT NULL,
    close_ms INTEGER,
    volume REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    sl REAL, tp REAL,
    gross REAL NOT NULL,
    commission REAL NOT NULL,
    swap REAL NOT NULL,
    fee REAL NOT NULL,
    net REAL NOT NULL,
    risk_money REAL,
    r_multiple REAL,
    exit_reason TEXT,
    closed INTEGER NOT NULL,
    session TEXT,
    deals INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS trades_close ON trades(close_ms);

CREATE TABLE IF NOT EXISTS trade_context (
    position_id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    captured_at INTEGER NOT NULL,
    context_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_notes (
    position_id INTEGER PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    setup TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    screenshots_json TEXT NOT NULL DEFAULT '[]',
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_eval (
    position_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (position_id, kind)
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    if str(path) != ":memory:":
        db.execute("PRAGMA journal_mode=WAL")
    return db


class JournalStore:
    def __init__(self, path: Path | str, screenshots_dir: Path | None = None) -> None:
        self.db = connect(path)
        self.lock = threading.RLock()
        self.screenshots_dir = screenshots_dir
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ---- generic ----------------------------------------------------------------
    def get_kv(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_kv(self, key: str, value: Any) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, json.dumps(value)))
            self.db.commit()

    # ---- raw deals -----------------------------------------------------------------
    def insert_deals(self, deals: list[dict[str, Any]]) -> int:
        """Insert-only; returns how many were new. Duplicate tickets are ignored."""
        now = int(time.time() * 1000)
        with self.lock:
            before = self.db.total_changes
            self.db.executemany(
                "INSERT OR IGNORE INTO deals_raw (ticket, position_id, order_ticket, time_ms, type, entry, reason,"
                " symbol, volume, price, profit, commission, swap, fee, magic, comment, imported_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        d["ticket"],
                        d["positionId"],
                        d.get("order"),
                        d["timeMs"],
                        d["type"],
                        d["entry"],
                        d.get("reason"),
                        d["symbol"],
                        d["volume"],
                        d["price"],
                        d["profit"],
                        d["commission"],
                        d["swap"],
                        d["fee"],
                        d.get("magic"),
                        d.get("comment", ""),
                        now,
                    )
                    for d in deals
                ],
            )
            self.db.commit()
            return self.db.total_changes - before

    def deals(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM deals_raw ORDER BY time_ms, ticket").fetchall()
        return [dict(r) for r in rows]

    def last_deal_ms(self) -> int | None:
        with self.lock:
            row = self.db.execute("SELECT MAX(time_ms) AS m FROM deals_raw").fetchone()
        return row["m"]

    # ---- levels -------------------------------------------------------------------
    def set_levels(self, position_id: int, sl: float | None, tp: float | None, source: str) -> None:
        """Record the *initial* SL/TP of a position.

        The entry order's SL (source "order") is authoritative when it has one;
        otherwise the first SL the live monitor saw wins. A position first seen
        without SL is upgraded once an SL appears.
        """
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM position_levels WHERE position_id=?", (position_id,)
            ).fetchone()
            replace = row is None
            if row is not None:
                if source == "order" and sl and row["source"] != "order":
                    replace = True
                elif not row["sl"] and sl:
                    replace = True
            if replace:
                self.db.execute(
                    "INSERT OR REPLACE INTO position_levels(position_id, sl, tp, source, seen_at) VALUES (?,?,?,?,?)",
                    (position_id, sl or None, tp or None, source, int(time.time() * 1000)),
                )
                self.db.commit()

    def levels(self) -> dict[int, dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM position_levels").fetchall()
        return {r["position_id"]: dict(r) for r in rows}

    # ---- trades -------------------------------------------------------------------
    def replace_trades(self, trades: list[dict[str, Any]]) -> None:
        cols = [
            "position_id",
            "symbol",
            "direction",
            "open_ms",
            "close_ms",
            "volume",
            "entry_price",
            "exit_price",
            "sl",
            "tp",
            "gross",
            "commission",
            "swap",
            "fee",
            "net",
            "risk_money",
            "r_multiple",
            "exit_reason",
            "closed",
            "session",
            "deals",
        ]
        with self.lock:
            self.db.execute("DELETE FROM trades")
            self.db.executemany(
                f"INSERT INTO trades ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [tuple(t[c] for c in cols) for t in trades],
            )
            self.db.commit()

    def trades(self, closed_only: bool = True) -> list[dict[str, Any]]:
        q = (
            "SELECT t.*, n.note, n.setup, n.tags_json, n.screenshots_json, c.context_json"
            " FROM trades t LEFT JOIN trade_notes n USING(position_id) LEFT JOIN trade_context c USING(position_id)"
        )
        if closed_only:
            q += " WHERE t.closed = 1"
        q += " ORDER BY COALESCE(t.close_ms, t.open_ms)"
        with self.lock:
            rows = self.db.execute(q).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.pop("tags_json") or "[]")
            d["screenshots"] = json.loads(d.pop("screenshots_json") or "[]")
            d["context"] = json.loads(d.pop("context_json")) if d.get("context_json") else None
            d["note"] = d.get("note") or ""
            d["setup"] = d.get("setup") or ""
            out.append(d)
        return out

    def trade(self, position_id: int) -> dict[str, Any] | None:
        return next((t for t in self.trades(closed_only=False) if t["position_id"] == position_id), None)

    # ---- context ------------------------------------------------------------------
    def has_context(self, position_id: int) -> bool:
        with self.lock:
            return (
                self.db.execute("SELECT 1 FROM trade_context WHERE position_id=?", (position_id,)).fetchone()
                is not None
            )

    def set_context(
        self, position_id: int, context: dict[str, Any], source: str, overwrite: bool = False
    ) -> None:
        verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"
        with self.lock:
            self.db.execute(
                f"{verb} INTO trade_context(position_id, source, captured_at, context_json) VALUES (?,?,?,?)",
                (position_id, source, int(time.time() * 1000), json.dumps(context)),
            )
            self.db.commit()

    # ---- notes ----------------------------------------------------------------------
    def update_notes(
        self,
        position_id: int,
        note: str | None = None,
        setup: str | None = None,
        tags: list[str] | None = None,
        add_screenshot: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute("SELECT * FROM trade_notes WHERE position_id=?", (position_id,)).fetchone()
            cur = dict(row) if row else {"note": "", "setup": "", "tags_json": "[]", "screenshots_json": "[]"}
            shots = json.loads(cur["screenshots_json"])
            if add_screenshot:
                shots.append(add_screenshot)
            new = {
                "note": cur["note"] if note is None else note[:5000],
                "setup": cur["setup"] if setup is None else setup.strip()[:60],
                "tags_json": cur["tags_json"]
                if tags is None
                else json.dumps(sorted({t.strip()[:40] for t in tags if t.strip()})[:20]),
                "screenshots_json": json.dumps(shots[-10:]),
            }
            self.db.execute(
                "INSERT OR REPLACE INTO trade_notes(position_id, note, setup, tags_json, screenshots_json, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (
                    position_id,
                    new["note"],
                    new["setup"],
                    new["tags_json"],
                    new["screenshots_json"],
                    int(time.time() * 1000),
                ),
            )
            self.db.commit()
        return {
            "note": new["note"],
            "setup": new["setup"],
            "tags": json.loads(new["tags_json"]),
            "screenshots": shots[-10:],
        }

    # ---- generated evaluations --------------------------------------------------------
    def set_eval(self, position_id: int, kind: str, data: dict[str, Any]) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO trade_eval(position_id, kind, created_at, data_json) VALUES (?,?,?,?)",
                (position_id, kind, int(time.time() * 1000), json.dumps(data)),
            )
            self.db.commit()

    def evals(self, kind: str) -> dict[int, dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT position_id, data_json FROM trade_eval WHERE kind=?", (kind,)
            ).fetchall()
        return {r["position_id"]: json.loads(r["data_json"]) for r in rows}

    def close(self) -> None:
        with self.lock:
            self.db.close()
