from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from test_phase3_ai import SequenceTransport, review_settings, valid_assessment
from test_phase3_consensus import analysis_fixture, persist_candidate
from test_phase3_service_alerts import FakeSlack, alert_settings, committed_alert
from test_phase4_research import (
    candidate,
    config,
    decision,
    instrument,
    manifest,
    opportunity,
    policy,
    quote,
)

from marketintel.ai import ClaudeAnalyst, GPTAnalyst
from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.notifications import AlertWorker
from marketintel.orchestration import ReviewOrchestrator, frozen_provider_config
from marketintel.paper_worker import PaperWorkerConfig, run_cycle
from marketintel.research import main as research_main
from marketintel.research_engine import run_shared_workflow
from marketintel.research_evaluation import evaluate_bar_path, evaluate_quotes
from marketintel.research_fixtures import FIXTURE_NOW, generate_fixture
from marketintel.research_models import (
    DatasetManifest,
    ExperimentConfig,
    PriceBar,
    ReplayObservation,
)
from marketintel.research_replay import iter_observations, load_manifest
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


@pytest.mark.asyncio
async def test_p5_01_alert_authorization_uses_advancing_clock_and_fresh_evidence(tmp_path) -> None:
    settings = alert_settings(tmp_path, alert_lease_seconds=300)
    store = Store(settings.database_path)
    candidate_value = committed_alert(store)
    safe = candidate_value.observed_at_utc + timedelta(minutes=1)
    stale = candidate_value.observed_at_utc + timedelta(minutes=5)
    transport = FakeSlack()
    clock = AdvancingClock(safe, safe, stale, stale)

    assert await AlertWorker(store, settings, transport, clock=clock).run_once(
        owner="phase6-advancing-clock", now=safe
    )

    assert transport.calls == []
    assert store.outbox_items()[0]["status"] == "SUPPRESSED"
    assert store.dispatch_authorization(store.outbox_items()[0]["outbox_id"]) is None


def test_p5_02_delayed_quote_availability_is_the_actionable_fill_time() -> None:
    rows = [
        quote("entry", 11, "100", "100.5").model_copy(
            update={"available_at_utc": NOW + timedelta(seconds=15)}
        ),
        quote("target", 30, "105", "105.5").model_copy(
            update={"available_at_utc": NOW + timedelta(seconds=40)}
        ),
    ]

    outcome = evaluate_quotes(
        candidate(),
        decision(),
        instrument(),
        rows,
        policy().model_copy(update={"maximum_quote_gap_seconds": 120}),
    )

    assert outcome.entry_at_utc == NOW + timedelta(seconds=15)
    assert outcome.exit_at_utc == NOW + timedelta(seconds=40)


def _rewrite_fixture(
    manifest_path,
    transform,
    *,
    data_mode: str | None = None,
    extra_rows: tuple[ReplayObservation, ...] = (),
) -> DatasetManifest:
    loaded = load_manifest(manifest_path)
    source = manifest_path.parent / loaded.files[0].path
    rows = [
        ReplayObservation.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
    ]
    changed_rows = [transform(row) for row in rows] + list(extra_rows)
    with source.open("w", encoding="utf-8", newline="\n") as handle:
        for row in changed_rows:
            handle.write(row.model_dump_json() + "\n")
    changed_file = loaded.files[0].model_copy(
        update={
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "record_count": len(changed_rows),
        }
    )
    changed = loaded.model_copy(
        update={
            "files": (changed_file,),
            "data_mode": data_mode or loaded.data_mode,
            "content_hash": "0" * 64,
        }
    )
    changed = changed.model_copy(update={"content_hash": changed.canonical_content_hash()})
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(changed.model_dump_json(indent=2) + "\n")
    return changed


def test_p5_02_public_workflow_honors_provider_availability_and_rejects_mode_conflict(
    tmp_path,
) -> None:
    delayed_manifest, config_path = generate_fixture("GOLD", tmp_path / "delayed")

    def delay_provider(row: ReplayObservation) -> ReplayObservation:
        if row.kind != "PROVIDER_COMPLETION":
            return row
        return row.model_copy(
            update={"available_at_utc": row.available_at_utc + timedelta(seconds=120)}
        )

    delayed = _rewrite_fixture(delayed_manifest, delay_provider)
    database = tmp_path / "delayed.sqlite3"
    production = tmp_path / "production.sqlite3"
    assert research_main(["validate-data", "--manifest", str(delayed_manifest)]) == 0
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(delayed_manifest),
                "--config",
                str(config_path),
                "--database",
                str(database),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    rows = ResearchStore(database, production_path=production).opportunities(
        "phase5-gold-workflow-v1"
    )
    assert rows
    for row in rows:
        rules = next(arm for arm in row.arms if arm.arm == "RULES_ONLY")
        assert rules.outcome is not None and rules.outcome.code == "TARGET_BEFORE_STOP"
        for arm in row.arms:
            if arm.arm != "RULES_ONLY":
                assert arm.decision_ready_at_utc is not None
                assert arm.decision_ready_at_utc >= FIXTURE_NOW + timedelta(seconds=122)
                assert arm.outcome is not None and arm.outcome.code == "NO_ENTRY"
                assert arm.evidence_mode == "SYNTHETIC_FIXTURE"

    conflict_manifest, conflict_config = generate_fixture("BTC", tmp_path / "conflict")
    _rewrite_fixture(
        conflict_manifest,
        lambda row: row,
        data_mode="RECORDED_PROSPECTIVE_MODEL",
    )
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(conflict_manifest),
                "--config",
                str(conflict_config),
                "--database",
                str(tmp_path / "conflict.sqlite3"),
                "--production-database",
                str(production),
            ]
        )
        == 2
    )
    assert delayed.data_mode == "SYNTHETIC_FIXTURE"


