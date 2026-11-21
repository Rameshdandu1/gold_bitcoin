"""Entitlement-gated CoinGlass V4 enrichment; unavailable access fails closed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import IntEnum
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from marketintel.models import ExternalMetric


class CoinGlassError(Exception):
    pass


class CoinGlassUnavailable(CoinGlassError):
    pass


class CoinGlassPlan(IntEnum):
    HOBBYIST = 1
    STARTUP = 2
    STANDARD = 3
    PROFESSIONAL = 4
    ENTERPRISE = 5

    @classmethod
    def parse(cls, value: str) -> CoinGlassPlan:
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ValueError("Unknown CoinGlass plan") from exc


class CoinGlassContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    metrics: tuple[ExternalMetric, ...] = ()
    warnings: tuple[str, ...] = ()
    delta_exchange_covered: bool = False


_ENDPOINT_PLAN = {
    "/api/futures/supported-coins": CoinGlassPlan.HOBBYIST,
    "/api/futures/supported-exchanges": CoinGlassPlan.HOBBYIST,
    "/api/futures/supported-exchange-pairs": CoinGlassPlan.HOBBYIST,
    "/api/futures/open-interest/exchange-list": CoinGlassPlan.HOBBYIST,
    "/api/futures/funding-rate/oi-weight-history": CoinGlassPlan.HOBBYIST,
    "/api/futures/liquidation/map": CoinGlassPlan.PROFESSIONAL,
}

_PLAN_MIN_INTERVAL = {
    CoinGlassPlan.HOBBYIST: "4h",
    CoinGlassPlan.STARTUP: "30m",
    CoinGlassPlan.STANDARD: "1m",
    CoinGlassPlan.PROFESSIONAL: "1m",
    CoinGlassPlan.ENTERPRISE: "1m",
}

_INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1_800,
    "1h": 3_600,
    "2h": 7_200,
    "4h": 14_400,
    "6h": 21_600,
    "8h": 28_800,
    "12h": 43_200,
    "1d": 86_400,
}


class CoinGlassV4:
    def __init__(
        self,
        key: str,
        base_url: str = "https://open-api-v4.coinglass.com",
        *,
        plan: CoinGlassPlan | str = CoinGlassPlan.HOBBYIST,
        client: httpx.AsyncClient | None = None,
        retries: int = 2,
        clock: Callable[[], datetime] | None = None,
    ):
        if not key:
            raise ValueError("COINGLASS_API_KEY required when enabled")
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.plan = CoinGlassPlan.parse(plan) if isinstance(plan, str) else plan
        self.client = client
        self.retries = retries
        self.clock = clock or (lambda: datetime.now(UTC))

    def _require_entitlement(self, path: str) -> None:
        required = _ENDPOINT_PLAN.get(path)
        if required is None:
            raise ValueError("CoinGlass endpoint must be explicitly allow-listed")
        if self.plan < required:
            raise CoinGlassUnavailable(f"CoinGlass {required.name} entitlement required for {path}")

    async def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/api/") or ".." in path:
            raise ValueError("Only explicit CoinGlass /api/ endpoint paths permitted")
        self._require_entitlement(path)
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=12)
        try:
            for attempt in range(self.retries + 1):
                response = await client.get(
                    self.base_url + path,
                    params=params,
                    headers={"CG-API-KEY": self.key, "Accept": "application/json"},
                )
                if response.status_code == 429 and attempt < self.retries:
                    retry_after = response.headers.get("Retry-After", "1")
                    try:
                        delay = min(max(float(retry_after), 0.0), 60.0)
                    except ValueError:
                        delay = 1.0
                    await asyncio.sleep(delay)
                    continue
                if response.status_code in {401, 403, 429}:
                    raise CoinGlassUnavailable("CoinGlass unavailable, unlicensed, or rate-limited")
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, dict) or str(value.get("code")) != "0":
                    raise CoinGlassUnavailable("CoinGlass unavailable, unlicensed, or rate-limited")
                return value.get("data")
            raise CoinGlassUnavailable("CoinGlass retry budget exhausted")
        finally:
            if owns_client:
                await client.aclose()

    async def supported_coins(self) -> list[str]:
        value = await self.request("/api/futures/supported-coins")
        if not isinstance(value, list):
            raise CoinGlassError("Unexpected supported-coins response")
        return [str(item).upper() for item in value]

    async def supported_exchanges(self) -> list[str]:
        value = await self.request("/api/futures/supported-exchanges")
        if not isinstance(value, list):
            raise CoinGlassError("Unexpected supported-exchanges response")
        return [str(item) for item in value]

    async def supported_exchange_pairs(self) -> dict[str, Any]:
        value = await self.request("/api/futures/supported-exchange-pairs")
        if not isinstance(value, dict):
            raise CoinGlassError("Unexpected supported-exchange-pairs response")
        return value

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CoinGlassError(f"Invalid CoinGlass {field}") from exc

    async def btc_context(self, *, as_of: datetime) -> CoinGlassContext:
        """Fetch basic-plan BTC OI/funding only; never call premium liquidation endpoints."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone aware")
        try:
            coins = await self.supported_coins()
            if "BTC" not in coins:
                return CoinGlassContext(
                    status="UNAVAILABLE", warnings=("BTC is not in supported-coins",)
                )
            pairs = await self.supported_exchange_pairs()
            exchange_names = {str(name) for name in pairs}
            btc_pair_available = any(
                "BTC" in str(pair).upper()
                for exchange_pairs in pairs.values()
                for pair in (exchange_pairs if isinstance(exchange_pairs, list) else [])
            )
            if not btc_pair_available:
                return CoinGlassContext(
                    status="UNAVAILABLE", warnings=("No BTC futures pair in supported pairs",)
                )
            delta_covered = any("delta" in name.lower() for name in exchange_names)
            oi_rows = await self.request(
                "/api/futures/open-interest/exchange-list", params={"symbol": "BTC"}
            )
            interval = _PLAN_MIN_INTERVAL[self.plan]
            funding_rows = await self.request(
                "/api/futures/funding-rate/oi-weight-history",
                params={"symbol": "BTC", "interval": interval, "limit": 3},
            )
        except CoinGlassUnavailable as exc:
            return CoinGlassContext(status="UNAVAILABLE", warnings=(str(exc),))
        if not isinstance(oi_rows, list) or not isinstance(funding_rows, list):
            return CoinGlassContext(
                status="UNAVAILABLE", warnings=("Malformed CoinGlass metric response",)
            )

        received_at = self.clock().astimezone(UTC)
        if received_at < as_of.astimezone(UTC):
            raise CoinGlassError("CoinGlass receive clock precedes request clock")
        metrics: list[ExternalMetric] = []
        total = next(
            (row for row in oi_rows if isinstance(row, dict) and row.get("exchange") == "All"),
            None,
        )
        if total and total.get("open_interest_usd") is not None:
            metrics.append(
                ExternalMetric(
                    provider="CoinGlass V4",
                    metric="open_interest_usd",
                    symbol="BTC",
                    value=self._decimal(total["open_interest_usd"], "open_interest_usd"),
                    unit="USD",
                    observed_at_utc=received_at,
                    received_at_utc=received_at,
                    timestamp_basis="RECEIVED_AT",
                    entitlement=self.plan.name,
                    source_scope="cross_exchange_aggregate",
                )
            )
        interval_seconds = _INTERVAL_SECONDS[interval]
        closed_funding = []
        for row in funding_rows:
            if not isinstance(row, dict) or row.get("time") is None:
                continue
            opened = datetime.fromtimestamp(int(row["time"]) / 1000, tz=UTC)
            if opened + timedelta(seconds=interval_seconds) <= received_at:
                closed_funding.append((opened, row))
        if closed_funding:
            opened, latest = max(closed_funding, key=lambda item: item[0])
            metrics.append(
                ExternalMetric(
                    provider="CoinGlass V4",
                    metric="oi_weighted_funding_rate_close",
                    symbol="BTC",
                    value=self._decimal(latest.get("close"), "funding close"),
                    unit="percent",
                    observed_at_utc=opened + timedelta(seconds=interval_seconds),
                    received_at_utc=received_at,
                    timestamp_basis="INTERVAL_CLOSE",
                    entitlement=self.plan.name,
                    source_scope="cross_exchange_aggregate",
                )
            )
        warnings = []
        if not delta_covered:
            warnings.append(
                "Delta India coverage was not returned; metrics are cross-venue context only"
            )
        if not metrics:
            return CoinGlassContext(
                status="UNAVAILABLE",
                warnings=tuple(warnings + ["No closed CoinGlass metrics available"]),
                delta_exchange_covered=delta_covered,
            )
        status = "AVAILABLE" if len(metrics) == 2 else "PARTIAL"
        return CoinGlassContext(
            status=status,
            metrics=tuple(metrics),
            warnings=tuple(warnings),
            delta_exchange_covered=delta_covered,
        )

    async def liquidation_map(self, *, symbol: str) -> Any:
        """Professional-only explicit opt-in; detectors never call this method implicitly."""
        return await self.request("/api/futures/liquidation/map", params={"symbol": symbol})


def unavailable_context(reason: str) -> CoinGlassContext:
    return CoinGlassContext(status="UNAVAILABLE", warnings=(reason,))
