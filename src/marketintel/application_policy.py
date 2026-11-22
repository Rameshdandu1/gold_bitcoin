"""Shared deterministic admission/lifecycle/current-market policy.

This module has no storage or transport dependencies. Production dispatch and
offline connected research both adapt their point-in-time evidence into this
contract so source loss, expiry, lifecycle, spread and entry drift cannot diverge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class ApplicationPolicyInput:
    revision_current: bool
    lifecycle_state: str
    observed_at_utc: datetime
    expires_at_utc: datetime
    evaluated_at_utc: datetime
    market_observed_at_utc: datetime
    sources_current: bool
    event_order_ambiguous: bool
    stop_breached: bool
    direction: Literal["BULLISH", "BEARISH"]
    entry: Decimal
    invalidation: Decimal
    best_bid: Decimal | None
    best_ask: Decimal | None
    maximum_spread_bps: Decimal
    maximum_entry_drift_bps: Decimal


@dataclass(frozen=True)
class PolicyCheck:
    code: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ApplicationPolicyVerdict:
    eligible: bool
    checks: tuple[PolicyCheck, ...]

    @property
    def failed_codes(self) -> tuple[str, ...]:
        return tuple(row.code for row in self.checks if not row.passed)


def executed_stop_breached(
    direction: Literal["BULLISH", "BEARISH"], invalidation: Decimal, price: Decimal
) -> bool:
    """Return the shared executed-price invalidation fact used by every workflow."""
    return price <= invalidation if direction == "BULLISH" else price >= invalidation


def current_target_feasible(
    *,
    direction: Literal["BULLISH", "BEARISH"],
    invalidation: Decimal,
    target: Decimal,
    best_bid: Decimal,
    best_ask: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
    minimum_net_reward_risk: Decimal,
) -> bool:
    """Evaluate the production/research current target economics contract."""
    quote_entry = best_ask if direction == "BULLISH" else best_bid
    risk = quote_entry - invalidation if direction == "BULLISH" else invalidation - quote_entry
    gross = target - quote_entry if direction == "BULLISH" else quote_entry - target
    costs = quote_entry * (fee_bps + slippage_bps) / Decimal("10000")
    net = gross - costs
    return risk > 0 and net > 0 and net / risk >= minimum_net_reward_risk


def evaluate_application_policy(value: ApplicationPolicyInput) -> ApplicationPolicyVerdict:
    """Evaluate the common policy using only evidence available at one clock boundary."""
    checks: list[PolicyCheck] = []

    def check(code: str, passed: bool, detail: str) -> None:
        checks.append(PolicyCheck(code, passed, detail))

    check("ACTIVE_REVISION", value.revision_current, "Candidate revision must be current")
    check(
        "LIFECYCLE",
        value.lifecycle_state == "CANDIDATE",
        f"Current lifecycle={value.lifecycle_state}",
    )
    check("EXPIRY", value.evaluated_at_utc < value.expires_at_utc, "Candidate is unexpired")
    check(
        "POINT_IN_TIME",
        value.observed_at_utc <= value.evaluated_at_utc
        and value.market_observed_at_utc <= value.evaluated_at_utc,
        "Candidate and market evidence are available at evaluation",
    )
    check("REQUIRED_SOURCES", value.sources_current, "Required market sources are current")
    check("EVENT_ORDER", not value.event_order_ambiguous, "Event ordering is unambiguous")
    check("STOP_BREACH", not value.stop_breached, "No post-observation stop breach")
    bid = value.best_bid
    ask = value.best_ask
    valid_book = bid is not None and ask is not None and ask > bid
    check("BOOK_GEOMETRY", valid_book, "Best ask must be greater than best bid")
    if valid_book:
        midpoint = (ask + bid) / Decimal("2")
        quote_entry = ask if value.direction == "BULLISH" else bid
        spread_bps = (ask - bid) / midpoint * Decimal("10000")
        drift_bps = abs(quote_entry - value.entry) / value.entry * Decimal("10000")
        risk = (
            quote_entry - value.invalidation
            if value.direction == "BULLISH"
            else value.invalidation - quote_entry
        )
        check("SPREAD", spread_bps <= value.maximum_spread_bps, f"spread_bps={spread_bps}")
        check(
            "ENTRY_DRIFT",
            drift_bps <= value.maximum_entry_drift_bps,
            f"entry_drift_bps={drift_bps}",
        )
        check("RISK_GEOMETRY", risk > 0, f"current_risk={risk}")
    else:
        for code in ("SPREAD", "ENTRY_DRIFT", "RISK_GEOMETRY"):
            check(code, False, "Validated current book is unavailable")
    return ApplicationPolicyVerdict(
        eligible=all(row.passed for row in checks), checks=tuple(checks)
    )
