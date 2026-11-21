import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from marketintel.detectors import EngineConfig, create_candidate
from marketintel.models import SignalState
from marketintel.quantitative import lifecycle_event
from marketintel.storage import Store


def test_candidate_idempotent_store(tmp_path, make_bars):
    store = Store(tmp_path / "db.sqlite3")
    bars = make_bars(n=35, last_close=125)
    c = create_candidate(
        EngineConfig("GOLD", "1m", 30),
        bars,
        now=bars[-1].open_time + timedelta(minutes=1, seconds=15),
    )
    assert c
    assert store.add_candidate(c) is True
    assert store.add_candidate(c) is False
    assert len(store.recent_candidates()) == 1
    assert len(store.candidate_revisions(c.candidate_id)) == 1

    revision = c.model_copy(update={"snapshot_id": "f" * 64})
    assert store.add_candidate(revision) is False
    assert len(store.candidate_revisions(c.candidate_id)) == 2
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._conn() as connection:
            connection.execute(
                "UPDATE candidate_revisions SET payload='{}' WHERE candidate_id=?",
                (c.candidate_id,),
            )


def test_candidate_lifecycle_is_append_only_and_idempotent(tmp_path, make_bars):
    store = Store(tmp_path / "db.sqlite3")
    bars = make_bars(n=35, last_close=125)
    candidate = create_candidate(
        EngineConfig("GOLD", "1m", 30),
        bars,
        now=bars[-1].open_time + timedelta(minutes=1, seconds=15),
    )
    assert candidate
    event = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE candidate emitted",
    )
    assert store.record_candidate_lifecycle(event) is True
    assert store.record_candidate_lifecycle(event) is False
    assert store.candidate_lifecycle(candidate.candidate_id) == [event]
    assert store.active_candidates(symbol=candidate.symbol, engine=candidate.engine) == []
    store.add_candidate(candidate)
    assert store.active_candidates(symbol=candidate.symbol, engine=candidate.engine) == [candidate]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._conn() as connection:
            connection.execute(
                "DELETE FROM candidate_lifecycle_events WHERE event_id=?", (event.event_id,)
            )


def test_candidate_and_initial_lifecycle_are_atomic_and_restart_safe(tmp_path, make_bars):
    store = Store(tmp_path / "db.sqlite3")
    bars = make_bars(n=35, last_close=125)
    candidate = create_candidate(
        EngineConfig("GOLD", "1m", 30),
        bars,
        now=bars[-1].open_time + timedelta(minutes=1, seconds=15),
    )
    assert candidate
    event = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE candidate emitted",
    )
    assert store.add_candidate_with_lifecycle(candidate, event) is True
    assert store.add_candidate_with_lifecycle(candidate, event) is False
    assert store.candidate_lifecycle(candidate.candidate_id) == [event]


def test_lifecycle_transition_is_monotonic_and_single_winner(tmp_path, make_bars):
    store = Store(tmp_path / "db.sqlite3")
    bars = make_bars(n=35, last_close=125)
    candidate = create_candidate(
        EngineConfig("GOLD", "1m", 30),
        bars,
        now=bars[-1].open_time + timedelta(minutes=1, seconds=15),
    )
    assert candidate
    initial = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=None,
        to_state=SignalState.CANDIDATE,
        occurred_at=candidate.observed_at_utc,
        reason="TEST_FIXTURE_NOT_LIVE candidate emitted",
    )
    assert store.add_candidate_with_lifecycle(candidate, initial)

    regressed = lifecycle_event(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        from_state=SignalState.CANDIDATE,
        to_state=SignalState.INVALIDATED,
        occurred_at=candidate.observed_at_utc - timedelta(seconds=1),
        reason="TEST_FIXTURE_NOT_LIVE regressed clock",
    )
    assert store.record_candidate_lifecycle(regressed) is False

    terminal_at = candidate.observed_at_utc + timedelta(seconds=1)
    competing = [
        lifecycle_event(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            from_state=SignalState.CANDIDATE,
            to_state=SignalState.INVALIDATED,
            occurred_at=terminal_at,
            reason=f"TEST_FIXTURE_NOT_LIVE terminal {index}",
        )
        for index in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(store.record_candidate_lifecycle, competing))
    assert sorted(outcomes) == [False, True]
    assert [event.to_state for event in store.candidate_lifecycle(candidate.candidate_id)] == [
        SignalState.CANDIDATE,
        SignalState.INVALIDATED,
    ]
