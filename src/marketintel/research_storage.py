"""SQLite stores isolated from production review, budget, and notification state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marketintel.research_models import (
    ArmDecision,
    DatasetManifest,
    ExecutableQuote,
    ExperimentConfig,
    OpportunityRecord,
    ReplayObservation,
    ReplayPoint,
    ResearchCandidate,
    ResearchOutcome,
)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


class ResearchStore:
    """Experiment state deliberately has no production tables or transports."""

    def __init__(self, path: Path, *, production_path: Path | None = None) -> None:
        if production_path is not None and path.resolve() == production_path.resolve():
            raise ValueError("Research database must be isolated from production state")
        self.path = path
        with _connect(path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    manifest_json TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replay_points (
                    experiment_id TEXT NOT NULL,
                    evaluated_at_utc TEXT NOT NULL,
                    point_json TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, evaluated_at_utc),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS opportunities (
                    experiment_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, opportunity_id, revision_id),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS reports (
                    experiment_id TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, report_name),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS research_observations (
                    experiment_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    available_at_utc TEXT NOT NULL,
                    persistence_sequence INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, observation_id),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE INDEX IF NOT EXISTS research_observations_time
                    ON research_observations (
                        experiment_id, kind, symbol, available_at_utc, persistence_sequence
                    );
                CREATE TABLE IF NOT EXISTS research_candidates (
                    experiment_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    persisted_at_utc TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, opportunity_id, revision_id),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS arm_decisions (
                    experiment_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    arm TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    persisted_at_utc TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, opportunity_id, revision_id, arm),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS research_outcomes (
                    experiment_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    arm TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    evaluation_version TEXT NOT NULL,
                    persisted_at_utc TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, opportunity_id, revision_id, arm),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS engine_evaluations (
                    experiment_id TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    evaluated_at_utc TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, engine, evaluated_at_utc),
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS holdout_access_events (
                    experiment_id TEXT PRIMARY KEY,
                    config_hash TEXT NOT NULL,
                    accessed_at_utc TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                CREATE TABLE IF NOT EXISTS experiment_action_counts (
                    experiment_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    external_calls INTEGER NOT NULL,
                    real_notifications INTEGER NOT NULL,
                    orders INTEGER NOT NULL,
                    measured_at_utc TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
                );
                """
            )

    def create_experiment(self, manifest: DatasetManifest, config: ExperimentConfig) -> None:
        if manifest.dataset_id != config.dataset_id:
            raise ValueError("Experiment dataset does not match manifest")
        with _connect(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO experiments VALUES (?, ?, ?, ?)",
                (
                    config.experiment_id,
                    manifest.model_dump_json(),
                    config.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            existing = db.execute(
                "SELECT manifest_json, config_json FROM experiments WHERE experiment_id=?",
                (config.experiment_id,),
            ).fetchone()
            if (
                existing["manifest_json"] != manifest.model_dump_json()
                or existing["config_json"] != config.model_dump_json()
            ):
                raise ValueError("Experiment identity is immutable")

    def experiment(self, experiment_id: str) -> tuple[DatasetManifest, ExperimentConfig] | None:
        with _connect(self.path) as db:
            row = db.execute(
                "SELECT manifest_json, config_json FROM experiments WHERE experiment_id=?",
                (experiment_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            DatasetManifest.model_validate_json(row["manifest_json"]),
            ExperimentConfig.model_validate_json(row["config_json"]),
        )

    def record_holdout_access(
        self,
        experiment_id: str,
        config_hash: str,
        *,
        purpose: str,
        accessed_at: datetime | None = None,
    ) -> bool:
        accessed_at = accessed_at or datetime.now(UTC)
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO holdout_access_events VALUES (?, ?, ?, ?)",
                (experiment_id, config_hash, accessed_at.isoformat(), purpose),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT config_hash, purpose FROM holdout_access_events WHERE experiment_id=?",
                    (experiment_id,),
                ).fetchone()
                if existing["config_hash"] != config_hash or existing["purpose"] != purpose:
                    raise ValueError("Protected holdout access identity is immutable")
                return False
        return True

    def experiments(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT experiment_id, manifest_json, config_json, created_at_utc "
                "FROM experiments ORDER BY created_at_utc DESC, experiment_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        result = []
        for row in rows:
            manifest = DatasetManifest.model_validate_json(row["manifest_json"])
            config = ExperimentConfig.model_validate_json(row["config_json"])
            result.append(
                {
                    "experiment_id": row["experiment_id"],
                    "created_at_utc": row["created_at_utc"],
                    "dataset_id": manifest.dataset_id,
                    "dataset_hash": manifest.content_hash,
                    "config_hash": config.canonical_config_hash(),
                    "data_mode": manifest.data_mode,
                    "coverage": [item.model_dump(mode="json") for item in manifest.coverage],
                }
            )
        return result

    def record_action_counts(
        self,
        experiment_id: str,
        *,
        scope: str,
        external_calls: int,
        real_notifications: int,
        orders: int,
        measured_at: datetime,
    ) -> None:
        values = (scope, external_calls, real_notifications, orders)
        if min(external_calls, real_notifications, orders) < 0:
            raise ValueError("Experiment action counters cannot be negative")
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO experiment_action_counts VALUES (?, ?, ?, ?, ?, ?)",
                (experiment_id, *values, measured_at.isoformat()),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT scope, external_calls, real_notifications, orders "
                    "FROM experiment_action_counts WHERE experiment_id=?",
                    (experiment_id,),
                ).fetchone()
                if tuple(existing) != values:
                    raise ValueError("Experiment action-count scope is immutable")

    def experiment_detail(self, experiment_id: str) -> dict | None:
        experiment = self.experiment(experiment_id)
        if experiment is None:
            return None
        manifest, config = experiment
        with _connect(self.path) as db:
            counts = db.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM research_candidates WHERE experiment_id=?) AS candidates, "
                "(SELECT COUNT(DISTINCT opportunity_id) FROM opportunities "
                " WHERE experiment_id=?) AS opportunities, "
                "(SELECT COUNT(*) FROM research_outcomes WHERE experiment_id=?) AS outcomes, "
                "(SELECT COUNT(*) FROM arm_decisions WHERE experiment_id=?) AS decisions",
                (experiment_id, experiment_id, experiment_id, experiment_id),
            ).fetchone()
            actions = db.execute(
                "SELECT scope, external_calls, real_notifications, orders, measured_at_utc "
                "FROM experiment_action_counts WHERE experiment_id=?",
                (experiment_id,),
            ).fetchone()
            report_rows = db.execute(
                "SELECT report_name, report_json, created_at_utc FROM reports "
                "WHERE experiment_id=? ORDER BY report_name",
                (experiment_id,),
            ).fetchall()
        return {
            "experiment_id": experiment_id,
            "manifest": manifest.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "config_hash": config.canonical_config_hash(),
            "counts": dict(counts),
            "engine_matrix": self.engine_matrix(experiment_id),
            "reports": [
                {
                    "name": row["report_name"],
                    "created_at_utc": row["created_at_utc"],
                    "report": json.loads(row["report_json"]),
                }
                for row in report_rows
            ],
            "action_counts": dict(actions) if actions else None,
        }

    def opportunity_page(
        self, experiment_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT record_json FROM opportunities WHERE experiment_id=? "
                "ORDER BY opportunity_id, revision_id LIMIT ? OFFSET ?",
                (experiment_id, limit, offset),
            ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]

    def save_observations(self, experiment_id: str, observations: list[ReplayObservation]) -> None:
        with _connect(self.path) as db:
            for row in observations:
                payload = row.model_dump_json()
                cursor = db.execute(
                    "INSERT OR IGNORE INTO research_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        experiment_id,
                        row.observation_id,
                        row.available_at_utc.isoformat(),
                        row.persistence_sequence,
                        row.kind,
                        row.symbol,
                        payload,
                    ),
                )
                if cursor.rowcount == 0:
                    existing = db.execute(
                        "SELECT observation_json FROM research_observations "
                        "WHERE experiment_id=? AND observation_id=?",
                        (experiment_id, row.observation_id),
                    ).fetchone()
                    if existing["observation_json"] != payload:
                        raise ValueError("Research observation identity is immutable")

    def observations(
        self,
        experiment_id: str,
        *,
        kind: str | None = None,
        symbol: str | None = None,
    ) -> list[ReplayObservation]:
        clauses = ["experiment_id=?"]
        values: list[object] = [experiment_id]
        if kind is not None:
            clauses.append("kind=?")
            values.append(kind)
        if symbol is not None:
            clauses.append("symbol=?")
            values.append(symbol)
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT observation_json FROM research_observations WHERE "
                + " AND ".join(clauses)
                + " ORDER BY available_at_utc, persistence_sequence, observation_id",
                values,
            ).fetchall()
        return [ReplayObservation.model_validate_json(row["observation_json"]) for row in rows]

    def save_engine_evaluation(
        self, experiment_id: str, *, engine: str, evaluated_at: datetime, result: dict
    ) -> None:
        payload = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO engine_evaluations VALUES (?, ?, ?, ?, ?)",
                (experiment_id, engine, evaluated_at.isoformat(), result["state"], payload),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT result_json FROM engine_evaluations WHERE experiment_id=? "
                    "AND engine=? AND evaluated_at_utc=?",
                    (experiment_id, engine, evaluated_at.isoformat()),
                ).fetchone()
                if existing["result_json"] != payload:
                    raise ValueError("Engine evaluation identity is immutable")

    def engine_matrix(self, experiment_id: str) -> list[dict]:
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT engine, state, COUNT(*) AS evaluations, "
                "SUM(CASE WHEN state='CANDIDATE' THEN 1 ELSE 0 END) AS candidates "
                "FROM engine_evaluations WHERE experiment_id=? GROUP BY engine ORDER BY engine",
                (experiment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_candidate(
        self,
        experiment_id: str,
        candidate: ResearchCandidate,
        *,
        persisted_at: datetime,
    ) -> bool:
        payload = candidate.model_dump_json()
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO research_candidates VALUES (?, ?, ?, ?, ?)",
                (
                    experiment_id,
                    candidate.opportunity_id,
                    candidate.revision_id,
                    payload,
                    persisted_at.isoformat(),
                ),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT candidate_json FROM research_candidates WHERE experiment_id=? "
                    "AND opportunity_id=? AND revision_id=?",
                    (experiment_id, candidate.opportunity_id, candidate.revision_id),
                ).fetchone()
                if existing["candidate_json"] != payload:
                    raise ValueError("Research candidate identity is immutable")
                return False
        return True

    def candidates(self, experiment_id: str) -> list[ResearchCandidate]:
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT candidate_json FROM research_candidates WHERE experiment_id=? "
                "ORDER BY persisted_at_utc, opportunity_id, revision_id",
                (experiment_id,),
            ).fetchall()
        return [ResearchCandidate.model_validate_json(row["candidate_json"]) for row in rows]

    def save_arm_decision(
        self,
        experiment_id: str,
        opportunity_id: str,
        revision_id: str,
        decision: ArmDecision,
        *,
        persisted_at: datetime,
    ) -> bool:
        payload = decision.model_dump_json()
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO arm_decisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    experiment_id,
                    opportunity_id,
                    revision_id,
                    decision.arm,
                    payload,
                    persisted_at.isoformat(),
                ),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT decision_json FROM arm_decisions WHERE experiment_id=? "
                    "AND opportunity_id=? AND revision_id=? AND arm=?",
                    (experiment_id, opportunity_id, revision_id, decision.arm),
                ).fetchone()
                if existing["decision_json"] != payload:
                    raise ValueError("Arm decision identity is immutable")
                return False
        return True

    def arm_decisions(
        self, experiment_id: str, opportunity_id: str, revision_id: str
    ) -> list[ArmDecision]:
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT decision_json FROM arm_decisions WHERE experiment_id=? "
                "AND opportunity_id=? AND revision_id=? ORDER BY arm",
                (experiment_id, opportunity_id, revision_id),
            ).fetchall()
        return [ArmDecision.model_validate_json(row["decision_json"]) for row in rows]

    def save_outcome(
        self,
        experiment_id: str,
        revision_id: str,
        outcome: ResearchOutcome,
        *,
        evaluation_version: str = "phase5-outcome-v1",
        persisted_at: datetime | None = None,
    ) -> bool:
        payload = outcome.model_dump_json()
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO research_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    experiment_id,
                    outcome.opportunity_id,
                    revision_id,
                    outcome.arm,
                    payload,
                    evaluation_version,
                    (persisted_at or datetime.now(UTC)).isoformat(),
                ),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT outcome_json, evaluation_version FROM research_outcomes "
                    "WHERE experiment_id=? AND opportunity_id=? AND revision_id=? AND arm=?",
                    (experiment_id, outcome.opportunity_id, revision_id, outcome.arm),
                ).fetchone()
                if existing["outcome_json"] != payload or existing["evaluation_version"] != (
                    evaluation_version
                ):
                    raise ValueError("Research outcome identity is immutable")
                return False
        return True

    def outcomes(
        self, experiment_id: str, opportunity_id: str, revision_id: str
    ) -> dict[str, ResearchOutcome]:
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT arm, outcome_json FROM research_outcomes WHERE experiment_id=? "
                "AND opportunity_id=? AND revision_id=?",
                (experiment_id, opportunity_id, revision_id),
            ).fetchall()
        return {
            row["arm"]: ResearchOutcome.model_validate_json(row["outcome_json"]) for row in rows
        }

    def quotes(
        self, experiment_id: str, symbol: str, *, opportunity_id: str | None = None
    ) -> list[ExecutableQuote]:
        result = []
        for row in self.observations(experiment_id, kind="EXECUTABLE_QUOTE", symbol=symbol):
            payload = dict(row.payload)
            bound_opportunity = payload.pop("opportunity_id", None)
            if bound_opportunity is not None and bound_opportunity != opportunity_id:
                continue
            payload.setdefault("event_id", row.observation_id)
            payload.setdefault("venue", row.venue)
            payload.setdefault("symbol", row.symbol)
            payload.setdefault("observed_at_utc", row.exchange_time_utc)
            result.append(ExecutableQuote.model_validate(payload))
        return result

    def save_points(self, experiment_id: str, points: list[ReplayPoint]) -> None:
        with _connect(self.path) as db:
            for row in points:
                identity = row.evaluated_at_utc.isoformat()
                payload = row.model_dump_json()
                cursor = db.execute(
                    "INSERT OR IGNORE INTO replay_points VALUES (?, ?, ?)",
                    (experiment_id, identity, payload),
                )
                if cursor.rowcount == 0:
                    existing = db.execute(
                        "SELECT point_json FROM replay_points WHERE experiment_id=? "
                        "AND evaluated_at_utc=?",
                        (experiment_id, identity),
                    ).fetchone()
                    if existing["point_json"] != payload:
                        raise ValueError("Replay point identity is immutable")

    def save_opportunity(self, experiment_id: str, record: OpportunityRecord) -> None:
        payload = record.model_dump_json()
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO opportunities VALUES (?, ?, ?, ?)",
                (
                    experiment_id,
                    record.opportunity_id,
                    record.revision_id,
                    payload,
                ),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT record_json FROM opportunities WHERE experiment_id=? "
                    "AND opportunity_id=? AND revision_id=?",
                    (experiment_id, record.opportunity_id, record.revision_id),
                ).fetchone()
                if existing["record_json"] != payload:
                    raise ValueError("Opportunity revision identity is immutable")

    def opportunities(self, experiment_id: str) -> list[OpportunityRecord]:
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT record_json FROM opportunities WHERE experiment_id=? "
                "ORDER BY opportunity_id, revision_id",
                (experiment_id,),
            ).fetchall()
        return [OpportunityRecord.model_validate_json(row["record_json"]) for row in rows]

    def save_report(self, experiment_id: str, name: str, report: dict) -> None:
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"))
        with _connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO reports VALUES (?, ?, ?, ?)",
                (experiment_id, name, payload, datetime.now(UTC).isoformat()),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT report_json FROM reports WHERE experiment_id=? AND report_name=?",
                    (experiment_id, name),
                ).fetchone()
                if existing["report_json"] != payload:
                    raise ValueError("Report identity is immutable; use a versioned report name")

    def summary(self) -> dict:
        with _connect(self.path) as db:
            experiments = db.execute("SELECT COUNT(*) AS count FROM experiments").fetchone()[
                "count"
            ]
            latest = db.execute(
                "SELECT experiment_id, manifest_json, created_at_utc FROM experiments "
                "ORDER BY created_at_utc DESC LIMIT 1"
            ).fetchone()
            reports = db.execute("SELECT COUNT(*) AS count FROM reports").fetchone()["count"]
            opportunities = db.execute("SELECT COUNT(*) AS count FROM opportunities").fetchone()[
                "count"
            ]
        status = (
            "NOT_STARTED"
            if not experiments
            else "INSUFFICIENT_DATA"
            if not reports or opportunities < 30
            else "EXPLORATORY"
        )
        return {
            "status": status,
            "experiment_count": experiments,
            "report_count": reports,
            "opportunity_count": opportunities,
            "latest_experiment": (
                {
                    "experiment_id": latest["experiment_id"],
                    "created_at_utc": latest["created_at_utc"],
                    "data_mode": DatasetManifest.model_validate_json(
                        latest["manifest_json"]
                    ).data_mode,
                }
                if latest
                else None
            ),
            "warning": "Hypothetical research only; no empirical performance claim.",
        }


