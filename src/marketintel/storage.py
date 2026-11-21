"""SQLite WAL audit store with an append-only M1 public-event journal."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from marketintel.delta import OrderBookAssembler
from marketintel.models import (
    AnalystAssessment,
    Candidate,
    CandidateLifecycleEvent,
    ConsensusResult,
    EngineDescriptor,
    FeatureSnapshot,
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
                CREATE TABLE IF NOT EXISTS candidate_revisions (
                    candidate_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    observed_at_utc TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (candidate_id, snapshot_id)
                );
                CREATE TRIGGER IF NOT EXISTS candidate_revisions_no_update
                    BEFORE UPDATE ON candidate_revisions
                    BEGIN SELECT RAISE(ABORT, 'candidate_revisions is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS candidate_revisions_no_delete
                    BEFORE DELETE ON candidate_revisions
                    BEGIN SELECT RAISE(ABORT, 'candidate_revisions is append-only'); END;
                CREATE TABLE IF NOT EXISTS feature_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    observed_at_utc TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS feature_snapshots_no_update
                    BEFORE UPDATE ON feature_snapshots
                    BEGIN SELECT RAISE(ABORT, 'feature_snapshots is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS feature_snapshots_no_delete
                    BEFORE DELETE ON feature_snapshots
                    BEGIN SELECT RAISE(ABORT, 'feature_snapshots is append-only'); END;
                CREATE TABLE IF NOT EXISTS candidate_lifecycle_events (
                    event_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS candidate_lifecycle_by_candidate_time
                    ON candidate_lifecycle_events (candidate_id, occurred_at_utc, event_id);
                CREATE TRIGGER IF NOT EXISTS candidate_lifecycle_no_update
                    BEFORE UPDATE ON candidate_lifecycle_events
                    BEGIN SELECT RAISE(ABORT, 'candidate_lifecycle_events is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS candidate_lifecycle_no_delete
                    BEFORE DELETE ON candidate_lifecycle_events
                    BEGIN SELECT RAISE(ABORT, 'candidate_lifecycle_events is append-only'); END;
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
                CREATE TABLE IF NOT EXISTS book_checkpoints (
                    symbol TEXT PRIMARY KEY,
                    updated_at_utc TEXT NOT NULL,
                    payload TEXT NOT NULL
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

    def append_raw_events(self, events: list[RawMarketEvent]) -> int:
        """Batch append journal fixtures/imports in one transaction; duplicates remain harmless."""
        inserted = 0
        with self._conn() as conn:
            for event in events:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO raw_market_events "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                inserted += cursor.rowcount
        return inserted

    def raw_events(
        self,
        *,
        symbol: str | None = None,
        channels: tuple[str, ...] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        received_start: datetime | None = None,
        received_end: datetime | None = None,
        limit: int | None = None,
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
        if received_start is not None:
            if received_start.tzinfo is None or received_start.utcoffset() is None:
                raise ValueError("received_start must be timezone aware")
            clauses.append("received_at_utc>=?")
            parameters.append(received_start.astimezone(UTC).isoformat())
        if received_end is not None:
            if received_end.tzinfo is None or received_end.utcoffset() is None:
                raise ValueError("received_end must be timezone aware")
            clauses.append("received_at_utc<=?")
            parameters.append(received_end.astimezone(UTC).isoformat())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        order = (
            "ORDER BY event_time_utc DESC, received_at_utc DESC, event_id DESC LIMIT ?"
            if limit is not None
            else "ORDER BY event_time_utc, COALESCE(sequence, -1), event_id"
        )
        if limit is not None:
            parameters.append(min(limit, 100_000))
        query = (
            "SELECT event_id, schema_version, venue, symbol, channel, event_time_utc, "
            "received_at_utc, publish_time_utc, sequence, checksum, payload "
            f"FROM raw_market_events{where} {order}"
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

    def book_replay_events(self, *, symbol: str, through: datetime) -> list[RawMarketEvent]:
        """Load the last persisted snapshot and every received update that follows it."""
        if through.tzinfo is None or through.utcoffset() is None:
            raise ValueError("through must be timezone aware")
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT received_at_utc FROM raw_market_events
                WHERE symbol=? AND channel='ob_updates' AND received_at_utc<=?
                  AND json_extract(payload, '$.action')='snapshot'
                ORDER BY received_at_utc DESC, event_id DESC LIMIT 1
                """,
                (symbol, through.astimezone(UTC).isoformat()),
            ).fetchone()
        if row is None:
            return []
        return self.raw_events(
            symbol=symbol,
            channels=("ob_updates",),
            received_start=datetime.fromisoformat(row[0]),
            received_end=through,
        )

    def save_book_checkpoint(self, book: OrderBookAssembler) -> None:
        """Materialize current state; immutable raw events remain authoritative."""
        payload = {
            "symbol": book.symbol,
            "max_age_seconds": book.max_age_seconds,
            "asks": list(book.asks.values()),
            "bids": list(book.bids.values()),
            "last_sequence": book.last_sequence,
            "last_event_time_utc": (
                book.last_event_time_utc.astimezone(UTC).isoformat()
                if book.last_event_time_utc is not None
                else None
            ),
            "last_received_at_utc": (
                book.last_received_at_utc.astimezone(UTC).isoformat()
                if book.last_received_at_utc is not None
                else None
            ),
            "valid": book.valid,
            "reason": book.reason,
        }
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO book_checkpoints VALUES (?, ?, ?)",
                (
                    book.symbol,
                    datetime.now(UTC).isoformat(),
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )

    def book_checkpoint(self, symbol: str) -> OrderBookAssembler | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM book_checkpoints WHERE symbol=?", (symbol,)
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        book = OrderBookAssembler(symbol, max_age_seconds=float(payload["max_age_seconds"]))
        book.asks = {Decimal(price): (str(price), str(size)) for price, size in payload["asks"]}
        book.bids = {Decimal(price): (str(price), str(size)) for price, size in payload["bids"]}
        book.last_sequence = payload["last_sequence"]
        book.last_event_time_utc = (
            datetime.fromisoformat(payload["last_event_time_utc"])
            if payload["last_event_time_utc"]
            else None
        )
        book.last_received_at_utc = (
            datetime.fromisoformat(payload["last_received_at_utc"])
            if payload.get("last_received_at_utc")
            else None
        )
        book.valid = bool(payload["valid"])
        book.reason = str(payload["reason"])
        return book

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
            conn.execute(
                "INSERT OR IGNORE INTO candidate_revisions VALUES (?, ?, ?, ?)",
                (
                    candidate.candidate_id,
                    candidate.snapshot_id,
                    candidate.observed_at_utc.astimezone(UTC).isoformat(),
                    candidate.model_dump_json(),
                ),
            )
            return cursor.rowcount == 1

    def add_candidate_with_lifecycle(
        self, candidate: Candidate, initial_event: CandidateLifecycleEvent
    ) -> bool:
        """Atomically create a candidate, revision and its initial lifecycle event."""
        if (
            initial_event.candidate_id != candidate.candidate_id
            or initial_event.snapshot_id != candidate.snapshot_id
            or initial_event.from_state is not None
            or initial_event.to_state.value != "CANDIDATE"
        ):
            raise ValueError("Initial lifecycle event does not match candidate")
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
            conn.execute(
                "INSERT OR IGNORE INTO candidate_revisions VALUES (?, ?, ?, ?)",
                (
                    candidate.candidate_id,
                    candidate.snapshot_id,
                    candidate.observed_at_utc.astimezone(UTC).isoformat(),
                    candidate.model_dump_json(),
                ),
            )
            lifecycle_exists = conn.execute(
                "SELECT 1 FROM candidate_lifecycle_events WHERE candidate_id=? LIMIT 1",
                (candidate.candidate_id,),
            ).fetchone()
            if lifecycle_exists is None:
                conn.execute(
                    "INSERT INTO candidate_lifecycle_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        initial_event.event_id,
                        initial_event.candidate_id,
                        initial_event.snapshot_id,
                        None,
                        initial_event.to_state.value,
                        initial_event.occurred_at_utc.astimezone(UTC).isoformat(),
                        initial_event.reason[:500],
                        initial_event.model_dump_json(),
                    ),
                )
            return cursor.rowcount == 1

    def add_feature_snapshot(self, snapshot: FeatureSnapshot) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO feature_snapshots VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot.snapshot_id,
                    snapshot.observed_at_utc.astimezone(UTC).isoformat(),
                    snapshot.symbol,
                    snapshot.engine,
                    snapshot.model_dump_json(),
                ),
            )
            return cursor.rowcount == 1

    def feature_snapshot(self, snapshot_id: str) -> FeatureSnapshot | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM feature_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
        return FeatureSnapshot.model_validate_json(row[0]) if row else None

    def record_candidate_lifecycle(self, event: CandidateLifecycleEvent) -> bool:
        """Atomically append only when the persisted latest state matches ``from_state``."""
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT to_state, occurred_at_utc FROM candidate_lifecycle_events "
                "WHERE candidate_id=? "
                "ORDER BY occurred_at_utc DESC, event_id DESC LIMIT 1",
                (event.candidate_id,),
            ).fetchone()
            persisted = row[0] if row else None
            expected = event.from_state.value if event.from_state is not None else None
            if persisted != expected:
                return False
            if row is not None and event.occurred_at_utc <= datetime.fromisoformat(row[1]):
                return False
            cursor = conn.execute(
                "INSERT OR IGNORE INTO candidate_lifecycle_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.candidate_id,
                    event.snapshot_id,
                    event.from_state.value if event.from_state is not None else None,
                    event.to_state.value,
                    event.occurred_at_utc.astimezone(UTC).isoformat(),
                    event.reason[:500],
                    event.model_dump_json(),
                ),
            )
            return cursor.rowcount == 1

    def candidate_lifecycle(self, candidate_id: str) -> list[CandidateLifecycleEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM candidate_lifecycle_events "
                "WHERE candidate_id=? ORDER BY occurred_at_utc, event_id",
                (candidate_id,),
            ).fetchall()
        return [CandidateLifecycleEvent.model_validate_json(row[0]) for row in rows]

    def candidate_revisions(self, candidate_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM candidate_revisions "
                "WHERE candidate_id=? ORDER BY observed_at_utc, snapshot_id",
                (candidate_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def active_candidates(self, *, engine: str, symbol: str | None = None) -> list[Candidate]:
        """Return candidates whose latest append-only lifecycle state is CANDIDATE."""
        symbol_filter = "AND c.symbol=?" if symbol is not None else ""
        parameters: tuple[str, ...] = (
            ("CANDIDATE", symbol) if symbol is not None else ("CANDIDATE",)
        )
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT COALESCE(
                    (
                        SELECT r.payload FROM candidate_revisions r
                        WHERE r.candidate_id=c.candidate_id
                        ORDER BY r.observed_at_utc DESC, r.snapshot_id DESC LIMIT 1
                    ),
                    c.payload
                )
                FROM candidates c
                JOIN candidate_lifecycle_events e
                  ON e.event_id = (
                    SELECT latest.event_id
                    FROM candidate_lifecycle_events latest
                    WHERE latest.candidate_id = c.candidate_id
                    ORDER BY latest.occurred_at_utc DESC, latest.event_id DESC
                    LIMIT 1
                  )
                WHERE e.to_state=? {symbol_filter}
                ORDER BY c.created_at, c.candidate_id
                """,
                parameters,
            ).fetchall()
        candidates = [Candidate.model_validate_json(row[0]) for row in rows]
        return [candidate for candidate in candidates if candidate.engine == engine]

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
                SELECT COALESCE(
                    (
                        SELECT r.payload FROM candidate_revisions r
                        WHERE r.candidate_id=c.candidate_id
                        ORDER BY r.observed_at_utc DESC, r.snapshot_id DESC LIMIT 1
                    ),
                    c.payload
                ), d.payload
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
        output: list[dict] = []
        with self._conn() as conn:
            for engine in engines:
                row = conn.execute(
                    "SELECT state, updated_at, detail FROM service_status WHERE service=?",
                    (engine.id,),
                ).fetchone()
                symbol_row = conn.execute(
                    "SELECT symbol FROM feature_snapshots WHERE engine=? "
                    "ORDER BY observed_at_utc DESC, snapshot_id DESC LIMIT 1",
                    (engine.id,),
                ).fetchone()
                if symbol_row:
                    engine.symbol = symbol_row[0]
                item = engine.model_dump()
                if row:
                    engine.state = row[0]
                    item = engine.model_dump()
                    item["updated_at_utc"] = row[1]
                    item["detail"] = row[2]
                output.append(item)
        return output
