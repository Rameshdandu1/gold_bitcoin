from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_phase2_quantitative import supporting_book
from test_phase3_ai import SequenceTransport, review_settings, valid_assessment
from test_phase3_consensus import analysis_fixture, approvals, persist_candidate
from test_phase3_service_alerts import FakeSlack, alert_settings, committed_alert
from test_phase4_corrections import trade_event
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
from marketintel.delta import OrderBookAssembler
from marketintel.models import SignalState
from marketintel.notifications import AlertWorker
from marketintel.orchestration import ReviewOrchestrator, frozen_provider_config
from marketintel.paper_worker import PaperWorkerConfig, run_cycle
from marketintel.quantitative import lifecycle_event
from marketintel.research_engine import SharedResearchEngine
from marketintel.research_evaluation import (
    arm_metrics,
    evaluate_bar_path,
    evaluate_quotes,
    paired_day_block_difference,
    purged_folds,
)
from marketintel.research_models import ArmRecord, PriceBar, ReplayObservation
from marketintel.research_replay import load_manifest, replay
from marketintel.research_storage import PaperLedger, ResearchStore
from marketintel.storage import Store

NOW = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)


def replace_book(store: Store, symbol: str, *, bid: str, ask: str, at: datetime) -> None:
    book = OrderBookAssembler(symbol, max_age_seconds=120)
    book.bids = {Decimal(bid): (bid, "10")}
    book.asks = {Decimal(ask): (ask, "10")}
    book.last_sequence = 2
    book.last_event_time_utc = at
    book.last_received_at_utc = at
    book.valid = True
    book.reason = "TEST_FIXTURE_NOT_LIVE"
    store.save_book_checkpoint(book)


@pytest.mark.asyncio
async def test_p4_06_trade_insert_before_dispatch_authorization_suppresses_alert(
    tmp_path, monkeypatch
) -> None:
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate_value = committed_alert(store)
    transport = FakeSlack()
    original = Store.mark_outbox_dispatch_started
    inserted = False

    def insert_breach_then_authorize(self, item, *, now, **kwargs):
        nonlocal inserted
        if not inserted:
            inserted = True
            breach_at = candidate_value.observed_at_utc + timedelta(seconds=45)
            assert self.append_raw_event(
                trade_event(
                    symbol=candidate_value.symbol,
                    event_at=breach_at,
                    received_at=breach_at,
                    price="2589",
                    sequence=99,
                )
            )
        return original(self, item, now=now, **kwargs)

    monkeypatch.setattr(Store, "mark_outbox_dispatch_started", insert_breach_then_authorize)

    assert await AlertWorker(store, settings, transport).run_once(
        owner="phase5-race",
        now=candidate_value.observed_at_utc + timedelta(minutes=1),
    )

    assert transport.calls == []
    assert store.outbox_items()[0]["status"] == "SUPPRESSED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bid", "ask"),
    [("2590", "2610"), ("2605", "2605.2")],
    ids=("wide-spread-and-drift", "drift-only"),
)
async def test_p4_06_alert_rechecks_full_quote_policy(tmp_path, bid, ask) -> None:
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate_value = committed_alert(store)
    sent_at = candidate_value.observed_at_utc + timedelta(minutes=1)
    replace_book(store, candidate_value.symbol, bid=bid, ask=ask, at=sent_at)
    transport = FakeSlack()

    assert await AlertWorker(store, settings, transport).run_once(
        owner="phase5-quote-policy", now=sent_at
    )

    assert transport.calls == []
    assert store.outbox_items()[0]["status"] == "SUPPRESSED"


