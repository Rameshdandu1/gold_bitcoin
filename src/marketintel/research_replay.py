"""Availability-clock historical replay with deterministic checkpoint/resume."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timedelta
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
    "EXPIRY": 8,
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path, *, verify_files: bool = True) -> DatasetManifest:
    manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
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


def load_observations(manifest_path: Path, manifest: DatasetManifest) -> list[ReplayObservation]:
    observations: list[ReplayObservation] = []
    for evidence in manifest.files:
        path = manifest_path.parent / evidence.path
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    try:
                        observations.append(ReplayObservation.model_validate_json(line))
                    except ValueError as exc:
                        raise ValueError(
                            f"Invalid record {evidence.path}:{line_number}: {exc}"
                        ) from exc
    return observations


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
) -> tuple[list[ReplayPoint], ReplayCheckpoint]:
    """Replay by availability time; exchange timestamps never reveal records early."""
    ordered = sorted(observations, key=_sort_key)
    if checkpoint is not None:
        if checkpoint.experiment_id != config.experiment_id:
            raise ValueError("Checkpoint belongs to another experiment")
        if checkpoint.dataset_hash != manifest.content_hash:
            raise ValueError("Checkpoint dataset hash differs")
        next_evaluation = checkpoint.next_evaluation_utc
        offset = checkpoint.input_offset
        visible = list(checkpoint.visible_observation_ids)
        rolling_hash = checkpoint.rolling_hash
        completed = checkpoint.points_completed
    else:
        next_evaluation = config.evaluation_start_utc
        offset = 0
        visible = []
        rolling_hash = "0" * 64
        completed = 0
    if offset > len(ordered):
        raise ValueError("Checkpoint offset exceeds dataset")
    points: list[ReplayPoint] = []
    cadence = timedelta(seconds=config.evaluation_cadence_seconds)
    while next_evaluation <= config.evaluation_end_utc:
        while offset < len(ordered) and ordered[offset].available_at_utc <= next_evaluation:
            visible.append(ordered[offset].observation_id)
            offset += 1
        status, reason = _coverage_status(manifest, next_evaluation)
        payload = {
            "at": next_evaluation.isoformat(),
            "visible": visible,
            "status": status,
            "reason": reason,
            "previous": rolling_hash,
        }
        rolling_hash = hashlib.sha256(_canonical(payload)).hexdigest()
        points.append(
            ReplayPoint(
                evaluated_at_utc=next_evaluation,
                visible_observation_ids=tuple(visible),
                visible_count=len(visible),
                status=status,
                reason=reason,
                rolling_hash=rolling_hash,
            )
        )
        completed += 1
        next_evaluation += cadence
        if maximum_points is not None and len(points) >= maximum_points:
            break
    return points, ReplayCheckpoint(
        experiment_id=config.experiment_id,
        dataset_hash=manifest.content_hash,
        next_evaluation_utc=next_evaluation,
        input_offset=offset,
        visible_observation_ids=tuple(visible),
        rolling_hash=rolling_hash,
        points_completed=completed,
    )


def write_checkpoint(path: Path, checkpoint: ReplayCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
