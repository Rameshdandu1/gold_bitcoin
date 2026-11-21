import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_phase3_ai import SequenceTransport, review_settings, valid_assessment
from test_phase3_analysis_storage import phase3_fixture
from test_phase3_consensus import analysis_fixture, approvals, eligibility, persist_candidate
from test_phase3_service_alerts import FakeSlack, alert_settings, committed_alert

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, TransportReply
from marketintel.analysis import build_analysis_envelope, material_proposal_digest
from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.consensus import decide_v2
from marketintel.delta import parse_trade_message
from marketintel.detectors import EngineConfig
from marketintel.features import structure_events
from marketintel.models import Candle, Direction, StructureKind
from marketintel.notifications import AlertWorker
from marketintel.orchestration import ReviewOrchestrator
from marketintel.quantitative import lifecycle_event
from marketintel.review import TokenUsage
from marketintel.review_worker import ReviewWorker, current_eligibility
from marketintel.storage import Store
from marketintel.worker import poll_closed_candles


def trade_event(
    *, symbol: str, event_at: datetime, received_at: datetime, price: str, sequence: int
):
    event_micros = int(event_at.timestamp() * 1_000_000)
    message = {
        "type": "trades",
        "sy": symbol,
        "p": price,
        "s": "1",
        "r": "t",
        "t": event_micros,
        "ts": event_micros + sequence,
    }
    return parse_trade_message(message, received_at=received_at)[0]


def test_p3_01_fresh_environment_template_starts_with_missing_optional_rates():
    settings = Settings(_env_file=".env.example")

    assert settings.live_ingestion_enabled is False
    assert settings.ai_enabled is False
    assert settings.alerts_enabled is False
    assert settings.trading_enabled is False
    assert settings.openai_input_microusd_per_million_tokens is None
    assert settings.anthropic_output_microusd_per_million_tokens is None


@pytest.mark.asyncio
async def test_p3_02_non_aligned_poll_reconciles_every_complete_minute(tmp_path, monkeypatch):
    decision_now = datetime(2026, 11, 21, 11, 5, 30, 123456, tzinfo=UTC)
    first_open = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)
    candles = []
    store = Store(tmp_path / "market.sqlite3")
    store.record_source_status(
        "delta_websocket",
        "CONNECTED",
        "TEST_FIXTURE_NOT_LIVE",
        occurred_at=first_open - timedelta(seconds=1),
    )
    for index in range(65):
        open_time = first_open + timedelta(minutes=index)
        candles.append(
            Candle(
                symbol="BTCUSD",
                resolution="1m",
                open_time=open_time,
                open=100,
                high=100,
                low=100,
                close=100,
                volume_contracts=1,
                available_at_utc=open_time + timedelta(minutes=1, seconds=1),
            )
        )
        store.append_raw_event(
            trade_event(
                symbol="BTCUSD",
                event_at=open_time + timedelta(seconds=5),
                received_at=open_time + timedelta(seconds=5, milliseconds=1),
                price="100",
                sequence=index + 1,
            )
        )

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return decision_now if tz is not None else decision_now.replace(tzinfo=None)

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return candles

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("marketintel.worker.datetime", FrozenDateTime)
    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (EngineConfig("BTC", "1m", 30),))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)

    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(
            Settings(database_path=tmp_path / "market.sqlite3"), store, {"BTC": "BTCUSD"}
        )

    status = store.source_status_history("candle_reconciliation:BTCUSD")[-1]
    assert status["state"] == "VALID"
    assert "matched=65" in status["detail"]


