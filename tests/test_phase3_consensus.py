from datetime import UTC, datetime, timedelta
from decimal import Decimal

from test_phase3_ai import valid_assessment
from test_phase3_analysis_storage import phase3_fixture

from marketintel.analysis import build_analysis_envelope
from marketintel.consensus import decide_v2
from marketintel.models import SignalState
from marketintel.quantitative import lifecycle_event
from marketintel.review import EligibilitySnapshot, ProviderResult, TokenUsage
from marketintel.storage import Store


def analysis_fixture():
    candidate, snapshot, instrument = phase3_fixture()
    return candidate, build_analysis_envelope(candidate, snapshot, instrument)


def btc_analysis_fixture():
    candidate, snapshot, instrument = phase3_fixture()
    candidate = candidate.model_copy(
        update={
            "candidate_id": "phase3-btc-fixture-0000001",
            "snapshot_id": "b" * 64,
            "asset": "BTC",
            "symbol": "BTCUSD",
            "engine": "BTC_FAST",
            "entry": 70_000,
            "invalidation": 69_000,
            "targets": (71_000, 72_000),
        }
    )
    snapshot = snapshot.model_copy(
        update={
            "snapshot_id": candidate.snapshot_id,
            "asset": "BTC",
            "symbol": "BTCUSD",
            "engine": "BTC_FAST",
            "book": snapshot.book.model_copy(
                update={
                    "best_bid": Decimal("69999"),
                    "best_ask": Decimal("70001"),
                    "spread": Decimal("2"),
                }
            ),
            "vwap": Decimal("69800"),
        }
    )
    instrument = instrument.model_copy(
        update={
            "product_id": 27,
            "symbol": "BTCUSD",
            "contract_value": Decimal("0.001"),
            "contract_unit_currency": "BTC",
            "underlying_asset": "BTC",
        }
    )
    return candidate, build_analysis_envelope(candidate, snapshot, instrument)


def provider_result(provider, assessment, *, status="SUCCEEDED"):
    now = assessment and datetime(2026, 11, 21, 10, 0, tzinfo=UTC) or datetime.now(UTC)
    return ProviderResult(
        provider=provider,
        status=status,
        requested_model=f"fixture-{provider.lower()}",
        returned_model=f"fixture-{provider.lower()}" if status == "SUCCEEDED" else None,
        sdk_version="fixture",
        started_at_utc=now,
        completed_at_utc=now + timedelta(milliseconds=20),
        latency_ms=20,
        attempt_number=1,
        finish_reason="completed" if status == "SUCCEEDED" else None,
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        failure_code=None if status == "SUCCEEDED" else status,
        assessment=assessment if status == "SUCCEEDED" else None,
    )


def persist_candidate(store, candidate):
    initial = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE",
    )
    assert store.add_candidate_with_lifecycle(candidate, initial)


def eligibility(store, analysis, **changes):
    token, evidence = store.eligibility_token(analysis.envelope.candidate_id)
    values = {
        "candidate_id": analysis.envelope.candidate_id,
        "candidate_revision_id": analysis.envelope.candidate_revision_id,
        "eligibility_token": token,
        "active_revision_generation": evidence["generation"],
        "lifecycle_state": evidence["lifecycle"][1],
        "evaluated_at_utc": analysis.envelope.observed_at_utc + timedelta(minutes=1),
        "latest_trade_price": "2600",
        "latest_trade_at_utc": analysis.envelope.observed_at_utc + timedelta(seconds=30),
        "best_bid": "2599.9",
        "best_ask": "2600.1",
        "book_observed_at_utc": analysis.envelope.observed_at_utc + timedelta(seconds=30),
        "discovery_current": True,
        "reconciliation_current": True,
        "trade_stream_current": True,
        "book_current": True,
        "stop_breached": False,
        "target_crossed_indices": (),
        "event_order_ambiguous": False,
        "required_costs_known": True,
        "fee_bps": "1",
        "slippage_bps": "1",
        "maximum_entry_drift_bps": "10",
        "maximum_spread_bps": "10",
        "minimum_net_reward_risk": "1.2",
        "calendar_policy": "TOKEN_MARKET_ONLY",
        "notification_ready": True,
    }
    values.update(changes)
    return EligibilitySnapshot(**values)


def approvals(analysis, *, indices=(2,)):
    assessment = valid_assessment(analysis, supported_target_indices=indices)
    return (
        provider_result("OPENAI", assessment),
        provider_result("ANTHROPIC", assessment),
    )


def test_positive_consensus_commits_one_revision_scoped_outbox_intent(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "phase3.sqlite3")
    persist_candidate(store, candidate)
    assert store.save_analysis_envelope(analysis)
    gpt, claude = approvals(analysis)
    decision = decide_v2(
        analysis,
        gpt,
        claude,
        eligibility(store, analysis),
        run_id="run-positive",
        provider_attempt_ids=("openai-attempt", "anthropic-attempt"),
    )
    assert decision.status == "CONFIRMED"
    assert decision.supported_target_indices == (2,)
    assert store.commit_consensus_decision_and_outbox(
        decision, destination_id="telegram:fixture-operator"
    )
    assert store.commit_consensus_decision_and_outbox(
        decision, destination_id="telegram:fixture-operator"
    )
    assert len(store.outbox_items()) == 1
    assert store.outbox_items()[0]["revision_id"] == analysis.envelope.candidate_revision_id


