import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from marketintel.analysis import build_analysis_envelope, candidate_revision_id
from marketintel.models import (
    BookFeatures,
    CandidateSignal,
    CoverageWindow,
    FeatureSnapshot,
    FlowWindow,
    Instrument,
    MarketRegime,
    OrderFlowFeatures,
    VolatilityBudget,
)
from marketintel.storage import Store


def phase3_fixture(*, target: float = 2610, observed_at: datetime | None = None):
    observed_at = observed_at or datetime(2026, 11, 21, 10, 0, tzinfo=UTC)
    candidate = CandidateSignal(
        candidate_id="phase3-candidate-fixture-0001",
        snapshot_id="a" * 64,
        asset="GOLD",
        symbol="XAUTUSD",
        engine="GOLD_FAST",
        horizon_minutes=30,
        candle_close_utc=observed_at,
        observed_at_utc=observed_at,
        expires_at_utc=observed_at + timedelta(minutes=30),
        direction="BULLISH",
        trigger="TEST_FIXTURE_NOT_LIVE",
        entry=2600,
        invalidation=2590,
        targets=(target, 2620),
        feature_evidence=("TEST_FIXTURE_NOT_LIVE",),
        counter_evidence=("licensed reference unavailable",),
        source_quality="FRESH",
        rule_version="m3a-v2",
    )
    empty_window = FlowWindow(
        label="fixture",
        requested_trade_count=500,
        trade_count=500,
        classified_trade_count=500,
        unclassified_trade_count=0,
    )
    coverage = CoverageWindow(
        name="UTC_SESSION",
        required=True,
        complete=True,
        expected_start_utc=observed_at.replace(hour=0),
        expected_end_utc=observed_at,
        actual_start_utc=observed_at.replace(hour=0),
        actual_end_utc=observed_at,
        candle_count=600,
        reason="complete fixture",
    )
    snapshot = FeatureSnapshot(
        snapshot_id=candidate.snapshot_id,
        asset="GOLD",
        symbol="XAUTUSD",
        engine="GOLD_FAST",
        horizon_minutes=30,
        candle_close_utc=observed_at,
        observed_at_utc=observed_at,
        regime=MarketRegime.TRENDING,
        order_flow=OrderFlowFeatures(
            last_500=empty_window,
            last_5000=empty_window.model_copy(
                update={"requested_trade_count": 5000, "trade_count": 5000}
            ),
            last_5m=empty_window.model_copy(
                update={"requested_trade_count": None, "window_seconds": 300}
            ),
            last_15m=empty_window.model_copy(
                update={"requested_trade_count": None, "window_seconds": 900}
            ),
        ),
        book=BookFeatures(
            available=True,
            observed_at_utc=observed_at,
            best_bid=Decimal("2599.9"),
            best_ask=Decimal("2600.1"),
            spread=Decimal("0.2"),
            reason="TEST_FIXTURE_NOT_LIVE",
        ),
        volatility=VolatilityBudget(
            atr=Decimal("5"),
            projected_move=Decimal("30"),
            relative_volume=Decimal("1.2"),
            range_expansion=Decimal("1.3"),
        ),
        vwap=Decimal("2598"),
        coverage=(coverage,),
        source_quality="FRESH",
        warnings=("TEST_FIXTURE_NOT_LIVE",),
    )
    instrument = Instrument(
        product_id=131253,
        symbol="XAUTUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency="XAUT",
        tick_size=Decimal("0.01"),
        underlying_asset="XAUT",
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )
    return candidate, snapshot, instrument


def test_canonical_envelope_is_byte_stable_and_sensitive_to_material_evidence():
    candidate, snapshot, instrument = phase3_fixture()
    first = build_analysis_envelope(
        candidate,
        snapshot,
        instrument,
        evaluation_settings={"temperature": "0", "max_output_tokens": "650"},
    )
    reordered = build_analysis_envelope(
        candidate,
        snapshot,
        instrument,
        evaluation_settings={"max_output_tokens": "650", "temperature": "0"},
    )
    changed_candidate, changed_snapshot, changed_instrument = phase3_fixture(target=2611)
    changed = build_analysis_envelope(changed_candidate, changed_snapshot, changed_instrument)

    assert first.canonical_bytes == reordered.canonical_bytes
    assert first.digest == reordered.digest
    assert changed.digest != first.digest
    assert changed.envelope.candidate_revision_id != first.envelope.candidate_revision_id