class PaperLedger:
    """Prospective decisions are immutable and must exist before outcomes."""

    TERMINAL = {
        "NO_ENTRY",
        "TARGET_BEFORE_STOP",
        "STOP_BEFORE_TARGET",
        "TIME_EXIT",
        "AMBIGUOUS",
        "INCOMPLETE",
    }

    def __init__(self, path: Path, *, production_path: Path | None = None) -> None:
        if production_path is not None and path.resolve() == production_path.resolve():
            raise ValueError("Paper ledger must be isolated from production state")
        self.path = path
        with _connect(path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_decisions (
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    arm TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    outcome_json TEXT,
                    outcome_recorded_at_utc TEXT,
                    PRIMARY KEY (opportunity_id, revision_id, arm)
                );
                CREATE TABLE IF NOT EXISTS paper_cursors (
                    source TEXT PRIMARY KEY,
                    cursor TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_gaps (
                    source TEXT NOT NULL,
                    gap_start_utc TEXT NOT NULL,
                    gap_end_utc TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    PRIMARY KEY (source, gap_start_utc, gap_end_utc)
                );
                CREATE TABLE IF NOT EXISTS paper_decision_evidence (
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    arm TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    target_index INTEGER NOT NULL,
                    evidence_mode TEXT NOT NULL,
                    source_identity TEXT NOT NULL,
                    eligible_entry_after_utc TEXT NOT NULL,
                    PRIMARY KEY (opportunity_id, revision_id, arm)
                );
                CREATE TABLE IF NOT EXISTS paper_cursor_bindings (
                    source TEXT PRIMARY KEY,
                    source_identity TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    cursor INTEGER NOT NULL,
                    source_size INTEGER NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_events (
                    event_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    arm TEXT NOT NULL,
                    state TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def record_decision(
        self,
        opportunity_id: str,
        revision_id: str,
        decision: ArmDecision,
        *,
        candidate: ResearchCandidate,
        config_hash: str,
        target_index: int,
        source_identity: str,
        evidence_mode: str = "PROSPECTIVE",
        entry_latency_ms: int = 0,
        recorded_at: datetime | None = None,
    ) -> bool:
        recorded_at = recorded_at or datetime.now(UTC)
        if decision.ready_at_utc > recorded_at:
            raise ValueError("Cannot prospectively record a future decision")
        if candidate.opportunity_id != opportunity_id or candidate.revision_id != revision_id:
            raise ValueError("Paper candidate identity does not match decision key")
        if target_index < 1 or target_index > len(candidate.targets):
            raise ValueError("Paper target identity is not present on candidate revision")
        if evidence_mode not in {"PROSPECTIVE", "HISTORICAL_IMPORT"}:
            raise ValueError("Paper evidence mode must be explicit")
        if len(config_hash) != 64 or any(char not in "0123456789abcdef" for char in config_hash):
            raise ValueError("Paper configuration hash must be canonical SHA-256")
        if not source_identity:
            raise ValueError("Paper source identity is required")
        eligible_entry_after = decision.ready_at_utc + timedelta(milliseconds=entry_latency_ms)
        if evidence_mode == "PROSPECTIVE" and (
            recorded_at > eligible_entry_after or recorded_at >= candidate.expires_at_utc
        ):
            raise ValueError("Prospective decision must be persisted before eligible entry")
        payload = decision.model_dump_json()
        evidence = (
            candidate.model_dump_json(),
            config_hash,
            target_index,
            evidence_mode,
            source_identity,
            eligible_entry_after.isoformat(),
        )
        with _connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "INSERT OR IGNORE INTO paper_decisions VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (opportunity_id, revision_id, decision.arm, payload, recorded_at.isoformat()),
            )
            if cursor.rowcount == 0:
                existing = db.execute(
                    "SELECT decision_json FROM paper_decisions WHERE opportunity_id=? "
                    "AND revision_id=? AND arm=?",
                    (opportunity_id, revision_id, decision.arm),
                ).fetchone()
                if existing["decision_json"] != payload:
                    raise ValueError("Prospective decision is immutable")
                existing_evidence = db.execute(
                    "SELECT candidate_json, config_hash, target_index, evidence_mode, "
                    "source_identity, eligible_entry_after_utc FROM paper_decision_evidence "
                    "WHERE opportunity_id=? AND revision_id=? AND arm=?",
                    (opportunity_id, revision_id, decision.arm),
                ).fetchone()
                if existing_evidence is None or tuple(existing_evidence) != evidence:
                    raise ValueError("Prospective decision evidence is immutable")
                return False
            db.execute(
                "INSERT INTO paper_decision_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    opportunity_id,
                    revision_id,
                    decision.arm,
                    *evidence,
                ),
            )
            event_id = hashlib.sha256(
                f"{opportunity_id}|{revision_id}|{decision.arm}|DECIDED".encode()
            ).hexdigest()
            db.execute(
                "INSERT INTO paper_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    opportunity_id,
                    revision_id,
                    decision.arm,
                    "DECIDED",
                    recorded_at.isoformat(),
                    payload,
                ),
            )
        return True

    def record_outcome(
        self, revision_id: str, outcome: ResearchOutcome, *, recorded_at: datetime | None = None
    ) -> bool:
        if outcome.code not in self.TERMINAL:
            raise ValueError("Outcome is not terminal")
        recorded_at = recorded_at or datetime.now(UTC)
        with _connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT d.recorded_at_utc, d.outcome_json, d.decision_json, "
                "e.candidate_json, e.target_index, e.evidence_mode, "
                "e.eligible_entry_after_utc FROM paper_decisions d "
                "JOIN paper_decision_evidence e USING (opportunity_id, revision_id, arm) "
                "WHERE d.opportunity_id=? AND d.revision_id=? AND d.arm=?",
                (outcome.opportunity_id, revision_id, outcome.arm),
            ).fetchone()
            if row is None:
                raise ValueError("A prospective decision must be recorded before its outcome")
            if recorded_at < datetime.fromisoformat(row["recorded_at_utc"]):
                raise ValueError("Outcome cannot predate decision persistence")
            decision = ArmDecision.model_validate_json(row["decision_json"])
            candidate = ResearchCandidate.model_validate_json(row["candidate_json"])
            if outcome.target_index != int(row["target_index"]):
                raise ValueError("Paper outcome target differs from frozen target identity")
            if outcome.decision_ready_at_utc != decision.ready_at_utc:
                raise ValueError("Paper outcome does not match frozen decision readiness")
            if decision.state != "APPROVED" and outcome.code not in {"NO_ENTRY", "INCOMPLETE"}:
                raise ValueError("Non-approved paper arm cannot receive an executed outcome")
            if row["evidence_mode"] == "PROSPECTIVE":
                persisted = datetime.fromisoformat(row["recorded_at_utc"])
                eligible = datetime.fromisoformat(row["eligible_entry_after_utc"])
                if outcome.entry_at_utc is not None and recorded_at < outcome.entry_at_utc:
                    raise ValueError("Paper entry is not yet factually available")
                if outcome.exit_at_utc is not None and recorded_at < outcome.exit_at_utc:
                    raise ValueError("Paper outcome is not yet factually available")
                if outcome.entry_at_utc is not None and (
                    outcome.entry_at_utc <= persisted or outcome.entry_at_utc < eligible
                ):
                    raise ValueError("Paper entry does not prove write-before-entry chronology")
                if outcome.exit_at_utc is not None and outcome.exit_at_utc <= persisted:
                    raise ValueError("Paper outcome predates prospective persistence")
                if outcome.entry_at_utc is not None and outcome.entry_at_utc < (
                    candidate.observed_at_utc
                ):
                    raise ValueError("Paper entry predates candidate observation")
            payload = outcome.model_dump_json()
            if row["outcome_json"] is not None:
                if row["outcome_json"] != payload:
                    raise ValueError("Paper outcome is immutable")
                return False
            db.execute(
                "UPDATE paper_decisions SET outcome_json=?, outcome_recorded_at_utc=? "
                "WHERE opportunity_id=? AND revision_id=? AND arm=?",
                (
                    payload,
                    recorded_at.isoformat(),
                    outcome.opportunity_id,
                    revision_id,
                    outcome.arm,
                ),
            )
            event_id = hashlib.sha256(
                (f"{outcome.opportunity_id}|{revision_id}|{outcome.arm}|{outcome.code}").encode()
            ).hexdigest()
            db.execute(
                "INSERT INTO paper_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    outcome.opportunity_id,
                    revision_id,
                    outcome.arm,
                    outcome.code,
                    recorded_at.isoformat(),
                    payload,
                ),
            )
        return True

    def bind_cursor(
        self,
        source: str,
        *,
        source_identity: str,
        generation: int,
        cursor: int,
        source_size: int,
        now: datetime | None = None,
    ) -> None:
        if generation < 1 or cursor < 0 or source_size < cursor:
            raise ValueError("Invalid paper cursor/generation/source size")
        with _connect(self.path) as db:
            existing = db.execute(
                "SELECT source_identity, generation, cursor, source_size "
                "FROM paper_cursor_bindings WHERE source=?",
                (source,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["source_identity"] != source_identity
                    or int(existing["generation"]) != generation
                ):
                    raise ValueError("Paper source identity/generation changed")
                if source_size < int(existing["source_size"]) or cursor < int(existing["cursor"]):
                    raise ValueError("Paper source was truncated or cursor moved backward")
            db.execute(
                "INSERT INTO paper_cursor_bindings VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET cursor=excluded.cursor, "
                "source_size=excluded.source_size, updated_at_utc=excluded.updated_at_utc",
                (
                    source,
                    source_identity,
                    generation,
                    cursor,
                    source_size,
                    (now or datetime.now(UTC)).isoformat(),
                ),
            )

    def cursor_binding(self, source: str) -> dict | None:
        with _connect(self.path) as db:
            row = db.execute(
                "SELECT source_identity, generation, cursor, source_size, updated_at_utc "
                "FROM paper_cursor_bindings WHERE source=?",
                (source,),
            ).fetchone()
        return dict(row) if row else None

    def set_cursor(self, source: str, cursor: str, *, now: datetime | None = None) -> None:
        with _connect(self.path) as db:
            db.execute(
                "INSERT OR REPLACE INTO paper_cursors VALUES (?, ?, ?)",
                (source, cursor, (now or datetime.now(UTC)).isoformat()),
            )

    def cursor(self, source: str) -> str | None:
        with _connect(self.path) as db:
            row = db.execute(
                "SELECT cursor FROM paper_cursors WHERE source=?", (source,)
            ).fetchone()
        return row["cursor"] if row else None

    def record_gap(self, source: str, start: datetime, end: datetime, reason: str) -> None:
        if end <= start:
            raise ValueError("Gap interval must increase")
        with _connect(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO paper_gaps VALUES (?, ?, ?, ?)",
                (source, start.isoformat(), end.isoformat(), reason),
            )

    def summary(self) -> dict:
        with _connect(self.path) as db:
            decisions = db.execute("SELECT COUNT(*) AS count FROM paper_decisions").fetchone()[
                "count"
            ]
            outcomes = db.execute(
                "SELECT COUNT(*) AS count FROM paper_decisions WHERE outcome_json IS NOT NULL"
            ).fetchone()["count"]
            gaps = db.execute("SELECT COUNT(*) AS count FROM paper_gaps").fetchone()["count"]
            modes = db.execute(
                "SELECT evidence_mode, COUNT(*) AS count FROM paper_decision_evidence "
                "GROUP BY evidence_mode"
            ).fetchall()
        return {
            "status": "NOT_STARTED" if decisions == 0 else "EXPLORATORY",
            "decisions": decisions,
            "outcomes": outcomes,
            "explicit_gaps": gaps,
            "evidence_modes": {row["evidence_mode"]: row["count"] for row in modes},
            "warning": "Prospective paper observation only; no orders are supported.",
        }

    def transitions(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        with _connect(self.path) as db:
            rows = db.execute(
                "SELECT event_id, opportunity_id, revision_id, arm, state, occurred_at_utc "
                "FROM paper_events ORDER BY occurred_at_utc, event_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]
