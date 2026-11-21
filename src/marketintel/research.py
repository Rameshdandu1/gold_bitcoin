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
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from marketintel.research_engine import run_shared_workflow
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


def command_run_workflow(args: argparse.Namespace) -> int:
    """Run the production detectors and evidence-derived evaluator with no external calls."""
    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path, verify_files=True)
    config = _load_config(Path(args.config).resolve())
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    with TemporaryDirectory(prefix="marketintel-workflow-") as temporary:
        observations = spool_observations(
            manifest_path,
            manifest,
            Path(temporary) / "sort.sqlite3",
            batch_size=args.chunk_size,
        )
        result = run_shared_workflow(
            manifest,
            config,
            observations,
            store,
            presorted=True,
        )
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    experiment = store.experiment(args.experiment_id)
    if experiment is None:
        raise ValueError("Experiment does not exist; run the shared workflow first")
    _, config = experiment
    all_rows = store.opportunities(args.experiment_id)
    selected: dict[str, OpportunityRecord] = {}
    for row in sorted(all_rows, key=lambda item: (item.observed_at_utc, item.revision_id)):
        selected[row.opportunity_id] = row
    rows = list(selected.values())
    holdout_start = config.holdout_start_utc
    development_rows = [
        row
        for row in rows
        if holdout_start is None or row.label_information_end_utc < holdout_start
    ]
    held_out = [
        row
        for row in rows
        if holdout_start is not None and row.label_information_end_utc >= holdout_start
    ]
    metrics = arm_metrics(development_rows)
    folds = (
        purged_folds(
            development_rows,
            fold_count=config.fold_count,
            embargo_seconds=config.embargo_seconds,
            holdout_start=holdout_start,
        )
        if len({x.opportunity_id for x in development_rows}) >= config.fold_count
        else []
    )
    paired = {
        arm: paired_day_block_difference(development_rows, "RULES_ONLY", arm)
        for arm in ("RULES_PLUS_GPT", "RULES_PLUS_CLAUDE", "RULES_PLUS_DUAL")
    }
    report = {
        "classification": "EXPLORATORY" if development_rows else "INSUFFICIENT_DATA",
        "partition": "DEVELOPMENT",
        "experiment_id": args.experiment_id,
        "config_hash": config.canonical_config_hash(),
        "unique_opportunities": len(rows),
        "development_opportunities": len(development_rows),
        "protected_or_crossing_holdout": len(held_out),
        "metrics": metrics,
        "folds": folds,
        "paired_day_blocks": paired,
        "actual_experiment_cost_microusd": 0,
        "cost_note": "Actual experiment spend is separate from per-arm attributable cost.",
    }
    store.save_report(args.experiment_id, "development-evaluation-v1", report)
    print(json.dumps(report, sort_keys=True, default=str))
    return 0


def command_final_holdout(args: argparse.Namespace) -> int:
    if args.acknowledge_protected_holdout != "FINAL_EVALUATION":
        raise ValueError("Explicit --acknowledge-protected-holdout FINAL_EVALUATION is required")
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    experiment = store.experiment(args.experiment_id)
    if experiment is None:
        raise ValueError("Experiment does not exist")
    _, config = experiment
    if config.holdout_start_utc is None:
        raise ValueError("Experiment has no frozen protected holdout")
    store.record_holdout_access(
        args.experiment_id,
        config.canonical_config_hash(),
        purpose="FINAL_EVALUATION",
    )
    selected: dict[str, OpportunityRecord] = {}
    for row in sorted(
        store.opportunities(args.experiment_id),
        key=lambda item: (item.observed_at_utc, item.revision_id),
    ):
        selected[row.opportunity_id] = row
    holdout = [
        row
        for row in selected.values()
        if row.label_information_end_utc >= config.holdout_start_utc
    ]
    report = {
        "classification": "EXPLORATORY" if holdout else "INSUFFICIENT_DATA",
        "partition": "FINAL_HOLDOUT",
        "experiment_id": args.experiment_id,
        "config_hash": config.canonical_config_hash(),
        "holdout_start_utc": config.holdout_start_utc.isoformat(),
        "unique_opportunities": len(holdout),
        "metrics": arm_metrics(holdout),
        "warning": "One-time protected hypothetical holdout access; not an empirical claim.",
    }
    store.save_report(args.experiment_id, "final-holdout-v1", report)
    print(json.dumps(report, sort_keys=True, default=str))
    return 0


