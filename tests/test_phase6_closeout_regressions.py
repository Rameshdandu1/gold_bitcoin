from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_phase3_consensus import analysis_fixture, approvals, eligibility, persist_candidate
from test_phase3_service_alerts import FakeSlack, alert_settings, committed_alert
from test_phase4_research import candidate, decision, instrument, policy, quote

from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.consensus import decide_v2
from marketintel.delta import OrderBookAssembler, parse_book_message
from marketintel.notifications import AlertWorker
from marketintel.research import main as research_main
from marketintel.research_engine import provider_request_digest
from marketintel.research_evaluation import evaluate_bar_path, evaluate_quotes
from marketintel.research_fixtures import FIXTURE_NOW, generate_fixture
from marketintel.research_models import (
    DatasetManifest,
    ExperimentConfig,
    PriceBar,
    ReplayObservation,
)
from marketintel.research_replay import load_manifest
from marketintel.research_storage import PaperLedger, ResearchStore
from marketintel.storage import Store

NOW = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)


class AdvancingClock:
    def __init__(self, *values: datetime) -> None:
        self.values = list(values)

    def __call__(self) -> datetime:
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


def _rewrite_fixture(manifest_path, transform, *, extra_rows=()) -> DatasetManifest:
    manifest = load_manifest(manifest_path)
    source = manifest_path.parent / manifest.files[0].path
    rows = [
        ReplayObservation.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
    ]
    changed = [value for row in rows if (value := transform(row)) is not None]
    changed.extend(extra_rows)
    changed.sort(
        key=lambda row: (row.available_at_utc, row.persistence_sequence, row.observation_id)
    )
    source.write_text("".join(row.model_dump_json() + "\n" for row in changed), encoding="utf-8")
    evidence = manifest.files[0].model_copy(
        update={
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "record_count": len(changed),
        }
    )
    updated = manifest.model_copy(update={"files": (evidence,), "content_hash": "0" * 64})
    updated = updated.model_copy(update={"content_hash": updated.canonical_content_hash()})
    manifest_path.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return updated


def _clock_observation(sequence: int, *, minutes: int = 241) -> ReplayObservation:
    at = FIXTURE_NOW + timedelta(minutes=minutes)
    return ReplayObservation(
        observation_id=f"closeout-clock-{minutes}",
        kind="EXPIRY",
        symbol="XAUTUSD",
        venue="delta_india",
        exchange_time_utc=at,
        available_at_utc=at,
        persistence_sequence=sequence,
        payload={},
    )


def _run_gold_workflow(tmp_path, manifest_path, config_path) -> tuple[object, object, str]:
    research = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest_path),
                "--config",
                str(config_path),
                "--database",
                str(research),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    return research, production, "phase5-gold-workflow-v1"


@pytest.mark.asyncio
async def test_p6_01_event_time_book_expiry_fences_dispatch(tmp_path) -> None:
    settings = alert_settings(tmp_path, alert_lease_seconds=300)
    store = Store(settings.database_path)
    value = committed_alert(store)
    event_at = value.observed_at_utc + timedelta(seconds=51)
    received_at = value.observed_at_utc + timedelta(seconds=59, milliseconds=900)
    evaluation_at = value.observed_at_utc + timedelta(minutes=1)
    authorization_at = value.observed_at_utc + timedelta(minutes=1, seconds=2)
    asks = [["2600.1", "10"]]
    bids = [["2599.9", "10"]]
    checksum = zlib.crc32(b"2600.1:10|2599.9:10") & 0xFFFFFFFF
    parsed = parse_book_message(
        {
            "type": "ob_updates",
            "action": "snapshot",
            "sy": value.symbol,
            "a": asks,
            "b": bids,
            "seq": 9,
            "cs": checksum,
            "ts": int(event_at.timestamp() * 1_000_000),
        },
        received_at=received_at,
    )
    book = OrderBookAssembler(value.symbol, max_age_seconds=10)
    assert book.apply(parsed)
    assert book.top_of_book(now=evaluation_at) == (Decimal("2599.9"), Decimal("2600.1"))
    store.save_book_checkpoint(book)
    transport = FakeSlack()
    clock = AdvancingClock(evaluation_at, evaluation_at, authorization_at, authorization_at)

    assert await AlertWorker(store, settings, transport, clock=clock).run_once(
        owner="phase6-event-time-fence", now=evaluation_at
    )

    assert transport.calls == []
    item = store.outbox_items()[0]
    assert item["status"] == "SUPPRESSED"
    assert store.dispatch_authorization(item["outbox_id"]) is None