def test_p5_03_source_outage_after_candidate_invalidates_shared_workflow_outcomes(
    tmp_path,
) -> None:
    manifest_path, config_path = generate_fixture("BTC", tmp_path / "fixture")
    manifest_value = load_manifest(manifest_path)
    config_value = ExperimentConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    rows = list(iter_observations(manifest_path, manifest_value))
    rows.append(
        ReplayObservation(
            observation_id="phase6-source-gap",
            kind="SOURCE_TRANSITION",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=FIXTURE_NOW + timedelta(seconds=1),
            available_at_utc=FIXTURE_NOW + timedelta(seconds=1),
            persistence_sequence=1_000_000,
            payload={"state": "GAP", "generation": 2, "reason": "fixture outage"},
        )
    )
    store = ResearchStore(tmp_path / "research.sqlite3", production_path=tmp_path / "prod.sqlite3")

    run_shared_workflow(manifest_value, config_value, rows, store)

    opportunities = store.opportunities(config_value.experiment_id)
    assert len(opportunities) == 3
    for row in opportunities:
        rules = next(arm for arm in row.arms if arm.arm == "RULES_ONLY")
        assert rules.outcome is not None
        assert rules.outcome.reason == "SOURCE_UNAVAILABLE_DURING_PRE_ENTRY_PATH"
        for arm in row.arms:
            if arm.arm == "RULES_ONLY":
                continue
            assert arm.state == "WAIT"
            assert arm.outcome is not None and arm.outcome.code == "NO_ENTRY"


@pytest.mark.parametrize("asset", ["GOLD", "BTC"])
def test_public_connected_paper_workflow_derives_all_six_engine_outcomes(tmp_path, asset) -> None:
    manifest_path, config_path = generate_fixture(asset, tmp_path / asset.lower())
    if asset == "BTC":
        _rewrite_fixture(
            manifest_path,
            lambda row: row,
            extra_rows=(
                ReplayObservation(
                    observation_id="btc-connected-paper-source-gap",
                    kind="SOURCE_TRANSITION",
                    symbol="BTCUSD",
                    venue="delta_india",
                    exchange_time_utc=FIXTURE_NOW + timedelta(seconds=10),
                    available_at_utc=FIXTURE_NOW + timedelta(seconds=10),
                    persistence_sequence=1_000_000,
                    payload={
                        "state": "GAP",
                        "generation": 2,
                        "reason": "fixture outage after entry",
                    },
                ),
            ),
        )
    research_database = tmp_path / f"{asset.lower()}-research.sqlite3"
    paper_database = tmp_path / f"{asset.lower()}-paper.sqlite3"
    production = tmp_path / "production.sqlite3"
    experiment_id = f"phase5-{asset.lower()}-workflow-v1"
    assert (
        research_main(
            [
                "run-workflow",
                "--manifest",
                str(manifest_path),
                "--config",
                str(config_path),
                "--database",
                str(research_database),
                "--production-database",
                str(production),
            ]
        )
        == 0
    )
    assert (
        research_main(
            [
                "paper-workflow",
                "--database",
                str(research_database),
                "--paper-database",
                str(paper_database),
                "--production-database",
                str(production),
                "--experiment-id",
                experiment_id,
            ]
        )
        == 0
    )

    ledger = PaperLedger(paper_database, production_path=production)
    summary = ledger.summary()
    assert summary["decisions"] == 12
    assert summary["outcomes"] == 12
    assert summary["evidence_modes"] == {"SIMULATED_PROSPECTIVE": 12}
    transitions = ledger.transitions(limit=100)
    decision_times = [
        datetime.fromisoformat(row["occurred_at_utc"])
        for row in transitions
        if row["state"] == "DECIDED"
    ]
    outcome_times = [
        datetime.fromisoformat(row["occurred_at_utc"])
        for row in transitions
        if row["state"] != "DECIDED"
    ]
    assert max(decision_times) < min(outcome_times)
    outcome_states = {row["state"] for row in transitions if row["state"] != "DECIDED"}
    if asset == "GOLD":
        assert outcome_states == {"TARGET_BEFORE_STOP"}
    else:
        assert outcome_states == {"INCOMPLETE"}


