"""Strict Phase 3 analyst response and server-owned provider result contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from marketintel.analysis import AnalysisEnvelope


class AnalystAssessmentV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2"]
    candidate_id: str
    candidate_revision_id: str
    snapshot_id: str
    analysis_input_hash: str
    asset: Literal["GOLD", "BTC"]
    symbol: str
    engine: str
    horizon_minutes: Literal[30, 60, 240]
    direction: Literal["BULLISH", "BEARISH"]
    decision: Literal["CONFIRM", "REJECT", "WAIT"]
    supported_target_indices: tuple[StrictInt, ...] = Field(max_length=20)
    agrees_with_invalidation: StrictBool
    reason: str = Field(min_length=1, max_length=1_000)
    counter_evidence: tuple[str, ...] = Field(max_length=20)
    data_warnings: tuple[str, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def semantic_contract(self) -> AnalystAssessmentV2:
        indices = self.supported_target_indices
        if len(set(indices)) != len(indices):
            raise ValueError("supported_target_indices must be unique")
        if any(index < 1 for index in indices):
            raise ValueError("supported_target_indices are 1-based positive integers")
        if self.decision == "CONFIRM":
            if not indices:
                raise ValueError("CONFIRM requires at least one supported target")
            if not self.agrees_with_invalidation:
                raise ValueError("CONFIRM requires invalidation agreement")
        elif indices:
            raise ValueError("REJECT/WAIT cannot advertise supported targets")
        return self

    def validate_for(self, envelope: AnalysisEnvelope, digest: str) -> None:
        expected = {
            "candidate_id": envelope.candidate_id,
            "candidate_revision_id": envelope.candidate_revision_id,
            "snapshot_id": envelope.snapshot_id,
            "analysis_input_hash": digest,
            "asset": envelope.asset,
            "symbol": envelope.symbol,
            "engine": envelope.engine,
            "horizon_minutes": envelope.horizon_minutes,
            "direction": envelope.direction,
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise ValueError(f"Assessment {field} does not match scheduled request")
        if any(index > len(envelope.targets) for index in self.supported_target_indices):
            raise ValueError("Assessment target index is outside the frozen target array")


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


ProviderStatus = Literal[
    "SUCCEEDED",
    "DISABLED",
    "NOT_READY",
    "TIMEOUT",
    "TRANSPORT_ERROR",
    "AUTHENTICATION_ERROR",
    "PERMISSION_ERROR",
    "RATE_LIMITED",
    "PROVIDER_ERROR",
    "UNSUPPORTED_MODEL",
    "REFUSED",
    "TRUNCATED",
    "MISSING_PARSED_OUTPUT",
    "INVALID_ASSESSMENT",
    "MODEL_MISMATCH",
    "DEADLINE_EXCEEDED",
]


class ProviderResult(BaseModel):
    """Server-owned metadata and typed outcome for exactly one provider attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2"] = "2"
    provider: Literal["OPENAI", "ANTHROPIC"]
    status: ProviderStatus
    requested_model: str
    returned_model: str | None = None
    request_id: str | None = None
    response_id: str | None = None
    sdk_version: str
    started_at_utc: datetime
    completed_at_utc: datetime
    latency_ms: int = Field(ge=0)
    attempt_number: int = Field(ge=1)
    finish_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    failure_code: str | None = None
    assessment: AnalystAssessmentV2 | None = None
    safe_metadata: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def success_requires_valid_payload(self) -> ProviderResult:
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("Provider completion cannot precede start")
        if self.status == "SUCCEEDED":
            if self.assessment is None or not self.returned_model:
                raise ValueError("Successful provider result requires assessment and model")
            if self.failure_code is not None:
                raise ValueError("Successful provider result cannot have a failure code")
        elif self.assessment is not None:
            raise ValueError("Non-success provider result cannot carry an approval assessment")
        return self


class EligibilitySnapshot(BaseModel):
    """Fresh server-owned facts read after both independent reviews complete."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    candidate_id: str
    candidate_revision_id: str
    eligibility_token: str
    active_revision_generation: int = Field(ge=1)
    lifecycle_state: Literal["CANDIDATE", "INVALIDATED", "EXPIRED"]
    evaluated_at_utc: datetime
    latest_trade_price: str
    latest_trade_at_utc: datetime
    best_bid: str
    best_ask: str
    book_observed_at_utc: datetime
    discovery_current: bool
    reconciliation_current: bool
    trade_stream_current: bool
    book_current: bool
    stop_breached: bool
    target_crossed_indices: tuple[StrictInt, ...] = ()
    event_order_ambiguous: bool = False
    required_costs_known: bool
    fee_bps: str | None = None
    slippage_bps: str | None = None
    maximum_entry_drift_bps: str
    maximum_spread_bps: str
    minimum_net_reward_risk: str
    calendar_policy: Literal["TOKEN_MARKET_ONLY", "VERIFIED_CALENDAR", "UNKNOWN"]
    notification_ready: bool = False


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    passed: bool
    detail: str


class ConsensusDecisionV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2"] = "2"
    decision_id: str
    run_id: str
    candidate_id: str
    candidate_revision_id: str
    envelope_digest: str
    status: Literal["CONFIRMED", "REJECTED", "WAIT"]
    reason: str
    supported_target_indices: tuple[StrictInt, ...] = ()
    provider_attempt_ids: tuple[str, ...]
    gates: tuple[GateResult, ...]
    eligibility: EligibilitySnapshot
    decided_at_utc: datetime