@pytest.mark.asyncio
async def test_p3_02_matching_partial_minute_remains_ineligible(tmp_path, monkeypatch):
    decision_now = datetime(2026, 11, 21, 11, 5, 30, tzinfo=UTC)
    open_time = datetime(2026, 11, 21, 11, 4, tzinfo=UTC)
    store = Store(tmp_path / "partial.sqlite3")
    store.record_source_status(
        "delta_websocket",
        "CONNECTED",
        "TEST_FIXTURE_NOT_LIVE collector started halfway through bucket",
        occurred_at=open_time + timedelta(seconds=30),
    )
    store.append_raw_event(
        trade_event(
            symbol="BTCUSD",
            event_at=open_time + timedelta(seconds=35),
            received_at=open_time + timedelta(seconds=35, milliseconds=1),
            price="100",
            sequence=1,
        )
    )
    candle = Candle(
        symbol="BTCUSD",
        resolution="1m",
        open_time=open_time,
        open=100,
        high=100,
        low=100,
        close=100,
        volume_contracts=1,
        available_at_utc=open_time + timedelta(minutes=1, seconds=1),
    )

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return decision_now if tz is not None else decision_now.replace(tzinfo=None)

    class FakeREST:
        def __init__(self, _url):
            pass

        async def historical_candles(self, *_args, **_kwargs):
            return [candle]

    async def stop_after_iteration(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("marketintel.worker.datetime", FrozenDateTime)
    monkeypatch.setattr("marketintel.worker.DeltaREST", FakeREST)
    monkeypatch.setattr("marketintel.worker.ENGINE_CONFIGS", (EngineConfig("BTC", "1m", 30),))
    monkeypatch.setattr("marketintel.worker.asyncio.sleep", stop_after_iteration)
    with pytest.raises(asyncio.CancelledError):
        await poll_closed_candles(
            Settings(database_path=tmp_path / "partial.sqlite3"), store, {"BTC": "BTCUSD"}
        )

    status = store.source_status_history("candle_reconciliation:BTCUSD")[-1]
    assert status["state"] == "WAIT"
    assert "coverage is incomplete" in status["detail"]


@pytest.mark.asyncio
async def test_p3_03_provider_can_echo_digest_using_only_request_visible_fields():
    _, analysis = analysis_fixture()

    class RequestOnlyTransport:
        async def __call__(self, request_bytes, **_kwargs):
            request = json.loads(request_bytes)
            envelope = request["analysis_input"]
            assessment = valid_assessment(analysis).model_copy(
                update={
                    "candidate_id": envelope["candidate_id"],
                    "candidate_revision_id": envelope["candidate_revision_id"],
                    "snapshot_id": envelope["snapshot_id"],
                    "analysis_input_hash": request["analysis_input_hash"],
                }
            )
            return TransportReply(
                parsed=assessment,
                returned_model="fixture-openai",
                finish_reason="completed",
                usage=TokenUsage(input_tokens=100, output_tokens=50),
            )

    settings = Settings(
        ai_enabled=True,
        openai_api_key="fixture-key",
        openai_model="fixture-openai",
    )
    result = await GPTAnalyst(settings, RequestOnlyTransport()).review(
        analysis, deadline_at=datetime.now(UTC) + timedelta(seconds=5)
    )

    assert result.status == "SUCCEEDED"
    assert result.assessment is not None
    assert result.assessment.analysis_input_hash == analysis.digest


def test_p3_05_older_timestamp_trade_insert_changes_commit_generation(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "phase4.sqlite3")
    persist_candidate(store, candidate)
    store.save_analysis_envelope(analysis)
    safe_at = candidate.observed_at_utc + timedelta(seconds=30)
    assert store.append_raw_event(
        trade_event(
            symbol=candidate.symbol,
            event_at=safe_at,
            received_at=safe_at,
            price="2600",
            sequence=1,
        )
    )
    current = eligibility(store, analysis)
    gpt, claude = approvals(analysis)
    decision = decide_v2(
        analysis,
        gpt,
        claude,
        current,
        run_id="phase4-race-regression",
        provider_attempt_ids=("openai-attempt", "anthropic-attempt"),
    )
    assert decision.status == "CONFIRMED"

    older = candidate.observed_at_utc + timedelta(seconds=20)
    assert store.append_raw_event(
        trade_event(
            symbol=candidate.symbol,
            event_at=older,
            received_at=older,
            price="2589",
            sequence=2,
        )
    )

    assert not store.commit_consensus_decision_and_outbox(
        decision, destination_id="slack:fixture-channel"
    )
    assert store.outbox_items() == []


def structure_fixture(values):
    start = datetime(2026, 11, 21, tzinfo=UTC)
    return [
        Candle(
            symbol="XAUTUSD",
            resolution="1m",
            open_time=start + timedelta(minutes=index),
            open=value,
            high=value + 0.5,
            low=value - 0.5,
            close=value,
            volume_contracts=1,
        )
        for index, value in enumerate(values)
    ]


@pytest.mark.parametrize(
    (
        "values",
        "continuation_direction",
        "continuation_level",
        "reversal_direction",
        "reversal_level",
    ),
    [
        (
            [
                100,
                101,
                110,
                105,
                95,
                100,
                115,
                105,
                98,
                104,
                108,
                100,
                90,
                95,
                103,
                95,
                85,
                90,
                99,
                90,
                80,
                85,
                90,
                101,
            ],
            Direction.BEARISH,
            84.5,
            Direction.BULLISH,
            99.5,
        ),
        (
            [
                100,
                99,
                90,
                95,
                105,
                100,
                85,
                95,
                102,
                96,
                92,
                100,
                110,
                105,
                97,
                105,
                115,
                110,
                101,
                110,
                120,
                115,
                110,
                99,
            ],
            Direction.BULLISH,
            115.5,
            Direction.BEARISH,
            100.5,
        ),
    ],
)
def test_p3_10_latest_confirmed_structure_drives_continuation_and_reversal(
    values, continuation_direction, continuation_level, reversal_direction, reversal_level
):
    events = structure_events(structure_fixture(values))
    continuation = [
        event
        for event in events
        if event.direction is continuation_direction
        and float(event.level) == continuation_level
        and event.kind in {StructureKind.BOS, StructureKind.CHOCH}
    ][-1]
    reversal = [
        event
        for event in events
        if event.direction is reversal_direction
        and float(event.level) == reversal_level
        and event.kind in {StructureKind.BOS, StructureKind.CHOCH}
    ][-1]
    assert continuation.kind is StructureKind.BOS
    assert reversal.kind is StructureKind.CHOCH


def test_non_ascii_basic_credentials_never_raise_internal_server_error(tmp_path):
    settings = Settings(
        database_path=tmp_path / "auth.sqlite3",
        operator_username="operátor",
        operator_password="pässword",
    )
    client = TestClient(create_app(settings, Store(settings.database_path)))

    assert client.get("/api/health", auth=("operátor", "pässword")).status_code == 200
    assert client.get("/api/health", auth=("operátor", "wrong")).status_code == 401


@pytest.mark.asyncio
async def test_p3_09_failed_provider_finish_status_cannot_approve():
    _, analysis = analysis_fixture()
    settings = Settings(
        ai_enabled=True,
        openai_api_key="fixture-key",
        openai_model="fixture-openai",
    )

    class FailedFinishTransport:
        async def __call__(self, _request_bytes, **_kwargs):
            return TransportReply(
                parsed=valid_assessment(analysis),
                returned_model="fixture-openai",
                finish_reason="failed",
                usage=TokenUsage(input_tokens=100, output_tokens=50),
            )

    result = await GPTAnalyst(settings, FailedFinishTransport()).review(
        analysis, deadline_at=datetime.now(UTC) + timedelta(seconds=5)
    )

    assert result.status == "INVALID_FINISH_STATUS"
    assert result.assessment is None


@pytest.mark.asyncio
async def test_p3_09_queued_model_identity_mismatch_makes_zero_calls(tmp_path):
    _, analysis = analysis_fixture()
    settings = review_settings()
    store = Store(tmp_path / "model-identity.sqlite3")
    now = datetime.now(UTC)
    run_id = store.create_review_run(
        analysis,
        provider_config={
            "openai_model": "queued-old-openai",
            "anthropic_model": "queued-old-anthropic",
        },
        now=now,
        deadline_at=now + timedelta(seconds=30),
    )
    claim = store.claim_review_job("fixture-worker", now=now, lease_seconds=30)
    assert claim is not None
    gpt_transport = SequenceTransport("fixture-openai", [valid_assessment(analysis)])
    claude_transport = SequenceTransport("fixture-anthropic", [valid_assessment(analysis)])

    results = await ReviewOrchestrator(
        store,
        settings,
        GPTAnalyst(settings, gpt_transport),
        ClaudeAnalyst(settings, claude_transport),
    ).execute(analysis, run_id=run_id, claim=claim)

    assert {item.failure_code for item in results} == {"QUEUED_PROVIDER_CONFIGURATION_MISMATCH"}
    assert gpt_transport.calls == claude_transport.calls == 0


@pytest.mark.asyncio
async def test_p3_07_complete_oversized_request_makes_zero_provider_calls(tmp_path):
    _, analysis = analysis_fixture()
    settings = review_settings(ai_max_input_tokens=1_000)
    store = Store(tmp_path / "input-bound.sqlite3")
    now = datetime.now(UTC)
    run_id = store.create_review_run(
        analysis,
        provider_config={
            "openai_model": settings.openai_model,
            "anthropic_model": settings.anthropic_model,
        },
        now=now,
        deadline_at=now + timedelta(seconds=30),
    )
    claim = store.claim_review_job("fixture-worker", now=now, lease_seconds=30)
    assert claim is not None
    gpt_transport = SequenceTransport("fixture-openai", [valid_assessment(analysis)])
    claude_transport = SequenceTransport("fixture-anthropic", [valid_assessment(analysis)])

    results = await ReviewOrchestrator(
        store,
        settings,
        GPTAnalyst(settings, gpt_transport),
        ClaudeAnalyst(settings, claude_transport),
    ).execute(analysis, run_id=run_id, claim=claim)

    assert all(item.failure_code == "COMPLETE_REQUEST_INPUT_LIMIT_EXCEEDED" for item in results)
    assert gpt_transport.calls == claude_transport.calls == 0
    assert store.budget_status(now=now)["reserved_calls"] == 0


def test_p3_07_actual_overspend_reduces_subsequent_budget_headroom(tmp_path):
    store = Store(tmp_path / "budget.sqlite3")
    now = datetime(2026, 11, 21, tzinfo=UTC)
    reservation = store.reserve_provider_budget(
        run_id="first-run",
        provider="OPENAI",
        attempt_number=1,
        now=now,
        input_tokens=100,
        output_tokens=50,
        cost_microusd=100,
        provider_call_limit=10,
        total_call_limit=10,
        total_cost_limit_microusd=5_000,
    )
    assert reservation is not None
    assert store.reconcile_provider_budget(
        reservation,
        input_tokens=6_000,
        output_tokens=16,
        actual_cost_microusd=6_016,
        status="RECONCILED",
        now=now + timedelta(seconds=1),
    )

    assert (
        store.reserve_provider_budget(
            run_id="second-run",
            provider="ANTHROPIC",
            attempt_number=1,
            now=now + timedelta(seconds=2),
            input_tokens=100,
            output_tokens=50,
            cost_microusd=100,
            provider_call_limit=10,
            total_call_limit=10,
            total_cost_limit_microusd=5_000,
        )
        is None
    )
    assert store.budget_status(now=now)["admission_cost_microusd"] == 6_016


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["BREACH", "DISCONNECT"])
async def test_p3_06_confirmation_delivery_rechecks_current_market(tmp_path, failure):
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    now = candidate.observed_at_utc + timedelta(minutes=1)
    if failure == "BREACH":
        breach_at = candidate.observed_at_utc + timedelta(seconds=45)
        store.append_raw_event(
            trade_event(
                symbol=candidate.symbol,
                event_at=breach_at,
                received_at=breach_at,
                price="2589",
                sequence=99,
            )
        )
    else:
        store.record_source_status(
            "delta_websocket",
            "DISCONNECTED",
            "TEST_FIXTURE_NOT_LIVE",
            occurred_at=candidate.observed_at_utc + timedelta(seconds=45),
        )
    transport = FakeSlack()

    assert await AlertWorker(store, settings, transport).run_once(owner="worker-a", now=now)
    assert transport.calls == []
    item = store.outbox_items()[0]
    assert item["status"] == "SUPPRESSED"
    assert "current confirmation gate failed" in item["last_error"]


