"""Execution-aware historical outcomes and leakage-safe arm comparisons."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from random import Random

from marketintel.research_models import (
    ArmDecision,
    ArmRecord,
    CostPolicy,
    ExecutableQuote,
    InstrumentVersion,
    OpportunityRecord,
    PriceBar,
    ResearchCandidate,
    ResearchLifecycleEvent,
    ResearchOutcome,
)


def _ticks(value: Decimal, tick: Decimal, rounding: str) -> Decimal:
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _entry_fill(
    candidate: ResearchCandidate, quote: ExecutableQuote, policy: CostPolicy, tick: Decimal
) -> Decimal:
    slip = policy.slippage_bps_per_side / Decimal(10_000)
    if candidate.direction == "BULLISH":
        return _ticks(quote.ask * (1 + slip), tick, ROUND_CEILING)
    return _ticks(quote.bid * (1 - slip), tick, ROUND_FLOOR)


def _exit_fill(
    candidate: ResearchCandidate, raw: Decimal, policy: CostPolicy, tick: Decimal
) -> Decimal:
    slip = policy.slippage_bps_per_side / Decimal(10_000)
    if candidate.direction == "BULLISH":
        return _ticks(raw * (1 - slip), tick, ROUND_FLOOR)
    return _ticks(raw * (1 + slip), tick, ROUND_CEILING)


def _outcome(
    candidate: ResearchCandidate,
    decision: ArmDecision,
    target_index: int,
    code: str,
    reason: str,
    *,
    events: tuple[str, ...] = (),
    complete: bool,
    entry_at: datetime | None = None,
    exit_at: datetime | None = None,
    entry: Decimal | None = None,
    exit: Decimal | None = None,
    policy: CostPolicy | None = None,
    instrument: InstrumentVersion | None = None,
    favorable_excursion: Decimal | None = None,
    adverse_excursion: Decimal | None = None,
) -> ResearchOutcome:
    gross_distance = gross = cost = net = net_r = None
    if entry is not None and exit is not None and policy is not None and instrument is not None:
        sign = Decimal(1) if candidate.direction == "BULLISH" else Decimal(-1)
        gross_distance = sign * (exit - entry)
        units = policy.quantity_contracts * instrument.contract_multiplier
        gross = gross_distance * units
        fee_rate = policy.fee_bps_per_side / Decimal(10_000)
        cost = (entry + exit) * units * fee_rate
        if policy.funding_bps is not None:
            cost += entry * units * policy.funding_bps / Decimal(10_000)
        net = gross - cost
        risk = abs(entry - candidate.invalidation) * units
        net_r = net / risk if risk else None
    return ResearchOutcome(
        opportunity_id=candidate.opportunity_id,
        arm=decision.arm,
        target_index=target_index,
        code=code,
        reason=reason,
        decision_ready_at_utc=decision.ready_at_utc,
        entry_at_utc=entry_at,
        exit_at_utc=exit_at,
        entry_price=entry,
        exit_price=exit,
        gross_price_distance=gross_distance,
        gross_pnl=gross,
        total_cost=cost,
        net_pnl=net,
        net_r=net_r,
        favorable_excursion=favorable_excursion,
        adverse_excursion=adverse_excursion,
        supporting_event_ids=events,
        data_complete=complete,
        decision_evidence_mode=decision.evidence_mode,
    )


def _quote_available_at(quote: ExecutableQuote) -> datetime:
    available = quote.available_at_utc or quote.observed_at_utc
    return max(quote.observed_at_utc, available)


def evaluate_quotes(
    candidate: ResearchCandidate,
    decision: ArmDecision,
    instrument: InstrumentVersion,
    quotes: Iterable[ExecutableQuote],
    policy: CostPolicy,
    *,
    target_index: int = 1,
    entry_latency_ms: int = 0,
    source_transitions: Iterable[tuple[datetime, str | object]] = (),
    lifecycle_events: Iterable[ResearchLifecycleEvent] = (),
    evaluated_through_utc: datetime | None = None,
) -> ResearchOutcome:
    """Evaluate against ordered executable quotes using each arm's real ready time."""
    if target_index < 1 or target_index > len(candidate.targets):
        raise ValueError("Target identity is the original one-based candidate index")
    if instrument.venue != candidate.venue or instrument.symbol != candidate.symbol:
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "INSTRUMENT_IDENTITY_MISMATCH",
            complete=False,
        )
    if instrument.product_id != candidate.product_id:
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "PRODUCT_VERSION_MISMATCH",
            complete=False,
        )
    if decision.state != "APPROVED":
        code = "NO_ENTRY" if decision.state in {"REJECTED", "WAIT"} else "INCOMPLETE"
        return _outcome(
            candidate, decision, target_index, code, decision.reason, complete=code == "NO_ENTRY"
        )
    if entry_latency_ms < 0:
        raise ValueError("Entry latency cannot be negative")
    ready = decision.ready_at_utc + timedelta(milliseconds=entry_latency_ms)
    if ready >= candidate.expires_at_utc:
        return _outcome(
            candidate,
            decision,
            target_index,
            "NO_ENTRY",
            "DECISION_READY_AFTER_EXPIRY",
            complete=True,
        )
    ordered = sorted(quotes, key=lambda row: (_quote_available_at(row), row.event_id))
    matching = [
        row
        for row in ordered
        if row.venue == candidate.venue
        and row.symbol == candidate.symbol
        and candidate.observed_at_utc <= row.observed_at_utc <= candidate.expires_at_utc
        and _quote_available_at(row) <= candidate.expires_at_utc
    ]
    target = candidate.targets[target_index - 1]
    interruptions = sorted(
        (at, getattr(transition, "state", transition))
        for at, transition in source_transitions
        if candidate.observed_at_utc <= at <= candidate.expires_at_utc
    )
    executed_breaches = sorted(
        (
            row
            for row in lifecycle_events
            if row.to_state == "INVALIDATED"
            and row.price_source == "EXECUTED_TRADE"
            and candidate.observed_at_utc <= row.available_at_utc <= candidate.expires_at_utc
        ),
        key=lambda row: (row.available_at_utc, row.event_id),
    )

    def source_interrupted(through: datetime) -> bool:
        return any(at <= through and state != "AVAILABLE" for at, state in interruptions)

    pre_entry = [row for row in matching if _quote_available_at(row) < ready]
    if (
        not matching
        or (_quote_available_at(matching[0]) - candidate.observed_at_utc).total_seconds()
        > policy.maximum_quote_gap_seconds
    ):
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "PRE_ENTRY_QUOTE_COVERAGE_INCOMPLETE",
            events=((matching[0].event_id,) if matching else ()),
            complete=False,
        )
    coverage_previous_at = candidate.observed_at_utc
    coverage_previous_id = matching[0].event_id
    for row in matching:
        row_at = _quote_available_at(row)
        if row_at >= ready:
            break
        if (row_at - coverage_previous_at).total_seconds() > policy.maximum_quote_gap_seconds:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "PRE_ENTRY_QUOTE_COVERAGE_INCOMPLETE",
                events=(coverage_previous_id, row.event_id),
                complete=False,
            )
        coverage_previous_at = row_at
        coverage_previous_id = row.event_id
    for row in pre_entry:
        stop_hit = (
            row.bid <= candidate.invalidation
            if candidate.direction == "BULLISH"
            else row.ask >= candidate.invalidation
        )
        target_hit = row.bid >= target if candidate.direction == "BULLISH" else row.ask <= target
        if stop_hit or target_hit:
            return _outcome(
                candidate,
                decision,
                target_index,
                "NO_ENTRY",
                "INVALIDATED_BEFORE_ENTRY" if stop_hit else "TARGET_PASSED_BEFORE_ENTRY",
                events=(row.event_id,),
                complete=True,
            )
    entry_quotes = [
        row for row in matching if ready <= _quote_available_at(row) < candidate.expires_at_utc
    ]
    if not entry_quotes:
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "NO_EXECUTABLE_QUOTE_BEFORE_EXPIRY",
            complete=False,
        )
    first = entry_quotes[0]
    first_at = _quote_available_at(first)
    pre_entry_breach = next(
        (row for row in executed_breaches if row.available_at_utc <= first_at), None
    )
    if pre_entry_breach is not None:
        return _outcome(
            candidate,
            decision,
            target_index,
            "NO_ENTRY",
            "EXECUTED_STOP_BREACH_BEFORE_ENTRY",
            events=tuple(
                value
                for value in (pre_entry_breach.source_event_id, pre_entry_breach.event_id)
                if value is not None
            ),
            complete=True,
        )
    if source_interrupted(first_at):
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "SOURCE_UNAVAILABLE_DURING_PRE_ENTRY_PATH",
            events=(first.event_id,),
            complete=False,
        )
    # Decision readiness is not market evidence. Coverage must remain continuous
    # from the last factual quote through the first eligible entry quote.
    if (first_at - coverage_previous_at).total_seconds() > (policy.maximum_quote_gap_seconds):
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "ENTRY_QUOTE_GAP_EXCEEDED",
            events=(first.event_id,),
            complete=False,
        )
    if not (
        instrument.valid_from_utc <= first_at
        and (instrument.valid_to_utc is None or first_at < instrument.valid_to_utc)
    ):
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "INSTRUMENT_VERSION_NOT_ACTIVE",
            events=(first.event_id,),
            complete=False,
        )
    entry = _entry_fill(candidate, first, policy, instrument.tick_size)
    risk_breached_at_entry = (
        entry >= candidate.invalidation
        if candidate.direction == "BEARISH"
        else entry <= candidate.invalidation
    )
    target_passed_at_entry = (
        entry <= target if candidate.direction == "BEARISH" else entry >= target
    )
    if risk_breached_at_entry or target_passed_at_entry:
        return _outcome(
            candidate,
            decision,
            target_index,
            "NO_ENTRY",
            "GEOMETRY_ALREADY_PASSED_AT_ENTRY",
            events=(first.event_id,),
            complete=True,
        )
    favorable = Decimal(0)
    adverse = Decimal(0)
    relevant = [
        row for row in matching if first_at <= _quote_available_at(row) <= candidate.expires_at_utc
    ]
    previous = first
    for quote in relevant:
        quote_at = _quote_available_at(quote)
        previous_at = _quote_available_at(previous)
        breach = next(
            (row for row in executed_breaches if first_at < row.available_at_utc <= quote_at),
            None,
        )
        if breach is not None:
            if breach.available_at_utc == quote_at:
                return _outcome(
                    candidate,
                    decision,
                    target_index,
                    "AMBIGUOUS",
                    "EXECUTED_STOP_AND_QUOTE_ORDER_AMBIGUOUS",
                    events=tuple(
                        value
                        for value in (first.event_id, breach.source_event_id, quote.event_id)
                        if value is not None
                    ),
                    complete=False,
                    entry_at=first_at,
                    entry=entry,
                    favorable_excursion=favorable,
                    adverse_excursion=adverse,
                )
            raw_exit = breach.price or candidate.invalidation
            exit_fill = _exit_fill(candidate, raw_exit, policy, instrument.tick_size)
            return _outcome(
                candidate,
                decision,
                target_index,
                "STOP_BEFORE_TARGET",
                "EXECUTED_STOP_BREACH_AFTER_ENTRY",
                events=tuple(
                    value
                    for value in (first.event_id, breach.source_event_id, breach.event_id)
                    if value is not None
                ),
                complete=True,
                entry_at=first_at,
                exit_at=breach.available_at_utc,
                entry=entry,
                exit=exit_fill,
                policy=policy,
                instrument=instrument,
                favorable_excursion=favorable,
                adverse_excursion=adverse,
            )
        if source_interrupted(quote_at):
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "SOURCE_UNAVAILABLE_DURING_OUTCOME_PATH",
                events=(previous.event_id, quote.event_id),
                complete=False,
                entry_at=first_at,
                entry=entry,
            )
        if (quote_at - previous_at).total_seconds() > (policy.maximum_quote_gap_seconds):
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "QUOTE_PATH_GAP_EXCEEDED",
                events=(previous.event_id, quote.event_id),
                complete=False,
                entry_at=first_at,
                entry=entry,
                favorable_excursion=favorable,
                adverse_excursion=adverse,
            )
        if not (
            instrument.valid_from_utc <= quote_at
            and (instrument.valid_to_utc is None or quote_at < instrument.valid_to_utc)
        ):
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "INSTRUMENT_VERSION_CHANGED_DURING_PATH",
                events=(quote.event_id,),
                complete=False,
                entry_at=first_at,
                entry=entry,
            )
        if candidate.direction == "BULLISH":
            hit_target = quote.bid >= target
            hit_stop = quote.bid <= candidate.invalidation
            raw_exit = quote.bid
            favorable = max(favorable, quote.bid - entry)
            adverse = max(adverse, entry - quote.bid)
        else:
            hit_target = quote.ask <= target
            hit_stop = quote.ask >= candidate.invalidation
            raw_exit = quote.ask
            favorable = max(favorable, entry - quote.ask)
            adverse = max(adverse, quote.ask - entry)
        if hit_target or hit_stop:
            code = "TARGET_BEFORE_STOP" if hit_target else "STOP_BEFORE_TARGET"
            exit_fill = _exit_fill(candidate, raw_exit, policy, instrument.tick_size)
            return _outcome(
                candidate,
                decision,
                target_index,
                code,
                "ORDERED_EXECUTABLE_QUOTE",
                events=(first.event_id, quote.event_id),
                complete=True,
                entry_at=first_at,
                exit_at=quote_at,
                entry=entry,
                exit=exit_fill,
                policy=policy,
                instrument=instrument,
                favorable_excursion=favorable,
                adverse_excursion=adverse,
            )
        previous = quote
    if evaluated_through_utc is not None and source_interrupted(evaluated_through_utc):
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "SOURCE_UNAVAILABLE_DURING_OUTCOME_PATH",
            events=(first.event_id, previous.event_id),
            complete=False,
            entry_at=first_at,
            entry=entry,
            favorable_excursion=favorable,
            adverse_excursion=adverse,
        )
    last = relevant[-1]
    if _quote_available_at(last) < candidate.expires_at_utc:
        return _outcome(
            candidate,
            decision,
            target_index,
            "INCOMPLETE",
            "PATH_DOES_NOT_REACH_EXPIRY",
            events=(first.event_id, last.event_id),
            complete=False,
            entry_at=first_at,
            entry=entry,
            favorable_excursion=favorable,
            adverse_excursion=adverse,
        )
    raw_exit = last.bid if candidate.direction == "BULLISH" else last.ask
    exit_fill = _exit_fill(candidate, raw_exit, policy, instrument.tick_size)
    return _outcome(
        candidate,
        decision,
        target_index,
        "TIME_EXIT",
        "EXECUTABLE_QUOTE_AT_EXPIRY",
        events=(first.event_id, last.event_id),
        complete=True,
        entry_at=first_at,
        exit_at=_quote_available_at(last),
        entry=entry,
        exit=exit_fill,
        policy=policy,
        instrument=instrument,
        favorable_excursion=favorable,
        adverse_excursion=adverse,
    )


