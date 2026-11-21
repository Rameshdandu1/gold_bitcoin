"""Typed contracts shared by connectors, deterministic calculations and the API."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Direction(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Decision(StrEnum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    WAIT = "WAIT"


class Status(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    WAIT = "WAIT"


class SignalState(StrEnum):
    """M2 research-signal states. CONFIRMED is intentionally impossible here."""

    UNAVAILABLE = "UNAVAILABLE"
    WAIT = "WAIT"
    WATCH = "WATCH"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class MarketRegime(StrEnum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class StructureKind(StrEnum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    BOS = "BOS"
    CHOCH = "CHOCH"


class DeltaAsset(BaseModel):
    """Minimal asset metadata required to interpret a Delta contract."""

    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(min_length=1)
    precision: int | None = Field(default=None, ge=0)


class DeltaProduct(BaseModel):
    """Versioned boundary contract for the public ``/v2/products`` response."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["1"] = "1"
    id: int = Field(gt=0)
    symbol: str = Field(min_length=1)
    description: str = ""
    state: str
    trading_status: str
    contract_type: str
    contract_value: Decimal = Field(gt=0)
    contract_unit_currency: str = Field(min_length=1)
    tick_size: Decimal = Field(gt=0)
    notional_type: str
    underlying_asset: DeltaAsset
    quoting_asset: DeltaAsset
    settling_asset: DeltaAsset


class Instrument(BaseModel):
    """Validated market metadata used when normalizing contract quantities."""

    schema_version: Literal["1"] = "1"
    venue: Literal["delta_india"] = "delta_india"
    product_id: int = Field(gt=0)
    symbol: str
    contract_type: Literal["futures", "perpetual_futures"]
    contract_value: Decimal = Field(gt=0)
    contract_unit_currency: str
    tick_size: Decimal = Field(gt=0)
    underlying_asset: str
    quoting_asset: str
    settling_asset: str
    notional_type: Literal["vanilla"]

    @classmethod
    def from_product(cls, product: DeltaProduct) -> "Instrument":
        if product.contract_type not in {"futures", "perpetual_futures"}:
            raise ValueError("Only linear futures/perpetual products are eligible")
        if product.state != "live" or product.trading_status != "operational":
            raise ValueError("Instrument is not live and operational")
        if product.contract_unit_currency != product.underlying_asset.symbol:
            raise ValueError("Contract unit must match the underlying asset")
        if product.notional_type != "vanilla":
            raise ValueError("Only vanilla quote-notional contracts are eligible")
        if product.settling_asset.symbol != product.quoting_asset.symbol:
            raise ValueError("Settlement asset must match the quoting asset")
        return cls(
            product_id=product.id,
            symbol=product.symbol,
            contract_type=product.contract_type,
            contract_value=product.contract_value,
            contract_unit_currency=product.contract_unit_currency,
            tick_size=product.tick_size,
            underlying_asset=product.underlying_asset.symbol,
            quoting_asset=product.quoting_asset.symbol,
            settling_asset=product.settling_asset.symbol,
            notional_type=product.notional_type,
        )

    def quote_notional(self, contracts: Decimal, price: Decimal) -> Decimal:
        """Normalize contract quantity only when units are explicitly verified."""
        if contracts < 0 or price <= 0:
            raise ValueError("Contracts must be non-negative and price must be positive")
        if self.contract_unit_currency != self.underlying_asset:
            raise ValueError("Cannot normalize an instrument with mismatched units")
        return contracts * self.contract_value * price


class InstrumentDiscovery(BaseModel):
    schema_version: Literal["1"] = "1"
    btc: Instrument | None = None
    gold: Instrument | None = None
    gold_alternatives: list[Instrument] = Field(default_factory=list)
    unavailable: dict[str, str] = Field(default_factory=dict)
    invalid_product_count: int = Field(default=0, ge=0)


