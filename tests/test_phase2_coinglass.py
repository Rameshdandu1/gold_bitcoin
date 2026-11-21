from datetime import UTC, datetime, timedelta

import httpx
import pytest

from marketintel.coinglass import CoinGlassPlan, CoinGlassUnavailable, CoinGlassV4
from marketintel.reference import FixtureGoldReference, UnavailableGoldReference


@pytest.mark.asyncio
async def test_missing_subscription_never_calls_professional_liquidation_endpoint():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"code": "0", "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = CoinGlassV4("fixture-key", plan="HOBBYIST", client=client)
        with pytest.raises(CoinGlassUnavailable, match="PROFESSIONAL"):
            await adapter.liquidation_map(symbol="BTC")
    assert calls == []


@pytest.mark.asyncio
async def test_btc_context_uses_closed_funding_and_tags_cross_exchange_scope():
    as_of = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    responses = {
        "/api/futures/supported-coins": ["BTC", "ETH"],
        "/api/futures/supported-exchange-pairs": {"Binance": ["BTCUSDT"]},
        "/api/futures/open-interest/exchange-list": [
            {"exchange": "All", "symbol": "BTC", "open_interest_usd": 123456}
        ],
        "/api/futures/funding-rate/oi-weight-history": [
            {
                "time": int((as_of - timedelta(hours=8)).timestamp() * 1000),
                "open": "0.01",
                "high": "0.02",
                "low": "0.00",
                "close": "0.015",
            },
            {
                "time": int((as_of - timedelta(hours=2)).timestamp() * 1000),
                "open": "9",
                "high": "9",
                "low": "9",
                "close": "9",
            },
        ],
    }

    def handler(request):
        return httpx.Response(200, json={"code": "0", "data": responses[request.url.path]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        context = await CoinGlassV4(
            "fixture-key", plan=CoinGlassPlan.HOBBYIST, client=client, clock=lambda: as_of
        ).btc_context(as_of=as_of)
    assert context.status == "AVAILABLE"
    assert context.delta_exchange_covered is False
    assert {metric.metric for metric in context.metrics} == {
        "open_interest_usd",
        "oi_weighted_funding_rate_close",
    }
    funding = next(
        metric for metric in context.metrics if metric.metric == "oi_weighted_funding_rate_close"
    )
    open_interest = next(
        metric for metric in context.metrics if metric.metric == "open_interest_usd"
    )
    assert str(funding.value) == "0.015"
    assert funding.unit == "percent"
    assert funding.timestamp_basis == "INTERVAL_CLOSE"
    assert funding.received_at_utc == as_of
    assert open_interest.timestamp_basis == "RECEIVED_AT"
    assert open_interest.observed_at_utc == as_of
    assert all(metric.source_scope == "cross_exchange_aggregate" for metric in context.metrics)
    assert "Delta India coverage" in context.warnings[0]


@pytest.mark.asyncio
async def test_unsupported_btc_never_calls_metric_endpoints():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"code": "0", "data": ["ETH"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        context = await CoinGlassV4("fixture-key", client=client).btc_context(
            as_of=datetime(2026, 11, 21, tzinfo=UTC)
        )
    assert context.status == "UNAVAILABLE"
    assert paths == ["/api/futures/supported-coins"]


@pytest.mark.asyncio
async def test_supported_coin_without_supported_btc_pair_never_calls_metrics():
    paths = []
    responses = {
        "/api/futures/supported-coins": ["BTC"],
        "/api/futures/supported-exchange-pairs": {"Binance": ["ETHUSDT"]},
    }

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"code": "0", "data": responses[request.url.path]})

    as_of = datetime(2026, 11, 21, tzinfo=UTC)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        context = await CoinGlassV4("fixture-key", client=client, clock=lambda: as_of).btc_context(
            as_of=as_of
        )
    assert context.status == "UNAVAILABLE"
    assert paths == [
        "/api/futures/supported-coins",
        "/api/futures/supported-exchange-pairs",
    ]


@pytest.mark.asyncio
async def test_reference_provider_is_unavailable_by_default_and_fixture_is_labelled():
    now = datetime(2026, 11, 21, tzinfo=UTC)
    unavailable = await UnavailableGoldReference().snapshot(as_of=now)
    assert unavailable.status == "UNAVAILABLE"
    assert unavailable.metrics == ()

    fixture = FixtureGoldReference(xau_usd=123, observed_at=now)
    available = await fixture.snapshot(as_of=now)
    assert available.status == "AVAILABLE"
    assert available.metrics[0].provider == "TEST_FIXTURE_NOT_LIVE"