def test_provider_timeout_or_valid_rejection_never_confirms(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "phase3.sqlite3")
    persist_candidate(store, candidate)
    approval = valid_assessment(analysis, supported_target_indices=(2,))
    timeout = provider_result("ANTHROPIC", None, status="TIMEOUT")
    wait = decide_v2(
        analysis,
        provider_result("OPENAI", approval),
        timeout,
        eligibility(store, analysis),
        run_id="run-timeout",
        provider_attempt_ids=("a", "b"),
    )
    assert wait.status == "WAIT"

    rejection = valid_assessment(
        analysis,
        decision="REJECT",
        supported_target_indices=(),
        agrees_with_invalidation=False,
    )
    rejected = decide_v2(
        analysis,
        provider_result("OPENAI", approval),
        provider_result("ANTHROPIC", rejection),
        eligibility(store, analysis),
        run_id="run-reject",
        provider_attempt_ids=("a", "b"),
    )
    assert rejected.status == "REJECTED"


def test_hypothetical_btc_fixture_confirms_only_fresh_shared_feasible_target(tmp_path):
    candidate, analysis = btc_analysis_fixture()
    store = Store(tmp_path / "btc-phase3.sqlite3")
    persist_candidate(store, candidate)
    assert store.save_analysis_envelope(analysis)
    gpt, claude = approvals(analysis, indices=(2,))
    current = eligibility(
        store,
        analysis,
        latest_trade_price="70000",
        best_bid="69999",
        best_ask="70001",
    )
    decision = decide_v2(
        analysis,
        gpt,
        claude,
        current,
        run_id="run-btc-positive-fixture",
        provider_attempt_ids=("openai-btc", "anthropic-btc"),
    )
    assert decision.status == "CONFIRMED"
    assert decision.supported_target_indices == (2,)
    assert store.commit_consensus_decision_and_outbox(
        decision, destination_id="slack:fixture-operator"
    )


def test_expiry_equality_stop_breach_spread_and_exhausted_target_fail_closed(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "phase3.sqlite3")
    persist_candidate(store, candidate)
    gpt, claude = approvals(analysis)
    cases = (
        eligibility(store, analysis, evaluated_at_utc=analysis.envelope.expires_at_utc),
        eligibility(store, analysis, stop_breached=True),
        eligibility(store, analysis, best_bid="2590", best_ask="2610"),
        eligibility(store, analysis, target_crossed_indices=(2,)),
        eligibility(store, analysis, event_order_ambiguous=True),
    )
    for index, current in enumerate(cases):
        result = decide_v2(
            analysis,
            gpt,
            claude,
            current,
            run_id=f"run-negative-{index}",
            provider_attempt_ids=("a", "b"),
        )
        assert result.status == "WAIT"


def test_commit_race_after_invalidation_creates_no_decision_or_alert(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "phase3.sqlite3")
    persist_candidate(store, candidate)
    current = eligibility(store, analysis)
    gpt, claude = approvals(analysis)
    decision = decide_v2(
        analysis,
        gpt,
        claude,
        current,
        run_id="run-race",
        provider_attempt_ids=("a", "b"),
    )
    terminal = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=SignalState.CANDIDATE,
        to_state=SignalState.INVALIDATED,
        occurred_at=current.evaluated_at_utc + timedelta(seconds=1),
        reason="TEST_FIXTURE_NOT_LIVE stop breach before commit",
        price_source="EXECUTED_TRADE",
        source_event_id="fixture-breach",
    )
    assert store.record_candidate_lifecycle(terminal)
    assert not store.commit_consensus_decision_and_outbox(
        decision, destination_id="telegram:fixture-operator"
    )
    assert store.consensus_decision_v2("run-race") is None
    assert store.outbox_items() == []


def test_new_revision_never_inherits_old_revision_approval(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "phase3.sqlite3")
    persist_candidate(store, candidate)
    old_eligibility = eligibility(store, analysis)
    gpt, claude = approvals(analysis)
    old_decision = decide_v2(
        analysis,
        gpt,
        claude,
        old_eligibility,
        run_id="run-old-revision",
        provider_attempt_ids=("a", "b"),
    )

    revised = candidate.model_copy(
        update={
            "snapshot_id": "b" * 64,
            "observed_at_utc": candidate.observed_at_utc + timedelta(seconds=1),
            "targets": (2611.0, 2621.0),
        }
    )
    assert not store.add_candidate(revised)
    assert store.active_candidate_revision(candidate.candidate_id)["revision_id"] != (
        analysis.envelope.candidate_revision_id
    )
    assert not store.commit_consensus_decision_and_outbox(
        old_decision, destination_id="telegram:fixture-operator"
    )
    assert store.outbox_items() == []