@pytest.mark.parametrize("conflicting_kind", ["PROVIDER_COMPLETION", "EXECUTABLE_QUOTE"])
def test_p6_02_public_workflow_rejects_payload_availability_before_envelope(
    tmp_path, conflicting_kind: str
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / conflicting_kind.lower())

    def delay_envelope(row: ReplayObservation) -> ReplayObservation:
        if row.kind != conflicting_kind:
            return row
        payload = dict(row.payload)
        payload["available_at_utc"] = row.available_at_utc.isoformat()
        return row.model_copy(
            update={
                "available_at_utc": row.available_at_utc + timedelta(seconds=120),
                "payload": payload,
            }
        )

    _rewrite_fixture(manifest_path, delay_envelope)

    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest_path),
                "--config",
                str(config_path),
                "--database",
                str(tmp_path / "research.sqlite3"),
                "--production-database",
                str(tmp_path / "production.sqlite3"),
            ]
        )
        == 2
    )


@pytest.mark.parametrize("direction", ["BULLISH", "BEARISH"])
def test_p6_03_readiness_cannot_erase_anchored_quote_gap(direction: str) -> None:
    value = candidate().model_copy(
        update=(
            {}
            if direction == "BULLISH"
            else {
                "direction": "BEARISH",
                "invalidation": Decimal("105"),
                "targets": (Decimal("95"), Decimal("90")),
            }
        )
    )
    approved = decision().model_copy(update={"ready_at_utc": NOW + timedelta(seconds=150)})
    target_bid, target_ask = ("105", "105.5") if direction == "BULLISH" else ("94", "94.5")
    rows = [
        quote("anchor", 0, "99.5", "100").model_copy(update={"available_at_utc": NOW}),
        quote("entry", 150, "99.5", "100").model_copy(
            update={"available_at_utc": NOW + timedelta(seconds=150)}
        ),
        quote("target", 155, target_bid, target_ask).model_copy(
            update={"available_at_utc": NOW + timedelta(seconds=155)}
        ),
    ]

    outcome = evaluate_quotes(
        value,
        approved,
        instrument(),
        rows,
        policy().model_copy(update={"maximum_quote_gap_seconds": 10}),
    )

    assert outcome.code == "INCOMPLETE"
    assert outcome.data_complete is False


@pytest.mark.parametrize("direction", ["BULLISH", "BEARISH"])
def test_p6_03_incomplete_pre_entry_bar_cannot_establish_coverage(direction: str) -> None:
    value = candidate().model_copy(
        update=(
            {}
            if direction == "BULLISH"
            else {
                "direction": "BEARISH",
                "invalidation": Decimal("105"),
                "targets": (Decimal("95"), Decimal("90")),
            }
        )
    )
    approved = decision().model_copy(update={"ready_at_utc": NOW + timedelta(seconds=30)})
    target_high, target_low = (
        (Decimal("106"), Decimal("99"))
        if direction == "BULLISH"
        else (Decimal("101"), Decimal("94"))
    )
    bars = [
        PriceBar(
            event_id="incomplete-anchor",
            venue=value.venue,
            symbol=value.symbol,
            start_utc=NOW,
            end_utc=NOW + timedelta(seconds=30),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            complete=False,
        ),
        PriceBar(
            event_id="target",
            venue=value.venue,
            symbol=value.symbol,
            start_utc=NOW + timedelta(seconds=30),
            end_utc=NOW + timedelta(seconds=40),
            open=Decimal("100"),
            high=target_high,
            low=target_low,
            close=Decimal("100"),
            complete=True,
        ),
    ]

    outcome = evaluate_bar_path(value, approved, bars)

    assert outcome.code == "INCOMPLETE"
    assert outcome.data_complete is False
    assert outcome.supporting_event_ids == ("incomplete-anchor",)


