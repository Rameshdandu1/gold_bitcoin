from datetime import timedelta

from fastapi.testclient import TestClient
from test_phase3_consensus import analysis_fixture, approvals, eligibility, persist_candidate

from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.consensus import decide_v2
from marketintel.models import SignalState
from marketintel.notifications import (
    AlertWorker,
    DeliveryAcceptedUnknown,
    SlackTransientError,
)
from marketintel.quantitative import lifecycle_event
from marketintel.storage import Store


def authenticated_service(tmp_path):
    settings = Settings(
        database_path=tmp_path / "service.sqlite3",
        operator_username="operator",
        operator_password="fixture-password",
    )
    store = Store(settings.database_path)
    return TestClient(create_app(settings, store)), store


def test_operator_auth_protects_api_docs_and_readiness_but_not_liveness(tmp_path):
    client, _ = authenticated_service(tmp_path)
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/health").status_code == 401
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    auth = ("operator", "fixture-password")
    assert client.get("/api/health", auth=auth).status_code == 200
    ready = client.get("/readyz", auth=auth)
    assert ready.status_code == 200
    assert ready.json()["ready"] is True


def test_cors_allows_configured_origin_and_rejects_unlisted_origin(tmp_path):
    client, _ = authenticated_service(tmp_path)
    headers = {
        "Origin": "http://127.0.0.1:5173",
        "Access-Control-Request-Method": "GET",
    }
    allowed = client.options("/api/health", headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    denied = client.options(
        "/api/health",
        headers={**headers, "Origin": "https://untrusted.example"},
    )
    assert "access-control-allow-origin" not in denied.headers


def committed_alert(store):
    candidate, analysis = analysis_fixture()
    persist_candidate(store, candidate)
    assert store.save_analysis_envelope(analysis)
    gpt, claude = approvals(analysis)
    decision = decide_v2(
        analysis,
        gpt,
        claude,
        eligibility(store, analysis),
        run_id="run-alert-fixture",
        provider_attempt_ids=("gpt-attempt", "claude-attempt"),
    )
    assert decision.status == "CONFIRMED"
    assert store.commit_consensus_decision_and_outbox(
        decision, destination_id="slack:fixture-channel"
    )
    return candidate


class FakeSlack:
    def __init__(self, outcomes=("receipt-1",)):
        self.outcomes = list(outcomes)
        self.calls = []

    async def send(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def alert_settings(tmp_path, **changes):
    values = {
        "database_path": tmp_path / "alerts.sqlite3",
        "alerts_enabled": True,
        "slack_bot_token": "fixture-secret-token",
        "slack_channel_id": "fixture-channel",
    }
    values.update(changes)
    return Settings(**values)


async def test_alert_delivery_is_durable_and_restart_does_not_duplicate(tmp_path):
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    transport = FakeSlack()
    worker = AlertWorker(store, settings, transport)
    sent_at = candidate.observed_at_utc + timedelta(minutes=1)

    assert await worker.run_once(owner="worker-a", now=sent_at)
    assert not await AlertWorker(store, settings, transport).run_once(
        owner="worker-b", now=sent_at + timedelta(seconds=1)
    )
    item = store.outbox_items()[0]
    assert item["status"] == "SENT"
    assert item["receipt_id"] == "receipt-1"
    assert len(transport.calls) == 1
    assert transport.calls[0]["token"] == "fixture-secret-token"
    assert "NO ORDER EXECUTION" in transport.calls[0]["text"]


async def test_expired_alert_is_suppressed_before_remote_delivery(tmp_path):
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    transport = FakeSlack()
    assert await AlertWorker(store, settings, transport).run_once(
        owner="worker-a", now=candidate.expires_at_utc
    )
    assert transport.calls == []
    assert store.outbox_items()[0]["status"] == "SUPPRESSED"


async def test_transient_delivery_retries_but_acceptance_without_receipt_does_not(tmp_path):
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    now = candidate.observed_at_utc + timedelta(minutes=1)
    transient = FakeSlack((SlackTransientError("fixture"), "receipt-after-retry"))
    worker = AlertWorker(store, settings, transient)
    assert await worker.run_once(owner="worker-a", now=now)
    assert store.outbox_items()[0]["status"] == "RETRY"
    assert await worker.run_once(owner="worker-b", now=now + timedelta(seconds=3))
    assert store.outbox_items()[0]["status"] == "SENT"

    second_store = Store(tmp_path / "unknown.sqlite3")
    committed_alert(second_store)
    unknown = FakeSlack((DeliveryAcceptedUnknown("fixture"),))
    unknown_settings = alert_settings(tmp_path, database_path=tmp_path / "unknown.sqlite3")
    assert await AlertWorker(second_store, unknown_settings, unknown).run_once(
        owner="worker-a", now=now
    )
    assert second_store.outbox_items()[0]["status"] == "RECEIPT_UNKNOWN"
    assert not await AlertWorker(second_store, unknown_settings, unknown).run_once(
        owner="worker-b", now=now + timedelta(minutes=1)
    )
    assert len(unknown.calls) == 1


def test_terminal_alert_has_separate_revision_and_lifecycle_identity(tmp_path):
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    terminal = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=SignalState.CANDIDATE,
        to_state=SignalState.INVALIDATED,
        occurred_at=candidate.observed_at_utc + timedelta(minutes=2),
        reason="TEST_FIXTURE_NOT_LIVE executed price breached stop",
        price_source="EXECUTED_TRADE",
        source_event_id="fixture-terminal-trade",
    )
    assert store.record_candidate_lifecycle(terminal)
    confirmation, invalidation = store.outbox_items()
    assert confirmation["event_type"] == "CONFIRMED"
    assert invalidation["event_type"] == "INVALIDATED"
    assert confirmation["delivery_key"] != invalidation["delivery_key"]
    assert invalidation["revision_id"] == confirmation["revision_id"]
    assert invalidation["payload"]["lifecycle_event_id"] == terminal.event_id


def test_consistent_backup_restore_preserves_phase3_audit_state(tmp_path):
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate = committed_alert(store)
    _, analysis = analysis_fixture()
    store.create_review_run(
        analysis,
        provider_config={"openai_model": "fixture", "anthropic_model": "fixture"},
        deadline_at=candidate.expires_at_utc,
        now=candidate.observed_at_utc,
    )
    assert store.reserve_provider_budget(
        run_id="backup-fixture-run",
        provider="OPENAI",
        attempt_number=1,
        now=candidate.observed_at_utc,
        input_tokens=100,
        output_tokens=50,
        cost_microusd=10,
        provider_call_limit=5,
        total_call_limit=10,
        total_cost_limit_microusd=100,
    )
    backup = tmp_path / "restored.sqlite3"
    store.backup_to(backup)

    restored = Store(backup)
    assert restored.recent_candidates()[0]["candidate"]["candidate_id"] == candidate.candidate_id
    assert restored.queue_status()["review_jobs"]["QUEUED"] == 1
    assert restored.budget_status(now=candidate.observed_at_utc)["reserved_calls"] == 1
    assert len(restored.outbox_items()) == 1
    assert "0003_phase3_review_pipeline" in restored.migration_ids()
    assert Store(backup).migration_ids() == restored.migration_ids()
