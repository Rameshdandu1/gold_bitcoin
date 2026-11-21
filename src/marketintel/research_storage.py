"""SQLite stores isolated from production review, budget, and notification state."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from marketintel.research_models import (
    ArmDecision,
    DatasetManifest,
    ExperimentConfig,
    OpportunityRecord,
    ReplayPoint,
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

    def save_points(self, experiment_id: str, points: list[ReplayPoint]) -> None:
        with _connect(self.path) as db:
            db.executemany(
                "INSERT OR REPLACE INTO replay_points VALUES (?, ?, ?)",
                [
                    (experiment_id, row.evaluated_at_utc.isoformat(), row.model_dump_json())
                    for row in points
                ],
            )

    def save_opportunity(self, experiment_id: str, record: OpportunityRecord) -> None:
        with _connect(self.path) as db:
            db.execute(
                "INSERT OR REPLACE INTO opportunities VALUES (?, ?, ?, ?)",
                (
                    experiment_id,
                    record.opportunity_id,
                    record.revision_id,
                    record.model_dump_json(),
                ),
            )

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
            db.execute(
                "INSERT OR REPLACE INTO reports VALUES (?, ?, ?, ?)",
                (experiment_id, name, payload, datetime.now(UTC).isoformat()),
            )

    def summary(self) -> dict:
        with _connect(self.path) as db:
            experiments = db.execute("SELECT COUNT(*) AS count FROM experiments").fetchone()[
                "count"
            ]
            latest = db.execute(
                "SELECT experiment_id, created_at_utc FROM experiments "
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
            "latest_experiment": dict(latest) if latest else None,
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
                """
            )

    def record_decision(
        self,
        opportunity_id: str,
        revision_id: str,
        decision: ArmDecision,
        *,
        recorded_at: datetime | None = None,
    ) -> bool:
        recorded_at = recorded_at or datetime.now(UTC)
        if decision.ready_at_utc > recorded_at:
            raise ValueError("Cannot prospectively record a future decision")
        payload = decision.model_dump_json()
        with _connect(self.path) as db:
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
                return False
        return True

    def record_outcome(
        self, revision_id: str, outcome: ResearchOutcome, *, recorded_at: datetime | None = None
    ) -> bool:
        if outcome.code not in self.TERMINAL:
            raise ValueError("Outcome is not terminal")
        recorded_at = recorded_at or datetime.now(UTC)
        with _connect(self.path) as db:
            row = db.execute(
                "SELECT recorded_at_utc, outcome_json FROM paper_decisions "
                "WHERE opportunity_id=? AND revision_id=? AND arm=?",
                (outcome.opportunity_id, revision_id, outcome.arm),
            ).fetchone()
            if row is None:
                raise ValueError("A prospective decision must be recorded before its outcome")
            if recorded_at < datetime.fromisoformat(row["recorded_at_utc"]):
                raise ValueError("Outcome cannot predate decision persistence")
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
        return True

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
        return {
            "status": "NOT_STARTED" if decisions == 0 else "EXPLORATORY",
            "decisions": decisions,
            "outcomes": outcomes,
            "explicit_gaps": gaps,
            "warning": "Prospective paper observation only; no orders are supported.",
        }