def test_p5_04_sparse_pre_entry_quotes_and_ohlc_paths_are_incomplete() -> None:
    sparse_quote = evaluate_quotes(
        candidate(),
        decision(),
        instrument(),
        [quote("isolated-target", 170, "105", "105.5")],
        policy(),
    )
    sparse_bar = evaluate_bar_path(
        candidate(),
        decision(),
        [
            PriceBar(
                event_id="isolated-target-bar",
                venue="delta_india",
                symbol="BTCUSD",
                start_utc=NOW + timedelta(seconds=160),
                end_utc=NOW + timedelta(seconds=170),
                open=Decimal("100"),
                high=Decimal("106"),
                low=Decimal("99"),
                close=Decimal("105"),
            )
        ],
    )

    assert sparse_quote.code == "INCOMPLETE"
    assert sparse_quote.reason == "PRE_ENTRY_QUOTE_COVERAGE_INCOMPLETE"
    assert sparse_bar.code == "INCOMPLETE"
    assert sparse_bar.reason == "OHLC_PATH_GAP"


def _decision_event() -> dict:
    return {
        "type": "DECISION",
        "opportunity_id": "opp-1",
        "revision_id": "rev-1",
        "candidate": candidate().model_dump(mode="json"),
        "decision": decision().model_dump(mode="json"),
        "config_hash": "a" * 64,
        "target_index": 1,
        "evidence_mode": "PROSPECTIVE",
    }