def evaluate_bar_path(
    candidate: ResearchCandidate,
    decision: ArmDecision,
    bars: Iterable[PriceBar],
    *,
    target_index: int = 1,
    entry_latency_ms: int = 0,
) -> ResearchOutcome:
    """Classify OHLC-only paths; never invent ordering inside a bar."""
    if target_index < 1 or target_index > len(candidate.targets):
        raise ValueError("Target identity is the original one-based candidate index")
    if decision.state != "APPROVED":
        code = "NO_ENTRY" if decision.state in {"REJECTED", "WAIT"} else "INCOMPLETE"
        return _outcome(
            candidate, decision, target_index, code, decision.reason, complete=code == "NO_ENTRY"
        )
    if entry_latency_ms < 0:
        raise ValueError("Entry latency cannot be negative")
    ready = decision.ready_at_utc + timedelta(milliseconds=entry_latency_ms)
    if ready >= candidate.expires_at_utc:
        return _outcome(
            candidate,
            decision,
            target_index,
            "NO_ENTRY",
            "DECISION_READY_AFTER_EXPIRY",
            complete=True,
        )
    target = candidate.targets[target_index - 1]
    relevant = [
        bar
        for bar in sorted(bars, key=lambda row: (row.start_utc, row.end_utc, row.event_id))
        if bar.venue == candidate.venue
        and bar.symbol == candidate.symbol
        and bar.end_utc > candidate.observed_at_utc
        and bar.start_utc < candidate.expires_at_utc
    ]
    coverage_end = candidate.observed_at_utc
    for bar in relevant:
        if bar.start_utc < ready < bar.end_utc:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "PARTIAL_BAR_OVERLAPS_ENTRY_BOUNDARY",
                events=(bar.event_id,),
                complete=False,
            )
        if bar.start_utc < candidate.expires_at_utc < bar.end_utc:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "BAR_OVERLAPS_EXPIRY_BOUNDARY",
                events=(bar.event_id,),
                complete=False,
            )
        if not bar.complete:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "PARTIAL_BAR_IN_PATH",
                events=(bar.event_id,),
                complete=False,
            )
        if bar.start_utc > coverage_end:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "OHLC_PATH_GAP",
                events=(bar.event_id,),
                complete=False,
            )
        coverage_end = max(coverage_end, bar.end_utc)
        target_hit = bar.high >= target if candidate.direction == "BULLISH" else bar.low <= target
        stop_hit = (
            bar.low <= candidate.invalidation
            if candidate.direction == "BULLISH"
            else bar.high >= candidate.invalidation
        )
        if bar.start_utc < ready < bar.end_utc:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "PARTIAL_BAR_OVERLAPS_ENTRY_BOUNDARY",
                events=(bar.event_id,),
                complete=False,
            )
        if bar.start_utc < candidate.expires_at_utc < bar.end_utc:
            return _outcome(
                candidate,
                decision,
                target_index,
                "INCOMPLETE",
                "BAR_OVERLAPS_EXPIRY_BOUNDARY",
                events=(bar.event_id,),
                complete=False,
            )
        if bar.end_utc <= ready:
            if target_hit or stop_hit:
                return _outcome(
                    candidate,
                    decision,
                    target_index,
                    "NO_ENTRY",
                    "INVALIDATED_BEFORE_ENTRY" if stop_hit else "TARGET_PASSED_BEFORE_ENTRY",
                    events=(bar.event_id,),
                    complete=bar.complete,
                )
            continue
        if target_hit and stop_hit:
            return _outcome(
                candidate,
                decision,
                target_index,
                "AMBIGUOUS",
                "TARGET_AND_STOP_WITHIN_SAME_BAR",
                events=(bar.event_id,),
                complete=bar.complete,
            )
        if target_hit or stop_hit:
            return _outcome(
                candidate,
                decision,
                target_index,
                "TARGET_BEFORE_STOP" if target_hit else "STOP_BEFORE_TARGET",
                "OHLC_PATH_WITHOUT_EXECUTABLE_FILL",
                events=(bar.event_id,),
                complete=bar.complete,
            )
    return _outcome(
        candidate, decision, target_index, "INCOMPLETE", "OHLC_PATH_INCOMPLETE", complete=False
    )