def command_report(args: argparse.Namespace) -> int:
    store = ResearchStore(
        Path(args.database).resolve(), production_path=Path(args.production_database).resolve()
    )
    experiment = store.experiment(args.experiment_id)
    if experiment is None:
        raise ValueError("Experiment does not exist")
    manifest, config = experiment
    selected: dict[str, OpportunityRecord] = {}
    for row in sorted(
        store.opportunities(args.experiment_id),
        key=lambda item: (item.observed_at_utc, item.revision_id),
    ):
        selected[row.opportunity_id] = row
    rows = [
        row
        for row in selected.values()
        if config.holdout_start_utc is None
        or row.label_information_end_utc < config.holdout_start_utc
    ]
    metrics = arm_metrics(rows)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "experiment_id": args.experiment_id,
        "classification": "EXPLORATORY" if rows else "INSUFFICIENT_DATA",
        "hypothetical": True,
        "partition": "DEVELOPMENT",
        "dataset_id": manifest.dataset_id,
        "dataset_hash": manifest.content_hash,
        "config_hash": config.canonical_config_hash(),
        "data_mode": manifest.data_mode,
        "opportunities": len({x.opportunity_id for x in rows}),
        "revision_records": len(rows),
        "engine_matrix": store.engine_matrix(args.experiment_id),
        "source_coverage": [item.model_dump(mode="json") for item in manifest.coverage],
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
        "# Phase 5 research report\n\n"
        + summary["warning"]
        + "\n\n```json\n"
        + json.dumps(summary, indent=2, sort_keys=True)
        + "\n```\n"
    )
    (output / "report.md").write_text(markdown, encoding="utf-8")
    (output / "report.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Research report</title>"
        "<h1>Phase 5 research report</h1><p>"
        + html.escape(summary["warning"])
        + "</p><pre>"
        + html.escape(json.dumps(summary, indent=2, sort_keys=True))
        + "</pre>",
        encoding="utf-8",
    )
    _write_json(output / "dataset-manifest.json", manifest.model_dump(mode="json"))
    _write_json(output / "experiment-config.json", config.model_dump(mode="json"))
    with (output / "selected-opportunities.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row.model_dump_json() + "\n")
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
    workflow = commands.add_parser("run-workflow")
    workflow.add_argument("--manifest", required=True)
    workflow.add_argument("--config", required=True)
    workflow.add_argument("--database", required=True)
    workflow.add_argument("--production-database", default="data/marketintel.sqlite3")
    workflow.add_argument("--chunk-size", type=int, default=2_000)
    workflow.set_defaults(handler=command_run_workflow)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--database", required=True)
    evaluate.add_argument("--production-database", default="data/marketintel.sqlite3")
    evaluate.add_argument("--experiment-id", required=True)
    evaluate.set_defaults(handler=command_evaluate)
    holdout = commands.add_parser("final-holdout")
    holdout.add_argument("--database", required=True)
    holdout.add_argument("--production-database", default="data/marketintel.sqlite3")
    holdout.add_argument("--experiment-id", required=True)
    holdout.add_argument("--acknowledge-protected-holdout", required=True)
    holdout.set_defaults(handler=command_final_holdout)
    report = commands.add_parser("report")
    report.add_argument("--database", required=True)
    report.add_argument("--production-database", default="data/marketintel.sqlite3")
    report.add_argument("--experiment-id", required=True)
    report.add_argument("--output", required=True)
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