@pytest.mark.asyncio
async def test_p3_08_destination_drift_blocks_instead_of_redirecting(tmp_path):
    original = alert_settings(tmp_path)
    store = Store(original.database_path)
    candidate = committed_alert(store)
    changed = alert_settings(tmp_path, slack_channel_id="different-channel")
    transport = FakeSlack()

    assert await AlertWorker(store, changed, transport).run_once(
        owner="worker-a", now=candidate.observed_at_utc + timedelta(minutes=1)
    )
    assert transport.calls == []
    item = store.outbox_items()[0]
    assert item["status"] == "SUPPRESSED"
    assert "immutable destination" in item["last_error"]


@pytest.mark.asyncio
async def test_p3_08_dispatch_started_crash_is_not_blindly_replayed(tmp_path):
    settings = alert_settings(tmp_path, alert_lease_seconds=5)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    now = candidate.observed_at_utc + timedelta(minutes=1)

    class AcceptedThenCancelled:
        def __init__(self):
            self.calls = 0

        async def send(self, **_kwargs):
            self.calls += 1
            raise asyncio.CancelledError

    transport = AcceptedThenCancelled()
    with pytest.raises(asyncio.CancelledError):
        await AlertWorker(store, settings, transport).run_once(owner="worker-a", now=now)

    assert store.outbox_items()[0]["status"] == "DISPATCH_STARTED"
    assert not await AlertWorker(store, settings, transport).run_once(
        owner="worker-b", now=now + timedelta(seconds=10)
    )
    assert transport.calls == 1


