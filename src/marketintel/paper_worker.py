"""Bounded prospective-paper recorder; disabled unless explicitly configured."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from marketintel.config import Settings
from marketintel.research_models import ArmDecision
from marketintel.research_storage import PaperLedger


class PaperWorkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    enabled: bool = False
    ledger_path: Path = Path("data/paper.sqlite3")
    production_database_path: Path = Path("data/marketintel.sqlite3")
    recorded_decisions_path: Path | None = None
    maximum_records_per_cycle: int = Field(default=100, ge=1, le=10_000)


def run_cycle(config: PaperWorkerConfig, *, now: datetime | None = None) -> dict:
    """Ingest pre-recorded local decisions; never invokes an AI or market-data provider."""
    if not config.enabled:
        return {"status": "DISABLED", "recorded": 0}
    if config.recorded_decisions_path is None:
        return {"status": "NO_LOCAL_INPUT", "recorded": 0}
    ledger = PaperLedger(config.ledger_path, production_path=config.production_database_path)
    cursor = int(ledger.cursor("recorded_decisions") or "0")
    recorded = 0
    next_cursor = cursor
    with config.recorded_decisions_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            if line_number < cursor or not line.strip():
                continue
            payload = json.loads(line)
            decision = ArmDecision.model_validate(payload["decision"])
            ledger.record_decision(
                payload["opportunity_id"],
                payload["revision_id"],
                decision,
                recorded_at=now or datetime.now(UTC),
            )
            recorded += 1
            next_cursor = line_number + 1
            if recorded >= config.maximum_records_per_cycle:
                break
    ledger.set_cursor("recorded_decisions", str(next_cursor), now=now)
    return {"status": "RECORDED", "recorded": recorded, "cursor": next_cursor}


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