def purged_folds(
    opportunities: Iterable[OpportunityRecord],
    *,
    fold_count: int,
    embargo_seconds: int = 0,
    holdout_start: datetime | None = None,
) -> list[dict[str, tuple[str, ...]]]:
    """Chronological grouped folds; revisions/arms never cross partitions."""
    if fold_count < 2:
        raise ValueError("At least two folds are required")
    grouped: dict[str, list[OpportunityRecord]] = defaultdict(list)
    for row in opportunities:
        grouped[row.opportunity_id].append(row)
    groups = sorted(grouped.items(), key=lambda pair: min(x.observed_at_utc for x in pair[1]))
    holdout = [
        item
        for item in groups
        if holdout_start is not None and min(x.observed_at_utc for x in item[1]) >= holdout_start
    ]
    holdout_crossing = [
        item
        for item in groups
        if holdout_start is not None
        and item not in holdout
        and max(x.label_information_end_utc for x in item[1]) >= holdout_start
    ]
    groups = [item for item in groups if item not in holdout and item not in holdout_crossing]
    if len(groups) < fold_count:
        raise ValueError("Insufficient opportunity groups for requested folds")
    folds: list[dict[str, tuple[str, ...]]] = []
    for fold in range(fold_count):
        start = len(groups) * fold // fold_count
        end = len(groups) * (fold + 1) // fold_count
        test = groups[start:end]
        test_start = min(x.label_information_start_utc for _, rows in test for x in rows)
        test_end = max(x.label_information_end_utc for _, rows in test for x in rows)
        embargo = timedelta(seconds=embargo_seconds)
        train = []
        purged = []
        for opportunity_id, rows in groups[:start]:
            overlaps = any(
                row.label_information_start_utc <= test_end + embargo
                and row.label_information_end_utc >= test_start - embargo
                for row in rows
            )
            (purged if overlaps else train).append(opportunity_id)
        for opportunity_id, rows in groups[end:]:
            overlaps = any(
                row.label_information_start_utc <= test_end + embargo
                and row.label_information_end_utc >= test_start - embargo
                for row in rows
            )
            if overlaps:
                purged.append(opportunity_id)
        folds.append(
            {
                "train": tuple(train),
                "test": tuple(key for key, _ in test),
                "purged": tuple(purged + [key for key, _ in holdout_crossing]),
                "holdout": tuple(key for key, _ in holdout),
                "future": tuple(key for key, _ in groups[end:] if key not in purged),
            }
        )
    return folds