@pytest.mark.asyncio
async def test_p4_06_terminal_lifecycle_insert_before_authorization_suppresses_alert(
    tmp_path, monkeypatch
) -> None:
    settings = alert_settings(tmp_path)
    store = Store(settings.database_path)
    candidate_value = committed_alert(store)
    transport = FakeSlack()
    original = Store.mark_outbox_dispatch_started
    inserted = False

    def insert_terminal_then_authorize(self, item, *, now, **kwargs):
        nonlocal inserted
        if not inserted:
            inserted = True
            assert self.record_candidate_lifecycle(
                lifecycle_event(
                    candidate_id=candidate_value.candidate_id,
                    snapshot_id=candidate_value.snapshot_id,
                    from_state=SignalState.CANDIDATE,
                    to_state=SignalState.INVALIDATED,
                    occurred_at=candidate_value.observed_at_utc + timedelta(seconds=50),
                    reason="TEST_FIXTURE_NOT_LIVE dispatch race",
                    price_source="EXECUTED_TRADE",
                    source_event_id="phase5-terminal-race",
                )
            )
        return original(self, item, now=now, **kwargs)

    monkeypatch.setattr(Store, "mark_outbox_dispatch_started", insert_terminal_then_authorize)

    assert await AlertWorker(store, settings, transport).run_once(
        owner="phase5-terminal-race",
        now=candidate_value.observed_at_utc + timedelta(minutes=1),
    )
    assert transport.calls == []
    confirmation = next(item for item in store.outbox_items() if item["event_type"] == "CONFIRMED")
    assert confirmation["status"] == "SUPPRESSED"


@pytest.mark.asyncio
async def test_p4_07_terminal_candidate_makes_zero_provider_calls(tmp_path) -> None:
    candidate_value, analysis = analysis_fixture()
    settings = review_settings()
    store = Store(tmp_path / "terminal-preflight.sqlite3")
    persist_candidate(store, candidate_value)
    now = candidate_value.observed_at_utc
    run_id = store.create_review_run(
        analysis,
        provider_config=frozen_provider_config(settings, analysis),
        now=now,
        deadline_at=now + timedelta(seconds=90),
    )
    assert store.record_candidate_lifecycle(
        lifecycle_event(
            candidate_id=candidate_value.candidate_id,
            snapshot_id=candidate_value.snapshot_id,
            from_state=SignalState.CANDIDATE,
            to_state=SignalState.INVALIDATED,
            occurred_at=now + timedelta(seconds=1),
            reason="TEST_FIXTURE_NOT_LIVE terminal before provider start",
        )
    )
    claim = store.claim_review_job("phase5-provider", now=now + timedelta(seconds=2))
    assert claim is not None
    gpt_transport = SequenceTransport("fixture-openai", [valid_assessment(analysis)])
    claude_transport = SequenceTransport("fixture-anthropic", [valid_assessment(analysis)])

    results = await ReviewOrchestrator(
        store,
        settings,
        GPTAnalyst(settings, gpt_transport),
        ClaudeAnalyst(settings, claude_transport),
        clock=lambda: now + timedelta(seconds=2),
    ).execute(analysis, run_id=run_id, claim=claim)

    assert gpt_transport.calls == claude_transport.calls == 0
    assert {result.failure_code for result in results} == {"CANDIDATE_LIFECYCLE_TERMINAL"}
    assert store.review_dispositions(run_id)[-1]["code"] == "CANDIDATE_LIFECYCLE_TERMINAL"


@pytest.mark.asyncio
async def test_p4_08_output_cap_drift_is_a_frozen_configuration_mismatch(tmp_path) -> None:
    candidate_value, analysis = analysis_fixture()
    queued_settings = review_settings(ai_max_output_tokens=64)
    runtime_settings = review_settings(ai_max_output_tokens=650)
    store = Store(tmp_path / "frozen-request.sqlite3")
    persist_candidate(store, candidate_value)
    now = candidate_value.observed_at_utc
    run_id = store.create_review_run(
        analysis,
        provider_config=frozen_provider_config(queued_settings, analysis),
        now=now,
        deadline_at=now + timedelta(seconds=90),
    )
    claim = store.claim_review_job("phase5-config", now=now)
    assert claim is not None
    gpt_transport = SequenceTransport("fixture-openai", [valid_assessment(analysis)])
    claude_transport = SequenceTransport("fixture-anthropic", [valid_assessment(analysis)])

    results = await ReviewOrchestrator(
        store,
        runtime_settings,
        GPTAnalyst(runtime_settings, gpt_transport),
        ClaudeAnalyst(runtime_settings, claude_transport),
        clock=lambda: now,
    ).execute(analysis, run_id=run_id, claim=claim)

    assert gpt_transport.calls == claude_transport.calls == 0
    assert {result.failure_code for result in results} == {"QUEUED_PROVIDER_CONFIGURATION_MISMATCH"}
    assert len(store.review_run(run_id)["request_config_digest"]) == 64


