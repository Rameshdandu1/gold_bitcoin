from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_phase6_closeout_regressions import _rewrite_fixture
from test_phase6_workflow_acceptance import _trade_observation

from marketintel.models import BookFeatures
from marketintel.research import main as research_main
from marketintel.research_engine import (
    ProviderCompletion,
    SharedResearchEngine,
    _apply_market_gate,
    _dual_decision,
    _provider_decision,
    provider_request_digest,
)
from marketintel.research_evaluation import evaluate_quotes
from marketintel.research_fixtures import FIXTURE_NOW, generate_fixture
from marketintel.research_models import (
    RESEARCH_ARMS,
    ArmDecision,
    ArmRecord,
    CostPolicy,
    ExecutableQuote,
    ExperimentConfig,
    InstrumentVersion,
    OpportunityRecord,
    ResearchCandidate,
    ResearchLifecycleEvent,
    ResearchTargetCrossing,
)
from marketintel.research_replay import load_manifest
from marketintel.research_storage import ResearchStore

EXPERIMENT_ID = "phase5-gold-workflow-v1"


def _run_process(manifest: Path, config: Path, database: Path, production: Path) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "marketintel.research",
            "run-workflow",
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--database",
            str(database),
            "--production-database",
            str(production),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.splitlines()[-1])


def test_p6w_01_candidate_and_rules_arm_rollback_and_fresh_process_resume(tmp_path) -> None:
    manifest, config = generate_fixture("GOLD", tmp_path / "fixture")
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    ResearchStore(database, production_path=production)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER fail_initial_rules BEFORE INSERT ON arm_decisions "
            "WHEN NEW.arm='RULES_ONLY' BEGIN "
            "SELECT RAISE(ABORT, 'injected candidate-rules boundary'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="candidate-rules boundary"):
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest),
                "--config",
                str(config),
                "--database",
                str(database),
                "--production-database",
                str(production),
            ]
        )
    store = ResearchStore(database, production_path=production)
    assert store.candidates(EXPERIMENT_ID) == []
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER fail_initial_rules")

    result = _run_process(manifest, config, database, production)
    assert result["status"] == "DERIVED_WORKFLOW_COMPLETE"
    assert len(store.candidates(EXPERIMENT_ID)) == 3
    assert len(store.opportunities(EXPERIMENT_ID)) == 3
    assert (
        sum(
            len(store.arm_decisions(EXPERIMENT_ID, row.opportunity_id, row.revision_id))
            for row in store.candidates(EXPERIMENT_ID)
        )
        == 12
    )
    assert _run_process(manifest, config, database, production)["status"] == (
        "DERIVED_WORKFLOW_COMPLETE"
    )


def test_p6w_01_obsolete_checkpoint_is_refused_without_deleting_database(tmp_path) -> None:
    manifest_path, _ = generate_fixture("GOLD", tmp_path / "fixture")
    with pytest.raises(ValueError, match="existing database is retained for audit"):
        SharedResearchEngine.from_checkpoint(
            load_manifest(manifest_path),
            {"schema": "phase6-workflow-acceptance-derived-state-v2"},
        )


def test_p6w_02_late_pre_candidate_trade_is_not_a_new_stop(tmp_path, capsys) -> None:
    manifest, config = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest,
        lambda row: row,
        extra_rows=(
            _trade_observation(
                "late-historical-stop",
                event_seconds=Decimal("-0.1"),
                receipt_seconds=Decimal("1"),
                price=Decimal("2594.8"),
                sequence=950_001,
            ),
            _trade_observation(
                "late-historical-recovery",
                event_seconds=Decimal("1.4"),
                receipt_seconds=Decimal("1.5"),
                price=Decimal("2599.2285714285713"),
                sequence=950_002,
            ),
        ),
    )
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest),
                "--config",
                str(config),
                "--database",
                str(database),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    capsys.readouterr()
    store = ResearchStore(database, production_path=production)
    for candidate in store.candidates(EXPERIMENT_ID):
        assert all(
            row.source_event_id != "late-historical-stop"
            for row in store.lifecycle_events(
                EXPERIMENT_ID, candidate.opportunity_id, candidate.revision_id
            )
        )
    assert all(
        arm.outcome is not None and arm.outcome.code == "TARGET_BEFORE_STOP"
        for row in store.opportunities(EXPERIMENT_ID)
        for arm in row.arms
    )


