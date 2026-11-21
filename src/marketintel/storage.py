"""SQLite WAL audit store with an append-only M1 public-event journal."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from marketintel.models import (
    AnalystAssessment,
    Candidate,
    ConsensusResult,
    EngineDescriptor,
    RawMarketEvent,
)


class Store:
    def __init__(self, database_path: Path | str):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout=5000")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
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
                CREATE TABLE IF NOT EXISTS raw_market_events (
                    event_id TEXT PRIMARY KEY,
                    partition_day_utc TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    event_time_utc TEXT NOT NULL,
                    received_at_utc TEXT NOT NULL,
                    publish_time_utc TEXT,
                    sequence INTEGER,
                    checksum INTEGER,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS raw_events_partition_symbol_channel_time
                    ON raw_market_events (
                        partition_day_utc, symbol, channel, event_time_utc, event_id
                    );
                CREATE INDEX IF NOT EXISTS raw_events_symbol_channel_time
                    ON raw_market_events (symbol, channel, event_time_utc, event_id);
                CREATE TRIGGER IF NOT EXISTS raw_market_events_no_update
                    BEFORE UPDATE ON raw_market_events
                    BEGIN SELECT RAISE(ABORT, 'raw_market_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS raw_market_events_no_delete
                    BEFORE DELETE ON raw_market_events
                    BEGIN SELECT RAISE(ABORT, 'raw_market_events is append-only'); END;
                CREATE TABLE IF NOT EXISTS source_status_events (
                    event_id TEXT PRIMARY KEY,
                    occurred_at_utc TEXT NOT NULL,
                    source TEXT NOT NULL,
                    state TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS source_status_time
                    ON source_status_events (source, occurred_at_utc);
                CREATE TRIGGER IF NOT EXISTS source_status_events_no_update
                    BEFORE UPDATE ON source_status_events
                    BEGIN SELECT RAISE(ABORT, 'source_status_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS source_status_events_no_delete
                    BEFORE DELETE ON source_status_events
                    BEGIN SELECT RAISE(ABORT, 'source_status_events is append-only'); END;
            """)

    def append_raw_event(self, event: RawMarketEvent) -> bool:
        """Persist once by deterministic event ID; duplicate delivery is harmless."""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO raw_market_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_time_utc.astimezone(UTC).date().isoformat(),
                    event.schema_version,
                    event.venue,
                    event.symbol,
                    event.channel,
                    event.event_time_utc.astimezone(UTC).isoformat(),
                    event.received_at_utc.astimezone(UTC).isoformat(),
                    event.publish_time_utc.astimezone(UTC).isoformat()
                    if event.publish_time_utc
                    else None,
                    event.sequence,
                    event.checksum,
                    json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            return cursor.rowcount == 1

    def raw_events(
        self,
        *,
        symbol: str | None = None,
        channels: tuple[str, ...] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[RawMarketEvent]:
        clauses: list[str] = []
        parameters: list[object] = []
        if symbol is not None:
            clauses.append("symbol=?")
            parameters.append(symbol)
        if channels:
            placeholders = ",".join("?" for _ in channels)
            clauses.append(f"channel IN ({placeholders})")
            parameters.extend(channels)
        if start is not None:
            if start.tzinfo is None or start.utcoffset() is None:
                raise ValueError("start must be timezone aware")
            clauses.append("event_time_utc>=?")
            parameters.append(start.astimezone(UTC).isoformat())
        if end is not None:
            if end.tzinfo is None or end.utcoffset() is None:
                raise ValueError("end must be timezone aware")
            clauses.append("event_time_utc<?")
            parameters.append(end.astimezone(UTC).isoformat())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = (
            "SELECT event_id, schema_version, venue, symbol, channel, event_time_utc, "
            "received_at_utc, publish_time_utc, sequence, checksum, payload "
            f"FROM raw_market_events{where} "
            "ORDER BY event_time_utc, COALESCE(sequence, -1), event_id"
        )
        with self._conn() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [
            RawMarketEvent(
                event_id=row[0],
                schema_version=row[1],
                venue=row[2],
                symbol=row[3],
                channel=row[4],
                event_time_utc=datetime.fromisoformat(row[5]),
                received_at_utc=datetime.fromisoformat(row[6]),
                publish_time_utc=datetime.fromisoformat(row[7]) if row[7] else None,
                sequence=row[8],
                checksum=row[9],
                payload=json.loads(row[10]),
            )
            for row in rows
        ]

    def record_source_status(
        self,
        source: str,
        state: str,
        detail: str = "",
        *,
        occurred_at: datetime | None = None,
    ) -> bool:
        occurred_at = occurred_at or datetime.now(UTC)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone aware")
        safe_detail = detail[:500]
        canonical = "|".join([source, state, safe_detail, occurred_at.astimezone(UTC).isoformat()])
        event_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT state, detail FROM service_status WHERE service=?", (source,)
            ).fetchone()
            if current == (state, safe_detail):
                return False
            cursor = conn.execute(
                "INSERT OR IGNORE INTO source_status_events VALUES (?, ?, ?, ?, ?)",
                (
                    event_id,
                    occurred_at.astimezone(UTC).isoformat(),
                    source,
                    state,
                    safe_detail,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO service_status VALUES (?, ?, ?, ?)",
                (
                    source,
                    occurred_at.astimezone(UTC).isoformat(),
                    state,
                    safe_detail,
                ),
            )
            return cursor.rowcount == 1

    def source_status_history(self, source: str | None = None) -> list[dict]:
        query = "SELECT event_id, occurred_at_utc, source, state, detail FROM source_status_events"
        parameters: tuple[object, ...] = ()
        if source is not None:
            query += " WHERE source=?"
            parameters = (source,)
        query += " ORDER BY occurred_at_utc, event_id"
        with self._conn() as conn:
            rows = conn.execute(query, parameters).fetchall()
        fields = ("event_id", "occurred_at_utc", "source", "state", "detail")
        return [dict(zip(fields, row, strict=True)) for row in rows]

    def reserve_ai_calls(self, n: int, limit: int) -> bool:
        """Atomic across worker restarts; reservations count even failed attempts."""
        if n <= 0 or limit <= 0:
            return False
        day = datetime.now(UTC).date().isoformat()
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
                (
                    candidate.candidate_id,
                    datetime.now(UTC).isoformat(),
                    candidate.symbol,
                    candidate.asset,
                    candidate.horizon_minutes,
                    candidate.model_dump_json(),
                ),
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
                (
                    candidate_id,
                    provider,
                    model_id,
                    datetime.now(UTC).isoformat(),
                    assessment.model_dump_json(),
                ),
            )

    def assessments(self, candidate_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT provider, model_id, received_at, payload FROM analyst_assessments "
                "WHERE candidate_id=? ORDER BY provider",
                (candidate_id,),
            ).fetchall()
        return [
            {
                "provider": provider,
                "model_id": model_id,
                "received_at": at,
                "assessment": json.loads(payload),
            }
            for provider, model_id, at, payload in rows
        ]

    def add_decision(self, decision: ConsensusResult) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?)",
                (
                    decision.candidate_id,
                    decision.evaluated_at_utc.isoformat(),
                    decision.status.value,
                    decision.model_dump_json(),
                ),
            )

    def set_status(self, service: str, state: str, detail: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO service_status VALUES (?, ?, ?, ?)",
                (service, datetime.now(UTC).isoformat(), state, detail[:500]),
            )

    def get_status(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT service, updated_at, state, detail FROM service_status"
            ).fetchall()
        return [
            dict(zip(("service", "updated_at", "state", "detail"), r, strict=True)) for r in rows
        ]

    def recent_candidates(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.payload, d.payload
                FROM candidates c LEFT JOIN decisions d ON c.candidate_id = d.candidate_id
                ORDER BY c.created_at DESC LIMIT ?
            """,
                (min(max(limit, 1), 200),),
            ).fetchall()
        return [
            {
                "candidate": json.loads(candidate),
                "consensus": json.loads(decision) if decision else None,
            }
            for candidate, decision in rows
        ]

    def last_engine_states(self, engines: list[EngineDescriptor]) -> list[dict]:
        with self._conn() as conn:
            for engine in engines:
                row = conn.execute(
                    """
                    SELECT d.status FROM candidates c
                    LEFT JOIN decisions d ON c.candidate_id = d.candidate_id
                    WHERE c.symbol=? AND c.horizon_minutes=?
                    ORDER BY c.created_at DESC LIMIT 1
                """,
                    (engine.symbol, engine.horizon_minutes),
                ).fetchone()
                if row and row[0]:
                    engine.state = row[0]
        return [e.model_dump() for e in engines]