def test_p4_09_expired_saved_results_terminalize_without_reclaim_or_redispatch(tmp_path) -> None:
    candidate_value, analysis = analysis_fixture()
    store = Store(tmp_path / "expired-results.sqlite3")
    persist_candidate(store, candidate_value)
    now = candidate_value.observed_at_utc
    run_id = store.create_review_run(
        analysis,
        provider_config={"openai_model": "fixture-openai", "anthropic_model": "fixture-anthropic"},
        now=now,
        deadline_at=now + timedelta(seconds=90),
    )
    claim = store.claim_review_job("phase5-first", now=now, lease_seconds=30)
    assert claim is not None
    for result in approvals(analysis):
        assert store.save_provider_result(
            run_id=run_id,
            job_id=claim["job_id"],
            owner=claim["owner"],
            generation=claim["generation"],
            dispatch_id=f"phase5-{result.provider}",
            result=result,
        )
    assert store.mark_review_results_ready(
        claim["job_id"],
        owner=claim["owner"],
        generation=claim["generation"],
        now=now + timedelta(seconds=1),
    )

    assert (
        store.claim_review_job("phase5-late", now=now + timedelta(seconds=121), lease_seconds=120)
        is None
    )
    assert store.review_job(claim["job_id"])["status"] == "WAIT"
    assert len(store.provider_results(run_id)) == 2
    assert store.review_dispositions(run_id)[-1]["code"] == "REVIEW_DEADLINE_EXPIRED"


def test_p4_02_pre_entry_stop_cannot_be_discarded_before_later_target() -> None:
    outcome = evaluate_quotes(
        candidate(),
        decision(),
        instrument(),
        [
            quote("pre-entry-stop", 5, "94.5", "95"),
            quote("entry", 11, "100", "100.5"),
            quote("target", 30, "105", "105.5"),
        ],
        policy(),
    )

    assert outcome.code == "NO_ENTRY"
    assert outcome.reason == "INVALIDATED_BEFORE_ENTRY"
    assert "pre-entry-stop" in outcome.supporting_event_ids


def test_p4_02_post_entry_quote_gap_cannot_be_labelled_as_supported_win() -> None:
    outcome = evaluate_quotes(
        candidate(),
        decision(),
        instrument(),
        [
            quote("entry", 11, "100", "100.5"),
            quote("unsupported-target", 151, "105", "105.5"),
        ],
        policy(),
    )

    assert outcome.code == "INCOMPLETE"
    assert outcome.reason == "QUOTE_PATH_GAP_EXCEEDED"
    assert outcome.data_complete is False


def test_p4_02_rejected_arm_and_partial_boundary_bar_cannot_win() -> None:
    rejected = decision().model_copy(update={"state": "REJECTED", "reason": "fixture rejection"})
    boundary_bar = PriceBar(
        event_id="partial-entry-boundary",
        venue="delta_india",
        symbol="BTCUSD",
        start_utc=NOW + timedelta(seconds=5),
        end_utc=NOW + timedelta(seconds=20),
        open=Decimal("100"),
        high=Decimal("106"),
        low=Decimal("99"),
        close=Decimal("105"),
        complete=False,
    )

    rejected_outcome = evaluate_bar_path(candidate(), rejected, [boundary_bar])
    partial_outcome = evaluate_bar_path(candidate(), decision(), [boundary_bar])

    assert rejected_outcome.code == "NO_ENTRY"
    assert partial_outcome.code == "INCOMPLETE"
    assert partial_outcome.reason == "PARTIAL_BAR_OVERLAPS_ENTRY_BOUNDARY"


def test_p4_03_walk_forward_training_is_past_only_and_holdout_crossing_is_purged() -> None:
    holdout_start = NOW + timedelta(hours=72)
    rows = [
        opportunity("day-1", NOW, NOW + timedelta(hours=1)),
        opportunity("day-2", NOW + timedelta(hours=24), NOW + timedelta(hours=25)),
        opportunity("crossing", NOW + timedelta(hours=71), NOW + timedelta(hours=73)),
        opportunity("holdout", NOW + timedelta(hours=72), NOW + timedelta(hours=74)),
    ]

    folds = purged_folds(rows, fold_count=2, holdout_start=holdout_start)

    assert folds[0]["train"] == ()
    assert folds[1]["train"] == ("day-1",)
    assert all("crossing" not in fold["train"] + fold["test"] for fold in folds)
    assert all("holdout" not in fold["train"] + fold["test"] for fold in folds)


