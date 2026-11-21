"""Pluggable external macro/reference contract with an explicit unavailable default."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from marketintel.models import ExternalMetric


class ReferenceContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    metrics: tuple[ExternalMetric, ...] = ()
    warnings: tuple[str, ...] = ()


class GoldReferenceProvider(Protocol):
    async def snapshot(self, *, as_of: datetime) -> ReferenceContext: ...


class UnavailableGoldReference:
    """Production-safe default: no provider, no synthetic XAU/DXY/yield values."""

    async def snapshot(self, *, as_of: datetime) -> ReferenceContext:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone aware")
        return ReferenceContext(
            status="UNAVAILABLE",
            warnings=("No licensed external XAU/USD, DXY, or Treasury provider configured",),
        )


class FixtureGoldReference:
    """Test-only provider whose source and units must be explicitly supplied."""

    def __init__(
        self,
        *,
        xau_usd: Decimal,
        observed_at: datetime,
        provider: str = "TEST_FIXTURE_NOT_LIVE",
    ):
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone aware")
        self.metric = ExternalMetric(
            provider=provider,
            metric="xau_usd_reference",
            symbol="XAUUSD",
            value=xau_usd,
            unit="USD_per_troy_ounce",
            observed_at_utc=observed_at,
            received_at_utc=observed_at,
            timestamp_basis="PROVIDER_EVENT",
            entitlement="fixture",
            source_scope="test_only",
        )

    async def snapshot(self, *, as_of: datetime) -> ReferenceContext:
        if self.metric.observed_at_utc > as_of:
            return ReferenceContext(
                status="UNAVAILABLE", warnings=("Reference observation is in the future",)
            )
        return ReferenceContext(status="AVAILABLE", metrics=(self.metric,))
