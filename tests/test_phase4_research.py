from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.research_evaluation import (
    arm_metrics,
    evaluate_bar_path,
    evaluate_quotes,
    paired_day_block_difference,
    purged_folds,
)
from marketintel.research_models import (
    ArmDecision,
    ArmRecord,
    CostPolicy,
    DatasetManifest,
    ExecutableQuote,
    ExperimentConfig,
    InstrumentVersion,
    OpportunityRecord,
    PriceBar,
    ReplayObservation,
    ResearchCandidate,
    SourceCoverage,
)
from marketintel.research_replay import replay, spool_observations
from marketintel.research_storage import PaperLedger, ResearchStore
from marketintel.storage import Store

NOW = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)


def manifest(*, gap: bool = False) -> DatasetManifest:
    return DatasetManifest(
        dataset_id="dataset-001",
        content_hash="a" * 64,
        code_commit="d1978d3",
        rule_version="rules-v1",
        feature_version="features-v1",
        created_at_utc=NOW,
        data_mode="SYNTHETIC_FIXTURE",
        provenance="deterministic unit fixture",
        license_notes="test-only",
        files=(),
        instruments=(instrument(),),
        coverage=(
            SourceCoverage(
                source="fixture",
                symbol="BTCUSD",
                start_utc=NOW,
                end_utc=NOW + timedelta(minutes=5),
                record_count=3,
                gaps=((NOW + timedelta(minutes=2), NOW + timedelta(minutes=3)),) if gap else (),
            ),
        ),
    )


def config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="experiment-001",
        dataset_id="dataset-001",
        created_at_utc=NOW,
        evaluation_start_utc=NOW,
        evaluation_end_utc=NOW + timedelta(minutes=4),
        evaluation_cadence_seconds=60,
        cost_policy=policy(),
    )


def policy() -> CostPolicy:
    return CostPolicy(
        policy_id="cost-v1",
        quantity_contracts=Decimal("2"),
        fee_bps_per_side=Decimal("1"),
        slippage_bps_per_side=Decimal("1"),
        maximum_quote_gap_seconds=60,
    )


def instrument() -> InstrumentVersion:
    return InstrumentVersion(
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        valid_from_utc=NOW - timedelta(days=1),
        contract_multiplier=Decimal("0.001"),
        tick_size=Decimal("0.5"),
        quote_currency="USD",
        base_currency="BTC",
        settlement_currency="USD",
    )


def observations() -> list[ReplayObservation]:
    return [
        ReplayObservation(
            observation_id="early",
            kind="CANDLE_OBSERVATION",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW + timedelta(seconds=1),
            persistence_sequence=1,
            payload={"close": "100"},
        ),
        ReplayObservation(
            observation_id="correction",
            kind="CANDLE_OBSERVATION",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW + timedelta(minutes=2, seconds=1),
            persistence_sequence=2,
            payload={"close": "101", "corrects": "early"},
        ),
    ]


def candidate(*, expires: datetime | None = None) -> ResearchCandidate:
    return ResearchCandidate(
        opportunity_id="opp-1",
        revision_id="rev-1",
        venue="delta_india",
        symbol="BTCUSD",
        product_id=27,
        asset="BTC",
        engine="BTC_FAST",
        direction="BULLISH",
        observed_at_utc=NOW,
        expires_at_utc=expires or NOW + timedelta(minutes=3),
        entry=Decimal("100"),
        invalidation=Decimal("95"),
        targets=(Decimal("105"), Decimal("110")),
    )


def decision(arm: str = "RULES_ONLY") -> ArmDecision:
    return ArmDecision(
        arm=arm,
        state="APPROVED",
        ready_at_utc=NOW + timedelta(seconds=10),
        reason="fixture approval",
        provider_latency_ms=1000,
        attributable_cost_microusd=0,
    )


def quote(event_id: str, seconds: int, bid: str, ask: str) -> ExecutableQuote:
    return ExecutableQuote(
        event_id=event_id,
        venue="delta_india",
        symbol="BTCUSD",
        observed_at_utc=NOW + timedelta(seconds=seconds),
        bid=Decimal(bid),
        ask=Decimal(ask),
    )


