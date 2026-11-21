from datetime import timedelta

from marketintel.consensus import decide
from marketintel.detectors import EngineConfig, create_candidate
from marketintel.models import AnalystAssessment, Status


def sample_candidate(make_bars):
    bars = make_bars(n=35, last_close=125)
    now = bars[-1].open_time + timedelta(minutes=1, seconds=20)
    candidate = create_candidate(EngineConfig("GOLD", "1m", 30), bars, now=now)
    return candidate.model_copy(update={"source_quality": "FRESH"}), now


def assessment(candidate, **changes):
    data = dict(
        snapshot_id=candidate.snapshot_id,
        direction=candidate.direction,
        decision="CONFIRM",
        supported_target_indices=[1, 2, 3],
        reason="Test only, not live analysis",
        counter_evidence=[],
        data_warnings=[],
    )
    data.update(changes)
    return AnalystAssessment(**data)


def test_missing_ai_fails_closed(make_bars):
    c, now = sample_candidate(make_bars)
    assert c and decide(c, assessment(c), None, now=now).status == Status.WAIT


def test_two_approvals_are_not_automatically_sufficient(make_bars):
    c, now = sample_candidate(make_bars)
    assert c
    a = assessment(c, supported_target_indices=[1])
    b = assessment(c, supported_target_indices=[2])
    assert decide(c, a, b, now=now).status == Status.WAIT


def test_matching_ai_can_confirm_after_gate(make_bars):
    c, now = sample_candidate(make_bars)
    assert c
    a = assessment(c)
    verdict = decide(c, a, a, now=now)
    assert verdict.status == Status.CONFIRMED
    assert verdict.supported_target_indices


def test_bad_snapshot_blocks(make_bars):
    c, now = sample_candidate(make_bars)
    assert c
    assert decide(c, assessment(c), assessment(c, snapshot_id="wrong"), now=now).status == Status.WAIT


def test_model_reject_blocks(make_bars):
    c, now = sample_candidate(make_bars)
    assert c
    assert decide(c, assessment(c), assessment(c, decision="REJECT"), now=now).status == Status.REJECTED


def test_model_data_warning_blocks(make_bars):
    c, now = sample_candidate(make_bars)
    assert c
    assert decide(c, assessment(c), assessment(c, data_warnings=["stale OI"]), now=now).status == Status.WAIT


def test_expired_candidate_blocks(make_bars):
    c, now = sample_candidate(make_bars)
    assert c
    assert decide(c, assessment(c), assessment(c), now=c.expires_at_utc + timedelta(seconds=1)).status == Status.WAIT
