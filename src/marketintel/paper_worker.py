"""Bounded prospective-paper recorder; disabled unless explicitly configured."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from marketintel.config import Settings
from marketintel.research_models import ArmDecision, ResearchCandidate, ResearchOutcome
from marketintel.research_storage import PaperLedger


class PaperWorkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    enabled: bool = False
    ledger_path: Path = Path("data/paper.sqlite3")
    production_database_path: Path = Path("data/marketintel.sqlite3")
    recorded_decisions_path: Path | None = None
    source_identity: str | None = None
    source_generation: int = Field(default=1, ge=1)
    maximum_records_per_cycle: int = Field(default=100, ge=1, le=10_000)


def run_cycle(config: PaperWorkerConfig, *, now: datetime | None = None) -> dict:
    """Ingest pre-recorded local decisions; never invokes an AI or market-data provider."""
    if not config.enabled:
        return {"status": "DISABLED", "recorded": 0}
    if config.recorded_decisions_path is None:
        return {"status": "NO_LOCAL_INPUT", "recorded": 0}
    if not config.source_identity:
        raise ValueError("Paper source_identity is required when local input is enabled")
    ledger = PaperLedger(config.ledger_path, production_path=config.production_database_path)
    with config.recorded_decisions_path.open("r", encoding="utf-8") as handle:
        source_size = sum(1 for _ in handle)
    binding = ledger.cursor_binding("recorded_decisions")
    if binding is not None and (
        binding["source_identity"] != config.source_identity
        or int(binding["generation"]) != config.source_generation
    ):
        raise ValueError("Paper source identity/generation changed")
    cursor = int(binding["cursor"]) if binding else 0
    if source_size < cursor:
        raise ValueError("Paper source was truncated below its committed cursor")
    ledger.bind_cursor(
        "recorded_decisions",
        source_identity=config.source_identity,
        generation=config.source_generation,
        cursor=cursor,
        source_size=source_size,
        now=now,
    )
    decisions = 0
    outcomes = 0
    next_cursor = cursor
    with config.recorded_decisions_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if line_number < cursor or not line.strip():
                continue
            payload = json.loads(line)
            kind = payload.get("type", "DECISION")
            if kind == "DECISION":
                decision = ArmDecision.model_validate(payload["decision"])
                candidate = ResearchCandidate.model_validate(payload["candidate"])
                ledger.record_decision(
                    payload["opportunity_id"],
                    payload["revision_id"],
                    decision,
                    candidate=candidate,
                    config_hash=payload["config_hash"],
                    target_index=int(payload["target_index"]),
                    source_identity=config.source_identity,
                    evidence_mode=payload.get("evidence_mode", "PROSPECTIVE"),
                    entry_latency_ms=int(payload.get("entry_latency_ms", 0)),
                    recorded_at=now or datetime.now(UTC),
                )
                decisions += 1
            elif kind == "OUTCOME":
                outcome = ResearchOutcome.model_validate(payload["outcome"])
                ledger.record_outcome(
                    payload["revision_id"],
                    outcome,
                    recorded_at=now or datetime.now(UTC),
                )
                outcomes += 1
            else:
                raise ValueError(f"Unsupported paper stream event type: {kind}")
            next_cursor = line_number + 1
            ledger.bind_cursor(
                "recorded_decisions",
                source_identity=config.source_identity,
                generation=config.source_generation,
                cursor=next_cursor,
                source_size=source_size,
                now=now,
            )
            if decisions + outcomes >= config.maximum_records_per_cycle:
                break
    return {
        "status": "RECORDED",
        "recorded": decisions + outcomes,
        "decisions": decisions,
        "outcomes": outcomes,
        "cursor": next_cursor,
        "source_identity": config.source_identity,
        "source_generation": config.source_generation,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m marketintel.paper_worker")
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true", help="Required bounded execution mode")
    args = parser.parse_args(argv)
    if not args.once:
        print(json.dumps({"error": "Only bounded --once execution is supported"}), file=sys.stderr)
        return 2
    config = PaperWorkerConfig.model_validate_json(Path(args.config).read_text(encoding="utf-8"))
    settings = Settings()
    if config.enabled and not settings.paper_collection_enabled:
        print(json.dumps({"status": "DISABLED_BY_ENV", "recorded": 0}))
        return 3
    print(json.dumps(run_cycle(config), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