def arm_metrics(opportunities: Iterable[OpportunityRecord]) -> dict[str, dict]:
    """Preserve abstention denominators and mark small samples insufficient."""
    by_arm: dict[str, list[ArmRecord]] = defaultdict(list)
    total = 0
    for opportunity in opportunities:
        total += 1
        for arm in opportunity.arms:
            by_arm[arm.arm].append(arm)
    result: dict[str, dict] = {}
    for arm, records in sorted(by_arm.items()):
        outcomes = [row.outcome for row in records if row.outcome is not None]
        complete_records = [
            row
            for row in records
            if row.outcome is not None
            and row.outcome.data_complete
            and row.outcome.net_pnl is not None
        ]
        complete = [row.outcome for row in complete_records if row.outcome is not None]
        gains = sum((row.net_pnl for row in complete if row.net_pnl > 0), Decimal(0))
        losses = -sum((row.net_pnl for row in complete if row.net_pnl < 0), Decimal(0))
        known_abstentions = [
            row
            for row in records
            if row.state in {"REJECTED", "WAIT", "NO_ENTRY"}
            and (row.outcome is None or row.outcome.code == "NO_ENTRY")
        ]
        unresolved = [
            row
            for row in records
            if row.state != "UNAVAILABLE"
            and row not in known_abstentions
            and (row.outcome is None or not row.outcome.data_complete)
        ]
        model_cost = sum(
            (Decimal(row.attributable_cost_microusd) / Decimal(1_000_000) for row in records),
            Decimal(0),
        )
        operational_pnl = sum((row.net_pnl for row in complete), Decimal(0)) - sum(
            (
                Decimal(row.attributable_cost_microusd) / Decimal(1_000_000)
                for row in complete_records + known_abstentions
            ),
            Decimal(0),
        )
        result[arm] = {
            "opportunity_denominator": total,
            "observed_records": len(records),
            "unavailable": sum(row.state == "UNAVAILABLE" for row in records),
            "rejected_or_wait": sum(row.state in {"REJECTED", "WAIT"} for row in records),
            "known_no_position": len(known_abstentions),
            "unresolved": len(unresolved),
            "approved": sum(row.state in {"APPROVED", "NO_ENTRY", "EXECUTABLE"} for row in records),
            "executable": sum(row.state == "EXECUTABLE" for row in records),
            "complete_executions": len(complete),
            "latency_ms_total": sum(row.provider_latency_ms for row in records),
            "attributable_cost_microusd": sum(row.attributable_cost_microusd for row in records),
            "net_pnl": str(sum((row.net_pnl for row in complete), Decimal(0))),
            "operational_net_pnl_after_attributable_ai_cost": str(operational_pnl),
            "attributable_ai_cost_usd": str(model_cost),
            "target_before_stop": sum(row.code == "TARGET_BEFORE_STOP" for row in outcomes),
            "stop_before_target": sum(row.code == "STOP_BEFORE_TARGET" for row in outcomes),
            "time_exit": sum(row.code == "TIME_EXIT" for row in outcomes),
            "ambiguous": sum(row.code == "AMBIGUOUS" for row in outcomes),
            "incomplete": sum(row.code == "INCOMPLETE" for row in outcomes),
            "mean_favorable_excursion": (
                str(
                    sum(
                        (row.favorable_excursion or Decimal(0) for row in complete),
                        Decimal(0),
                    )
                    / len(complete)
                )
                if complete
                else None
            ),
            "mean_adverse_excursion": (
                str(
                    sum(
                        (row.adverse_excursion or Decimal(0) for row in complete),
                        Decimal(0),
                    )
                    / len(complete)
                )
                if complete
                else None
            ),
            "profit_factor": str(gains / losses) if losses > 0 else None,
            "classification": "EXPLORATORY" if len(complete) >= 30 else "INSUFFICIENT_DATA",
            "warning": "Hypothetical research output; not a probability or profitability claim.",
        }
    return result


