"""Bounded prospective-paper recorder; disabled unless explicitly configured."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from marketintel.config import Settings
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
    source_lines = config.recorded_decisions_path.read_bytes().splitlines(keepends=True)
    source_size = len(source_lines)

    def prefix_digest(cursor_value: int) -> str:
        return hashlib.sha256(b"".join(source_lines[:cursor_value])).hexdigest()

    binding = ledger.cursor_binding("recorded_decisions")
    if binding is not None and (
        binding["source_identity"] != config.source_identity
        or int(binding["generation"]) != config.source_generation
    ):
        raise ValueError("Paper source identity/generation changed")
    cursor = int(binding["cursor"]) if binding else 0
    if source_size < cursor:
        raise ValueError("Paper source was truncated below its committed cursor")
    committed_prefix_digest = prefix_digest(cursor)
    ledger.bind_cursor(
        "recorded_decisions",
        source_identity=config.source_identity,
        generation=config.source_generation,
        cursor=cursor,
        source_size=source_size,
        prefix_digest=committed_prefix_digest,
        now=now,
    )
    decisions = 0
    outcomes = 0
    next_cursor = cursor
    for line_number, raw_line in enumerate(source_lines):
        if line_number < cursor:
            continue
        if not raw_line.strip():
            raise ValueError("Blank records are not permitted in the paper stream")
        payload = json.loads(raw_line.decode("utf-8"))
        next_cursor = line_number + 1
        next_prefix_digest = prefix_digest(next_cursor)
        kind = ledger.process_stream_event(
            payload,
            source="recorded_decisions",
            source_identity=config.source_identity,
            generation=config.source_generation,
            previous_cursor=line_number,
            cursor=next_cursor,
            source_size=source_size,
            previous_prefix_digest=committed_prefix_digest,
            prefix_digest=next_prefix_digest,
            recorded_at=now or datetime.now(UTC),
        )
        if kind == "DECISION":
            decisions += 1
        elif kind == "OUTCOME":
            outcomes += 1
        committed_prefix_digest = next_prefix_digest
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
