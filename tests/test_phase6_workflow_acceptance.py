from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_phase6_closeout_regressions import _rewrite_fixture, _run_gold_workflow

from marketintel.delta import parse_trade_message
from marketintel.research import main as research_main
from marketintel.research_evaluation import evaluate_quotes
from marketintel.research_fixtures import FIXTURE_NOW, generate_fixture
from marketintel.research_models import (
    ArmDecision,
    CostPolicy,
    ExecutableQuote,
    InstrumentVersion,
    ReplayObservation,
    ResearchCandidate,
    ResearchLifecycleEvent,
)
from marketintel.research_replay import load_manifest
from marketintel.research_storage import ResearchStore


def _same_price_book(seconds: Decimal) -> ReplayObservation:
    at = FIXTURE_NOW + timedelta(seconds=float(seconds))
    return ReplayObservation(
        observation_id=f"phase6c-book-{seconds}",
        kind="BOOK_SNAPSHOT",
        symbol="XAUTUSD",
        venue="delta_india",
        exchange_time_utc=at,
        available_at_utc=at,
        persistence_sequence=910_000 + int(seconds * 10),
        payload={
            "sequence": 2,
            "generation": 2,
            "snapshot": True,
            "features": {
                "available": True,
                "observed_at_utc": at.isoformat(),
                "best_bid": "2599.9",
                "best_ask": "2600.1",
                "spread": "0.2",
                "bid_depth_quote": "1400",
                "ask_depth_quote": "600",
                "imbalance": "0.4",
                "absorption": "NONE",
                "reason": "SYNTHETIC_FIXTURE_NOT_LIVE",
            },
        },
    )