def paired_day_block_difference(
    opportunities: Iterable[OpportunityRecord],
    baseline_arm: str,
    comparison_arm: str,
    *,
    minimum_days: int = 10,
    samples: int = 2_000,
    seed: int = 0,
) -> dict:
    """Deterministic day-block paired interval; unavailable pairs stay in the denominator."""
    day_values: dict[str, list[Decimal]] = defaultdict(list)
    denominator = 0
    paired = 0

    def operational_value(record: ArmRecord | None) -> Decimal | None:
        if record is None or record.state == "UNAVAILABLE":
            return None
        cost = Decimal(record.attributable_cost_microusd) / Decimal(1_000_000)
        if record.state in {"REJECTED", "WAIT", "NO_ENTRY"} and (
            record.outcome is None or record.outcome.code == "NO_ENTRY"
        ):
            return -cost
        if (
            record.outcome is None
            or record.outcome.net_pnl is None
            or not record.outcome.data_complete
        ):
            return None
        return record.outcome.net_pnl - cost

    for opportunity in opportunities:
        denominator += 1
        arms = {row.arm: row for row in opportunity.arms}
        baseline = arms.get(baseline_arm)
        comparison = arms.get(comparison_arm)
        baseline_value = operational_value(baseline)
        comparison_value = operational_value(comparison)
        if baseline_value is None or comparison_value is None:
            continue
        paired += 1
        day = opportunity.label_information_end_utc.date().isoformat()
        day_values[day].append(comparison_value - baseline_value)
    day_means = [sum(values, Decimal(0)) / len(values) for _, values in sorted(day_values.items())]
    if len(day_means) < minimum_days:
        return {
            "classification": "INSUFFICIENT_DATA",
            "opportunity_denominator": denominator,
            "paired_opportunities": paired,
            "independent_day_blocks": len(day_means),
            "interval": None,
        }
    random = Random(seed)
    estimates = []
    for _ in range(samples):
        selected = [random.choice(day_means) for _ in day_means]
        estimates.append(sum(selected, Decimal(0)) / len(selected))
    estimates.sort()
    return {
        "classification": "EXPLORATORY",
        "opportunity_denominator": denominator,
        "paired_opportunities": paired,
        "independent_day_blocks": len(day_means),
        "mean_difference": str(sum(day_means, Decimal(0)) / len(day_means)),
        "interval": {
            "lower_2_5_percent": str(estimates[int(samples * 0.025)]),
            "upper_97_5_percent": str(estimates[min(samples - 1, int(samples * 0.975))]),
            "method": "deterministic paired day-block bootstrap",
        },
        "warning": "Exploratory difference, not a probability or profitability claim.",
    }
