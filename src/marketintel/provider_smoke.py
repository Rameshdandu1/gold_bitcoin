"""Bounded, explicitly authorized paid-provider connectivity smoke test."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from marketintel.ai import (
    ClaudeAnalyst,
    GPTAnalyst,
    ProviderAdapter,
    provider_request_input_token_upper_bound,
)
from marketintel.analysis import CanonicalAnalysis, build_analysis_envelope
from marketintel.config import Settings
from marketintel.models import (
    BookFeatures,
    CandidateSignal,
    CoverageWindow,
    FeatureSnapshot,
    FlowWindow,
    Instrument,
    MarketRegime,
    OrderFlowFeatures,
    VolatilityBudget,
)
from marketintel.review import ProviderResult
from marketintel.storage import Store

SMOKE_MARKER = "SYNTHETIC_PROVIDER_CONNECTIVITY_SMOKE_NOT_MARKET_SIGNAL"


def smoke_analysis(now: datetime) -> CanonicalAnalysis:
    """Build strict synthetic evidence solely to validate provider schema connectivity."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Smoke-test time must be timezone aware")
    now = now.astimezone(UTC)
    candidate = CandidateSignal(
        candidate_id="operational-provider-smoke-v1",
        snapshot_id=hashlib.sha256(f"provider-smoke|{now.date()}".encode()).hexdigest(),
        asset="GOLD",
        symbol="XAUTUSD",
        engine="GOLD_FAST",
        horizon_minutes=30,
        candle_close_utc=now,
        observed_at_utc=now,
        expires_at_utc=now + timedelta(minutes=30),
        direction="BULLISH",
        trigger=SMOKE_MARKER,
        entry=2600,
        invalidation=2590,
        targets=(2610,),
        feature_evidence=(SMOKE_MARKER,),
        counter_evidence=("No live market inference is permitted from this payload",),
        source_quality="FRESH",
        rule_version="operational-smoke-v1",
    )
    window = FlowWindow(
        label="synthetic-smoke",
        requested_trade_count=500,
        trade_count=500,
        classified_trade_count=500,
        unclassified_trade_count=0,
    )
    coverage = CoverageWindow(
        name="TRIGGER",
        required=True,
        complete=True,
        expected_start_utc=now - timedelta(minutes=1),
        expected_end_utc=now,
        actual_start_utc=now - timedelta(minutes=1),
        actual_end_utc=now,
        candle_count=1,
        reason=SMOKE_MARKER,
    )
    snapshot = FeatureSnapshot(
        snapshot_id=candidate.snapshot_id,
        asset="GOLD",
        symbol="XAUTUSD",
        engine="GOLD_FAST",
        horizon_minutes=30,
        candle_close_utc=now,
        observed_at_utc=now,
        regime=MarketRegime.RANGING,
        order_flow=OrderFlowFeatures(
            last_500=window,
            last_5000=window.model_copy(
                update={"requested_trade_count": 5000, "trade_count": 5000}
            ),
            last_5m=window.model_copy(
                update={"requested_trade_count": None, "window_seconds": 300}
            ),
            last_15m=window.model_copy(
                update={"requested_trade_count": None, "window_seconds": 900}
            ),
        ),
        book=BookFeatures(
            available=True,
            observed_at_utc=now,
            best_bid=Decimal("2599.9"),
            best_ask=Decimal("2600.1"),
            spread=Decimal("0.2"),
            reason=SMOKE_MARKER,
        ),
        volatility=VolatilityBudget(
            atr=Decimal("5"),
            projected_move=Decimal("10"),
            relative_volume=Decimal("1"),
            range_expansion=Decimal("1"),
        ),
        coverage=(coverage,),
        source_quality="FRESH",
        warnings=(SMOKE_MARKER,),
    )
    instrument = Instrument(
        product_id=131253,
        symbol="XAUTUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency="XAUT",
        tick_size=Decimal("0.01"),
        underlying_asset="XAUT",
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )
    return build_analysis_envelope(
        candidate,
        snapshot,
        instrument,
        required_context=(SMOKE_MARKER,),
        optional_context=(),
        evaluation_settings={"purpose": SMOKE_MARKER},
    )


def _rates(settings: Settings, provider: str) -> tuple[int, int]:
    values = (
        (
            settings.openai_input_microusd_per_million_tokens,
            settings.openai_output_microusd_per_million_tokens,
        )
        if provider == "OPENAI"
        else (
            settings.anthropic_input_microusd_per_million_tokens,
            settings.anthropic_output_microusd_per_million_tokens,
        )
    )
    if values[0] is None or values[1] is None:
        raise ValueError(f"{provider} pricing is not configured")
    return int(values[0]), int(values[1])


