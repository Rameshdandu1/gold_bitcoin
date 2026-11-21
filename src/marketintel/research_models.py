"""Versioned contracts for isolated historical and prospective research."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DataMode = Literal[
    "SYNTHETIC_FIXTURE",
    "DOWNLOADED_OHLC",
    "RECORDED_AS_OBSERVED",
    "RECORDED_PROSPECTIVE_MODEL",
    "RETROSPECTIVE_LLM_EXPLORATORY",
]
ResearchArm = Literal[
    "RULES_ONLY",
    "RULES_PLUS_GPT",
    "RULES_PLUS_CLAUDE",
    "RULES_PLUS_DUAL",
]
RESEARCH_ARMS = (
    "RULES_ONLY",
    "RULES_PLUS_GPT",
    "RULES_PLUS_CLAUDE",
    "RULES_PLUS_DUAL",
)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone aware")
    return value


class EvidenceFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_count: int = Field(ge=0)


class InstrumentVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue: str
    symbol: str
    product_id: int
    valid_from_utc: datetime
    valid_to_utc: datetime | None = None
    contract_multiplier: Decimal = Field(gt=0)
    tick_size: Decimal = Field(gt=0)
    quote_currency: str
    base_currency: str
    settlement_currency: str

    @model_validator(mode="after")
    def valid_interval(self) -> InstrumentVersion:
        _aware(self.valid_from_utc, "valid_from_utc")
        if self.valid_to_utc is not None:
            _aware(self.valid_to_utc, "valid_to_utc")
            if self.valid_to_utc <= self.valid_from_utc:
                raise ValueError("Instrument validity interval must increase")
        return self


class SourceCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    symbol: str
    start_utc: datetime
    end_utc: datetime
    record_count: int = Field(ge=0)
    gaps: tuple[tuple[datetime, datetime], ...] = ()
    sequence_valid: bool = True
    checksum_valid: bool = True
    duplicate_count: int = Field(default=0, ge=0)
    exclusions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_coverage(self) -> SourceCoverage:
        _aware(self.start_utc, "start_utc")
        _aware(self.end_utc, "end_utc")
        if self.end_utc <= self.start_utc:
            raise ValueError("Coverage interval must increase")
        for start, end in self.gaps:
            _aware(start, "gap start")
            _aware(end, "gap end")
            if end <= start or start < self.start_utc or end > self.end_utc:
                raise ValueError("Coverage gaps must be increasing and inside coverage")
        return self


class DatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    dataset_id: str = Field(min_length=8)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(min_length=7)
    rule_version: str
    feature_version: str
    created_at_utc: datetime
    data_mode: DataMode
    provenance: str
    license_notes: str
    files: tuple[EvidenceFile, ...]
    instruments: tuple[InstrumentVersion, ...]
    coverage: tuple[SourceCoverage, ...]

    @field_validator("created_at_utc")
    @classmethod
    def created_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, "created_at_utc")

    def canonical_content_hash(self) -> str:
        """Hash the complete manifest preimage without trusting its asserted digest."""
        preimage = self.model_dump(mode="json", exclude={"content_hash"})
        return _canonical_hash(preimage)

    def validate_identity(self) -> None:
        actual = self.canonical_content_hash()
        if actual != self.content_hash:
            raise ValueError(
                "Dataset manifest content_hash does not match its canonical preimage: "
                f"expected {actual}"
            )


class CostPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    policy_id: str
    quantity_contracts: Decimal = Field(gt=0)
    fee_bps_per_side: Decimal = Field(ge=0)
    slippage_bps_per_side: Decimal = Field(ge=0)
    funding_bps: Decimal | None = None
    funding_required: bool = False
    maximum_quote_gap_seconds: int = Field(default=60, ge=1)

    @model_validator(mode="after")
    def required_funding_is_known(self) -> CostPolicy:
        if self.funding_required and self.funding_bps is None:
            raise ValueError("Required funding cost must be configured")
        return self


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    experiment_id: str = Field(min_length=8)
    dataset_id: str = Field(min_length=8)
    created_at_utc: datetime
    evaluation_start_utc: datetime
    evaluation_end_utc: datetime
    evaluation_cadence_seconds: int = Field(ge=1, le=86_400)
    arms: tuple[ResearchArm, ...] = (
        "RULES_ONLY",
        "RULES_PLUS_GPT",
        "RULES_PLUS_CLAUDE",
        "RULES_PLUS_DUAL",
    )
    target_index: int = Field(default=1, ge=1)
    entry_latency_ms: int = Field(default=0, ge=0)
    maximum_entry_drift_bps: Decimal = Field(default=Decimal("10"), ge=0)
    maximum_spread_bps: Decimal = Field(default=Decimal("10"), ge=0)
    cost_policy: CostPolicy
    seed: int = 0
    trial_number: int = Field(default=1, ge=1)
    holdout_start_utc: datetime | None = None
    embargo_seconds: int = Field(default=0, ge=0)
    code_commit: str = "UNRECORDED"
    algorithm_version: str = "phase5-shared-engine-v1"
    engine_policy_version: str = "m3a-v2"
    feature_policy_version: str = "phase5-feature-state-v1"
    revision_selection_policy: Literal["LATEST_ELIGIBLE_BEFORE_OUTCOME"] = (
        "LATEST_ELIGIBLE_BEFORE_OUTCOME"
    )
    partition_policy: Literal["PAST_ONLY_PURGED_WALK_FORWARD"] = "PAST_ONLY_PURGED_WALK_FORWARD"
    fold_count: int = Field(default=3, ge=2, le=50)
    variant_id: str = "PRIMARY"

    @model_validator(mode="after")
    def valid_window(self) -> ExperimentConfig:
        for name in ("created_at_utc", "evaluation_start_utc", "evaluation_end_utc"):
            _aware(getattr(self, name), name)
        if self.evaluation_end_utc <= self.evaluation_start_utc:
            raise ValueError("Experiment evaluation window must increase")
        if len(set(self.arms)) != len(self.arms):
            raise ValueError("Research arms must be unique")
        if self.holdout_start_utc is not None:
            _aware(self.holdout_start_utc, "holdout_start_utc")
        return self

    def canonical_config_hash(self) -> str:
        """Bind all scientific choices while excluding the human experiment label."""
        preimage = self.model_dump(mode="json", exclude={"experiment_id"})
        return _canonical_hash(preimage)


class ReplayObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    observation_id: str
    kind: Literal[
        "TRADE",
        "BOOK_SNAPSHOT",
        "BOOK_DELTA",
        "CANDLE_OBSERVATION",
        "SOURCE_TRANSITION",
        "INSTRUMENT_VERSION",
        "CANDIDATE",
        "PROVIDER_COMPLETION",
        "EXECUTABLE_QUOTE",
        "EXPIRY",
    ]
    symbol: str
    venue: str
    exchange_time_utc: datetime
    available_at_utc: datetime
    persistence_sequence: int = Field(ge=0)
    payload: dict

    @model_validator(mode="after")
    def valid_times(self) -> ReplayObservation:
        _aware(self.exchange_time_utc, "exchange_time_utc")
        _aware(self.available_at_utc, "available_at_utc")
        return self


class ReplayPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluated_at_utc: datetime
    visible_observation_ids: tuple[str, ...]
    visible_count: int = Field(ge=0)
    status: Literal["ELIGIBLE", "UNAVAILABLE"]
    reason: str
    rolling_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_hash: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")


class ReplayCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    experiment_id: str
    dataset_hash: str
    config_hash: str = "0" * 64
    state_schema_version: str = "phase5-bounded-v1"
    next_evaluation_utc: datetime
    input_offset: int = Field(ge=0)
    visible_observation_ids: tuple[str, ...]
    visible_count: int = Field(default=0, ge=0)
    evidence_hash: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    input_prefix_hash: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    rolling_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    points_completed: int = Field(ge=0)


class ExecutableQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    venue: str
    symbol: str
    observed_at_utc: datetime
    available_at_utc: datetime | None = None
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def valid_quote(self) -> ExecutableQuote:
        _aware(self.observed_at_utc, "observed_at_utc")
        if self.available_at_utc is not None:
            _aware(self.available_at_utc, "available_at_utc")
        if not self.bid.is_finite() or not self.ask.is_finite() or self.ask <= self.bid:
            raise ValueError("Executable quote must have finite positive bid below ask")
        return self


class ResearchCandidate(BaseModel):
    """Frozen opportunity geometry used by every comparison arm."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    opportunity_id: str
    revision_id: str
    venue: str
    symbol: str
    product_id: int = Field(gt=0)
    asset: Literal["GOLD", "BTC"]
    engine: str
    direction: Literal["BULLISH", "BEARISH"]
    observed_at_utc: datetime
    expires_at_utc: datetime
    entry: Decimal = Field(gt=0)
    invalidation: Decimal = Field(gt=0)
    targets: tuple[Decimal, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_geometry(self) -> ResearchCandidate:
        _aware(self.observed_at_utc, "observed_at_utc")
        _aware(self.expires_at_utc, "expires_at_utc")
        if self.expires_at_utc <= self.observed_at_utc:
            raise ValueError("Candidate expiry must follow observation")
        prices = (self.entry, self.invalidation, *self.targets)
        if any(not value.is_finite() or value <= 0 for value in prices):
            raise ValueError("Candidate prices must be finite and positive")
        if self.direction == "BULLISH":
            if self.invalidation >= self.entry or any(x <= self.entry for x in self.targets):
                raise ValueError("Invalid bullish geometry")
        elif self.invalidation <= self.entry or any(x >= self.entry for x in self.targets):
            raise ValueError("Invalid bearish geometry")
        return self


class ArmDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: ResearchArm
    state: Literal["UNAVAILABLE", "REJECTED", "WAIT", "APPROVED"]
    ready_at_utc: datetime
    reason: str
    provider_latency_ms: int = Field(default=0, ge=0)
    attributable_cost_microusd: int = Field(default=0, ge=0)
    evidence_mode: DataMode | None = None
    provider: Literal["GPT", "CLAUDE", "DUAL"] | None = None
    provider_completed_at_utc: datetime | None = None
    provider_available_at_utc: datetime | None = None
    request_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    configuration_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    requested_model_id: str | None = Field(default=None, min_length=1)
    returned_model_id: str | None = Field(default=None, min_length=1)

    @field_validator("ready_at_utc")
    @classmethod
    def ready_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, "ready_at_utc")

    @model_validator(mode="after")
    def provider_times_are_aware(self) -> ArmDecision:
        if self.provider_completed_at_utc is not None:
            _aware(self.provider_completed_at_utc, "provider_completed_at_utc")
        if self.provider_available_at_utc is not None:
            _aware(self.provider_available_at_utc, "provider_available_at_utc")
        return self