def test_p5_05_paper_duplicate_replay_file_replacement_and_transaction_rollback(
    tmp_path, monkeypatch
) -> None:
    ledger = PaperLedger(tmp_path / "direct.sqlite3")
    assert ledger.record_decision(
        "opp-1",
        "rev-1",
        decision(),
        candidate=candidate(),
        config_hash="a" * 64,
        target_index=1,
        source_identity="direct-v1",
        recorded_at=NOW + timedelta(seconds=10),
    )
    assert not ledger.record_decision(
        "opp-1",
        "rev-1",
        decision(),
        candidate=candidate(),
        config_hash="a" * 64,
        target_index=1,
        source_identity="direct-v1",
        recorded_at=NOW + timedelta(days=1),
    )

    source = tmp_path / "stream.jsonl"
    source.write_text(json.dumps(_decision_event(), default=str) + "\n", encoding="utf-8")
    worker = PaperWorkerConfig(
        enabled=True,
        ledger_path=tmp_path / "paper.sqlite3",
        production_database_path=tmp_path / "production.sqlite3",
        recorded_decisions_path=source,
        source_identity="stream-v1",
    )
    assert run_cycle(worker, now=NOW + timedelta(seconds=10))["recorded"] == 1
    source.write_text(
        source.read_text(encoding="utf-8").replace('"config_hash": "a', '"config_hash": "b', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="content changed"):
        run_cycle(worker, now=NOW + timedelta(seconds=20))

    rollback_source = tmp_path / "rollback.jsonl"
    rollback_source.write_text(json.dumps(_decision_event(), default=str) + "\n", encoding="utf-8")
    rollback_worker = worker.model_copy(
        update={
            "ledger_path": tmp_path / "rollback.sqlite3",
            "recorded_decisions_path": rollback_source,
            "source_identity": "rollback-v1",
        }
    )
    original = PaperLedger._bind_cursor_in_transaction
    calls = 0

    def interrupt_after_event(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(PaperLedger, "_bind_cursor_in_transaction", interrupt_after_event)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_cycle(rollback_worker, now=NOW + timedelta(seconds=10))
    rollback_ledger = PaperLedger(rollback_worker.ledger_path)
    assert rollback_ledger.summary()["decisions"] == 0
    assert rollback_ledger.cursor_binding("recorded_decisions")["cursor"] == 0

    outcome_value = evaluate_quotes(
        candidate(),
        decision(),
        instrument(),
        [quote("entry", 11, "100", "100.5"), quote("target", 30, "105", "105.5")],
        policy(),
    )
    outcome_source = tmp_path / "outcome-rollback.jsonl"
    outcome_source.write_text(
        "\n".join(
            (
                json.dumps(_decision_event(), default=str),
                json.dumps(
                    {
                        "type": "OUTCOME",
                        "revision_id": "rev-1",
                        "outcome": outcome_value.model_dump(mode="json"),
                    },
                    default=str,
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    outcome_worker = worker.model_copy(
        update={
            "ledger_path": tmp_path / "outcome-rollback.sqlite3",
            "recorded_decisions_path": outcome_source,
            "source_identity": "outcome-rollback-v1",
            "maximum_records_per_cycle": 1,
        }
    )
    monkeypatch.setattr(PaperLedger, "_bind_cursor_in_transaction", staticmethod(original))
    assert run_cycle(outcome_worker, now=NOW + timedelta(seconds=10))["decisions"] == 1

    outcome_calls = 0

    def interrupt_after_outcome(self, *args, **kwargs):
        nonlocal outcome_calls
        outcome_calls += 1
        if outcome_calls == 2:
            raise RuntimeError("simulated outcome interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        PaperLedger,
        "_bind_cursor_in_transaction",
        interrupt_after_outcome,
    )
    with pytest.raises(RuntimeError, match="simulated outcome interruption"):
        run_cycle(outcome_worker, now=NOW + timedelta(minutes=1))
    outcome_ledger = PaperLedger(outcome_worker.ledger_path)
    assert outcome_ledger.summary()["decisions"] == 1
    assert outcome_ledger.summary()["outcomes"] == 0
    assert outcome_ledger.cursor_binding("recorded_decisions")["cursor"] == 1


def test_p5_06_api_hides_protected_outcomes_until_final_holdout_open(tmp_path) -> None:
    holdout_start = NOW + timedelta(days=1)
    config_value = config().model_copy(update={"holdout_start_utc": holdout_start})
    database = tmp_path / "research.sqlite3"
    production = tmp_path / "production.sqlite3"
    store = ResearchStore(database, production_path=production)
    store.create_experiment(manifest(), config_value)
    store.save_opportunity(
        config_value.experiment_id,
        opportunity("development", NOW, NOW + timedelta(hours=1)),
    )
    store.save_opportunity(
        config_value.experiment_id,
        opportunity("crossing", NOW, holdout_start + timedelta(hours=1)),
    )
    store.save_opportunity(
        config_value.experiment_id,
        opportunity(
            "protected",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1, hours=1),
        ),
    )
    settings = Settings(
        database_path=production,
        research_database_path=database,
        paper_database_path=tmp_path / "paper.sqlite3",
        operator_username="operator",
        operator_password="secret",
    )
    client = TestClient(create_app(settings, Store(production)))
    path = f"/api/research/experiments/{config_value.experiment_id}/opportunities"

    before = client.get(path, auth=("operator", "secret"))
    assert [row["opportunity_id"] for row in before.json()] == ["development"]
    report = tmp_path / "report"
    assert (
        research_main(
            [
                "report",
                "--database",
                str(database),
                "--production-database",
                str(production),
                "--experiment-id",
                config_value.experiment_id,
                "--output",
                str(report),
            ]
        )
        == 0
    )
    exported = "\n".join(
        path.read_text(encoding="utf-8")
        for path in report.iterdir()
        if path.suffix in {".json", ".jsonl", ".md", ".html", ".csv"}
    )
    assert "development" in exported
    assert "crossing" not in exported
    assert "protected" not in exported
    assert (
        research_main(
            [
                "final-holdout",
                "--database",
                str(database),
                "--production-database",
                str(production),
                "--experiment-id",
                config_value.experiment_id,
                "--acknowledge-protected-holdout",
                "FINAL_EVALUATION",
            ]
        )
        == 0
    )
    after = client.get(path, auth=("operator", "secret"))
    assert {row["opportunity_id"] for row in after.json()} == {
        "development",
        "crossing",
        "protected",
    }


@pytest.mark.asyncio
async def test_p5_07_legacy_request_configuration_makes_zero_provider_calls(tmp_path) -> None:
    candidate_value, analysis = analysis_fixture()
    settings = review_settings()
    store = Store(tmp_path / "legacy.sqlite3")
    persist_candidate(store, candidate_value)
    now = candidate_value.observed_at_utc
    legacy = frozen_provider_config(settings, analysis)
    legacy.pop("request_config_version")
    run_id = store.create_review_run(
        analysis,
        provider_config=legacy,
        now=now,
        deadline_at=now + timedelta(seconds=90),
    )
    claim = store.claim_review_job("phase6-legacy", now=now, lease_seconds=120)
    assert claim is not None
    gpt_transport = SequenceTransport("fixture-openai", [valid_assessment(analysis)])
    claude_transport = SequenceTransport("fixture-anthropic", [valid_assessment(analysis)])

    results = await ReviewOrchestrator(
        store,
        settings,
        GPTAnalyst(settings, gpt_transport),
        ClaudeAnalyst(settings, claude_transport),
        clock=lambda: now + timedelta(seconds=1),
    ).execute(analysis, run_id=run_id, claim=claim)

    assert {row.failure_code for row in results} == {"LEGACY_REQUEST_CONFIGURATION_INCOMPLETE"}
    assert gpt_transport.calls == 0
    assert claude_transport.calls == 0