@pytest.mark.parametrize("seconds", [Decimal("2.5"), Decimal("21")])
def test_p6c_01_later_unchanged_book_cannot_rewrite_earlier_arm_decisions(
    tmp_path, capsys, seconds: Decimal
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest_path,
        lambda row: row,
        extra_rows=(_same_price_book(seconds),),
    )

    research = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    result = research_main(
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

    assert result == 0, capsys.readouterr().err
    store = ResearchStore(research, production_path=production)
    experiment_id = "phase5-gold-workflow-v1"
    opportunities = store.opportunities(experiment_id)
    assert len(opportunities) == 3
    assert sum(len(row.arms) for row in opportunities) == 12
    assert store.workflow_checkpoint(experiment_id)["status"] == "COMPLETE"
    candidate = store.candidates(experiment_id)[0]
    original = store.arm_decisions(experiment_id, candidate.opportunity_id, candidate.revision_id)[
        0
    ]
    with pytest.raises(ValueError, match="Arm decision identity is immutable"):
        store.save_arm_decision(
            experiment_id,
            candidate.opportunity_id,
            candidate.revision_id,
            original.model_copy(update={"reason": "conflicting rewrite must fail"}),
            persisted_at=original.ready_at_utc,
        )


def test_p6c_01_fresh_process_resume_after_gpt_before_book_and_claude(
    tmp_path,
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest_path,
        lambda row: row,
        extra_rows=(_same_price_book(Decimal("2.5")),),
    )
    manifest = load_manifest(manifest_path)
    source = manifest_path.parent / manifest.files[0].path
    rows = [
        ReplayObservation.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
    ]
    gpt_boundary = max(
        index
        for index, row in enumerate(rows, start=1)
        if row.kind == "PROVIDER_COMPLETION" and row.payload["provider"] == "GPT"
    )
    root = str(Path(__file__).resolve().parents[1])
    production = tmp_path / "production.sqlite3"
    resumed = tmp_path / "resumed.sqlite3"
    uninterrupted = tmp_path / "uninterrupted.sqlite3"

    def run(database: Path, *extra: str) -> dict:
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

    partial = run(resumed, "--maximum-events", str(gpt_boundary))
    assert partial["status"] == "DERIVED_WORKFLOW_PARTIAL"
    partial_store = ResearchStore(resumed, production_path=production)
    assert (
        sum(
            len(
                partial_store.arm_decisions(
                    "phase5-gold-workflow-v1", row.opportunity_id, row.revision_id
                )
            )
            for row in partial_store.candidates("phase5-gold-workflow-v1")
        )
        == 6
    )

    assert run(resumed)["status"] == "DERIVED_WORKFLOW_COMPLETE"
    assert run(uninterrupted)["status"] == "DERIVED_WORKFLOW_COMPLETE"
    resumed_store = ResearchStore(resumed, production_path=production)
    full_store = ResearchStore(uninterrupted, production_path=production)
    experiment_id = "phase5-gold-workflow-v1"
    assert resumed_store.opportunities(experiment_id) == full_store.opportunities(experiment_id)
    for candidate in resumed_store.candidates(experiment_id):
        assert resumed_store.arm_decisions(
            experiment_id, candidate.opportunity_id, candidate.revision_id
        ) == full_store.arm_decisions(
            experiment_id, candidate.opportunity_id, candidate.revision_id
        )
        assert resumed_store.lifecycle_events(
            experiment_id, candidate.opportunity_id, candidate.revision_id
        ) == full_store.lifecycle_events(
            experiment_id, candidate.opportunity_id, candidate.revision_id
        )
    resumed_checkpoint = resumed_store.workflow_checkpoint(experiment_id)
    full_checkpoint = full_store.workflow_checkpoint(experiment_id)
    assert resumed_checkpoint["status"] == full_checkpoint["status"] == "COMPLETE"
    assert resumed_checkpoint["state"] == full_checkpoint["state"]


def test_p6c_01_output_write_before_checkpoint_failure_converges_on_retry(
    tmp_path, capsys, monkeypatch
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    research = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    args = [
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
    original = ResearchStore.save_workflow_checkpoint
    failed = False

    def fail_once(self, *call_args, **call_kwargs):
        nonlocal failed
        if call_kwargs.get("status") == "COMPLETE" and not failed:
            failed = True
            raise RuntimeError("injected output-before-checkpoint fault")
        return original(self, *call_args, **call_kwargs)

    monkeypatch.setattr(ResearchStore, "save_workflow_checkpoint", fail_once)
    with pytest.raises(RuntimeError, match="output-before-checkpoint"):
        research_main(args)
    capsys.readouterr()
    store = ResearchStore(research, production_path=production)
    experiment_id = "phase5-gold-workflow-v1"
    before = store.opportunities(experiment_id)
    assert len(before) == 3
    assert store.workflow_checkpoint(experiment_id)["status"] == "INPUT_COMPLETE"

    monkeypatch.setattr(ResearchStore, "save_workflow_checkpoint", original)
    assert research_main(args) == 0
    capsys.readouterr()
    assert store.opportunities(experiment_id) == before
    assert store.workflow_checkpoint(experiment_id)["status"] == "COMPLETE"


def _trade_observation(
    event_id: str,
    *,
    event_seconds: Decimal,
    receipt_seconds: Decimal,
    price: Decimal,
    sequence: int,
) -> ReplayObservation:
    event_at = FIXTURE_NOW + timedelta(seconds=float(event_seconds))
    received_at = FIXTURE_NOW + timedelta(seconds=float(receipt_seconds))
    event_micros = int(event_at.timestamp() * 1_000_000)
    _, trade = parse_trade_message(
        {
            "type": "trades",
            "sy": "XAUTUSD",
            "p": str(price),
            "s": "1",
            "r": "m",
            "t": event_micros,
            "ts": event_micros,
            "fixture_id": event_id,
        },
        received_at=received_at,
    )
    return ReplayObservation(
        observation_id=trade.event_id,
        kind="TRADE",
        symbol="XAUTUSD",
        venue="delta_india",
        exchange_time_utc=event_at,
        available_at_utc=received_at,
        persistence_sequence=sequence,
        payload=trade.model_dump(mode="json"),
    )


def test_p6c_02_executed_stop_breach_survives_price_recovery_in_public_workflow(
    tmp_path, capsys
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest_path,
        lambda row: row,
        extra_rows=(
            _trade_observation(
                "phase6c-stop-breach",
                event_seconds=Decimal("0.9"),
                receipt_seconds=Decimal("1.0"),
                price=Decimal("2594.8"),
                sequence=920_001,
            ),
            _trade_observation(
                "phase6c-price-recovery",
                event_seconds=Decimal("1.4"),
                receipt_seconds=Decimal("1.5"),
                price=Decimal("2599.2285714285713"),
                sequence=920_002,
            ),
        ),
    )
    research, production, experiment_id = _run_gold_workflow(
        tmp_path / "workflow", manifest_path, config_path
    )
    capsys.readouterr()

    opportunities = ResearchStore(research, production_path=production).opportunities(experiment_id)
    assert len(opportunities) == 3
    assert all(
        arm.outcome is not None and arm.outcome.code != "TARGET_BEFORE_STOP"
        for row in opportunities
        for arm in row.arms
    )
    assert all(
        arm.outcome is not None
        and arm.outcome.entry_at_utc is None
        and "STOP_BREACH" in arm.outcome.reason
        for row in opportunities
        for arm in row.arms
    )


def test_p6c_02_benign_trade_update_preserves_healthy_public_outcomes(tmp_path, capsys) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest_path,
        lambda row: row,
        extra_rows=(
            _trade_observation(
                "phase6c-benign-update",
                event_seconds=Decimal("0.9"),
                receipt_seconds=Decimal("1.0"),
                price=Decimal("2599.0"),
                sequence=921_001,
            ),
            _trade_observation(
                "phase6c-benign-recovery",
                event_seconds=Decimal("1.4"),
                receipt_seconds=Decimal("1.5"),
                price=Decimal("2599.2"),
                sequence=921_002,
            ),
        ),
    )
    research, production, experiment_id = _run_gold_workflow(
        tmp_path / "workflow", manifest_path, config_path
    )
    capsys.readouterr()
    store = ResearchStore(research, production_path=production)
    opportunities = store.opportunities(experiment_id)
    assert len(opportunities) == 3
    assert all(
        arm.outcome is not None and arm.outcome.code == "TARGET_BEFORE_STOP"
        for row in opportunities
        for arm in row.arms
    )
    assert all(
        not store.lifecycle_events(experiment_id, row.opportunity_id, row.revision_id)
        or all(
            event.price_source == "CLOCK"
            for event in store.lifecycle_events(experiment_id, row.opportunity_id, row.revision_id)
        )
        for row in opportunities
    )


def test_p6c_02_bearish_stop_after_entry_is_not_erased_by_recovery() -> None:
    candidate = ResearchCandidate(
        opportunity_id="bearish-stop-recovery",
        revision_id="bearish-stop-recovery-v1",
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        asset="BTC",
        engine="BTC_FAST",
        direction="BEARISH",
        observed_at_utc=FIXTURE_NOW,
        expires_at_utc=FIXTURE_NOW + timedelta(seconds=10),
        entry=Decimal("100"),
        invalidation=Decimal("105"),
        targets=(Decimal("95"),),
    )
    decision = ArmDecision(
        arm="RULES_ONLY",
        state="APPROVED",
        ready_at_utc=FIXTURE_NOW,
        reason="fixture candidate",
    )
    instrument = InstrumentVersion(
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        valid_from_utc=FIXTURE_NOW - timedelta(days=1),
        contract_multiplier=Decimal("1"),
        tick_size=Decimal("0.1"),
        quote_currency="USD",
        base_currency="BTC",
        settlement_currency="USD",
    )
    quotes = (
        ExecutableQuote(
            event_id="bear-entry",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW,
            available_at_utc=FIXTURE_NOW,
            bid=Decimal("99.9"),
            ask=Decimal("100.1"),
        ),
        ExecutableQuote(
            event_id="bear-recovery",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=2),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=2),
            bid=Decimal("99.8"),
            ask=Decimal("100"),
        ),
        ExecutableQuote(
            event_id="bear-expiry",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=10),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=10),
            bid=Decimal("99.7"),
            ask=Decimal("99.9"),
        ),
    )
    breach = ResearchLifecycleEvent(
        opportunity_id=candidate.opportunity_id,
        revision_id=candidate.revision_id,
        event_id="bear-stop-event",
        to_state="INVALIDATED",
        occurred_at_utc=FIXTURE_NOW + timedelta(seconds=1),
        available_at_utc=FIXTURE_NOW + timedelta(seconds=1),
        reason="EXECUTED_STOP_BREACH",
        price_source="EXECUTED_TRADE",
        source_event_id="bear-stop-trade",
        price=Decimal("106"),
    )
    outcome = evaluate_quotes(
        candidate,
        decision,
        instrument,
        quotes,
        CostPolicy(
            policy_id="bear-stop-cost",
            quantity_contracts=Decimal("1"),
            fee_bps_per_side=Decimal("0"),
            slippage_bps_per_side=Decimal("0"),
            maximum_quote_gap_seconds=10,
        ),
        lifecycle_events=(breach,),
    )

    assert outcome.code == "STOP_BEFORE_TARGET"
    assert outcome.reason == "EXECUTED_STOP_WITH_EXECUTABLE_QUOTE"
    assert outcome.entry_at_utc == FIXTURE_NOW
    assert outcome.exit_at_utc == FIXTURE_NOW + timedelta(seconds=2)
    assert outcome.exit_price == Decimal("100")


