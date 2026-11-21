"""Fail-closed decision gate; does NOT authorize trading or place orders."""

from datetime import datetime, timezone

from marketintel.models import AnalystAssessment, Candidate, ConsensusResult, Status


def decide(
    candidate: Candidate,
    gpt: AnalystAssessment | None,
    claude: AnalystAssessment | None,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 180,
    min_reward_risk: float = 1.5,
) -> ConsensusResult:
    now = now or datetime.now(timezone.utc)

    def result(status: Status, reason: str, indices: list[int] | None = None) -> ConsensusResult:
        return ConsensusResult(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            status=status,
            reason=reason,
            supported_target_indices=indices or [],
            evaluated_at_utc=now,
        )

    if candidate.source_quality != "FRESH":
        return result(Status.WAIT, "Market data is stale or incomplete")
    if now > candidate.expires_at_utc:
        return result(Status.WAIT, "Candidate expired")
    if (now - candidate.observed_at_utc).total_seconds() > max_age_seconds:
        return result(Status.WAIT, "Market observation too old")
    if gpt is None or claude is None:
        return result(Status.WAIT, "Both independent AI assessments are required")
    for name, analyst in (("GPT", gpt), ("Claude", claude)):
        if analyst.snapshot_id != candidate.snapshot_id:
            return result(Status.WAIT, f"{name} analyzed a different snapshot")
        if analyst.decision == "REJECT":
            return result(Status.REJECTED, f"{name} rejected candidate: {analyst.reason}")
        if analyst.decision != "CONFIRM":
            return result(Status.WAIT, f"{name} requested WAIT: {analyst.reason}")
        if analyst.direction != candidate.direction:
            return result(Status.WAIT, f"{name} direction differs from quantitative candidate")
        if analyst.data_warnings:
            return result(Status.WAIT, f"{name} reported data warnings")
    overlap = set(gpt.supported_target_indices) & set(claude.supported_target_indices)
    risk = abs(candidate.entry - candidate.invalidation)
    accepted = sorted(
        i for i in overlap
        if 1 <= i <= len(candidate.targets)
        and abs(candidate.targets[i - 1] - candidate.entry) / risk >= min_reward_risk
    )
    if not accepted:
        return result(Status.WAIT, "No shared eligible target with sufficient reward/risk")
    return result(Status.CONFIRMED, "Both analysts agree; deterministic checks passed", accepted)
