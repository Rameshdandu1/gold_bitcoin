"""Fail-closed decision gate; does NOT authorize trading or place orders."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from marketintel.analysis import CanonicalAnalysis, canonical_json_bytes
from marketintel.models import AnalystAssessment, Candidate, ConsensusResult, Status
from marketintel.review import (
    ConsensusDecisionV2,
    EligibilitySnapshot,
    GateResult,
    ProviderResult,
)


def decide(
    candidate: Candidate,
    gpt: AnalystAssessment | None,
    claude: AnalystAssessment | None,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 180,
    min_reward_risk: float = 1.5,
) -> ConsensusResult:
    now = now or datetime.now(UTC)

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
        i
        for i in overlap
        if 1 <= i <= len(candidate.targets)
        and abs(candidate.targets[i - 1] - candidate.entry) / risk >= min_reward_risk
    )
    if not accepted:
        return result(Status.WAIT, "No shared eligible target with sufficient reward/risk")
    return result(Status.CONFIRMED, "Both analysts agree; deterministic checks passed", accepted)


def decide_v2(
    analysis: CanonicalAnalysis,
    openai: ProviderResult,
    anthropic: ProviderResult,
    eligibility: EligibilitySnapshot,
    *,
    run_id: str,
    provider_attempt_ids: tuple[str, str],
) -> ConsensusDecisionV2:
    """Combine independent opinions, then apply fresh deterministic eligibility gates."""
    envelope = analysis.envelope
    gates: list[GateResult] = []

    def gate(code: str, passed: bool, detail: str) -> bool:
        gates.append(GateResult(code=code, passed=passed, detail=detail))
        return passed

    def decision(status: str, reason: str, indices: tuple[int, ...] = ()) -> ConsensusDecisionV2:
        preimage = {
            "run_id": run_id,
            "revision_id": envelope.candidate_revision_id,
            "digest": analysis.digest,
            "status": status,
            "indices": indices,
            "provider_attempt_ids": provider_attempt_ids,
            "eligibility_token": eligibility.eligibility_token,
        }
        decision_id = hashlib.sha256(canonical_json_bytes(preimage)).hexdigest()
        return ConsensusDecisionV2(
            decision_id=decision_id,
            run_id=run_id,
            candidate_id=envelope.candidate_id,
            candidate_revision_id=envelope.candidate_revision_id,
            envelope_digest=analysis.digest,
            status=status,
            reason=reason,
            supported_target_indices=indices,
            provider_attempt_ids=provider_attempt_ids,
            gates=tuple(gates),
            eligibility=eligibility,
            decided_at_utc=eligibility.evaluated_at_utc,
        )

    if {openai.provider, anthropic.provider} != {"OPENAI", "ANTHROPIC"}:
        gate("PROVIDER_SLOTS", False, "One result from each configured provider is required")
        return decision("WAIT", "Independent provider slots are incomplete or duplicated")
    if openai.status != "SUCCEEDED" or anthropic.status != "SUCCEEDED":
        gate(
            "PROVIDER_RESULTS",
            False,
            f"OPENAI={openai.status}; ANTHROPIC={anthropic.status}",
        )
        return decision("WAIT", "Both valid provider assessments are required")
    assessments = (openai.assessment, anthropic.assessment)
    if any(item is None for item in assessments):
        gate("PROVIDER_RESULTS", False, "Successful result omitted parsed assessment")
        return decision("WAIT", "Parsed provider assessment is unavailable")
    try:
        for assessment in assessments:
            assert assessment is not None
            assessment.validate_for(envelope, analysis.digest)
    except ValueError:
        gate("ASSESSMENT_IDENTITY", False, "Assessment identity/target validation failed")
        return decision("WAIT", "Provider assessment does not match the active request")
    gate("ASSESSMENT_IDENTITY", True, "Both assessments match the exact revision and envelope")

    if any(assessment.data_warnings for assessment in assessments if assessment is not None):
        gate("MODEL_WARNINGS", False, "At least one reviewer reported blocking data warnings")
        return decision("WAIT", "Reviewer-reported data uncertainty blocks confirmation")
    if any(assessment.decision == "REJECT" for assessment in assessments if assessment):
        gate("MODEL_AGREEMENT", False, "At least one valid reviewer rejected the proposal")
        return decision("REJECTED", "A valid independent reviewer rejected the proposal")
    if any(assessment.decision != "CONFIRM" for assessment in assessments if assessment):
        gate("MODEL_AGREEMENT", False, "At least one valid reviewer requested WAIT")
        return decision("WAIT", "Both reviewers did not approve the fixed proposal")
    overlap = set(assessments[0].supported_target_indices) & set(
        assessments[1].supported_target_indices
    )
    if not overlap:
        gate("MODEL_TARGET_OVERLAP", False, "No shared 1-based target identity")
        return decision("WAIT", "Reviewers approved no common frozen target")
    gate("MODEL_TARGET_OVERLAP", True, f"Shared target indices={sorted(overlap)}")

    now = eligibility.evaluated_at_utc
    current = True
    current &= gate(
        "ACTIVE_REVISION",
        eligibility.candidate_id == envelope.candidate_id
        and eligibility.candidate_revision_id == envelope.candidate_revision_id,
        "Eligibility snapshot must match the scheduled revision",
    )
    current &= gate(
        "LIFECYCLE",
        eligibility.lifecycle_state == "CANDIDATE",
        f"Current lifecycle={eligibility.lifecycle_state}",
    )
    current &= gate(
        "EXPIRY",
        now < envelope.expires_at_utc,
        "Candidate must be unexpired at decision commit",
    )
    current &= gate(
        "POINT_IN_TIME",
        envelope.observed_at_utc <= now
        and envelope.feature_snapshot.observed_at_utc <= now
        and eligibility.latest_trade_at_utc <= now
        and eligibility.book_observed_at_utc <= now,
        "Observation, trade and book timestamps cannot be in the future",
    )
    current &= gate(
        "REQUIRED_SOURCES",
        eligibility.discovery_current
        and eligibility.reconciliation_current
        and eligibility.trade_stream_current
        and eligibility.book_current,
        "Discovery, reconciliation, trades and validated book must be current",
    )
    current &= gate(
        "EVENT_ORDER",
        not eligibility.event_order_ambiguous,
        "Stop/target ordering must be unambiguous",
    )
    current &= gate(
        "STOP_BREACH",
        not eligibility.stop_breached,
        "Any post-observation stop breach is terminal",
    )
    current &= gate(
        "COST_ASSUMPTIONS",
        eligibility.required_costs_known
        and eligibility.fee_bps is not None
        and eligibility.slippage_bps is not None,
        "Configured fee and slippage assumptions are required",
    )
    current &= gate(
        "CALENDAR_POLICY",
        eligibility.calendar_policy != "UNKNOWN",
        f"Calendar/session policy={eligibility.calendar_policy}",
    )
    current &= gate(
        "NOTIFICATION_CONFIGURATION",
        eligibility.notification_ready,
        "A durable operator destination must be configured before confirmation",
    )
    if not current:
        return decision("WAIT", "Current deterministic eligibility checks failed")

    entry = Decimal(envelope.entry)
    invalidation = Decimal(envelope.invalidation)
    bid = Decimal(eligibility.best_bid)
    ask = Decimal(eligibility.best_ask)
    if ask <= bid:
        gate("BOOK_GEOMETRY", False, "Best ask must be greater than best bid")
        return decision("WAIT", "Current order book geometry is invalid")
    quote_entry = ask if envelope.direction == "BULLISH" else bid
    spread_bps = (ask - bid) / ((ask + bid) / Decimal("2")) * Decimal("10000")
    drift_bps = abs(quote_entry - entry) / entry * Decimal("10000")
    geometry_ok = gate(
        "SPREAD",
        spread_bps <= Decimal(eligibility.maximum_spread_bps),
        f"spread_bps={spread_bps}",
    )
    geometry_ok &= gate(
        "ENTRY_DRIFT",
        drift_bps <= Decimal(eligibility.maximum_entry_drift_bps),
        f"entry_drift_bps={drift_bps}",
    )
    risk = (
        quote_entry - invalidation
        if envelope.direction == "BULLISH"
        else invalidation - quote_entry
    )
    geometry_ok &= gate("RISK_GEOMETRY", risk > 0, f"current_risk={risk}")
    if not geometry_ok:
        return decision("WAIT", "Current spread, entry drift or stop geometry failed")

    costs = (
        quote_entry
        * (Decimal(eligibility.fee_bps or "0") + Decimal(eligibility.slippage_bps or "0"))
        / Decimal("10000")
    )
    crossed = set(eligibility.target_crossed_indices)
    feasible: list[int] = []
    for index in sorted(overlap):
        if index in crossed:
            continue
        target = Decimal(envelope.targets[index - 1])
        gross = target - quote_entry if envelope.direction == "BULLISH" else quote_entry - target
        net = gross - costs
        if risk > 0 and net > 0 and net / risk >= Decimal(eligibility.minimum_net_reward_risk):
            feasible.append(index)
    if not feasible:
        gate(
            "FEASIBLE_TARGETS",
            False,
            "All shared targets are crossed or fail cost-adjusted reward/risk",
        )
        return decision("WAIT", "No shared target remains feasible at the fresh quote")
    gate("FEASIBLE_TARGETS", True, f"eligible original indices={feasible}")
    return decision(
        "CONFIRMED",
        "Both independent reviews and all current deterministic gates passed",
        tuple(feasible),
    )