def test_p6w_03_executed_target_crossing_survives_recovery_and_provider_retirement(
    tmp_path, capsys
) -> None:
    manifest, config = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest,
        lambda row: row,
        extra_rows=(
            _trade_observation(
                "executed-target-one",
                event_seconds=Decimal("0.9"),
                receipt_seconds=Decimal("1"),
                price=Decimal("2700"),
                sequence=951_001,
            ),
            _trade_observation(
                "target-price-recovery",
                event_seconds=Decimal("1.4"),
                receipt_seconds=Decimal("1.5"),
                price=Decimal("2599.2285714285713"),
                sequence=951_002,
            ),
        ),
    )
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest),
                "--config",
                str(config),
                "--database",
                str(database),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    capsys.readouterr()
    store = ResearchStore(database, production_path=production)
    for candidate in store.candidates(EXPERIMENT_ID):
        crossings = store.target_crossings(
            EXPERIMENT_ID, candidate.opportunity_id, candidate.revision_id
        )
        assert crossings and crossings[0].occurred_at_utc == FIXTURE_NOW + timedelta(seconds=0.9)
        assert crossings[0].available_at_utc == FIXTURE_NOW + timedelta(seconds=1)
    assert all(
        arm.outcome is not None and arm.outcome.code == "NO_ENTRY"
        for row in store.opportunities(EXPERIMENT_ID)
        for arm in row.arms
    )
    checkpoint = store.workflow_checkpoint(EXPERIMENT_ID)
    assert checkpoint["state"]["provider_completions"] == []
    assert store.provider_completion_count(EXPERIMENT_ID) == 6


def test_p6w_03_bearish_target_history_is_scoped_to_crossed_index() -> None:
    candidate = ResearchCandidate(
        opportunity_id="bearish-target-history",
        revision_id="bearish-target-history-v1",
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        asset="BTC",
        engine="BTC_FAST",
        direction="BEARISH",
        observed_at_utc=FIXTURE_NOW,
        expires_at_utc=FIXTURE_NOW + timedelta(seconds=20),
        entry=Decimal("100"),
        invalidation=Decimal("105"),
        targets=(Decimal("90"), Decimal("80")),
    )
    decision = ArmDecision(
        arm="RULES_ONLY",
        state="APPROVED",
        ready_at_utc=FIXTURE_NOW,
        reason="synthetic fixture",
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
            event_id="bear-target-entry",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=4),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=4),
            bid=Decimal("99.9"),
            ask=Decimal("100.1"),
        ),
        ExecutableQuote(
            event_id="bear-target-two",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=10),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=10),
            bid=Decimal("79.8"),
            ask=Decimal("79.9"),
        ),
    )
    crossing = ResearchTargetCrossing(
        opportunity_id=candidate.opportunity_id,
        revision_id=candidate.revision_id,
        target_index=1,
        event_id="bear-target-one-crossing",
        occurred_at_utc=FIXTURE_NOW + timedelta(seconds=0.9),
        available_at_utc=FIXTURE_NOW + timedelta(seconds=1),
        source_event_id="bear-target-one-trade",
        price=Decimal("89"),
    )
    policy = CostPolicy(
        policy_id="bear-target-policy",
        quantity_contracts=Decimal("1"),
        fee_bps_per_side=Decimal("0"),
        slippage_bps_per_side=Decimal("0"),
        maximum_quote_gap_seconds=10,
    )

    crossed = evaluate_quotes(
        candidate,
        decision,
        instrument,
        quotes,
        policy,
        target_index=1,
        target_crossings=(crossing,),
    )
    higher = evaluate_quotes(
        candidate,
        decision,
        instrument,
        quotes,
        policy,
        target_index=2,
        target_crossings=(crossing,),
    )
    assert crossed.code == "NO_ENTRY"
    assert crossed.reason == "EXECUTED_TARGET_CROSSING_BEFORE_ENTRY"
    assert higher.code == "TARGET_BEFORE_STOP"


