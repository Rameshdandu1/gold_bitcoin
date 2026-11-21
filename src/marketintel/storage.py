"""Simple SQLite WAL event audit for single-instance MVP; not tick archive."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from marketintel.models import AnalystAssessment, Candidate, ConsensusResult, EngineDescriptor


class Store:
    def __init__(self, database_path: Path | str):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    horizon_minutes INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    candidate_id TEXT PRIMARY KEY,
                    evaluated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analyst_assessments (
                    candidate_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (candidate_id, provider)
                );
                CREATE TABLE IF NOT EXISTS ai_usage (
                    day_utc TEXT PRIMARY KEY,
                    reserved_calls INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS service_status (
                    service TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
            """)

    def reserve_ai_calls(self, n: int, limit: int) -> bool:
        """Atomic across worker restarts; reservations count even failed attempts."""
        if n <= 0 or limit <= 0:
            return False
        day = datetime.now(timezone.utc).date().isoformat()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT reserved_calls FROM ai_usage WHERE day_utc=?", (day,)
            ).fetchone()
            current = int(row[0]) if row else 0
            if current + n > limit:
                return False
            conn.execute(
                "INSERT INTO ai_usage(day_utc, reserved_calls) VALUES (?, ?) "
                "ON CONFLICT(day_utc) DO UPDATE SET reserved_calls=excluded.reserved_calls",
                (day, current + n),
            )
        return True

    def add_candidate(self, candidate: Candidate) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO candidates VALUES (?, ?, ?, ?, ?, ?)",
                (candidate.candidate_id, datetime.now(timezone.utc).isoformat(),
                 candidate.symbol, candidate.asset, candidate.horizon_minutes,
                 candidate.model_dump_json()),
            )
            return cursor.rowcount == 1

    def save_assessment(
        self, candidate_id: str, provider: str, model_id: str, assessment: AnalystAssessment
    ) -> None:
        if provider not in ("GPT", "Claude"):
            raise ValueError("Unknown analyst provider")
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO analyst_assessments VALUES (?, ?, ?, ?, ?)",
                (candidate_id, provider, model_id,
                 datetime.now(timezone.utc).isoformat(), assessment.model_dump_json()),
            )

    def assessments(self, candidate_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT provider, model_id, received_at, payload FROM analyst_assessments "
                "WHERE candidate_id=? ORDER BY provider", (candidate_id,)
            ).fetchall()
        return [{"provider": provider, "model_id": model_id, "received_at": at,
                 "assessment": json.loads(payload)} for provider, model_id, at, payload in rows]

    def add_decision(self, decision: ConsensusResult) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?)",
                (decision.candidate_id, decision.evaluated_at_utc.isoformat(),
                 decision.status.value, decision.model_dump_json()),
            )

    def set_status(self, service: str, state: str, detail: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO service_status VALUES (?, ?, ?, ?)",
                (service, datetime.now(timezone.utc).isoformat(), state, detail[:500]),
            )

    def get_status(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT service, updated_at, state, detail FROM service_status"
            ).fetchall()
        return [dict(zip(("service", "updated_at", "state", "detail"), r, strict=True))
                for r in rows]

    def recent_candidates(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT c.payload, d.payload
                FROM candidates c LEFT JOIN decisions d ON c.candidate_id = d.candidate_id
                ORDER BY c.created_at DESC LIMIT ?
            """, (min(max(limit, 1), 200),)).fetchall()
        return [{"candidate": json.loads(candidate),
                 "consensus": json.loads(decision) if decision else None}
                for candidate, decision in rows]

    def last_engine_states(self, engines: list[EngineDescriptor]) -> list[dict]:
        with self._conn() as conn:
            for engine in engines:
                row = conn.execute("""
                    SELECT d.status FROM candidates c
                    LEFT JOIN decisions d ON c.candidate_id = d.candidate_id
                    WHERE c.symbol=? AND c.horizon_minutes=?
                    ORDER BY c.created_at DESC LIMIT 1
                """, (engine.symbol, engine.horizon_minutes)).fetchone()
                if row and row[0]:
                    engine.state = row[0]
        return [e.model_dump() for e in engines]