def test_nested_candidate_and_envelope_values_are_immutable():
    candidate, snapshot, instrument = phase3_fixture()
    analysis = build_analysis_envelope(candidate, snapshot, instrument)
    with pytest.raises(TypeError):
        candidate.targets[0] = 9999  # type: ignore[index]
    with pytest.raises(ValidationError):
        analysis.envelope.feature_snapshot.coverage[0].complete = False


def test_envelope_store_rejects_same_digest_with_different_bytes(tmp_path):
    candidate, snapshot, instrument = phase3_fixture()
    analysis = build_analysis_envelope(candidate, snapshot, instrument)
    store = Store(tmp_path / "phase3.sqlite3")
    assert store.save_analysis_envelope(analysis)
    assert not store.save_analysis_envelope(analysis)
    conflicting = analysis.model_copy(update={"canonical_bytes": b"different"})
    with pytest.raises(ValueError, match="Conflicting"):
        store.save_analysis_envelope(conflicting)


def test_review_job_claim_is_single_winner_and_stale_worker_is_fenced(tmp_path):
    candidate, snapshot, instrument = phase3_fixture()
    analysis = build_analysis_envelope(candidate, snapshot, instrument)
    store = Store(tmp_path / "phase3.sqlite3")
    now = candidate.observed_at_utc
    store.create_review_run(
        analysis,
        provider_config={"openai_model": "fixture-openai", "anthropic_model": "fixture-claude"},
        now=now,
        deadline_at=now + timedelta(minutes=5),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda owner: store.claim_review_job(owner, now=now, lease_seconds=10),
                ("worker-a", "worker-b"),
            )
        )
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    first = winners[0]
    second = store.claim_review_job("worker-c", now=now + timedelta(seconds=11), lease_seconds=10)
    assert second is not None and second["generation"] == first["generation"] + 1
    assert not store.complete_review_job(
        first["job_id"],
        owner=first["owner"],
        generation=first["generation"],
        status="COMPLETED",
        now=now + timedelta(seconds=12),
    )


def test_budget_reservation_is_atomic_across_workers_and_utc_day(tmp_path):
    store = Store(tmp_path / "phase3.sqlite3")
    now = datetime(2026, 11, 21, 23, 59, tzinfo=UTC)

    def reserve(attempt):
        return store.reserve_provider_budget(
            run_id=f"run-{attempt}",
            provider="OPENAI",
            attempt_number=1,
            now=now,
            input_tokens=1_000,
            output_tokens=500,
            cost_microusd=5_000,
            provider_call_limit=1,
            total_call_limit=1,
            total_cost_limit_microusd=5_000,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, (1, 2)))
    assert sum(value is not None for value in outcomes) == 1
    assert store.reserve_provider_budget(
        run_id="run-next-day",
        provider="OPENAI",
        attempt_number=1,
        now=now + timedelta(minutes=2),
        input_tokens=1_000,
        output_tokens=500,
        cost_microusd=5_000,
        provider_call_limit=1,
        total_call_limit=1,
        total_cost_limit_microusd=5_000,
    )


def test_existing_candidate_database_migrates_once_and_preserves_revision(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    candidate, _, _ = phase3_fixture()
    with sqlite3.connect(database) as conn:
        conn.executescript("""
            CREATE TABLE candidates (
                candidate_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL,
                asset TEXT NOT NULL, horizon_minutes INTEGER NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE candidate_revisions (
                candidate_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
                observed_at_utc TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (candidate_id, snapshot_id)
            );
        """)
        payload = candidate.model_copy(update={"schema_version": "1"}).model_dump_json()
        values = (
            candidate.candidate_id,
            candidate.observed_at_utc.isoformat(),
            candidate.symbol,
            candidate.asset,
            candidate.horizon_minutes,
            payload,
        )
        conn.execute("INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?)", values)
        conn.execute(
            "INSERT INTO candidate_revisions VALUES (?, ?, ?, ?)",
            (
                candidate.candidate_id,
                candidate.snapshot_id,
                candidate.observed_at_utc.isoformat(),
                payload,
            ),
        )

    first = Store(database)
    second = Store(database)
    assert first.active_candidate_revision(
        candidate.candidate_id
    ) == second.active_candidate_revision(candidate.candidate_id)
    assert first.active_candidate_revision(candidate.candidate_id)["revision_id"] == (
        candidate_revision_id(candidate.model_copy(update={"schema_version": "1"}))
    )
    with sqlite3.connect(database) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM schema_migrations "
                "WHERE migration_id='0003_phase3_review_pipeline'"
            ).fetchone()[0]
            == 1
        )