def _candidate_and_config(tmp_path) -> tuple[ResearchCandidate, ExperimentConfig]:
    _, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    config = ExperimentConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    candidate = ResearchCandidate(
        opportunity_id="temporary-book",
        revision_id="temporary-book-v1",
        venue="delta_india",
        symbol="XAUTUSD",
        product_id=84,
        asset="GOLD",
        engine="GOLD_FAST",
        direction="BULLISH",
        observed_at_utc=FIXTURE_NOW,
        expires_at_utc=FIXTURE_NOW + timedelta(minutes=30),
        entry=Decimal("2600"),
        invalidation=Decimal("2595"),
        targets=(Decimal("2610"), Decimal("2620")),
    )
    return candidate, config


def _completion(
    candidate: ResearchCandidate,
    config: ExperimentConfig,
    provider: str,
    seconds: int,
    verdict: str = "CONFIRM",
) -> ProviderCompletion:
    return ProviderCompletion(
        provider=provider,
        candidate_id=candidate.opportunity_id,
        revision_id=candidate.revision_id,
        decision=verdict,
        supported_target_indices=(1,),
        completed_at_utc=FIXTURE_NOW + timedelta(seconds=seconds),
        available_at_utc=FIXTURE_NOW + timedelta(seconds=seconds),
        request_digest=provider_request_digest(candidate, config, provider),
        configuration_digest=config.canonical_config_hash(),
        provider_latency_ms=10,
        attributable_cost_microusd=0,
        evidence_mode="SYNTHETIC_FIXTURE",
    )


def _book(at, bid: str, ask: str) -> BookFeatures:
    return BookFeatures(
        available=True,
        observed_at_utc=at,
        best_bid=Decimal(bid),
        best_ask=Decimal(ask),
        spread=Decimal(ask) - Decimal(bid),
        bid_depth_quote=Decimal("1400"),
        ask_depth_quote=Decimal("600"),
        imbalance=Decimal("0.4"),
        absorption="NONE",
        reason="SYNTHETIC_FIXTURE_NOT_LIVE",
    )


def _book_observation(seconds: Decimal, bid: str, ask: str, generation: int):
    at = FIXTURE_NOW + timedelta(seconds=float(seconds))
    book = _book(at, bid, ask)
    return {
        "observation_id": f"contract-book-{seconds}",
        "kind": "BOOK_SNAPSHOT",
        "symbol": "XAUTUSD",
        "venue": "delta_india",
        "exchange_time_utc": at,
        "available_at_utc": at,
        "persistence_sequence": 952_000 + generation,
        "payload": {
            "sequence": generation,
            "generation": generation,
            "snapshot": True,
            "features": book.model_dump(mode="json"),
        },
    }