def test_availability_replay_hides_correction_until_arrival_and_resumes_identically() -> None:
    full, full_checkpoint = replay(manifest(), config(), observations())
    first, checkpoint = replay(manifest(), config(), observations(), maximum_points=2)
    second, resumed = replay(manifest(), config(), observations(), checkpoint=checkpoint)

    assert "correction" not in first[-1].visible_observation_ids
    assert "correction" not in second[0].visible_observation_ids
    assert "correction" in second[1].visible_observation_ids
    assert [row.rolling_hash for row in first + second] == [row.rolling_hash for row in full]
    assert resumed.rolling_hash == full_checkpoint.rolling_hash


def test_declared_source_gap_is_unavailable_not_negative_result() -> None:
    points, _ = replay(manifest(gap=True), config(), observations())
    assert points[2].status == "UNAVAILABLE"
    assert points[2].reason == "DECLARED_SOURCE_GAP:fixture"
    assert points[3].status == "ELIGIBLE"


def test_disk_spool_orders_chunks_without_materializing_input(tmp_path) -> None:
    source = tmp_path / "observations.jsonl"
    rows = list(reversed(observations()))
    source.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
    supplied_data = manifest().model_dump(mode="json")
    supplied_data["files"] = [
        {
            "path": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "record_count": 2,
        }
    ]
    supplied = DatasetManifest.model_validate(supplied_data)
    ordered = spool_observations(
        tmp_path / "manifest.json", supplied, tmp_path / "spool.sqlite3", batch_size=1
    )
    points, checkpoint = replay(supplied, config(), ordered, presorted=True)
    assert points[-1].visible_observation_ids == ("early", "correction")
    assert checkpoint.input_offset == 2


def test_quote_evaluation_uses_actual_ready_time_costs_and_original_target_index() -> None:
    rows = [
        quote("too-early", 5, "99.5", "100"),
        quote("entry", 11, "100", "100.5"),
        quote("target-two", 40, "110", "110.5"),
    ]
    outcome = evaluate_quotes(candidate(), decision(), instrument(), rows, policy(), target_index=2)

    assert outcome.code == "TARGET_BEFORE_STOP"
    assert outcome.entry_at_utc == NOW + timedelta(seconds=11)
    assert outcome.supporting_event_ids == ("entry", "target-two")
    assert outcome.entry_price == Decimal("101")
    assert outcome.exit_price == Decimal("109.5")
    assert outcome.total_cost is not None and outcome.total_cost > 0
    assert outcome.net_pnl is not None and outcome.net_pnl < outcome.gross_pnl


def test_evaluation_rejects_instrument_mismatch_and_incomplete_expiry_path() -> None:
    wrong = instrument().model_copy(update={"product_id": 99})
    mismatch = evaluate_quotes(candidate(), decision(), wrong, [], policy())
    incomplete = evaluate_quotes(
        candidate(), decision(), instrument(), [quote("entry", 11, "100", "100.5")], policy()
    )

    assert mismatch.code == "INCOMPLETE"
    assert mismatch.reason == "PRODUCT_VERSION_MISMATCH"
    assert incomplete.code == "INCOMPLETE"
    assert incomplete.reason == "PATH_DOES_NOT_REACH_EXPIRY"


def test_expiry_boundary_is_inclusive_and_does_not_reset_for_ai_arm() -> None:
    expiry = NOW + timedelta(seconds=30)
    late_decision = decision("RULES_PLUS_DUAL").model_copy(
        update={"ready_at_utc": expiry + timedelta(microseconds=1)}
    )
    no_entry = evaluate_quotes(candidate(expires=expiry), late_decision, instrument(), [], policy())
    at_boundary = evaluate_quotes(
        candidate(expires=expiry),
        decision(),
        instrument(),
        [quote("entry", 11, "100", "100.5"), quote("boundary", 30, "105", "105.5")],
        policy(),
    )

    assert no_entry.code == "NO_ENTRY"
    assert no_entry.reason == "DECISION_READY_AFTER_EXPIRY"
    assert at_boundary.code == "TARGET_BEFORE_STOP"


def test_ohlc_same_bar_target_and_stop_is_ambiguous() -> None:
    bar = PriceBar(
        event_id="bar-1",
        venue="delta_india",
        symbol="BTCUSD",
        start_utc=NOW + timedelta(seconds=11),
        end_utc=NOW + timedelta(minutes=1),
        open=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("94"),
        close=Decimal("101"),
    )
    outcome = evaluate_bar_path(candidate(), decision(), [bar])
    assert outcome.code == "AMBIGUOUS"