class RawMarketEvent(BaseModel):
    """Immutable normalized envelope around a verbatim public feed payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    event_id: str = Field(min_length=16)
    venue: Literal["delta_india"] = "delta_india"
    symbol: str = Field(min_length=1)
    channel: Literal["trades", "ob_updates"]
    event_time_utc: datetime
    received_at_utc: datetime
    publish_time_utc: datetime | None = None
    sequence: int | None = Field(default=None, ge=0)
    checksum: int | None = Field(default=None, ge=0, le=4_294_967_295)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def timestamps_are_aware(self) -> "RawMarketEvent":
        values = [self.event_time_utc, self.received_at_utc]
        if self.publish_time_utc is not None:
            values.append(self.publish_time_utc)
        if any(value.tzinfo is None or value.utcoffset() is None for value in values):
            raise ValueError("Raw event timestamps must be timezone aware")
        return self


class TradeRecord(BaseModel):
    event_id: str
    symbol: str
    price: Decimal = Field(gt=0)
    contracts: Decimal = Field(gt=0)
    aggressor: Literal["BUY", "SELL"] | None
    event_time_utc: datetime
    received_at_utc: datetime
    publish_time_utc: datetime | None = None


class TradeWindow(BaseModel):
    symbol: str
    requested_size: int = Field(gt=0)
    trade_count: int = Field(ge=0)
    classified_trade_count: int = Field(ge=0)
    unclassified_trade_count: int = Field(ge=0)
    buy_contracts: Decimal = Decimal("0")
    sell_contracts: Decimal = Decimal("0")
    delta_contracts: Decimal = Decimal("0")
    elapsed_seconds: Decimal = Decimal("0")


class LiquidityLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    kind: Literal[
        "SWING_HIGH",
        "SWING_LOW",
        "SESSION_HIGH",
        "SESSION_LOW",
        "PREVIOUS_DAY_HIGH",
        "PREVIOUS_DAY_LOW",
    ]
    price: Decimal = Field(gt=0)
    observed_at_utc: datetime
    source: str
    touches: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "LiquidityLevel":
        if self.observed_at_utc.tzinfo is None or self.observed_at_utc.utcoffset() is None:
            raise ValueError("Liquidity level timestamp must be timezone aware")
        return self


class FlowWindow(BaseModel):
    """Normalized executed-trade flow for an exact count or event-time window."""

    model_config = ConfigDict(frozen=True)

    label: str
    requested_trade_count: int | None = Field(default=None, gt=0)
    window_seconds: int | None = Field(default=None, gt=0)
    trade_count: int = Field(ge=0)
    classified_trade_count: int = Field(ge=0)
    unclassified_trade_count: int = Field(ge=0)
    elapsed_seconds: Decimal = Field(default=Decimal("0"), ge=0)
    trades_per_second: Decimal = Field(default=Decimal("0"), ge=0)
    latest_event_time_utc: datetime | None = None
    latest_received_at_utc: datetime | None = None
    buy_contracts: Decimal = Field(default=Decimal("0"), ge=0)
    sell_contracts: Decimal = Field(default=Decimal("0"), ge=0)
    unclassified_contracts: Decimal = Field(default=Decimal("0"), ge=0)
    cvd_contracts: Decimal = Decimal("0")
    cvd_base_units: Decimal = Decimal("0")
    cvd_quote_notional: Decimal = Decimal("0")

    @model_validator(mode="after")
    def timestamps_are_aware(self) -> "FlowWindow":
        values = [self.latest_event_time_utc, self.latest_received_at_utc]
        if any(
            value is not None and (value.tzinfo is None or value.utcoffset() is None)
            for value in values
        ):
            raise ValueError("Flow timestamps must be timezone aware")
        return self


class OrderFlowFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    last_500: FlowWindow
    last_5000: FlowWindow
    last_5m: FlowWindow
    last_15m: FlowWindow


class BookFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    available: bool
    observed_at_utc: datetime | None = None
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    spread: Decimal | None = Field(default=None, ge=0)
    bid_depth_quote: Decimal = Field(default=Decimal("0"), ge=0)
    ask_depth_quote: Decimal = Field(default=Decimal("0"), ge=0)
    imbalance: Decimal | None = Field(default=None, ge=-1, le=1)
    absorption: Literal["BUY", "SELL", "NONE", "UNKNOWN"] = "UNKNOWN"
    reason: str = ""


class VolatilityBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    atr: Decimal = Field(ge=0)
    projected_move: Decimal = Field(ge=0)
    relative_volume: Decimal | None = Field(default=None, ge=0)
    range_expansion: Decimal | None = Field(default=None, ge=0)
    method: str = "ATR horizon scaling; provisional, not a probability"


class StructureEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: StructureKind
    direction: Direction
    resolution: str = Field(min_length=1)
    level: Decimal = Field(gt=0)
    pivot_time_utc: datetime
    confirmed_at_utc: datetime
    explanation: str

    @model_validator(mode="after")
    def timestamps_are_aware_and_ordered(self) -> "StructureEvent":
        for value in (self.pivot_time_utc, self.confirmed_at_utc):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Structure timestamps must be timezone aware")
        if self.confirmed_at_utc < self.pivot_time_utc:
            raise ValueError("Structure confirmation cannot precede its pivot")
        return self


class ExternalMetric(BaseModel):
    """Source-attributed optional enrichment; never synthesized when unavailable."""

    model_config = ConfigDict(frozen=True)

    provider: str
    metric: str
    symbol: str
    value: Decimal
    unit: str
    observed_at_utc: datetime
    received_at_utc: datetime | None = None
    timestamp_basis: Literal["PROVIDER_EVENT", "INTERVAL_CLOSE", "RECEIVED_AT"]
    entitlement: str
    source_scope: str

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "ExternalMetric":
        timestamps = [self.observed_at_utc]
        if self.received_at_utc is not None:
            timestamps.append(self.received_at_utc)
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("External metric timestamps must be timezone aware")
        if self.received_at_utc is not None and self.received_at_utc < self.observed_at_utc:
            raise ValueError("External metric receive time cannot precede observation time")
        return self


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    snapshot_id: str = Field(min_length=32)
    asset: Literal["GOLD", "BTC"]
    symbol: str
    venue: Literal["delta_india"] = "delta_india"
    engine: str
    horizon_minutes: Literal[30, 60, 240]
    candle_close_utc: datetime
    observed_at_utc: datetime
    regime: MarketRegime
    structures: tuple[StructureEvent, ...] = ()
    liquidity_levels: tuple[LiquidityLevel, ...] = ()
    order_flow: OrderFlowFeatures
    book: BookFeatures
    volatility: VolatilityBudget
    vwap: Decimal | None = Field(default=None, gt=0)
    source_quality: Literal["FRESH", "STALE", "INCOMPLETE"]
    warnings: tuple[str, ...] = ()
    external_metrics: tuple[ExternalMetric, ...] = ()


class CandidateLifecycleEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    event_id: str = Field(min_length=16)
    candidate_id: str = Field(min_length=16)
    snapshot_id: str = Field(min_length=16)
    from_state: SignalState | None = None
    to_state: SignalState
    occurred_at_utc: datetime
    reason: str

    @model_validator(mode="after")
    def lifecycle_timestamp_is_aware(self) -> "CandidateLifecycleEvent":
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() is None:
            raise ValueError("Lifecycle timestamp must be timezone aware")
        return self


class Candle(BaseModel):
    symbol: str
    resolution: str
    open_time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume_contracts: float = Field(default=0, ge=0)
    source: str = "delta_india"
    available_at_utc: datetime | None = None

    @model_validator(mode="after")
    def valid_range(self) -> "Candle":
        if self.open_time.tzinfo is None or self.open_time.utcoffset() is None:
            raise ValueError("Candle timestamp must be timezone aware")
        if self.available_at_utc is not None and (
            self.available_at_utc.tzinfo is None or self.available_at_utc.utcoffset() is None
        ):
            raise ValueError("Candle availability timestamp must be timezone aware")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open/close/low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open/close/high")
        return self


class CandidateSignal(BaseModel):
    """Canonical immutable M2 research candidate; never an order or AI confirmation."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1"] = "1"
    candidate_id: str
    snapshot_id: str
    asset: Literal["GOLD", "BTC"]
    symbol: str
    venue: Literal["delta_india"] = "delta_india"
    engine: str = "LEGACY_BREAKOUT"
    horizon_minutes: Literal[30, 60, 240]
    candle_close_utc: datetime
    observed_at_utc: datetime
    expires_at_utc: datetime
    direction: Literal["BULLISH", "BEARISH"]
    state: SignalState = SignalState.CANDIDATE
    trigger: str
    entry: float = Field(gt=0)
    invalidation: float = Field(gt=0)
    targets: list[float] = Field(min_length=1)
    feature_evidence: list[str]
    counter_evidence: list[str] = Field(default_factory=list)
    explanation: str = "Deterministic research candidate; NOT AI CONFIRMED"
    source_quality: Literal["FRESH", "STALE", "INCOMPLETE"] = "FRESH"
    rule_version: str = "breakout-v0.1"
    not_ai_confirmed: Literal[True] = True

    @model_validator(mode="after")
    def validate_prices(self) -> "CandidateSignal":
        if any(
            d.tzinfo is None or d.utcoffset() is None
            for d in [self.candle_close_utc, self.observed_at_utc, self.expires_at_utc]
        ):
            raise ValueError("Candidate timestamps must be timezone aware")
        if self.expires_at_utc <= self.candle_close_utc:
            raise ValueError("Candidate expiry must be after the candle close")
        if any(target <= 0 for target in self.targets):
            raise ValueError("Candidate targets must be positive")
        if self.direction == "BULLISH":
            if not self.invalidation < self.entry or any(t <= self.entry for t in self.targets):
                raise ValueError("Invalid bullish stop or target")
        elif not self.invalidation > self.entry or any(t >= self.entry for t in self.targets):
            raise ValueError("Invalid bearish stop or target")
        if self.state is not SignalState.CANDIDATE:
            raise ValueError("CandidateSignal must be in CANDIDATE state")
        return self


# Compatibility name used by M0/M1 AI, storage and backtest modules. There is one canonical model,
# not a divergent legacy candidate contract.
Candidate = CandidateSignal


class DetectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine: str
    state: SignalState
    observed_at_utc: datetime
    reason: str
    snapshot: FeatureSnapshot | None = None
    candidate: CandidateSignal | None = None

    @model_validator(mode="after")
    def state_matches_candidate(self) -> "DetectionResult":
        if (self.state is SignalState.CANDIDATE) != (self.candidate is not None):
            raise ValueError("Only CANDIDATE results may contain a candidate")
        return self


class AnalystAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    decision: Literal["CONFIRM", "REJECT", "WAIT"]
    supported_target_indices: list[int]
    reason: str
    counter_evidence: list[str]
    data_warnings: list[str]


class ConsensusResult(BaseModel):
    candidate_id: str
    snapshot_id: str
    status: Status
    reason: str
    supported_target_indices: list[int] = Field(default_factory=list)
    evaluated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EngineDescriptor(BaseModel):
    id: str
    asset: str
    symbol: str
    resolution: str
    horizon_minutes: int
    state: str = "WAITING_FOR_DATA"
