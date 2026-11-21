"""SQLite WAL audit store with an append-only M1 public-event journal."""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from marketintel.analysis import CanonicalAnalysis, candidate_revision_id
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
from marketintel.review import ConsensusDecisionV2, ProviderResult


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
                CREATE TABLE IF NOT EXISTS source_health (
                    source TEXT PRIMARY KEY,
                    transition_at_utc TEXT NOT NULL,
                    heartbeat_at_utc TEXT NOT NULL,
                    last_success_at_utc TEXT,
                    state TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS candidate_price_watermarks (
                    candidate_id TEXT PRIMARY KEY,
                    received_at_utc TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rest_candle_observations (
                    observation_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    request_start_utc TEXT NOT NULL,
                    request_end_utc TEXT NOT NULL,
                    response_available_at_utc TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS rest_candle_observations_no_update
                    BEFORE UPDATE ON rest_candle_observations
                    BEGIN SELECT RAISE(ABORT, 'rest_candle_observations is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS rest_candle_observations_no_delete
                    BEFORE DELETE ON rest_candle_observations
                    BEGIN SELECT RAISE(ABORT, 'rest_candle_observations is append-only'); END;
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
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at_utc TEXT NOT NULL
                );
            """)
            self._apply_phase3_migration(conn)
            self._backfill_candidate_revision_identities(conn)

    def _apply_phase3_migration(self, conn: sqlite3.Connection) -> None:
        migration_id = "0003_phase3_review_pipeline"
        if conn.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id=?", (migration_id,)
        ).fetchone():
            return
        conn.executescript("""
            CREATE TABLE analysis_envelopes (
                digest TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                canonical_bytes BLOB NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE UNIQUE INDEX analysis_envelope_identity
                ON analysis_envelopes (candidate_id, revision_id, digest);
            CREATE TRIGGER analysis_envelopes_no_update
                BEFORE UPDATE ON analysis_envelopes
                BEGIN SELECT RAISE(ABORT, 'analysis_envelopes is append-only'); END;
            CREATE TRIGGER analysis_envelopes_no_delete
                BEFORE DELETE ON analysis_envelopes
                BEGIN SELECT RAISE(ABORT, 'analysis_envelopes is append-only'); END;
            CREATE TABLE candidate_revision_identities (
                revision_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                observed_at_utc TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(candidate_id, snapshot_id)
            );
            CREATE TABLE active_candidate_revisions (
                candidate_id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                observed_at_utc TEXT NOT NULL,
                generation INTEGER NOT NULL
            );
            CREATE TABLE review_runs (
                run_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                envelope_digest TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                risk_policy_version TEXT NOT NULL,
                provider_config_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                deadline_at_utc TEXT NOT NULL,
                UNIQUE(revision_id, envelope_digest, prompt_version, provider_config_json)
            );
            CREATE TABLE review_jobs (
                job_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                available_at_utc TEXT NOT NULL,
                lease_owner TEXT,
                lease_expires_at_utc TEXT,
                lease_generation INTEGER NOT NULL DEFAULT 0,
                dispatch_id TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE INDEX review_jobs_claimable
                ON review_jobs(status, available_at_utc, lease_expires_at_utc);
            CREATE TABLE provider_attempts_v2 (
                attempt_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                lease_generation INTEGER NOT NULL,
                dispatch_id TEXT NOT NULL UNIQUE,
                requested_model TEXT NOT NULL,
                returned_model TEXT,
                status TEXT NOT NULL,
                started_at_utc TEXT NOT NULL,
                completed_at_utc TEXT,
                request_id TEXT,
                response_id TEXT,
                finish_reason TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_microusd INTEGER,
                actual_cost_microusd INTEGER,
                failure_code TEXT,
                assessment_json TEXT,
                metadata_json TEXT NOT NULL,
                UNIQUE(run_id, provider, attempt_number)
            );
            CREATE TRIGGER provider_attempts_v2_no_update
                BEFORE UPDATE ON provider_attempts_v2
                BEGIN SELECT RAISE(ABORT, 'provider_attempts_v2 is append-only'); END;
            CREATE TRIGGER provider_attempts_v2_no_delete
                BEFORE DELETE ON provider_attempts_v2
                BEGIN SELECT RAISE(ABORT, 'provider_attempts_v2 is append-only'); END;
            CREATE TABLE consensus_decisions_v2 (
                decision_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                candidate_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                envelope_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                decided_at_utc TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TRIGGER consensus_decisions_v2_no_update
                BEFORE UPDATE ON consensus_decisions_v2
                BEGIN SELECT RAISE(ABORT, 'consensus_decisions_v2 is append-only'); END;
            CREATE TRIGGER consensus_decisions_v2_no_delete
                BEFORE DELETE ON consensus_decisions_v2
                BEGIN SELECT RAISE(ABORT, 'consensus_decisions_v2 is append-only'); END;
            CREATE TABLE budget_ledger (
                reservation_id TEXT PRIMARY KEY,
                day_utc TEXT NOT NULL,
                run_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                reserved_calls INTEGER NOT NULL,
                reserved_input_tokens INTEGER NOT NULL,
                reserved_output_tokens INTEGER NOT NULL,
                reserved_cost_microusd INTEGER NOT NULL,
                actual_input_tokens INTEGER,
                actual_output_tokens INTEGER,
                actual_cost_microusd INTEGER,
                status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                reconciled_at_utc TEXT,
                UNIQUE(run_id, provider, attempt_number)
            );
            CREATE TRIGGER budget_ledger_no_delete
                BEFORE DELETE ON budget_ledger
                BEGIN SELECT RAISE(ABORT, 'budget_ledger is audit history'); END;
            CREATE TABLE notification_outbox (
                outbox_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                destination_id TEXT NOT NULL,
                delivery_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at_utc TEXT NOT NULL,
                lease_owner TEXT,
                lease_expires_at_utc TEXT,
                lease_generation INTEGER NOT NULL DEFAULT 0,
                receipt_id TEXT,
                last_error TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
        """)
        conn.execute(
            "INSERT INTO schema_migrations VALUES (?, ?)",
            (migration_id, datetime.now(UTC).isoformat()),
        )

    def _backfill_candidate_revision_identities(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT candidate_id, snapshot_id, observed_at_utc, payload "
            "FROM candidate_revisions ORDER BY observed_at_utc"
        ).fetchall()
        for candidate_id_value, snapshot_id, observed_at, payload in rows:
            candidate = Candidate.model_validate_json(payload)
            revision_id = candidate_revision_id(candidate)
            conn.execute(
                "INSERT OR IGNORE INTO candidate_revision_identities VALUES (?, ?, ?, ?, ?)",
                (revision_id, candidate_id_value, snapshot_id, observed_at, payload),
            )
            active = conn.execute(
                "SELECT observed_at_utc FROM active_candidate_revisions WHERE candidate_id=?",
                (candidate_id_value,),
            ).fetchone()
            if active is None:
                conn.execute(
                    "INSERT INTO active_candidate_revisions VALUES (?, ?, ?, ?, 1)",
                    (candidate_id_value, revision_id, snapshot_id, observed_at),
                )
            elif observed_at > active[0]:
                conn.execute(
                    "UPDATE active_candidate_revisions SET revision_id=?, snapshot_id=?, "
                    "observed_at_utc=?, generation=generation+1 WHERE candidate_id=?",
                    (revision_id, snapshot_id, observed_at, candidate_id_value),
                )

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
            health = conn.execute(
                "SELECT transition_at_utc, last_success_at_utc FROM source_health WHERE source=?",
                (source,),
            ).fetchone()
            transition_at = (
                health[0] if current == (state, safe_detail) and health else occurred_at.isoformat()
            )
            success = state in {"AVAILABLE", "VALID", "CONNECTED"}
            last_success = (
                occurred_at.astimezone(UTC).isoformat()
                if success
                else (health[1] if health else None)
            )
            conn.execute(
                "INSERT OR REPLACE INTO source_health VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    source,
                    transition_at,
                    occurred_at.astimezone(UTC).isoformat(),
                    last_success,
                    state,
                    safe_detail,
                    None if success else safe_detail,
                ),
            )
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

    def source_health(self, source: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT source, transition_at_utc, heartbeat_at_utc, last_success_at_utc, "
                "state, detail, last_error FROM source_health WHERE source=?",
                (source,),
            ).fetchone()
        if row is None:
            return None
        fields = (
            "source",
            "transition_at_utc",
            "heartbeat_at_utc",
            "last_success_at_utc",
            "state",
            "detail",
            "last_error",
        )
        return dict(zip(fields, row, strict=True))

    def source_is_eligible(
        self, source: str, *, now: datetime, maximum_success_age_seconds: int
    ) -> bool:
        health = self.source_health(source)
        if health is None or health["last_success_at_utc"] is None:
            return False
        verified = datetime.fromisoformat(health["last_success_at_utc"])
        age = (now - verified).total_seconds()
        return 0 <= age <= maximum_success_age_seconds

    def journal_rest_candles(
        self,
        *,
        source: str,
        symbol: str,
        resolution: str,
        request_start: datetime,
        request_end: datetime,
        response_available_at: datetime,
        candles: list,
    ) -> str:
        payload = json.dumps(
            [candle.model_dump(mode="json") for candle in candles],
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        identity = "|".join(
            [
                source,
                symbol,
                resolution,
                request_start.astimezone(UTC).isoformat(),
                request_end.astimezone(UTC).isoformat(),
                response_available_at.astimezone(UTC).isoformat(),
                digest,
            ]
        )
        observation_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO rest_candle_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observation_id,
                    source,
                    symbol,
                    resolution,
                    request_start.astimezone(UTC).isoformat(),
                    request_end.astimezone(UTC).isoformat(),
                    response_available_at.astimezone(UTC).isoformat(),
                    digest,
                    payload,
                ),
            )
        return observation_id

    def candidate_trade_events(
        self, candidate: Candidate, *, through: datetime
    ) -> list[RawMarketEvent]:
        with self._conn() as conn:
            watermark = conn.execute(
                "SELECT received_at_utc, event_id FROM candidate_price_watermarks "
                "WHERE candidate_id=?",
                (candidate.candidate_id,),
            ).fetchone()
            received_at = (
                watermark[0] if watermark else candidate.observed_at_utc.astimezone(UTC).isoformat()
            )
            event_id = watermark[1] if watermark else ""
            rows = conn.execute(
                "SELECT event_id, schema_version, venue, symbol, channel, event_time_utc, "
                "received_at_utc, publish_time_utc, sequence, checksum, payload "
                "FROM raw_market_events WHERE symbol=? AND channel='trades' "
                "AND event_time_utc>=? AND received_at_utc<=? "
                "AND (received_at_utc>? OR (received_at_utc=? AND event_id>?)) "
                "ORDER BY received_at_utc, event_time_utc, event_id",
                (
                    candidate.symbol,
                    candidate.observed_at_utc.astimezone(UTC).isoformat(),
                    through.astimezone(UTC).isoformat(),
                    received_at,
                    received_at,
                    event_id,
                ),
            ).fetchall()
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

    def advance_candidate_price_watermark(self, candidate_id: str, event: RawMarketEvent) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO candidate_price_watermarks VALUES (?, ?, ?, ?)",
                (
                    candidate_id,
                    event.received_at_utc.astimezone(UTC).isoformat(),
                    event.event_id,
                    datetime.now(UTC).isoformat(),
                ),
            )

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

    @staticmethod
    def _record_revision_identity(conn: sqlite3.Connection, candidate: Candidate) -> str:
        revision_id = candidate_revision_id(candidate)
        observed_at = candidate.observed_at_utc.astimezone(UTC).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO candidate_revision_identities VALUES (?, ?, ?, ?, ?)",
            (
                revision_id,
                candidate.candidate_id,
                candidate.snapshot_id,
                observed_at,
                candidate.model_dump_json(),
            ),
        )
        active = conn.execute(
            "SELECT observed_at_utc FROM active_candidate_revisions WHERE candidate_id=?",
            (candidate.candidate_id,),
        ).fetchone()
        if active is None:
            conn.execute(
                "INSERT INTO active_candidate_revisions VALUES (?, ?, ?, ?, 1)",
                (candidate.candidate_id, revision_id, candidate.snapshot_id, observed_at),
            )
        elif observed_at > active[0]:
            conn.execute(
                "UPDATE active_candidate_revisions SET revision_id=?, snapshot_id=?, "
                "observed_at_utc=?, generation=generation+1 WHERE candidate_id=?",
                (revision_id, candidate.snapshot_id, observed_at, candidate.candidate_id),
            )
        return revision_id

    def activate_candidate_revision(self, candidate_id: str, revision_id: str) -> int:
        """Explicitly select a tied/new revision and return its eligibility generation."""
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT snapshot_id, observed_at_utc FROM candidate_revision_identities "
                "WHERE candidate_id=? AND revision_id=?",
                (candidate_id, revision_id),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown candidate revision")
            conn.execute(
                "INSERT INTO active_candidate_revisions VALUES (?, ?, ?, ?, 1) "
                "ON CONFLICT(candidate_id) DO UPDATE SET revision_id=excluded.revision_id, "
                "snapshot_id=excluded.snapshot_id, observed_at_utc=excluded.observed_at_utc, "
                "generation=active_candidate_revisions.generation+1",
                (candidate_id, revision_id, row[0], row[1]),
            )
            generation = conn.execute(
                "SELECT generation FROM active_candidate_revisions WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
        return int(generation[0])

    def active_candidate_revision(self, candidate_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT revision_id, snapshot_id, observed_at_utc, generation "
                "FROM active_candidate_revisions WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "revision_id": row[0],
            "snapshot_id": row[1],
            "observed_at_utc": row[2],
            "generation": int(row[3]),
        }

    def save_analysis_envelope(self, analysis: CanonicalAnalysis) -> bool:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT canonical_bytes FROM analysis_envelopes WHERE digest=?",
                (analysis.digest,),
            ).fetchone()
            if existing is not None:
                if bytes(existing[0]) != analysis.canonical_bytes:
                    raise ValueError("Conflicting canonical bytes for analysis digest")
                return False
            conn.execute(
                "INSERT INTO analysis_envelopes VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    analysis.digest,
                    analysis.envelope.candidate_id,
                    analysis.envelope.candidate_revision_id,
                    analysis.envelope.snapshot_id,
                    analysis.envelope.schema_version,
                    analysis.canonical_bytes,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return True

    def analysis_envelope_bytes(self, digest: str) -> bytes | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT canonical_bytes FROM analysis_envelopes WHERE digest=?", (digest,)
            ).fetchone()
        return bytes(row[0]) if row else None

    def create_review_run(
        self,
        analysis: CanonicalAnalysis,
        *,
        provider_config: dict,
        deadline_at: datetime,
        now: datetime | None = None,
    ) -> str:
        now = now or datetime.now(UTC)
        if deadline_at <= now:
            raise ValueError("Review deadline must be in the future")
        self.save_analysis_envelope(analysis)
        config_json = json.dumps(provider_config, sort_keys=True, separators=(",", ":"))
        identity = "|".join(
            [
                analysis.envelope.candidate_revision_id,
                analysis.digest,
                analysis.envelope.prompt_version,
                config_json,
            ]
        )
        run_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        job_id = hashlib.sha256(f"review-job|{run_id}".encode()).hexdigest()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO review_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    analysis.envelope.candidate_id,
                    analysis.envelope.candidate_revision_id,
                    analysis.digest,
                    analysis.envelope.prompt_version,
                    analysis.envelope.schema_version,
                    analysis.envelope.risk_policy_version,
                    config_json,
                    "QUEUED",
                    now.astimezone(UTC).isoformat(),
                    deadline_at.astimezone(UTC).isoformat(),
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO review_jobs VALUES (?, ?, 'QUEUED', ?, NULL, NULL, 0, "
                "NULL, ?, ?)",
                (
                    job_id,
                    run_id,
                    now.astimezone(UTC).isoformat(),
                    now.astimezone(UTC).isoformat(),
                    now.astimezone(UTC).isoformat(),
                ),
            )
        return run_id

    def claim_review_job(
        self, owner: str, *, now: datetime, lease_seconds: int = 60
    ) -> dict | None:
        if not owner or lease_seconds < 1:
            raise ValueError("Lease owner and positive duration are required")
        now_text = now.astimezone(UTC).isoformat()
        expires = (now + timedelta(seconds=lease_seconds)).astimezone(UTC).isoformat()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT job_id, run_id, lease_generation FROM review_jobs "
                "WHERE available_at_utc<=? AND (status='QUEUED' OR "
                "(status='CLAIMED' AND lease_expires_at_utc<?)) "
                "ORDER BY created_at_utc, job_id LIMIT 1",
                (now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            generation = int(row[2]) + 1
            changed = conn.execute(
                "UPDATE review_jobs SET status='CLAIMED', lease_owner=?, "
                "lease_expires_at_utc=?, lease_generation=?, updated_at_utc=? "
                "WHERE job_id=? AND lease_generation=?",
                (owner, expires, generation, now_text, row[0], row[2]),
            )
            if changed.rowcount != 1:
                return None
        return {
            "job_id": row[0],
            "run_id": row[1],
            "owner": owner,
            "generation": generation,
            "lease_expires_at_utc": expires,
        }

    def mark_review_dispatched(
        self,
        job_id: str,
        *,
        owner: str,
        generation: int,
        dispatch_id: str,
        now: datetime,
    ) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE review_jobs SET status='DISPATCHED', dispatch_id=?, updated_at_utc=? "
                "WHERE job_id=? AND status='CLAIMED' AND lease_owner=? "
                "AND lease_generation=? AND lease_expires_at_utc>=?",
                (
                    dispatch_id,
                    now.astimezone(UTC).isoformat(),
                    job_id,
                    owner,
                    generation,
                    now.astimezone(UTC).isoformat(),
                ),
            )
        return cursor.rowcount == 1

    def review_run(self, run_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT candidate_id, revision_id, envelope_digest, prompt_version, "
                "schema_version, risk_policy_version, provider_config_json, status, "
                "created_at_utc, deadline_at_utc FROM review_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        fields = (
            "candidate_id",
            "revision_id",
            "envelope_digest",
            "prompt_version",
            "schema_version",
            "risk_policy_version",
            "provider_config",
            "status",
            "created_at_utc",
            "deadline_at_utc",
        )
        result = dict(zip(fields, row, strict=True))
        result["provider_config"] = json.loads(result["provider_config"])
        return result

    def save_provider_result(
        self,
        *,
        run_id: str,
        job_id: str,
        owner: str,
        generation: int,
        dispatch_id: str,
        result: ProviderResult,
    ) -> str | None:
        attempt_id = hashlib.sha256(
            f"{run_id}|{result.provider}|{result.attempt_number}|{dispatch_id}".encode()
        ).hexdigest()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            lease = conn.execute(
                "SELECT lease_owner, lease_generation FROM review_jobs "
                "WHERE job_id=? AND run_id=? AND status IN ('CLAIMED', 'DISPATCHED')",
                (job_id, run_id),
            ).fetchone()
            if lease != (owner, generation):
                return None
            try:
                conn.execute(
                    "INSERT INTO provider_attempts_v2 (attempt_id, run_id, provider, "
                    "attempt_number, lease_generation, dispatch_id, requested_model, "
                    "returned_model, status, started_at_utc, completed_at_utc, request_id, "
                    "response_id, finish_reason, input_tokens, output_tokens, "
                    "estimated_cost_microusd, actual_cost_microusd, failure_code, "
                    "assessment_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt_id,
                        run_id,
                        result.provider,
                        result.attempt_number,
                        generation,
                        dispatch_id,
                        result.requested_model,
                        result.returned_model,
                        result.status,
                        result.started_at_utc.astimezone(UTC).isoformat(),
                        result.completed_at_utc.astimezone(UTC).isoformat(),
                        result.request_id,
                        result.response_id,
                        result.finish_reason,
                        result.usage.input_tokens,
                        result.usage.output_tokens,
                        None,
                        None,
                        result.failure_code,
                        result.assessment.model_dump_json() if result.assessment else None,
                        json.dumps(dict(result.safe_metadata), sort_keys=True),
                    ),
                )
            except sqlite3.IntegrityError:
                return None
        return attempt_id

    def provider_results(self, run_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT attempt_id, provider, attempt_number, requested_model, returned_model, "
                "status, started_at_utc, completed_at_utc, request_id, response_id, "
                "finish_reason, input_tokens, output_tokens, failure_code, assessment_json, "
                "metadata_json FROM provider_attempts_v2 WHERE run_id=? "
                "ORDER BY provider, attempt_number",
                (run_id,),
            ).fetchall()
        fields = (
            "attempt_id",
            "provider",
            "attempt_number",
            "requested_model",
            "returned_model",
            "status",
            "started_at_utc",
            "completed_at_utc",
            "request_id",
            "response_id",
            "finish_reason",
            "input_tokens",
            "output_tokens",
            "failure_code",
            "assessment",
            "metadata",
        )
        results = [dict(zip(fields, row, strict=True)) for row in rows]
        for result in results:
            result["assessment"] = (
                json.loads(result["assessment"]) if result["assessment"] else None
            )
            result["metadata"] = json.loads(result["metadata"])
        return results

    @staticmethod
    def _eligibility_token_in_transaction(
        conn: sqlite3.Connection, candidate_id_value: str
    ) -> tuple[str, dict] | None:
        active = conn.execute(
            "SELECT a.revision_id, a.snapshot_id, a.generation, r.payload "
            "FROM active_candidate_revisions a "
            "JOIN candidate_revision_identities r ON r.revision_id=a.revision_id "
            "WHERE a.candidate_id=?",
            (candidate_id_value,),
        ).fetchone()
        if active is None:
            return None
        candidate = json.loads(active[3])
        lifecycle = conn.execute(
            "SELECT event_id, to_state, occurred_at_utc FROM candidate_lifecycle_events "
            "WHERE candidate_id=? ORDER BY occurred_at_utc DESC, event_id DESC LIMIT 1",
            (candidate_id_value,),
        ).fetchone()
        watermark = conn.execute(
            "SELECT received_at_utc, event_id FROM candidate_price_watermarks WHERE candidate_id=?",
            (candidate_id_value,),
        ).fetchone()
        sources = [
            f"product_discovery:{candidate['asset']}",
            f"candle_reconciliation:{candidate['symbol']}",
            f"delta_book:{candidate['symbol']}",
            "delta_websocket",
        ]
        health = []
        for source in sources:
            row = conn.execute(
                "SELECT state, heartbeat_at_utc, last_success_at_utc FROM source_health "
                "WHERE source=?",
                (source,),
            ).fetchone()
            health.append((source, *(row or (None, None, None))))
        book = conn.execute(
            "SELECT updated_at_utc FROM book_checkpoints WHERE symbol=?",
            (candidate["symbol"],),
        ).fetchone()
        evidence = {
            "candidate_id": candidate_id_value,
            "revision_id": active[0],
            "snapshot_id": active[1],
            "generation": int(active[2]),
            "lifecycle": lifecycle,
            "price_watermark": watermark,
            "source_health": health,
            "book_checkpoint_at": book[0] if book else None,
        }
        token = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return token, evidence

    def eligibility_token(self, candidate_id_value: str) -> tuple[str, dict] | None:
        with self._conn() as conn:
            return self._eligibility_token_in_transaction(conn, candidate_id_value)

    def commit_consensus_decision_and_outbox(
        self,
        decision: ConsensusDecisionV2,
        *,
        destination_id: str | None = None,
    ) -> bool:
        """Conditionally commit a revision decision and its alert intent in one transaction."""
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._eligibility_token_in_transaction(conn, decision.candidate_id)
            if current is None:
                return False
            token, evidence = current
            lifecycle = evidence["lifecycle"]
            if (
                token != decision.eligibility.eligibility_token
                or evidence["revision_id"] != decision.candidate_revision_id
                or evidence["generation"] != decision.eligibility.active_revision_generation
                or lifecycle is None
                or lifecycle[1] != decision.eligibility.lifecycle_state
            ):
                return False
            try:
                conn.execute(
                    "INSERT INTO consensus_decisions_v2 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        decision.decision_id,
                        decision.run_id,
                        decision.candidate_id,
                        decision.candidate_revision_id,
                        decision.envelope_digest,
                        decision.status,
                        decision.decided_at_utc.astimezone(UTC).isoformat(),
                        decision.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    "SELECT payload FROM consensus_decisions_v2 WHERE run_id=?",
                    (decision.run_id,),
                ).fetchone()
                return existing is not None and existing[0] == decision.model_dump_json()
            if decision.status == "CONFIRMED":
                if not destination_id:
                    raise ValueError("Confirmed decision requires an alert destination identity")
                delivery_key = hashlib.sha256(
                    (
                        f"{decision.decision_id}|{decision.candidate_revision_id}|"
                        f"CONFIRMED|{destination_id}"
                    ).encode()
                ).hexdigest()
                outbox_id = hashlib.sha256(f"outbox|{delivery_key}".encode()).hexdigest()
                now_text = decision.decided_at_utc.astimezone(UTC).isoformat()
                conn.execute(
                    "INSERT OR IGNORE INTO notification_outbox VALUES (?, ?, ?, ?, ?, ?, ?, "
                    "'PENDING', ?, 0, ?, NULL, NULL, 0, NULL, NULL, ?, ?)",
                    (
                        outbox_id,
                        decision.decision_id,
                        decision.candidate_id,
                        decision.candidate_revision_id,
                        "CONFIRMED",
                        destination_id,
                        delivery_key,
                        decision.model_dump_json(),
                        now_text,
                        now_text,
                        now_text,
                    ),
                )
        return True

    def consensus_decision_v2(self, run_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM consensus_decisions_v2 WHERE run_id=?", (run_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def outbox_items(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT outbox_id, decision_id, candidate_id, revision_id, event_type, "
                "destination_id, delivery_key, status, payload, attempts, available_at_utc, "
                "receipt_id, last_error FROM notification_outbox ORDER BY created_at_utc"
            ).fetchall()
        fields = (
            "outbox_id",
            "decision_id",
            "candidate_id",
            "revision_id",
            "event_type",
            "destination_id",
            "delivery_key",
            "status",
            "payload",
            "attempts",
            "available_at_utc",
            "receipt_id",
            "last_error",
        )
        result = [dict(zip(fields, row, strict=True)) for row in rows]
        for item in result:
            item["payload"] = json.loads(item["payload"])
        return result

    def complete_review_job(
        self,
        job_id: str,
        *,
        owner: str,
        generation: int,
        status: str,
        now: datetime,
    ) -> bool:
        if status not in {"COMPLETED", "WAIT", "FAILED", "DISPATCH_UNKNOWN"}:
            raise ValueError("Invalid terminal review job status")
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE review_jobs SET status=?, lease_owner=NULL, lease_expires_at_utc=NULL, "
                "updated_at_utc=? WHERE job_id=? AND lease_owner=? AND lease_generation=?",
                (
                    status,
                    now.astimezone(UTC).isoformat(),
                    job_id,
                    owner,
                    generation,
                ),
            )
            if cursor.rowcount == 1:
                conn.execute(
                    "UPDATE review_runs SET status=? WHERE run_id=(SELECT run_id FROM review_jobs "
                    "WHERE job_id=?)",
                    (status, job_id),
                )
        return cursor.rowcount == 1

    def reserve_provider_budget(
        self,
        *,
        run_id: str,
        provider: str,
        attempt_number: int,
        now: datetime,
        input_tokens: int,
        output_tokens: int,
        cost_microusd: int,
        provider_call_limit: int,
        total_call_limit: int,
        total_cost_limit_microusd: int,
    ) -> str | None:
        if min(input_tokens, output_tokens, cost_microusd) < 0:
            raise ValueError("Budget reservations cannot be negative")
        day = now.astimezone(UTC).date().isoformat()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            provider_calls = conn.execute(
                "SELECT COALESCE(SUM(reserved_calls), 0) FROM budget_ledger "
                "WHERE day_utc=? AND provider=?",
                (day, provider),
            ).fetchone()[0]
            totals = conn.execute(
                "SELECT COALESCE(SUM(reserved_calls), 0), "
                "COALESCE(SUM(reserved_cost_microusd), 0) FROM budget_ledger WHERE day_utc=?",
                (day,),
            ).fetchone()
            if (
                int(provider_calls) + 1 > provider_call_limit
                or int(totals[0]) + 1 > total_call_limit
                or int(totals[1]) + cost_microusd > total_cost_limit_microusd
            ):
                return None
            reservation_id = uuid.uuid4().hex
            try:
                conn.execute(
                    "INSERT INTO budget_ledger VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, NULL, "
                    "NULL, NULL, 'RESERVED', ?, NULL)",
                    (
                        reservation_id,
                        day,
                        run_id,
                        provider,
                        attempt_number,
                        input_tokens,
                        output_tokens,
                        cost_microusd,
                        now.astimezone(UTC).isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                return None
        return reservation_id

    def reconcile_provider_budget(
        self,
        reservation_id: str,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        actual_cost_microusd: int | None,
        status: str,
        now: datetime,
    ) -> bool:
        if status not in {"RECONCILED", "USAGE_UNKNOWN"}:
            raise ValueError("Invalid budget reconciliation status")
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE budget_ledger SET actual_input_tokens=?, actual_output_tokens=?, "
                "actual_cost_microusd=?, status=?, reconciled_at_utc=? "
                "WHERE reservation_id=? AND status='RESERVED'",
                (
                    input_tokens,
                    output_tokens,
                    actual_cost_microusd,
                    status,
                    now.astimezone(UTC).isoformat(),
                    reservation_id,
                ),
            )
        return cursor.rowcount == 1

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
            self._record_revision_identity(conn, candidate)
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
            self._record_revision_identity(conn, candidate)
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
                SELECT r.payload
                FROM candidates c
                JOIN active_candidate_revisions a ON a.candidate_id=c.candidate_id
                JOIN candidate_revision_identities r ON r.revision_id=a.revision_id
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
                SELECT r.payload, a.revision_id,
                (
                    SELECT d2.payload FROM consensus_decisions_v2 d2
                    WHERE d2.candidate_id=c.candidate_id AND d2.revision_id=a.revision_id
                    ORDER BY d2.decided_at_utc DESC, d2.decision_id DESC LIMIT 1
                ),
                (
                    SELECT e.to_state FROM candidate_lifecycle_events e
                    WHERE e.candidate_id=c.candidate_id
                    ORDER BY e.occurred_at_utc DESC, e.event_id DESC LIMIT 1
                ),
                (
                    SELECT e.reason FROM candidate_lifecycle_events e
                    WHERE e.candidate_id=c.candidate_id
                    ORDER BY e.occurred_at_utc DESC, e.event_id DESC LIMIT 1
                ),
                (
                    SELECT e.occurred_at_utc FROM candidate_lifecycle_events e
                    WHERE e.candidate_id=c.candidate_id
                    ORDER BY e.occurred_at_utc DESC, e.event_id DESC LIMIT 1
                )
                FROM candidates c
                JOIN active_candidate_revisions a ON a.candidate_id=c.candidate_id
                JOIN candidate_revision_identities r ON r.revision_id=a.revision_id
                ORDER BY c.created_at DESC LIMIT ?
            """,
                (min(max(limit, 1), 200),),
            ).fetchall()
        return [
            {
                "candidate": json.loads(candidate),
                "candidate_revision_id": revision_id,
                "consensus": json.loads(decision) if decision else None,
                "current_lifecycle_state": lifecycle_state,
                "current_lifecycle_reason": lifecycle_reason,
                "current_lifecycle_at_utc": lifecycle_at,
            }
            for (
                candidate,
                revision_id,
                decision,
                lifecycle_state,
                lifecycle_reason,
                lifecycle_at,
            ) in rows
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