def test_bearish_gold_uses_bid_entry_ask_exit_and_contract_units() -> None:
    gold = instrument().model_copy(
        update={
            "symbol": "XAUTUSD",
            "product_id": 88,
            "contract_multiplier": Decimal("0.01"),
            "tick_size": Decimal("0.1"),
            "base_currency": "XAUT",
        }
    )
    short = candidate().model_copy(
        update={
            "asset": "GOLD",
            "symbol": "XAUTUSD",
            "product_id": 88,
            "engine": "GOLD_FAST",
            "direction": "BEARISH",
            "entry": Decimal("3000"),
            "invalidation": Decimal("3010"),
            "targets": (Decimal("2990"),),
        }
    )
    quotes = [
        ExecutableQuote(
            event_id="gold-entry",
            venue="delta_india",
            symbol="XAUTUSD",
            observed_at_utc=NOW + timedelta(seconds=11),
            bid=Decimal("3000"),
            ask=Decimal("3000.5"),
        ),
        ExecutableQuote(
            event_id="gold-target",
            venue="delta_india",
            symbol="XAUTUSD",
            observed_at_utc=NOW + timedelta(seconds=30),
            bid=Decimal("2989.5"),
            ask=Decimal("2990"),
        ),
    ]
    outcome = evaluate_quotes(short, decision(), gold, quotes, policy())
    assert outcome.code == "TARGET_BEFORE_STOP"
    assert outcome.entry_price == Decimal("2999.7")
    assert outcome.exit_price == Decimal("2990.3")
    assert outcome.gross_pnl == Decimal("0.188")


def test_required_unknown_funding_is_rejected() -> None:
    with pytest.raises(ValueError, match="funding"):
        CostPolicy(
            policy_id="invalid",
            quantity_contracts=Decimal("1"),
            fee_bps_per_side=Decimal("1"),
            slippage_bps_per_side=Decimal("1"),
            funding_required=True,
        )


def opportunity(identifier: str, start: datetime, end: datetime) -> OpportunityRecord:
    outcome = evaluate_quotes(
        candidate().model_copy(update={"opportunity_id": identifier}),
        decision(),
        instrument(),
        [
            quote(f"{identifier}-entry", 11, "100", "100.5"),
            quote(f"{identifier}-target", 30, "105", "105.5"),
        ],
        policy(),
    )
    return OpportunityRecord(
        opportunity_id=identifier,
        revision_id=f"{identifier}-rev",
        asset="BTC",
        engine="BTC_FAST",
        direction="BULLISH",
        observed_at_utc=start,
        label_information_start_utc=start,
        label_information_end_utc=end,
        quantitatively_eligible=True,
        arms=(
            ArmRecord(
                arm="RULES_ONLY",
                state="EXECUTABLE",
                decision_ready_at_utc=decision().ready_at_utc,
                reason="fixture",
                outcome=outcome,
            ),
            ArmRecord(arm="RULES_PLUS_GPT", state="UNAVAILABLE", reason="no genuine assessment"),
            ArmRecord(arm="RULES_PLUS_CLAUDE", state="UNAVAILABLE", reason="no genuine assessment"),
            ArmRecord(arm="RULES_PLUS_DUAL", state="UNAVAILABLE", reason="no genuine assessment"),
        ),
    )


def test_grouped_purging_keeps_missing_ai_in_denominator() -> None:
    rows = [
        opportunity("a", NOW, NOW + timedelta(hours=2)),
        opportunity("b", NOW + timedelta(hours=1), NOW + timedelta(hours=3)),
        opportunity("c", NOW + timedelta(hours=2, minutes=30), NOW + timedelta(hours=5)),
        opportunity("d", NOW + timedelta(hours=6), NOW + timedelta(hours=7)),
    ]
    folds = purged_folds(rows, fold_count=2)
    metrics = arm_metrics(rows)

    assert "c" in folds[0]["purged"]
    assert metrics["RULES_PLUS_GPT"]["opportunity_denominator"] == 4
    assert metrics["RULES_PLUS_GPT"]["unavailable"] == 4
    assert metrics["RULES_ONLY"]["classification"] == "INSUFFICIENT_DATA"
    paired = paired_day_block_difference(rows, "RULES_ONLY", "RULES_PLUS_DUAL")
    assert paired["classification"] == "INSUFFICIENT_DATA"
    assert paired["opportunity_denominator"] == 4