def _older_quotes(count: int) -> tuple[ReplayObservation, ...]:
    rows = []
    for index in range(count):
        seconds = index - count
        at = FIXTURE_NOW + timedelta(seconds=seconds)
        rows.append(
            ReplayObservation(
                observation_id=f"phase6c-old-quote-{count}-{index}",
                kind="EXECUTABLE_QUOTE",
                symbol="XAUTUSD",
                venue="delta_india",
                exchange_time_utc=at,
                available_at_utc=at,
                persistence_sequence=930_000 + index,
                payload={"bid": "2599.9", "ask": "2600.1"},
            )
        )
    return tuple(rows)


@pytest.mark.parametrize("history_length", [1_000, 8_000])
def test_p6c_03_paper_workflow_does_not_materialize_full_irrelevant_quote_history(
    tmp_path, capsys, monkeypatch, history_length: int
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest_path,
        lambda row: row,
        extra_rows=_older_quotes(history_length),
    )
    research, production, experiment_id = _run_gold_workflow(
        tmp_path / "workflow", manifest_path, config_path
    )
    capsys.readouterr()

    materialized = []
    original = ResearchStore.quotes

    def measured_quotes(self, *args, **kwargs):
        rows = original(self, *args, **kwargs)
        materialized.append(len(rows))
        return rows

    monkeypatch.setattr(ResearchStore, "quotes", measured_quotes)
    assert (
        research_main(
            [
                "paper-workflow",
                "--database",
                str(research),
                "--paper-database",
                str(tmp_path / "paper.sqlite3"),
                "--production-database",
                str(production),
                "--experiment-id",
                experiment_id,
                "--maximum-events",
                "100",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["status"] == "SIMULATED_PROSPECTIVE_WARMUP_PARTIAL"
    assert max(materialized, default=0) <= 2
    assert result["resource_evidence"]["active_candidate_count"] == 0
    assert result["resource_evidence"]["maximum_active_candidates"] == 0
    assert (
        research_main(
            [
                "paper-workflow",
                "--database",
                str(research),
                "--paper-database",
                str(tmp_path / "paper.sqlite3"),
                "--production-database",
                str(production),
                "--experiment-id",
                experiment_id,
            ]
        )
        == 0
    )
    complete = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert complete["status"] == "SIMULATED_PROSPECTIVE_COMPLETE"
    assert complete["resource_evidence"]["maximum_quotes_per_candidate"] <= 2
    assert complete["resource_evidence"]["maximum_quote_page"] <= 6
    assert complete["resource_evidence"]["maximum_quotes_materialized_before_filter"] <= 6
    assert complete["resource_evidence"]["maximum_active_candidates"] == 3
    assert complete["resource_evidence"]["retired_candidate_count"] == 3