def test_p6w_04_dual_uses_raw_verdicts_and_its_own_market_boundary(tmp_path) -> None:
    candidate, config = _candidate_and_config(tmp_path)
    gpt = _provider_decision(
        candidate, config, _completion(candidate, config, "GPT", 2), "RULES_PLUS_GPT"
    )
    gpt = _apply_market_gate(
        gpt,
        candidate,
        config,
        book=_book(FIXTURE_NOW + timedelta(seconds=1.5), "2600", "3000"),
    )
    claude = _provider_decision(
        candidate,
        config,
        _completion(candidate, config, "CLAUDE", 3),
        "RULES_PLUS_CLAUDE",
    )
    healthy = _book(FIXTURE_NOW + timedelta(seconds=2.5), "2599.9", "2600.1")
    claude = _apply_market_gate(claude, candidate, config, book=healthy)
    dual = _apply_market_gate(
        _dual_decision(gpt, claude, config.target_index),
        candidate,
        config,
        book=healthy,
    )

    assert gpt.state == "WAIT"
    assert gpt.raw_provider_verdict == "CONFIRM"
    assert claude.state == "APPROVED"
    assert dual.state == "APPROVED"
    assert "provider returned WAIT" not in dual.reason

    genuine_wait = _provider_decision(
        candidate,
        config,
        _completion(candidate, config, "GPT", 2, verdict="WAIT"),
        "RULES_PLUS_GPT",
    )
    blocked = _dual_decision(genuine_wait, claude, config.target_index)
    assert blocked.state == "WAIT"
    assert blocked.reason == "At least one independent provider returned WAIT"


def test_p6w_04_public_workflow_persists_independent_dual_market_gate(tmp_path, capsys) -> None:
    from marketintel.research_models import ReplayObservation

    manifest, config = generate_fixture("GOLD", tmp_path / "fixture")
    _rewrite_fixture(
        manifest,
        lambda row: row,
        extra_rows=(
            ReplayObservation.model_validate(_book_observation(Decimal("1.5"), "2600", "3000", 2)),
            ReplayObservation.model_validate(
                _book_observation(Decimal("2.5"), "2599.9", "2600.1", 3)
            ),
        ),
    )
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest),
                "--config",
                str(config),
                "--database",
                str(database),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    capsys.readouterr()
    store = ResearchStore(database, production_path=production)
    for candidate in store.candidates(EXPERIMENT_ID):
        decisions = {
            row.arm: row
            for row in store.arm_decisions(
                EXPERIMENT_ID, candidate.opportunity_id, candidate.revision_id
            )
        }
        assert decisions["RULES_PLUS_GPT"].state == "WAIT"
        assert decisions["RULES_PLUS_GPT"].raw_provider_verdict == "CONFIRM"
        assert decisions["RULES_PLUS_CLAUDE"].state == "APPROVED"
        assert decisions["RULES_PLUS_DUAL"].state == "APPROVED"


@pytest.mark.parametrize("direction", ["BULLISH", "BEARISH"])
def test_p6w_05_executed_stop_requires_continuous_executable_quotes(direction) -> None:
    bullish = direction == "BULLISH"
    candidate = ResearchCandidate(
        opportunity_id=f"stop-coverage-{direction}",
        revision_id=f"stop-coverage-{direction}-v1",
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        asset="BTC",
        engine="BTC_FAST",
        direction=direction,
        observed_at_utc=FIXTURE_NOW,
        expires_at_utc=FIXTURE_NOW + timedelta(seconds=200),
        entry=Decimal("100"),
        invalidation=Decimal("95" if bullish else "105"),
        targets=(Decimal("110" if bullish else "90"),),
    )
    decision = ArmDecision(
        arm="RULES_ONLY",
        state="APPROVED",
        ready_at_utc=FIXTURE_NOW,
        reason="synthetic fixture",
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
            event_id="entry",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=4),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=4),
            bid=Decimal("99.9"),
            ask=Decimal("100.1"),
        ),
        ExecutableQuote(
            event_id="next-quote",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=150),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=150),
            bid=Decimal("99.8"),
            ask=Decimal("100.2"),
        ),
    )
    breach = ResearchLifecycleEvent(
        opportunity_id=candidate.opportunity_id,
        revision_id=candidate.revision_id,
        event_id="terminal-stop",
        to_state="INVALIDATED",
        occurred_at_utc=FIXTURE_NOW + timedelta(seconds=99.9),
        available_at_utc=FIXTURE_NOW + timedelta(seconds=100),
        reason="EXECUTED_STOP_BREACH",
        price_source="EXECUTED_TRADE",
        source_event_id="stop-trade",
        price=Decimal("94" if bullish else "106"),
    )
    outcome = evaluate_quotes(
        candidate,
        decision,
        instrument,
        quotes,
        CostPolicy(
            policy_id="coverage-policy",
            quantity_contracts=Decimal("1"),
            fee_bps_per_side=Decimal("0"),
            slippage_bps_per_side=Decimal("0"),
            maximum_quote_gap_seconds=60,
        ),
        lifecycle_events=(breach,),
    )

    assert outcome.code == "INCOMPLETE"
    assert outcome.reason == "EXECUTED_STOP_WITH_INCOMPLETE_QUOTE_PATH"
    assert outcome.data_complete is False
    assert outcome.exit_price is None and outcome.net_pnl is None


