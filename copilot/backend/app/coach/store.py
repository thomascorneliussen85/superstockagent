"""Coach persistence: AI outcome evaluations, reviews, knowledge base and versions."""

from __future__ import annotations

import json
import time
from typing import Any

from ..journal.store import JournalStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_outcomes (
    comment_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    r REAL,
    data_json TEXT NOT NULL,
    evaluated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    UNIQUE(period, start_ms)
);
CREATE TABLE IF NOT EXISTS knowledge (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    strength TEXT,
    first_seen INTEGER NOT NULL,
    last_confirmed INTEGER NOT NULL,
    times_confirmed INTEGER NOT NULL,
    status TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    at INTEGER NOT NULL,
    event TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    component TEXT NOT NULL,
    version TEXT NOT NULL,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    details_json TEXT NOT NULL,
    PRIMARY KEY (component, version)
);
"""

STALE_AFTER_MS = 30 * 86_400_000


class CoachStore:
    def __init__(self, journal: JournalStore) -> None:
        self.db = journal.db
        self.lock = journal.lock
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ---- AI outcomes ----------------------------------------------------------------
    def outcomes(self) -> dict[int, dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT comment_id, data_json FROM ai_outcomes").fetchall()
        return {r["comment_id"]: json.loads(r["data_json"]) for r in rows}

    def set_outcome(self, comment_id: int, data: dict[str, Any]) -> None:
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO ai_outcomes(comment_id, status, r, data_json, evaluated_at) VALUES (?,?,?,?,?)",
                (comment_id, data["status"], data.get("r"), json.dumps(data), int(time.time() * 1000)),
            )
            self.db.commit()

    # ---- reviews -------------------------------------------------------------------------
    def save_review(self, period: str, start_ms: int, end_ms: int, data: dict[str, Any]) -> int:
        with self.lock:
            cur = self.db.execute(
                "INSERT OR REPLACE INTO reviews(period, start_ms, end_ms, created_at, data_json) VALUES (?,?,?,?,?)",
                (period, start_ms, end_ms, int(time.time() * 1000), json.dumps(data)),
            )
            self.db.commit()
            return int(cur.lastrowid)

    def reviews(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM reviews ORDER BY start_ms DESC, period LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "period": r["period"],
                "startMs": r["start_ms"],
                "endMs": r["end_ms"],
                "createdAt": r["created_at"],
                **json.loads(r["data_json"]),
            }
            for r in rows
        ]

    def has_review(self, period: str, start_ms: int) -> bool:
        with self.lock:
            return (
                self.db.execute(
                    "SELECT 1 FROM reviews WHERE period=? AND start_ms=?", (period, start_ms)
                ).fetchone()
                is not None
            )

    # ---- knowledge base --------------------------------------------------------------------
    def update_knowledge(self, insights: list[dict[str, Any]], now_ms: int | None = None) -> None:
        """Upsert confirmed patterns; patterns not re-confirmed for 30 days become stale."""
        now = now_ms or int(time.time() * 1000)
        seen = set()
        with self.lock:
            for ins in insights:
                key = ins["id"]
                seen.add(key)
                row = self.db.execute("SELECT * FROM knowledge WHERE key=?", (key,)).fetchone()
                if row is None:
                    self.db.execute(
                        "INSERT INTO knowledge(key, kind, title, detail, strength, first_seen, last_confirmed,"
                        " times_confirmed, status, data_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            key,
                            ins["kind"],
                            ins["title"],
                            ins["detail"],
                            ins.get("strength"),
                            now,
                            now,
                            1,
                            "active",
                            json.dumps(ins),
                        ),
                    )
                    self._history(key, now, "new", ins)
                else:
                    changed = row["title"] != ins["title"]
                    self.db.execute(
                        "UPDATE knowledge SET kind=?, title=?, detail=?, strength=?, last_confirmed=?,"
                        " times_confirmed=times_confirmed+1, status='active', data_json=? WHERE key=?",
                        (
                            ins["kind"],
                            ins["title"],
                            ins["detail"],
                            ins.get("strength"),
                            now,
                            json.dumps(ins),
                            key,
                        ),
                    )
                    if changed or row["status"] != "active":
                        self._history(key, now, "changed" if changed else "reconfirmed", ins)
            for row in self.db.execute("SELECT key, last_confirmed, status FROM knowledge").fetchall():
                if (
                    row["key"] not in seen
                    and row["status"] == "active"
                    and now - row["last_confirmed"] > STALE_AFTER_MS
                ):
                    self.db.execute("UPDATE knowledge SET status='stale' WHERE key=?", (row["key"],))
                    self._history(row["key"], now, "stale", {})
            self.db.commit()

    def _history(self, key: str, at: int, event: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO knowledge_history(key, at, event, data_json) VALUES (?,?,?,?)",
            (key, at, event, json.dumps(data)),
        )

    def knowledge(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM knowledge ORDER BY status, last_confirmed DESC").fetchall()
        return [
            {
                "key": r["key"],
                "kind": r["kind"],
                "title": r["title"],
                "detail": r["detail"],
                "strength": r["strength"],
                "firstSeen": r["first_seen"],
                "lastConfirmed": r["last_confirmed"],
                "timesConfirmed": r["times_confirmed"],
                "status": r["status"],
            }
            for r in rows
        ]

    # ---- versions -------------------------------------------------------------------------
    def record_version(self, component: str, version: str, details: dict[str, Any]) -> None:
        now = int(time.time() * 1000)
        with self.lock:
            self.db.execute(
                "INSERT INTO versions(component, version, first_seen, last_seen, details_json) VALUES (?,?,?,?,?)"
                " ON CONFLICT(component, version) DO UPDATE SET last_seen=excluded.last_seen",
                (component, version, now, now, json.dumps(details)),
            )
            self.db.commit()

    def versions(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM versions ORDER BY component, first_seen").fetchall()
        return [
            {
                "component": r["component"],
                "version": r["version"],
                "firstSeen": r["first_seen"],
                "lastSeen": r["last_seen"],
                "details": json.loads(r["details_json"]),
            }
            for r in rows
        ]