def review_lifecycle(candidate):
    from marketintel.models import SignalState

    return lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE",
    )


def test_p3_04_time_only_observation_deduplicates_but_material_change_requeues(tmp_path):
    candidate, snapshot, instrument = phase3_fixture()
    store = Store(tmp_path / "material.sqlite3")
    now = candidate.observed_at_utc
    first = build_analysis_envelope(candidate, snapshot, instrument)
    first_state, first_run = store.admit_candidate_review(
        candidate,
        review_lifecycle(candidate),
        first,
        material_digest=material_proposal_digest(candidate, snapshot),
        provider_config={"openai_model": "gpt", "anthropic_model": "claude"},
        deadline_at=now + timedelta(minutes=5),
        now=now,
    )
    assert first_state == "CREATED"
    assert first_run is not None

    refreshed_candidate = candidate.model_copy(
        update={
            "snapshot_id": "c" * 64,
            "observed_at_utc": now + timedelta(seconds=30),
        }
    )
    refreshed_snapshot = snapshot.model_copy(
        update={
            "snapshot_id": refreshed_candidate.snapshot_id,
            "observed_at_utc": refreshed_candidate.observed_at_utc,
        }
    )
    refreshed = build_analysis_envelope(refreshed_candidate, refreshed_snapshot, instrument)
    state, run_id = store.admit_candidate_review(
        refreshed_candidate,
        review_lifecycle(refreshed_candidate),
        refreshed,
        material_digest=material_proposal_digest(refreshed_candidate, refreshed_snapshot),
        provider_config={"openai_model": "gpt", "anthropic_model": "claude"},
        deadline_at=now + timedelta(minutes=5),
        now=now + timedelta(seconds=30),
    )
    assert (state, run_id) == ("UNCHANGED", None)
    assert store.active_candidate_revision(candidate.candidate_id)["revision_id"] == (
        first.envelope.candidate_revision_id
    )
    assert store.queue_status()["review_jobs"] == {"QUEUED": 1}

    changed_candidate = refreshed_candidate.model_copy(
        update={"snapshot_id": "d" * 64, "targets": (2611.0, 2621.0)}
    )
    changed_snapshot = refreshed_snapshot.model_copy(update={"snapshot_id": "d" * 64})
    changed = build_analysis_envelope(changed_candidate, changed_snapshot, instrument)
    changed_state, changed_run = store.admit_candidate_review(
        changed_candidate,
        review_lifecycle(changed_candidate),
        changed,
        material_digest=material_proposal_digest(changed_candidate, changed_snapshot),
        provider_config={"openai_model": "gpt", "anthropic_model": "claude"},
        deadline_at=now + timedelta(minutes=5),
        now=now + timedelta(seconds=31),
    )
    assert changed_state == "SUPERSEDED"
    assert changed_run != first_run
    assert store.active_candidate_revision(candidate.candidate_id)["revision_id"] == (
        changed.envelope.candidate_revision_id
    )
    assert store.queue_status()["review_jobs"] == {"QUEUED": 1, "SUPERSEDED": 1}