def test_p6w_05_source_loss_keeps_stop_terminal_without_priced_exit() -> None:
    candidate = ResearchCandidate(
        opportunity_id="source-loss-stop",
        revision_id="source-loss-stop-v1",
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        asset="BTC",
        engine="BTC_FAST",
        direction="BULLISH",
        observed_at_utc=FIXTURE_NOW,
        expires_at_utc=FIXTURE_NOW + timedelta(seconds=10),
        entry=Decimal("100"),
        invalidation=Decimal("95"),
        targets=(Decimal("110"),),
    )
    decision = ArmDecision(
        arm="RULES_ONLY",
        state="APPROVED",
        ready_at_utc=FIXTURE_NOW,
        reason="synthetic fixture",
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
            event_id="source-entry",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW,
            available_at_utc=FIXTURE_NOW,
            bid=Decimal("99.9"),
            ask=Decimal("100.1"),
        ),
        ExecutableQuote(
            event_id="source-next",
            venue="delta_india",
            symbol="BTCUSD",
            observed_at_utc=FIXTURE_NOW + timedelta(seconds=2),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=2),
            bid=Decimal("99.8"),
            ask=Decimal("100.2"),
        ),
    )
    breach = ResearchLifecycleEvent(
        opportunity_id=candidate.opportunity_id,
        revision_id=candidate.revision_id,
        event_id="source-stop",
        to_state="INVALIDATED",
        occurred_at_utc=FIXTURE_NOW + timedelta(seconds=0.9),
        available_at_utc=FIXTURE_NOW + timedelta(seconds=1),
        reason="EXECUTED_STOP_BREACH",
        price_source="EXECUTED_TRADE",
        source_event_id="source-stop-trade",
        price=Decimal("94"),
    )
    outcome = evaluate_quotes(
        candidate,
        decision,
        instrument,
        quotes,
        CostPolicy(
            policy_id="source-stop-policy",
            quantity_contracts=Decimal("1"),
            fee_bps_per_side=Decimal("0"),
            slippage_bps_per_side=Decimal("0"),
            maximum_quote_gap_seconds=10,
        ),
        source_transitions=((FIXTURE_NOW + timedelta(seconds=0.5), "UNAVAILABLE"),),
        lifecycle_events=(breach,),
    )
    assert outcome.code == "INCOMPLETE"
    assert outcome.reason == "EXECUTED_STOP_WITH_INCOMPLETE_QUOTE_PATH"
    assert outcome.exit_price is None and outcome.net_pnl is None