class PriceBar(BaseModel):
    """Fallback OHLC evidence; simultaneous target/stop hits remain ambiguous."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    venue: str
    symbol: str
    start_utc: datetime
    end_utc: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    complete: bool = True

    @model_validator(mode="after")
    def valid_bar(self) -> PriceBar:
        _aware(self.start_utc, "start_utc")
        _aware(self.end_utc, "end_utc")
        if self.end_utc <= self.start_utc:
            raise ValueError("Bar interval must increase")
        values = (self.open, self.high, self.low, self.close)
        if any(not value.is_finite() for value in values):
            raise ValueError("Bar prices must be finite")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Bar OHLC is inconsistent")
        return self


OutcomeCode = Literal[
    "NO_ENTRY",
    "TARGET_BEFORE_STOP",
    "STOP_BEFORE_TARGET",
    "TIME_EXIT",
    "AMBIGUOUS",
    "INCOMPLETE",
]


class ResearchOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"] = "1"
    opportunity_id: str
    arm: ResearchArm
    target_index: int = Field(ge=1)
    code: OutcomeCode
    reason: str
    decision_ready_at_utc: datetime
    entry_at_utc: datetime | None = None
    exit_at_utc: datetime | None = None
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    gross_price_distance: Decimal | None = None
    gross_pnl: Decimal | None = None
    total_cost: Decimal | None = None
    net_pnl: Decimal | None = None
    net_r: Decimal | None = None
    favorable_excursion: Decimal | None = None
    adverse_excursion: Decimal | None = None
    supporting_event_ids: tuple[str, ...] = ()
    data_complete: bool
    hypothetical: Literal[True] = True
    decision_evidence_mode: DataMode | None = None
    market_data_mode: DataMode | None = None


class ArmRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: ResearchArm
    state: Literal[
        "UNAVAILABLE",
        "REJECTED",
        "WAIT",
        "APPROVED",
        "NO_ENTRY",
        "EXECUTABLE",
    ]
    decision_ready_at_utc: datetime | None = None
    provider_latency_ms: int = Field(default=0, ge=0)
    attributable_cost_microusd: int = Field(default=0, ge=0)
    evidence_mode: DataMode | None = None
    reason: str
    outcome: ResearchOutcome | None = None

    @model_validator(mode="after")
    def outcome_matches_arm(self) -> ArmRecord:
        if self.outcome is not None and self.outcome.arm != self.arm:
            raise ValueError("Outcome arm must match arm record")
        if self.state in {"UNAVAILABLE", "REJECTED", "WAIT"} and self.outcome is not None:
            if self.outcome.code not in {"NO_ENTRY", "INCOMPLETE"}:
                raise ValueError("Non-executable arm cannot carry an executed outcome")
        return self


class OpportunityRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    opportunity_id: str
    revision_id: str
    asset: Literal["GOLD", "BTC"]
    engine: str
    direction: Literal["BULLISH", "BEARISH"]
    observed_at_utc: datetime
    label_information_start_utc: datetime
    label_information_end_utc: datetime
    quantitatively_eligible: bool
    market_data_mode: DataMode | None = None
    arms: tuple[ArmRecord, ...]

    @model_validator(mode="after")
    def valid_label_interval(self) -> OpportunityRecord:
        _aware(self.observed_at_utc, "observed_at_utc")
        _aware(self.label_information_start_utc, "label_information_start_utc")
        _aware(self.label_information_end_utc, "label_information_end_utc")
        if self.label_information_end_utc < self.label_information_start_utc:
            raise ValueError("Label-information interval cannot run backward")
        if len({arm.arm for arm in self.arms}) != len(self.arms):
            raise ValueError("Opportunity arms must be unique")
        if {arm.arm for arm in self.arms} != set(RESEARCH_ARMS):
            raise ValueError("Every opportunity must preserve all four research arms")
        return self