def test_p4_10_manifest_identity_is_recomputed_from_canonical_preimage(tmp_path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "research" / "manifest.json"
    loaded = load_manifest(fixture)
    assert loaded.content_hash == loaded.canonical_content_hash()

    changed = loaded.model_copy(update={"provenance": "silently changed provenance"})
    supplied = tmp_path / "manifest.json"
    supplied.write_text(changed.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical preimage"):
        load_manifest(supplied, verify_files=False)


def test_p4_10_checkpoint_refuses_changed_experiment_policy() -> None:
    rows = [
        ReplayObservation(
            observation_id="identity-row",
            kind="CANDLE_OBSERVATION",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW,
            persistence_sequence=1,
            payload={"close": "100"},
        )
    ]
    _, checkpoint = replay(manifest(), config(), rows, maximum_points=1)
    changed = config().model_copy(update={"entry_latency_ms": 10})
    with pytest.raises(ValueError, match="configuration differs"):
        replay(manifest(), changed, rows, checkpoint=checkpoint)


def test_p4_11_replay_checkpoint_and_points_keep_bounded_references() -> None:
    rows = [
        ReplayObservation(
            observation_id=f"bounded-{index:04d}",
            kind="TRADE",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW,
            persistence_sequence=index,
            payload={"price": str(100 + index), "contracts": "1", "aggressor": "BUY"},
        )
        for index in range(1_000)
    ]
    points, checkpoint = replay(manifest(), config(), rows)

    assert checkpoint.visible_count == 1_000
    assert len(checkpoint.visible_observation_ids) == 128
    assert all(len(point.visible_observation_ids) <= 128 for point in points)
    assert len(checkpoint.model_dump_json()) < 10_000


def test_p4_01_book_gap_requires_new_snapshot_generation() -> None:
    state = SharedResearchEngine(manifest())
    features = supporting_book(NOW, "BULLISH")
    state.apply(
        ReplayObservation(
            observation_id="book-snapshot-1",
            kind="BOOK_SNAPSHOT",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW,
            persistence_sequence=1,
            payload={
                "sequence": 1,
                "generation": 1,
                "snapshot": True,
                "features": features.model_dump(mode="json"),
            },
        )
    )
    state.apply(
        ReplayObservation(
            observation_id="book-delta-gap",
            kind="BOOK_DELTA",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW,
            persistence_sequence=2,
            payload={
                "sequence": 3,
                "generation": 1,
                "snapshot": False,
                "features": features.model_dump(mode="json"),
            },
        )
    )
    assert state.books["BTCUSD"].available is False
    assert state.books["BTCUSD"].reason == "BOOK_SEQUENCE_GAP_REQUIRES_SNAPSHOT"

    state.apply(
        ReplayObservation(
            observation_id="book-snapshot-2",
            kind="BOOK_SNAPSHOT",
            symbol="BTCUSD",
            venue="delta_india",
            exchange_time_utc=NOW,
            available_at_utc=NOW,
            persistence_sequence=3,
            payload={
                "sequence": 1,
                "generation": 2,
                "snapshot": True,
                "features": features.model_dump(mode="json"),
            },
        )
    )
    assert state.books["BTCUSD"].available is True


def test_p4_10_research_records_are_conflict_detecting_not_overwritten(tmp_path) -> None:
    store = ResearchStore(tmp_path / "research.sqlite3")
    store.create_experiment(manifest(), config())
    original = opportunity("immutable", NOW, NOW + timedelta(hours=1))
    store.save_opportunity(config().experiment_id, original)
    changed = original.model_copy(update={"direction": "BEARISH"})

    with pytest.raises(ValueError, match="immutable"):
        store.save_opportunity(config().experiment_id, changed)


def test_p4_04_operational_comparison_keeps_known_abstentions() -> None:
    rows = []
    for day in range(10):
        original = opportunity(
            f"operational-{day}",
            NOW + timedelta(days=day),
            NOW + timedelta(days=day, hours=1),
        )
        baseline = original.arms[0]
        assert baseline.outcome is not None
        losing_outcome = baseline.outcome.model_copy(update={"net_pnl": Decimal("-6.2")})
        rows.append(
            original.model_copy(
                update={
                    "arms": (
                        baseline.model_copy(update={"outcome": losing_outcome}),
                        ArmRecord(
                            arm="RULES_PLUS_GPT",
                            state="REJECTED",
                            decision_ready_at_utc=NOW + timedelta(days=day, seconds=10),
                            reason="known filter abstention",
                        ),
                        original.arms[2],
                        original.arms[3],
                    )
                }
            )
        )

    metrics = arm_metrics(rows)
    paired = paired_day_block_difference(rows, "RULES_ONLY", "RULES_PLUS_GPT")

    assert metrics["RULES_ONLY"]["operational_net_pnl_after_attributable_ai_cost"] == "-62.0"
    assert metrics["RULES_PLUS_GPT"]["known_no_position"] == 10
    assert metrics["RULES_PLUS_GPT"]["operational_net_pnl_after_attributable_ai_cost"] == "0"
    assert paired["paired_opportunities"] == 10
    assert paired["mean_difference"] == "6.2"


def test_p4_05_paper_decision_cannot_be_backfilled_after_eligible_entry(tmp_path) -> None:
    with pytest.raises(ValueError, match="before eligible entry"):
        PaperLedger(tmp_path / "paper.sqlite3").record_decision(
            "opp-1",
            "rev-1",
            decision(),
            candidate=candidate(),
            config_hash="a" * 64,
            target_index=1,
            source_identity="fixture-source-v1",
            recorded_at=NOW + timedelta(days=1),
        )


def test_p4_05_rejected_paper_arm_cannot_receive_executed_win(tmp_path) -> None:
    ledger = PaperLedger(tmp_path / "paper.sqlite3")
    rejected = decision("RULES_PLUS_GPT").model_copy(
        update={"state": "REJECTED", "reason": "fixture rejection"}
    )
    ledger.record_decision(
        "opp-1",
        "rev-1",
        rejected,
        candidate=candidate(),
        config_hash="a" * 64,
        target_index=1,
        source_identity="fixture-source-v1",
        recorded_at=NOW + timedelta(seconds=10),
    )
    win = evaluate_quotes(
        candidate(),
        decision("RULES_PLUS_GPT"),
        instrument(),
        [quote("entry", 11, "100", "100.5"), quote("target", 30, "105", "105.5")],
        policy(),
    )

    with pytest.raises(ValueError, match="Non-approved"):
        ledger.record_outcome("rev-1", win, recorded_at=NOW + timedelta(minutes=1))


def test_p4_05_paper_worker_write_before_entry_restart_and_source_binding(tmp_path) -> None:
    approved = decision()
    result = evaluate_quotes(
        candidate(),
        approved,
        instrument(),
        [quote("entry", 11, "100", "100.5"), quote("target", 30, "105", "105.5")],
        policy(),
    )
    source = tmp_path / "paper-stream.jsonl"
    source.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "type": "DECISION",
                        "opportunity_id": "opp-1",
                        "revision_id": "rev-1",
                        "candidate": candidate().model_dump(mode="json"),
                        "decision": approved.model_dump(mode="json"),
                        "config_hash": "a" * 64,
                        "target_index": 1,
                        "evidence_mode": "PROSPECTIVE",
                    },
                    default=str,
                ),
                json.dumps(
                    {
                        "type": "OUTCOME",
                        "revision_id": "rev-1",
                        "outcome": result.model_dump(mode="json"),
                    },
                    default=str,
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    config_value = PaperWorkerConfig(
        enabled=True,
        ledger_path=tmp_path / "paper.sqlite3",
        production_database_path=tmp_path / "production.sqlite3",
        recorded_decisions_path=source,
        source_identity="fixture-stream-v1",
        source_generation=1,
        maximum_records_per_cycle=1,
    )

    first = run_cycle(config_value, now=NOW + timedelta(seconds=10))
    second = run_cycle(config_value, now=NOW + timedelta(minutes=1))
    restarted = run_cycle(config_value, now=NOW + timedelta(minutes=2))

    assert first["decisions"] == 1 and first["outcomes"] == 0
    assert second["decisions"] == 0 and second["outcomes"] == 1
    assert restarted["recorded"] == 0
    assert PaperLedger(config_value.ledger_path).summary()["outcomes"] == 1

    changed_source = config_value.model_copy(update={"source_identity": "replacement-stream-v2"})
    with pytest.raises(ValueError, match="identity/generation changed"):
        run_cycle(changed_source, now=NOW + timedelta(minutes=3))

    source.write_text(source.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="truncated"):
        run_cycle(config_value, now=NOW + timedelta(minutes=3))