def save_ready_results(store, analysis, *, now, lease_seconds=10):
    run_id = store.create_review_run(
        analysis,
        provider_config={
            "openai_model": "fixture-openai",
            "anthropic_model": "fixture-anthropic",
        },
        now=now,
        deadline_at=now + timedelta(minutes=5),
    )
    claim = store.claim_review_job("first-worker", now=now, lease_seconds=lease_seconds)
    assert claim is not None
    for result in approvals(analysis):
        assert store.save_provider_result(
            run_id=run_id,
            job_id=claim["job_id"],
            owner=claim["owner"],
            generation=claim["generation"],
            dispatch_id=f"fixture-{result.provider}",
            result=result,
        )
    assert store.mark_review_results_ready(
        claim["job_id"],
        owner=claim["owner"],
        generation=claim["generation"],
        now=now + timedelta(seconds=1),
    )
    return run_id, claim


def test_results_ready_restart_finalizes_without_provider_redispatch(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "recovery.sqlite3")
    persist_candidate(store, candidate)
    now = candidate.observed_at_utc
    run_id, first_claim = save_ready_results(store, analysis, now=now)

    recovered = store.claim_review_job(
        "recovery-worker", now=now + timedelta(seconds=11), lease_seconds=120
    )
    assert recovered is not None
    assert recovered["claimed_from_status"] == "RESULTS_READY"
    openai, anthropic = ReviewWorker._stored_results(store.provider_results(run_id))
    assert openai.status == anthropic.status == "SUCCEEDED"
    assert len(store.provider_results(run_id)) == 2
    decision = decide_v2(
        analysis,
        openai,
        anthropic,
        eligibility(store, analysis),
        run_id=run_id,
        provider_attempt_ids=tuple(item["attempt_id"] for item in store.provider_results(run_id)),
    )
    assert store.commit_consensus_decision_and_outbox(
        decision,
        destination_id="slack:fixture-channel",
        job_id=first_claim["job_id"],
        lease_owner=recovered["owner"],
        lease_generation=recovered["generation"],
        deadline_at=now + timedelta(minutes=5),
        now=now + timedelta(seconds=61),
    )
    assert store.review_job(first_claim["job_id"])["status"] == "COMPLETED"
    assert len(store.provider_results(run_id)) == 2