def test_holdout_is_never_used_in_training_or_validation_fold() -> None:
    rows = [
        opportunity("a", NOW, NOW + timedelta(minutes=30)),
        opportunity("b", NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
        opportunity("c", NOW + timedelta(hours=3), NOW + timedelta(hours=4)),
        opportunity("holdout", NOW + timedelta(days=1), NOW + timedelta(days=1, hours=1)),
    ]
    folds = purged_folds(rows, fold_count=2, holdout_start=NOW + timedelta(days=1))
    assert all(fold["holdout"] == ("holdout",) for fold in folds)
    assert all("holdout" not in fold["train"] + fold["test"] for fold in folds)


def test_research_store_refuses_production_database_and_identity_mutation(tmp_path) -> None:
    path = tmp_path / "research.sqlite3"
    with pytest.raises(ValueError, match="isolated"):
        ResearchStore(path, production_path=path)
    store = ResearchStore(path)
    store.create_experiment(manifest(), config())
    with pytest.raises(ValueError, match="immutable"):
        store.create_experiment(manifest(), config().model_copy(update={"seed": 2}))


def test_paper_ledger_requires_immutable_prior_decision_and_resumes_cursor(tmp_path) -> None:
    ledger = PaperLedger(tmp_path / "paper.sqlite3")
    approved = decision()
    assert ledger.record_decision(
        "opp-1",
        "rev-1",
        approved,
        candidate=candidate(),
        config_hash="a" * 64,
        target_index=1,
        source_identity="phase4-fixture-v1",
        recorded_at=NOW + timedelta(seconds=10),
    )
    assert not ledger.record_decision(
        "opp-1",
        "rev-1",
        approved,
        candidate=candidate(),
        config_hash="a" * 64,
        target_index=1,
        source_identity="phase4-fixture-v1",
        recorded_at=NOW + timedelta(seconds=10),
    )
    with pytest.raises(ValueError, match="immutable"):
        ledger.record_decision(
            "opp-1",
            "rev-1",
            approved.model_copy(update={"state": "REJECTED"}),
            candidate=candidate(),
            config_hash="a" * 64,
            target_index=1,
            source_identity="phase4-fixture-v1",
            recorded_at=NOW + timedelta(seconds=10),
        )
    result = evaluate_quotes(
        candidate(),
        approved,
        instrument(),
        [quote("entry", 11, "100", "100.5"), quote("target", 30, "105", "105.5")],
        policy(),
    )
    assert ledger.record_outcome("rev-1", result, recorded_at=NOW + timedelta(minutes=4))
    assert not ledger.record_outcome("rev-1", result, recorded_at=NOW + timedelta(minutes=5))
    ledger.set_cursor("fixture", "42", now=NOW)
    ledger.record_gap("fixture", NOW, NOW + timedelta(minutes=1), "fixture outage")
    assert PaperLedger(tmp_path / "paper.sqlite3").cursor("fixture") == "42"
    assert PaperLedger(tmp_path / "paper.sqlite3").summary()["explicit_gaps"] == 1


def test_paper_ledger_rejects_outcome_without_prospective_decision(tmp_path) -> None:
    result = evaluate_quotes(
        candidate(),
        decision(),
        instrument(),
        [quote("entry", 11, "100", "100.5"), quote("target", 30, "105", "105.5")],
        policy(),
    )
    with pytest.raises(ValueError, match="before its outcome"):
        PaperLedger(tmp_path / "paper.sqlite3").record_outcome("rev-1", result)


def test_authenticated_research_summary_has_honest_empty_states(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "production.sqlite3",
        research_database_path=tmp_path / "research.sqlite3",
        paper_database_path=tmp_path / "paper.sqlite3",
        operator_username="operator",
        operator_password="secret",
    )
    client = TestClient(create_app(settings, Store(settings.database_path)))
    assert client.get("/api/research/summary").status_code == 401
    response = client.get("/api/research/summary", auth=("operator", "secret"))
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_STARTED"
    assert response.json()["paper"]["status"] == "NOT_STARTED"
    assert response.json()["external_calls_performed"] is None
    assert response.json()["counter_scope"] == "NOT_MEASURED"