def test_p6w_05_public_workflow_preserves_stop_but_refuses_gap_pricing(tmp_path, capsys) -> None:
    manifest, config = generate_fixture("GOLD", tmp_path / "fixture")
    source_manifest = load_manifest(manifest)
    source_path = manifest.parent / source_manifest.files[0].path
    original_rows = [
        json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()
    ]
    original_ids = {
        row["payload"]["candidate_id"]
        for row in original_rows
        if row["kind"] == "PROVIDER_COMPLETION"
    }

    def delay_target_quote(row):
        if row.kind == "EXECUTABLE_QUOTE" and "-target-quote" in row.observation_id:
            at = FIXTURE_NOW + timedelta(seconds=150)
            return row.model_copy(update={"exchange_time_utc": at, "available_at_utc": at})
        return row

    _rewrite_fixture(
        manifest,
        delay_target_quote,
        extra_rows=(
            _trade_observation(
                "gap-stop",
                event_seconds=Decimal("99.9"),
                receipt_seconds=Decimal("100"),
                price=Decimal("2594.8"),
                sequence=953_001,
            ),
            _trade_observation(
                "gap-stop-recovery",
                event_seconds=Decimal("100.4"),
                receipt_seconds=Decimal("100.5"),
                price=Decimal("2599.2285714285713"),
                sequence=953_002,
            ),
        ),
    )
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest),
                "--config",
                str(config),
                "--database",
                str(database),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    capsys.readouterr()
    rows = {
        row.opportunity_id: row
        for row in ResearchStore(database, production_path=production).opportunities(EXPERIMENT_ID)
    }
    assert original_ids <= rows.keys()
    for opportunity_id in original_ids:
        assert all(
            arm.outcome is not None
            and arm.outcome.code == "INCOMPLETE"
            and arm.outcome.reason == "EXECUTED_STOP_WITH_INCOMPLETE_QUOTE_PATH"
            and arm.outcome.exit_price is None
            and arm.outcome.net_pnl is None
            for arm in rows[opportunity_id].arms
        )


def test_p6w_06_api_and_report_page_before_model_materialization(
    tmp_path, capsys, monkeypatch
) -> None:
    manifest_path, config_path = generate_fixture("GOLD", tmp_path / "fixture")
    manifest = load_manifest(manifest_path)
    config = ExperimentConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    store = ResearchStore(database, production_path=production)
    store.create_experiment(manifest, config)
    for index in range(600):
        observed = FIXTURE_NOW + timedelta(days=index)
        store.save_opportunity(
            config.experiment_id,
            OpportunityRecord(
                opportunity_id=f"bounded-{index:04d}",
                revision_id=f"bounded-{index:04d}-v1",
                asset="GOLD",
                engine="GOLD_FAST",
                direction="BULLISH",
                observed_at_utc=observed,
                label_information_start_utc=observed,
                label_information_end_utc=observed + timedelta(hours=1),
                quantitatively_eligible=True,
                market_data_mode="SYNTHETIC_FIXTURE",
                arms=tuple(
                    ArmRecord(
                        arm=arm,
                        state="WAIT",
                        decision_ready_at_utc=observed,
                        reason="SYNTHETIC_FIXTURE_NOT_LIVE",
                    )
                    for arm in RESEARCH_ARMS
                ),
            ),
        )

    original_validate = OpportunityRecord.model_validate_json
    constructed = 0

    def counted(value):
        nonlocal constructed
        constructed += 1
        return original_validate(value)

    monkeypatch.setattr(OpportunityRecord, "model_validate_json", staticmethod(counted))
    assert len(store.opportunity_page(config.experiment_id, limit=1)) == 1
    assert constructed == 1

    page_sizes = []
    original_page = ResearchStore.selected_opportunity_page

    def measured_page(self, *args, **kwargs):
        page = original_page(self, *args, **kwargs)
        page_sizes.append(len(page))
        return page

    monkeypatch.setattr(ResearchStore, "selected_opportunity_page", measured_page)
    output = tmp_path / "report"
    assert (
        research_main(
            [
                "report",
                "--database",
                str(database),
                "--production-database",
                str(production),
                "--experiment-id",
                config.experiment_id,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    capsys.readouterr()
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["opportunities"] == 600
    assert summary["resource_evidence"]["maximum_projection_page"] == 200
    assert max(page_sizes) == 200
    assert sum(page_sizes) == 600
    assert len((output / "selected-opportunities.jsonl").read_text().splitlines()) == 600