def test_deadline_equality_and_stale_lease_cannot_finalize(tmp_path):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "deadline.sqlite3")
    persist_candidate(store, candidate)
    now = candidate.observed_at_utc
    run_id, first = save_ready_results(store, analysis, now=now, lease_seconds=5)
    recovered = store.claim_review_job(
        "new-owner", now=now + timedelta(seconds=6), lease_seconds=30
    )
    assert recovered is not None
    openai, anthropic = ReviewWorker._stored_results(store.provider_results(run_id))
    decision = decide_v2(
        analysis,
        openai,
        anthropic,
        eligibility(store, analysis),
        run_id=run_id,
        provider_attempt_ids=tuple(item["attempt_id"] for item in store.provider_results(run_id)),
    )
    deadline = now + timedelta(seconds=20)
    assert not store.commit_consensus_decision_and_outbox(
        decision,
        destination_id="slack:fixture-channel",
        job_id=first["job_id"],
        lease_owner=first["owner"],
        lease_generation=first["generation"],
        deadline_at=deadline,
        now=now + timedelta(seconds=7),
    )
    assert not store.commit_consensus_decision_and_outbox(
        decision,
        destination_id="slack:fixture-channel",
        job_id=first["job_id"],
        lease_owner=recovered["owner"],
        lease_generation=recovered["generation"],
        deadline_at=deadline,
        now=deadline,
    )
    assert store.outbox_items() == []


def test_p3_05_insert_between_risk_read_and_token_capture_blocks_commit(tmp_path, monkeypatch):
    candidate, analysis = analysis_fixture()
    store = Store(tmp_path / "snapshot-race.sqlite3")
    persist_candidate(store, candidate)
    safe_at = candidate.observed_at_utc + timedelta(seconds=30)
    store.append_raw_event(
        trade_event(
            symbol=candidate.symbol,
            event_at=safe_at,
            received_at=safe_at,
            price="2600",
            sequence=1,
        )
    )
    original = Store._eligibility_token_in_transaction
    inserted = False

    def insert_after_snapshot_starts(conn, candidate_id):
        nonlocal inserted
        result = original(conn, candidate_id)
        if not inserted:
            inserted = True
            breach_at = candidate.observed_at_utc + timedelta(seconds=20)
            store.append_raw_event(
                trade_event(
                    symbol=candidate.symbol,
                    event_at=breach_at,
                    received_at=breach_at,
                    price="2589",
                    sequence=2,
                )
            )
        return result

    monkeypatch.setattr(
        Store, "_eligibility_token_in_transaction", staticmethod(insert_after_snapshot_starts)
    )
    current = current_eligibility(
        store,
        Settings(database_path=store.path),
        analysis,
        now=candidate.observed_at_utc + timedelta(minutes=1),
    )
    assert current.stop_breached is False
    gpt, claude = approvals(analysis)
    decision = decide_v2(
        analysis,
        gpt,
        claude,
        current.model_copy(
            update={
                "discovery_current": True,
                "reconciliation_current": True,
                "trade_stream_current": True,
                "book_current": True,
                "best_bid": "2599.9",
                "best_ask": "2600.1",
                "required_costs_known": True,
                "fee_bps": "1",
                "slippage_bps": "1",
                "notification_ready": True,
            }
        ),
        run_id="snapshot-race",
        provider_attempt_ids=("a", "b"),
    )
    assert decision.status == "CONFIRMED"
    assert not store.commit_consensus_decision_and_outbox(
        decision, destination_id="slack:fixture-channel"
    )
