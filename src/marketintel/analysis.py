"""Canonical immutable evidence supplied independently to both AI analysts."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from marketintel.models import CandidateSignal, FeatureSnapshot, Instrument


def canonical_decimal(value: Decimal | float | int | str) -> str:
    """Return a finite, non-exponent decimal string with no insignificant zeroes."""
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Decision prices must be decimal-compatible") from exc
    if not decimal.is_finite():
        raise ValueError("Decision prices must be finite")
    normalized = format(decimal.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", ""} else normalized


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Canonical timestamps must be timezone aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Canonical values cannot contain NaN or Infinity")
        return canonical_decimal(value)
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class EvaluationSetting(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, max_length=100)
    value: str = Field(max_length=500)


class AnalysisEnvelope(BaseModel):
    """Complete immutable request evidence. Its digest is stored outside the preimage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["2"] = "2"
    candidate_id: str = Field(min_length=16)
    candidate_revision_id: str = Field(min_length=64, max_length=64)
    snapshot_id: str = Field(min_length=32)
    asset: Literal["GOLD", "BTC"]
    symbol: str = Field(min_length=1)
    venue: Literal["delta_india"] = "delta_india"
    instrument: Instrument
    engine: str
    rule_version: str
    horizon_minutes: Literal[30, 60, 240]
    direction: Literal["BULLISH", "BEARISH"]
    entry: str
    invalidation: str
    targets: tuple[str, ...] = Field(min_length=1, max_length=20)
    price_unit: str = "USD quote price per underlying unit"
    trigger: str = Field(max_length=1_000)
    feature_evidence: tuple[str, ...] = Field(max_length=100)
    counter_evidence: tuple[str, ...] = Field(max_length=100)
    feature_snapshot: FeatureSnapshot
    candle_close_utc: datetime
    observed_at_utc: datetime
    expires_at_utc: datetime
    required_context: tuple[str, ...]
    optional_context: tuple[str, ...]
    prompt_version: str
    risk_policy_version: str
    evaluation_settings: tuple[EvaluationSetting, ...] = ()

    @model_validator(mode="after")
    def identities_and_prices_match(self) -> AnalysisEnvelope:
        if self.snapshot_id != self.feature_snapshot.snapshot_id:
            raise ValueError("Envelope snapshot identity mismatch")
        if self.symbol != self.feature_snapshot.symbol or self.symbol != self.instrument.symbol:
            raise ValueError("Envelope instrument/snapshot symbol mismatch")
        if self.engine != self.feature_snapshot.engine:
            raise ValueError("Envelope engine/snapshot mismatch")
        prices = [self.entry, self.invalidation, *self.targets]
        if any(canonical_decimal(value) != value for value in prices):
            raise ValueError("Envelope prices must use canonical decimal strings")
        if self.expires_at_utc <= self.candle_close_utc:
            raise ValueError("Envelope expiry must follow candle close")
        return self


class CanonicalAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    envelope: AnalysisEnvelope
    canonical_bytes: bytes
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def digest_matches_bytes(self) -> CanonicalAnalysis:
        expected = hashlib.sha256(self.canonical_bytes).hexdigest()
        if self.digest != expected:
            raise ValueError("Analysis digest does not match canonical bytes")
        if self.canonical_bytes != canonical_json_bytes(self.envelope):
            raise ValueError("Canonical bytes do not match envelope")
        return self


def load_canonical_analysis(payload: bytes, digest: str) -> CanonicalAnalysis:
    """Rehydrate stored evidence while rechecking both canonical bytes and digest."""
    envelope = AnalysisEnvelope.model_validate_json(payload)
    return CanonicalAnalysis(envelope=envelope, canonical_bytes=payload, digest=digest)


def candidate_revision_id(candidate: CandidateSignal) -> str:
    preimage = b"candidate-revision-v2\0" + canonical_json_bytes(candidate)
    return hashlib.sha256(preimage).hexdigest()


def material_proposal_digest(candidate: CandidateSignal, snapshot: FeatureSnapshot) -> str:
    """Versioned identity for decision-relevant evidence, excluding poll-time refresh identity."""
    candidate_values = candidate.model_dump(
        mode="python", exclude={"snapshot_id", "observed_at_utc"}
    )
    snapshot_values = snapshot.model_dump(mode="python", exclude={"snapshot_id", "observed_at_utc"})
    preimage = b"material-proposal-v1\0" + canonical_json_bytes(
        {"candidate": candidate_values, "feature_snapshot": snapshot_values}
    )
    return hashlib.sha256(preimage).hexdigest()


def build_analysis_envelope(
    candidate: CandidateSignal,
    snapshot: FeatureSnapshot,
    instrument: Instrument,
    *,
    prompt_version: str = "dual-analyst-v2",
    risk_policy_version: str = "m3-risk-v1",
    required_context: Sequence[str] = (
        "verified_instrument",
        "complete_utc_session",
        "executed_trade_flow_500_5000",
        "validated_order_book_when_engine_requires_it",
    ),
    optional_context: Sequence[str] = (
        "coinglass_entitled_metrics",
        "licensed_gold_reference",
        "economic_calendar",
    ),
    evaluation_settings: Mapping[str, str] | None = None,
) -> CanonicalAnalysis:
    """Freeze one evidence object and serialize it once for both provider adapters."""
    revision_id = candidate_revision_id(candidate)
    settings = tuple(
        EvaluationSetting(key=key, value=str(value))
        for key, value in sorted((evaluation_settings or {}).items())
    )
    envelope = AnalysisEnvelope(
        candidate_id=candidate.candidate_id,
        candidate_revision_id=revision_id,
        snapshot_id=candidate.snapshot_id,
        asset=candidate.asset,
        symbol=candidate.symbol,
        venue=candidate.venue,
        instrument=copy.deepcopy(instrument),
        engine=candidate.engine,
        rule_version=candidate.rule_version,
        horizon_minutes=candidate.horizon_minutes,
        direction=candidate.direction,
        entry=canonical_decimal(candidate.entry),
        invalidation=canonical_decimal(candidate.invalidation),
        targets=tuple(canonical_decimal(target) for target in candidate.targets),
        trigger=candidate.trigger,
        feature_evidence=tuple(candidate.feature_evidence),
        counter_evidence=tuple(candidate.counter_evidence),
        feature_snapshot=copy.deepcopy(snapshot),
        candle_close_utc=candidate.candle_close_utc,
        observed_at_utc=candidate.observed_at_utc,
        expires_at_utc=candidate.expires_at_utc,
        required_context=tuple(required_context),
        optional_context=tuple(optional_context),
        prompt_version=prompt_version,
        risk_policy_version=risk_policy_version,
        evaluation_settings=settings,
    )
    payload = canonical_json_bytes(envelope)
    return CanonicalAnalysis(
        envelope=envelope,
        canonical_bytes=payload,
        digest=hashlib.sha256(payload).hexdigest(),
    )
