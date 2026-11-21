"""Availability-clock historical replay with deterministic checkpoint/resume."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from marketintel.research_models import (
    DatasetManifest,
    ExperimentConfig,
    ReplayCheckpoint,
    ReplayObservation,
    ReplayPoint,
)

_KIND_ORDER = {
    "INSTRUMENT_VERSION": 0,
    "SOURCE_TRANSITION": 1,
    "TRADE": 2,
    "BOOK_SNAPSHOT": 3,
    "BOOK_DELTA": 4,
    "CANDLE_OBSERVATION": 5,
    "CANDIDATE": 6,
    "PROVIDER_COMPLETION": 7,
    "EXECUTABLE_QUOTE": 8,
    "EXPIRY": 9,
}

_RETAINED_OBSERVATION_LIMIT = 128


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _chain(previous: str, value: object) -> str:
    return hashlib.sha256(previous.encode("ascii") + b"\n" + _canonical(value)).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path, *, verify_files: bool = True) -> DatasetManifest:
    manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
    manifest.validate_identity()
    if verify_files:
        for evidence in manifest.files:
            evidence_path = (path.parent / evidence.path).resolve()
            if not evidence_path.is_file():
                raise ValueError(f"Evidence file missing: {evidence.path}")
            if sha256_file(evidence_path) != evidence.sha256:
                raise ValueError(f"Evidence checksum mismatch: {evidence.path}")
            with evidence_path.open("r", encoding="utf-8") as handle:
                count = sum(1 for line in handle if line.strip())
            if count != evidence.record_count:
                raise ValueError(f"Evidence record count mismatch: {evidence.path}")
    return manifest


def iter_observations(
    manifest_path: Path, manifest: DatasetManifest
) -> Iterator[ReplayObservation]:
    """Read evidence a line at a time without retaining the dataset in memory."""
    for evidence in manifest.files:
        path = manifest_path.parent / evidence.path
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    yield ReplayObservation.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid record {evidence.path}:{line_number}: {exc}"
                    ) from exc


def load_observations(manifest_path: Path, manifest: DatasetManifest) -> list[ReplayObservation]:
    """Compatibility helper for small fixtures; the CLI uses the disk spool below."""
    return list(iter_observations(manifest_path, manifest))


def spool_observations(
    manifest_path: Path,
    manifest: DatasetManifest,
    spool_path: Path,
    *,
    batch_size: int = 2_000,
) -> Iterator[ReplayObservation]:
    """Externally sort evidence using bounded batches and temporary SQLite."""
    if batch_size < 1:
        raise ValueError("Spool batch size must be positive")
    connection = sqlite3.connect(spool_path)
    connection.execute(
        """
        CREATE TABLE observations (
            available_at_utc TEXT NOT NULL,
            persistence_sequence INTEGER NOT NULL,
            kind_order INTEGER NOT NULL,
            observation_id TEXT NOT NULL PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """
    )
    pending: list[tuple] = []
    try:
        for observation in iter_observations(manifest_path, manifest):
            pending.append(
                (
                    observation.available_at_utc.astimezone(UTC).isoformat(),
                    observation.persistence_sequence,
                    _KIND_ORDER[observation.kind],
                    observation.observation_id,
                    observation.model_dump_json(),
                )
            )
            if len(pending) >= batch_size:
                connection.executemany("INSERT INTO observations VALUES (?, ?, ?, ?, ?)", pending)
                connection.commit()
                pending.clear()
        if pending:
            connection.executemany("INSERT INTO observations VALUES (?, ?, ?, ?, ?)", pending)
            connection.commit()
        cursor = connection.execute(
            "SELECT payload FROM observations ORDER BY available_at_utc, "
            "persistence_sequence, kind_order, observation_id"
        )
        for row in cursor:
            yield ReplayObservation.model_validate_json(row[0])
    finally:
        connection.close()


def _sort_key(item: ReplayObservation) -> tuple:
    return (
        item.available_at_utc,
        item.persistence_sequence,
        _KIND_ORDER[item.kind],
        item.observation_id,
    )


def _coverage_status(manifest: DatasetManifest, at: datetime) -> tuple[str, str]:
    active = [row for row in manifest.coverage if row.start_utc <= at <= row.end_utc]
    if not active:
        return "UNAVAILABLE", "NO_DECLARED_SOURCE_COVERAGE"
    for row in active:
        if not row.sequence_valid or not row.checksum_valid:
            return "UNAVAILABLE", f"INVALID_SOURCE_COVERAGE:{row.source}"
        if any(start <= at < end for start, end in row.gaps):
            return "UNAVAILABLE", f"DECLARED_SOURCE_GAP:{row.source}"
    return "ELIGIBLE", "FACTUAL_EVIDENCE_AVAILABLE"


def replay(
    manifest: DatasetManifest,
    config: ExperimentConfig,
    observations: Iterable[ReplayObservation],
    *,
    checkpoint: ReplayCheckpoint | None = None,
    maximum_points: int | None = None,
    presorted: bool = False,
    progress: Callable[[int], None] | None = None,
) -> tuple[list[ReplayPoint], ReplayCheckpoint]:
    """Replay by availability time; exchange timestamps never reveal records early."""
    if manifest.dataset_id != config.dataset_id:
        raise ValueError("Experiment dataset does not match replay manifest")
    ordered = observations if presorted else sorted(observations, key=_sort_key)
    config_hash = config.canonical_config_hash()
    if checkpoint is not None:
        if checkpoint.experiment_id != config.experiment_id:
            raise ValueError("Checkpoint belongs to another experiment")
        if checkpoint.dataset_hash != manifest.content_hash:
            raise ValueError("Checkpoint dataset hash differs")
        if checkpoint.config_hash != config_hash:
            raise ValueError("Checkpoint experiment configuration differs")
        if checkpoint.state_schema_version != "phase5-bounded-v1":
            raise ValueError("Checkpoint state schema is unsupported")
        next_evaluation = checkpoint.next_evaluation_utc
        offset = checkpoint.input_offset
        visible = list(checkpoint.visible_observation_ids)
        visible_count = checkpoint.visible_count
        evidence_hash = checkpoint.evidence_hash
        input_prefix_hash = checkpoint.input_prefix_hash
        rolling_hash = checkpoint.rolling_hash
        completed = checkpoint.points_completed
    else:
        next_evaluation = config.evaluation_start_utc
        offset = 0
        visible = []
        visible_count = 0
        evidence_hash = "0" * 64
        input_prefix_hash = "0" * 64
        rolling_hash = "0" * 64
        completed = 0
    iterator = iter(ordered)
    checked_prefix_hash = "0" * 64
    checked_evidence_hash = "0" * 64
    checked_visible: list[str] = []
    try:
        for _ in range(offset):
            prior = next(iterator)
            checked_prefix_hash = _chain(checked_prefix_hash, prior.model_dump(mode="json"))
            checked_evidence_hash = _chain(checked_evidence_hash, prior.model_dump(mode="json"))
            checked_visible.append(prior.observation_id)
            if len(checked_visible) > _RETAINED_OBSERVATION_LIMIT:
                del checked_visible[:-_RETAINED_OBSERVATION_LIMIT]
    except StopIteration as exc:
        raise ValueError("Checkpoint offset exceeds dataset") from exc
    if checkpoint is not None and (
        checked_prefix_hash != input_prefix_hash
        or checked_evidence_hash != evidence_hash
        or tuple(checked_visible) != tuple(visible)
        or visible_count != offset
    ):
        raise ValueError("Checkpoint input prefix or bounded state differs")
    next_observation = next(iterator, None)
    points: list[ReplayPoint] = []
    cadence = timedelta(seconds=config.evaluation_cadence_seconds)
    while next_evaluation <= config.evaluation_end_utc:
        while next_observation is not None and next_observation.available_at_utc <= next_evaluation:
            visible.append(next_observation.observation_id)
            if len(visible) > _RETAINED_OBSERVATION_LIMIT:
                del visible[:-_RETAINED_OBSERVATION_LIMIT]
            normalized = next_observation.model_dump(mode="json")
            input_prefix_hash = _chain(input_prefix_hash, normalized)
            evidence_hash = _chain(evidence_hash, normalized)
            offset += 1
            visible_count += 1
            next_observation = next(iterator, None)
        status, reason = _coverage_status(manifest, next_evaluation)
        payload = {
            "at": next_evaluation.isoformat(),
            "retained_visible": visible,
            "visible_count": visible_count,
            "evidence_hash": evidence_hash,
            "config_hash": config_hash,
            "status": status,
            "reason": reason,
            "previous": rolling_hash,
        }
        rolling_hash = hashlib.sha256(_canonical(payload)).hexdigest()
        points.append(
            ReplayPoint(
                evaluated_at_utc=next_evaluation,
                visible_observation_ids=tuple(visible),
                visible_count=visible_count,
                status=status,
                reason=reason,
                rolling_hash=rolling_hash,
                evidence_hash=evidence_hash,
            )
        )
        completed += 1
        if progress is not None:
            progress(completed)
        next_evaluation += cadence
        if maximum_points is not None and len(points) >= maximum_points:
            break
    return points, ReplayCheckpoint(
        experiment_id=config.experiment_id,
        dataset_hash=manifest.content_hash,
        config_hash=config_hash,
        state_schema_version="phase5-bounded-v1",
        next_evaluation_utc=next_evaluation,
        input_offset=offset,
        visible_observation_ids=tuple(visible),
        visible_count=visible_count,
        evidence_hash=evidence_hash,
        input_prefix_hash=input_prefix_hash,
        rolling_hash=rolling_hash,
        points_completed=completed,
    )


def write_checkpoint(path: Path, checkpoint: ReplayCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