def _cost_microusd(input_tokens: int, output_tokens: int, rates: tuple[int, int]) -> int:
    return math.ceil((input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000)


def _safe_reference(value: str | None) -> str | None:
    return hashlib.sha256(value.encode()).hexdigest()[:16] if value else None


async def run_provider_smoke(
    settings: Settings,
    store: Store,
    *,
    now: datetime,
    adapters: tuple[ProviderAdapter, ProviderAdapter] | None = None,
) -> dict[str, Any]:
    """Reserve the durable daily budget, then call each provider at most once."""
    if settings.ai_total_cost_limit_microusd_per_day <= 0:
        raise ValueError("A positive combined daily AI cost limit is required")
    if settings.ai_provider_call_limit_per_day < 1 or settings.ai_total_call_limit_per_day < 2:
        raise ValueError("Smoke test requires one call per provider and two combined calls")
    enabled = settings.model_copy(update={"ai_enabled": True})
    analysis = smoke_analysis(now)
    adapters = adapters or (GPTAnalyst(enabled), ClaudeAnalyst(enabled))
    input_bound = provider_request_input_token_upper_bound(analysis)
    if input_bound > enabled.ai_max_input_tokens:
        raise ValueError("Smoke request exceeds the configured input-token ceiling")
    run_id = f"operational-smoke-v1-{now.astimezone(UTC).date()}"

    async def call(adapter: ProviderAdapter) -> dict[str, Any]:
        if not adapter.api_key or not adapter.requested_model:
            return {
                "provider": adapter.provider,
                "status": "PROVIDER_CONFIGURATION_MISSING",
                "requested_model": adapter.requested_model,
            }
        rates = _rates(enabled, adapter.provider)
        estimated_cost = _cost_microusd(
            input_bound,
            enabled.ai_max_output_tokens,
            rates,
        )
        reservation = store.reserve_provider_budget(
            run_id=run_id,
            provider=adapter.provider,
            attempt_number=1,
            now=now,
            input_tokens=input_bound,
            output_tokens=enabled.ai_max_output_tokens,
            cost_microusd=estimated_cost,
            provider_call_limit=enabled.ai_provider_call_limit_per_day,
            total_call_limit=enabled.ai_total_call_limit_per_day,
            total_cost_limit_microusd=enabled.ai_total_cost_limit_microusd_per_day,
        )
        if reservation is None:
            return {
                "provider": adapter.provider,
                "status": "BUDGET_OR_CALL_LIMIT_BLOCKED",
                "requested_model": adapter.requested_model,
                "estimated_cost_microusd": estimated_cost,
            }
        deadline = now + timedelta(seconds=enabled.ai_total_deadline_seconds)
        result: ProviderResult = await adapter.review(
            analysis,
            deadline_at=deadline,
            attempt_number=1,
        )
        actual_cost = None
        if result.usage.input_tokens is not None and result.usage.output_tokens is not None:
            actual_cost = _cost_microusd(
                result.usage.input_tokens,
                result.usage.output_tokens,
                rates,
            )
        store.reconcile_provider_budget(
            reservation,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            actual_cost_microusd=actual_cost,
            status="RECONCILED" if actual_cost is not None else "USAGE_UNKNOWN",
            now=result.completed_at_utc,
        )
        return {
            "provider": adapter.provider,
            "status": result.status,
            "failure_code": result.failure_code,
            "requested_model": result.requested_model,
            "returned_model": result.returned_model,
            "request_reference": _safe_reference(result.request_id),
            "response_reference": _safe_reference(result.response_id),
            "finish_reason": result.finish_reason,
            "latency_ms": result.latency_ms,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "actual_cost_microusd": actual_cost,
            "schema_valid": result.status == "SUCCEEDED",
        }

    results = await asyncio.gather(*(call(adapter) for adapter in adapters))
    return {
        "evidence_type": SMOKE_MARKER,
        "analysis_input_hash": analysis.digest,
        "started_at_utc": now.astimezone(UTC).isoformat(),
        "daily_cost_limit_microusd": enabled.ai_total_cost_limit_microusd_per_day,
        "results": list(results),
        "both_succeeded": all(row["status"] == "SUCCEEDED" for row in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--authorize-paid-smoke",
        action="store_true",
        help="required acknowledgement; performs at most one paid call per provider",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.authorize_paid_smoke:
        raise SystemExit("Refusing paid calls without --authorize-paid-smoke")
    settings = Settings()
    evidence = asyncio.run(
        run_provider_smoke(settings, Store(settings.database_path), now=datetime.now(UTC))
    )
    payload = json.dumps(evidence, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    raise SystemExit(0 if evidence["both_succeeded"] else 2)


if __name__ == "__main__":
    main()
