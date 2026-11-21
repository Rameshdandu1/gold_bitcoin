"""Reproducible offline research CLI.

Examples use only local files and isolated SQLite state. This module has no provider,
notification, ingestion, or order client.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from marketintel.research_evaluation import (
    arm_metrics,
    paired_day_block_difference,
    purged_folds,
)
from marketintel.research_models import ExperimentConfig, OpportunityRecord, ReplayCheckpoint
from marketintel.research_replay import (
    iter_observations,
    load_manifest,
    replay,
    spool_observations,
    write_checkpoint,
)
from marketintel.research_storage import ResearchStore


def _load_config(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate_json(path.read_text(encoding="utf-8"))


def _safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def _checksums(directory: Path, excluded: set[str] | None = None) -> None:
    excluded = excluded or {"SHA256SUMS"}
    rows = []
    for path in sorted(
        item for item in directory.iterdir() if item.is_file() and item.name not in excluded
    ):
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (directory / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def command_validate(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path, verify_files=True)
    record_count = sum(1 for _ in iter_observations(manifest_path, manifest))
    print(
        json.dumps(
            {
                "valid": True,
                "dataset_id": manifest.dataset_id,
                "data_mode": manifest.data_mode,
                "record_count": record_count,
                "coverage": [row.model_dump(mode="json") for row in manifest.coverage],
            },
            sort_keys=True,
        )
    )
    return 0


def command_replay(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    config_path = Path(args.config).resolve()
    manifest = load_manifest(manifest_path, verify_files=True)
    config = _load_config(config_path)
    checkpoint_path = Path(args.checkpoint).resolve() if args.checkpoint else None
    checkpoint = None
    if checkpoint_path and checkpoint_path.exists():
        checkpoint = ReplayCheckpoint.model_validate_json(
            checkpoint_path.read_text(encoding="utf-8")
        )

    def progress(completed: int) -> None:
        if args.progress_every and completed % args.progress_every == 0:
            print(json.dumps({"progress_points_completed": completed}), file=sys.stderr)

    with TemporaryDirectory(prefix="marketintel-replay-") as temporary:
        observations = spool_observations(
            manifest_path,
            manifest,
            Path(temporary) / "sort.sqlite3",
            batch_size=args.chunk_size,
        )
        points, next_checkpoint = replay(
            manifest,
            config,
            observations,
            checkpoint=checkpoint,
            maximum_points=args.maximum_points,
            presorted=True,
            progress=progress,
        )
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    store.create_experiment(manifest, config)
    store.save_points(config.experiment_id, points)
    if checkpoint_path:
        write_checkpoint(checkpoint_path, next_checkpoint)
    print(
        json.dumps(
            {
                "experiment_id": config.experiment_id,
                "points_written": len(points),
                "points_completed": next_checkpoint.points_completed,
                "rolling_hash": next_checkpoint.rolling_hash,
                "complete": next_checkpoint.next_evaluation_utc > config.evaluation_end_utc,
            },
            sort_keys=True,
        )
    )
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    count = 0
    with Path(args.opportunities).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = OpportunityRecord.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"Invalid opportunity line {line_number}: {exc}") from exc
            store.save_opportunity(args.experiment_id, record)
            count += 1
    rows = store.opportunities(args.experiment_id)
    metrics = arm_metrics(rows)
    holdout_start = datetime.fromisoformat(args.holdout_start) if args.holdout_start else None
    if holdout_start is not None and (
        holdout_start.tzinfo is None or holdout_start.utcoffset() is None
    ):
        raise ValueError("Holdout start must be timezone aware")
    folds = (
        purged_folds(
            rows,
            fold_count=args.folds,
            embargo_seconds=args.embargo_seconds,
            holdout_start=holdout_start,
        )
        if len({x.opportunity_id for x in rows}) >= args.folds
        else []
    )
    paired = {
        arm: paired_day_block_difference(rows, "RULES_ONLY", arm)
        for arm in ("RULES_PLUS_GPT", "RULES_PLUS_CLAUDE", "RULES_PLUS_DUAL")
    }
    report = {
        "classification": "EXPLORATORY" if rows else "INSUFFICIENT_DATA",
        "metrics": metrics,
        "folds": folds,
        "paired_day_blocks": paired,
        "actual_experiment_cost_microusd": args.actual_experiment_cost_microusd,
        "cost_note": "Actual experiment spend is separate from per-arm attributable cost.",
    }
    store.save_report(args.experiment_id, "evaluation", report)
    print(json.dumps({"records_written": count, **report}, sort_keys=True, default=str))
    return 0


def command_report(args: argparse.Namespace) -> int:
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    rows = store.opportunities(args.experiment_id)
    metrics = arm_metrics(rows)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "experiment_id": args.experiment_id,
        "classification": "EXPLORATORY" if rows else "INSUFFICIENT_DATA",
        "hypothetical": True,
        "opportunities": len({x.opportunity_id for x in rows}),
        "metrics": metrics,
        "warning": (
            "Exploratory hypothetical research; fixtures do not establish accuracy or "
            "profitability."
        ),
    }
    _write_json(output / "summary.json", summary)
    with (output / "arm_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = [
            "arm",
            "opportunity_denominator",
            "unavailable",
            "complete_executions",
            "net_pnl",
            "profit_factor",
            "classification",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for arm, values in metrics.items():
            writer.writerow(
                {
                    column: _safe_cell(arm if column == "arm" else values.get(column))
                    for column in columns
                }
            )
    markdown = (
        "# Phase 4 research report\n\n"
        + summary["warning"]
        + "\n\n```json\n"
        + json.dumps(summary, indent=2, sort_keys=True)
        + "\n```\n"
    )
    (output / "report.md").write_text(markdown, encoding="utf-8")
    (output / "report.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Research report</title>"
        "<h1>Phase 4 research report</h1><p>"
        + html.escape(summary["warning"])
        + "</p><pre>"
        + html.escape(json.dumps(summary, indent=2, sort_keys=True))
        + "</pre>",
        encoding="utf-8",
    )
    if args.manifest:
        shutil.copy2(Path(args.manifest), output / "dataset-manifest.json")
    if args.config:
        shutil.copy2(Path(args.config), output / "experiment-config.json")
    _checksums(output)
    print(
        json.dumps(
            {"output": str(output), "files": sorted(x.name for x in output.iterdir())},
            sort_keys=True,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m marketintel.research")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-data")
    validate.add_argument("--manifest", required=True)
    validate.set_defaults(handler=command_validate)
    replay_command = commands.add_parser("replay")
    replay_command.add_argument("--manifest", required=True)
    replay_command.add_argument("--config", required=True)
    replay_command.add_argument("--database", required=True)
    replay_command.add_argument("--production-database", default="data/marketintel.sqlite3")
    replay_command.add_argument("--checkpoint")
    replay_command.add_argument("--maximum-points", type=int)
    replay_command.add_argument("--chunk-size", type=int, default=2_000)
    replay_command.add_argument("--progress-every", type=int, default=1_000)
    replay_command.set_defaults(handler=command_replay)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--database", required=True)
    evaluate.add_argument("--production-database", default="data/marketintel.sqlite3")
    evaluate.add_argument("--experiment-id", required=True)
    evaluate.add_argument("--opportunities", required=True)
    evaluate.add_argument("--folds", type=int, default=3)
    evaluate.add_argument("--embargo-seconds", type=int, default=0)
    evaluate.add_argument("--holdout-start", help="ISO-8601 UTC start of untouched holdout")
    evaluate.add_argument("--actual-experiment-cost-microusd", type=int, default=0)
    evaluate.set_defaults(handler=command_evaluate)
    report = commands.add_parser("report")
    report.add_argument("--database", required=True)
    report.add_argument("--production-database", default="data/marketintel.sqlite3")
    report.add_argument("--experiment-id", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--manifest")
    report.add_argument("--config")
    report.set_defaults(handler=command_report)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "success": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
