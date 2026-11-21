"""Typed contracts shared by deterministic calculations, AI and read-only API."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

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

    @model_validator(mode="after")
    def valid_range(self) -> "Candle":
        if self.open_time.tzinfo is None or self.open_time.utcoffset() is None:
            raise ValueError("Candle timestamp must be timezone aware")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open/close/low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open/close/high")
        return self


class Candidate(BaseModel):
    schema_version: Literal["1"] = "1"
    candidate_id: str
    snapshot_id: str
    asset: Literal["GOLD", "BTC"]
    symbol: str
    venue: Literal["delta_india"] = "delta_india"
    horizon_minutes: Literal[30, 60, 240]
    candle_close_utc: datetime
    observed_at_utc: datetime
    expires_at_utc: datetime
    direction: Literal["BULLISH", "BEARISH"]
    trigger: str
    entry: float = Field(gt=0)
    invalidation: float = Field(gt=0)
    targets: list[float] = Field(min_length=1)
    feature_evidence: list[str]
    source_quality: Literal["FRESH", "STALE", "INCOMPLETE"] = "FRESH"
    rule_version: str = "breakout-v0.1"

    @model_validator(mode="after")
    def validate_prices(self) -> "Candidate":
        if any(d.tzinfo is None or d.utcoffset() is None for d in [
            self.candle_close_utc, self.observed_at_utc, self.expires_at_utc
        ]):
            raise ValueError("Candidate timestamps must be timezone aware")
        if self.expires_at_utc <= self.candle_close_utc:
            raise ValueError("Candidate expiry must be after the candle close")
        if self.direction == "BULLISH":
            if not self.invalidation < self.entry or any(t <= self.entry for t in self.targets):
                raise ValueError("Invalid bullish stop or target")
        elif not self.invalidation > self.entry or any(t >= self.entry for t in self.targets):
            raise ValueError("Invalid bearish stop or target")
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
    evaluated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EngineDescriptor(BaseModel):
    id: str
    asset: str
    symbol: str
    resolution: str
    horizon_minutes: int
    state: str = "WAITING_FOR_DATA"