def test_p6_04_paper_derivation_and_api_preserve_frozen_holdout(tmp_path, capsys) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    scratch_research, scratch_production, experiment_id = _run_gold_workflow(
        tmp_path / "scratch", manifest_path, config_path
    )
    capsys.readouterr()
    scratch = ResearchStore(scratch_research, production_path=scratch_production)
    candidates = {
        (row.opportunity_id, row.revision_id): row for row in scratch.candidates(experiment_id)
    }
    original_config = ExperimentConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    protected_config = original_config.model_copy(update={"holdout_start_utc": FIXTURE_NOW})
    config_path.write_text(protected_config.model_dump_json(indent=2), encoding="utf-8")

    def rebind_provider(row: ReplayObservation) -> ReplayObservation:
        if row.kind != "PROVIDER_COMPLETION":
            return row
        payload = dict(row.payload)
        provider = str(payload["provider"])
        research_candidate = candidates[(payload["candidate_id"], payload["revision_id"])]
        payload["configuration_digest"] = protected_config.canonical_config_hash()
        payload["request_digest"] = provider_request_digest(
            research_candidate, protected_config, provider
        )
        return row.model_copy(update={"payload": payload})

    _rewrite_fixture(manifest_path, rebind_provider)
    research, production, _ = _run_gold_workflow(tmp_path / "protected", manifest_path, config_path)
    capsys.readouterr()
    paper = tmp_path / "protected" / "paper.sqlite3"
    paper_args = [
        "paper-workflow",
        "--database",
        str(research),
        "--paper-database",
        str(paper),
        "--production-database",
        str(production),
        "--experiment-id",
        experiment_id,
    ]

    assert research_main(paper_args) == 0
    protected_result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert protected_result["status"] == "HOLDOUT_PROTECTED"
    assert protected_result["decisions"] == protected_result["outcomes"] == 0
    store = ResearchStore(research, production_path=production)
    assert store.opportunities(experiment_id) == []
    assert not store.holdout_is_open(experiment_id, protected_config.canonical_config_hash())

    settings = Settings(
        database_path=production,
        research_database_path=research,
        paper_database_path=paper,
        operator_username="operator",
        operator_password="secret",
    )
    client = TestClient(create_app(settings, Store(production)))
    endpoint = f"/api/research/paper/transitions?experiment_id={experiment_id}"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, auth=("operator", "secret")).json() == []
    before_export = tmp_path / "before-open-export"
    assert (
        research_main(
            [
                "report",
                "--database",
                str(research),
                "--paper-database",
                str(paper),
                "--production-database",
                str(production),
                "--experiment-id",
                experiment_id,
                "--output",
                str(before_export),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (before_export / "paper-transitions.jsonl").read_text(encoding="utf-8") == ""

    assert (
        research_main(
            [
                "final-holdout",
                "--database",
                str(research),
                "--production-database",
                str(production),
                "--experiment-id",
                experiment_id,
                "--acknowledge-protected-holdout",
                "FINAL_EVALUATION",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert research_main(paper_args) == 0
    opened_result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert opened_result["status"] == "SIMULATED_PROSPECTIVE_COMPLETE"
    assert opened_result["outcomes"] == 12
    visible = client.get(endpoint, auth=("operator", "secret")).json()
    assert len([row for row in visible if row["state"] == "TARGET_BEFORE_STOP"]) == 12
    after_export = tmp_path / "after-open-export"
    assert (
        research_main(
            [
                "report",
                "--database",
                str(research),
                "--paper-database",
                str(paper),
                "--production-database",
                str(production),
                "--experiment-id",
                experiment_id,
                "--output",
                str(after_export),
            ]
        )
        == 0
    )
    capsys.readouterr()
    exported_transitions = (after_export / "paper-transitions.jsonl").read_text(encoding="utf-8")
    assert exported_transitions.count('"state": "TARGET_BEFORE_STOP"') == 12


@pytest.mark.parametrize(
    ("provider_case", "unavailable_outcomes"),
    [("missing_claude", 6), ("both_late", 9)],
)
def test_p6_05_public_paper_workflow_records_terminal_unavailable_arms(
    tmp_path, capsys, provider_case: str, unavailable_outcomes: int
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / provider_case)

    def provider_transform(row: ReplayObservation) -> ReplayObservation | None:
        if row.kind != "PROVIDER_COMPLETION":
            return row
        if provider_case == "missing_claude" and row.payload["provider"] == "CLAUDE":
            return None
        if provider_case == "both_late":
            payload = dict(row.payload)
            late = FIXTURE_NOW + timedelta(minutes=241)
            payload["available_at_utc"] = late.isoformat()
            return row.model_copy(update={"available_at_utc": late, "payload": payload})
        return row

    clock_minutes = 242 if provider_case == "both_late" else 241
    _rewrite_fixture(
        manifest_path,
        provider_transform,
        extra_rows=(_clock_observation(999_999, minutes=clock_minutes),),
    )
    research, production, experiment_id = _run_gold_workflow(
        tmp_path / "workflow", manifest_path, config_path
    )
    capsys.readouterr()
    paper = tmp_path / "workflow" / "paper.sqlite3"
    args = [
        "paper-workflow",
        "--database",
        str(research),
        "--paper-database",
        str(paper),
        "--production-database",
        str(production),
        "--experiment-id",
        experiment_id,
    ]

    assert research_main(args) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert first["status"] == "SIMULATED_PROSPECTIVE_COMPLETE"
    assert first["decisions"] == first["outcomes"] == 12
    transitions = PaperLedger(paper, production_path=production).transitions(
        experiment_id=experiment_id
    )
    assert len([row for row in transitions if row["state"] == "INCOMPLETE"]) == (
        unavailable_outcomes
    )
    assert len([row for row in transitions if row["state"] == "TARGET_BEFORE_STOP"]) == (
        12 - unavailable_outcomes
    )

    assert research_main(args) == 0
    repeated = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert repeated["decisions"] == repeated["outcomes"] == 12
    assert (
        PaperLedger(paper, production_path=production).transitions(experiment_id=experiment_id)
        == transitions
    )


def test_p6_05_bounded_partial_resume_matches_uninterrupted_public_workflow(
    tmp_path, capsys
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "resume")
    research, production, experiment_id = _run_gold_workflow(
        tmp_path / "workflow", manifest_path, config_path
    )
    capsys.readouterr()

    def paper_args(path, *extra: str) -> list[str]:
        return [
            "paper-workflow",
            "--database",
            str(research),
            "--paper-database",
            str(path),
            "--production-database",
            str(production),
            "--experiment-id",
            experiment_id,
            *extra,
        ]

    resumed = tmp_path / "resumed-paper.sqlite3"
    assert research_main(paper_args(resumed, "--maximum-events", "100")) == 0
    partial = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert partial["status"] == "SIMULATED_PROSPECTIVE_WARMUP_PARTIAL"
    assert partial["events_consumed"] == 100
    assert partial["events_remaining"] == 5_233
    assert partial["input_complete"] is False
    assert partial["resource_evidence"]["maximum_input_batch"] <= 100

    assert research_main(paper_args(resumed)) == 0
    resumed_result = json.loads(capsys.readouterr().out.splitlines()[-1])
    uninterrupted = tmp_path / "uninterrupted-paper.sqlite3"
    assert research_main(paper_args(uninterrupted)) == 0
    uninterrupted_result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert resumed_result["status"] == uninterrupted_result["status"]
    assert resumed_result["decisions"] == resumed_result["outcomes"] == 12
    assert resumed_result["events_consumed"] == uninterrupted_result["events_consumed"] == 5_333
    assert resumed_result["resource_evidence"]["maximum_input_batch"] <= 500
    resumed_events = PaperLedger(resumed, production_path=production).transitions(
        experiment_id=experiment_id
    )
    uninterrupted_events = PaperLedger(uninterrupted, production_path=production).transitions(
        experiment_id=experiment_id
    )
    assert resumed_events == uninterrupted_events


def test_complete_derived_workflow_resumes_in_fresh_process_from_warmup_and_provider(
    tmp_path,
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "derived-resume")
    manifest = load_manifest(manifest_path)
    source = manifest_path.parent / manifest.files[0].path
    rows = [
        ReplayObservation.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
    ]
    first_provider_offset = next(
        index for index, row in enumerate(rows, start=1) if row.kind == "PROVIDER_COMPLETION"
    )
    root = str(Path(__file__).resolve().parents[1])
    production = tmp_path / "production.sqlite3"
    resumed = tmp_path / "resumed-research.sqlite3"
    uninterrupted = tmp_path / "uninterrupted-research.sqlite3"

    def run(database, *extra: str) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "marketintel.research",
                "run-workflow",
                "--manifest",
                str(manifest_path),
                "--config",
                str(config_path),
                "--database",
                str(database),
                "--production-database",
                str(production),
                *extra,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout.splitlines()[-1])

    warmup = run(resumed, "--maximum-events", "100")
    assert warmup["status"] == "DERIVED_WORKFLOW_PARTIAL"
    assert warmup["observations"] == 100
    provider = run(
        resumed,
        "--maximum-events",
        str(first_provider_offset - warmup["observations"] + 1),
    )
    assert provider["status"] == "DERIVED_WORKFLOW_PARTIAL"
    assert provider["observations"] > first_provider_offset
    completed = run(resumed)
    full = run(uninterrupted)
    assert completed["status"] == full["status"] == "DERIVED_WORKFLOW_COMPLETE"
    assert completed["observations"] == full["observations"] == 5_333
    resumed_store = ResearchStore(resumed, production_path=production)
    full_store = ResearchStore(uninterrupted, production_path=production)
    experiment_id = "phase5-gold-workflow-v1"
    assert resumed_store.opportunities(experiment_id) == full_store.opportunities(experiment_id)
    assert resumed_store.engine_matrix(experiment_id) == full_store.engine_matrix(experiment_id)
    resumed_checkpoint = resumed_store.workflow_checkpoint(experiment_id)
    full_checkpoint = full_store.workflow_checkpoint(experiment_id)
    assert resumed_checkpoint is not None and full_checkpoint is not None
    assert resumed_checkpoint["status"] == full_checkpoint["status"] == "COMPLETE"
    assert resumed_checkpoint["input_offset"] == full_checkpoint["input_offset"] == 5_333
    assert resumed_checkpoint["state"] == full_checkpoint["state"]


@pytest.mark.parametrize("market_case", ["SOURCE_LOSS", "SPREAD_AND_DRIFT"])
def test_shared_application_policy_blocks_production_and_connected_research(
    tmp_path, capsys, market_case: str
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / market_case.lower())
    at = FIXTURE_NOW + timedelta(seconds=1)
    if market_case == "SOURCE_LOSS":
        extra = ReplayObservation(
            observation_id="shared-policy-source-loss",
            kind="SOURCE_TRANSITION",
            symbol="XAUTUSD",
            venue="delta_india",
            exchange_time_utc=at,
            available_at_utc=at,
            persistence_sequence=900_001,
            payload={"state": "GAP", "generation": 2, "reason": "fixture source loss"},
        )
    else:
        extra = ReplayObservation(
            observation_id="shared-policy-wide-book",
            kind="BOOK_SNAPSHOT",
            symbol="XAUTUSD",
            venue="delta_india",
            exchange_time_utc=at,
            available_at_utc=at,
            persistence_sequence=900_002,
            payload={
                "sequence": 2,
                "generation": 2,
                "snapshot": True,
                "features": {
                    "available": True,
                    "observed_at_utc": at.isoformat(),
                    "best_bid": "2500",
                    "best_ask": "2700",
                    "spread": "200",
                    "bid_depth_quote": "1000",
                    "ask_depth_quote": "1000",
                    "imbalance": "0",
                    "absorption": "NONE",
                    "reason": "TEST_FIXTURE_NOT_LIVE",
                },
            },
        )
    _rewrite_fixture(manifest_path, lambda row: row, extra_rows=(extra,))
    research, production, experiment_id = _run_gold_workflow(
        tmp_path / "workflow", manifest_path, config_path
    )
    capsys.readouterr()
    opportunities = ResearchStore(research, production_path=production).opportunities(experiment_id)
    assert len(opportunities) == 3
    assert all(
        arm.state == "WAIT" for row in opportunities for arm in row.arms if arm.arm != "RULES_ONLY"
    )

    production_candidate, analysis = analysis_fixture()
    gpt, claude = approvals(analysis)
    policy_store = Store(tmp_path / "production-policy.sqlite3")
    persist_candidate(policy_store, production_candidate)
    current = (
        eligibility(policy_store, analysis, discovery_current=False)
        if market_case == "SOURCE_LOSS"
        else eligibility(
            policy_store,
            analysis,
            best_bid="2500",
            best_ask="2700",
        )
    )
    decision_value = decide_v2(
        analysis,
        gpt,
        claude,
        current,
        run_id=f"shared-policy-{market_case.lower()}",
        provider_attempt_ids=("gpt-fixture", "claude-fixture"),
    )
    assert decision_value.status == "WAIT"
    failed = {row.code for row in decision_value.gates if not row.passed}
    assert ("REQUIRED_SOURCES" if market_case == "SOURCE_LOSS" else "SPREAD") in failed
