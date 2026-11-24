"""Local observability contracts; fixtures do not call providers or exchanges."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.delta import parse_trade_message
from marketintel.models import CandidateSignal, Candle, SignalState
from marketintel.operator_market import operator_overview
from marketintel.quantitative import lifecycle_event
from marketintel.storage import Store


def settings_for(tmp_path, *, enabled=True):
    return Settings(
        database_path=tmp_path / "market.sqlite3",
        research_database_path=tmp_path / "research.sqlite3",
        paper_database_path=tmp_path / "paper.sqlite3",
        operator_username="operator",
        operator_password="test-only-password",
        live_ingestion_enabled=enabled,
        ai_enabled=False,
    )


def trade(symbol, at, price):
    micros = int(at.timestamp() * 1_000_000)
    return parse_trade_message(
        {
            "type": "trades",
            "sy": symbol,
            "p": price,
            "s": "1",
            "r": "t",
            "t": micros,
            "ts": micros + 1000,
        },
        received_at=at + timedelta(milliseconds=2),
    )[0]


def test_overview_protected_and_empty_does_not_invent_prices(tmp_path):
    settings = settings_for(tmp_path, enabled=False)
    store = Store(settings.database_path)
    client = TestClient(create_app(settings, store))
    assert client.get("/api/market/overview").status_code == 401
    response = client.get("/api/market/overview", auth=("operator", "test-only-password"))
    assert response.status_code == 200
    result = response.json()
    assert len(result["engines"]) == 6
    assert all(row["price"] is None and row["state"] == "OFF" for row in result["markets"])
    assert all(not row["evaluation_fresh"] for row in result["engines"])
    assert result["ai_enabled"] is False
    assert "0007_operator_observability" in store.migration_ids()


def test_observed_price_and_engine_reason_then_staleness(tmp_path):
    settings = settings_for(tmp_path)
    store = Store(settings.database_path)
    now = datetime.now(UTC).replace(microsecond=0)
    store.record_source_status("worker", "AVAILABLE", "fixture", occurred_at=now)
    store.record_source_status("delta_websocket", "CONNECTED", "fixture", occurred_at=now)
    store.record_source_status(
        "product_discovery:GOLD", "AVAILABLE", "verified PAXGUSD product metadata", occurred_at=now
    )
    store.set_status("GOLD_FAST", "WAIT", "Fresh validated order book required")
    store.append_raw_event(trade("PAXGUSD", now - timedelta(seconds=2), "3601.25"))
    store.append_raw_event(trade("XAUTUSD", now - timedelta(seconds=1), "9999"))
    result = operator_overview(store, settings, now=now + timedelta(seconds=1))
    gold = result["markets"][0]
    assert gold["symbol"] == "PAXGUSD"
    assert gold["price"] == "3601.25"
    assert gold["price_state"] == "FRESH"
    assert gold["state"] == "DEGRADED"  # no valid book or reconciliation
    assert gold["book"]["best_bid"] is None
    assert gold["snapshot"] is None
    engine = next(row for row in result["engines"] if row["id"] == "GOLD_FAST")
    assert engine["detail"] == "Fresh validated order book required"
    assert engine["latest_record"] is None
    stale = operator_overview(
        store, settings, now=now + timedelta(seconds=settings.data_max_age_seconds + 10)
    )
    assert stale["markets"][0]["price_state"] == "STALE"
    assert stale["markets"][0]["state"] == "DEGRADED"


def test_history_filters_before_limit_and_validates_parameters(tmp_path):
    settings = settings_for(tmp_path, enabled=False)
    store = Store(settings.database_path)
    now = datetime.now(UTC)
    for index, (asset, horizon) in enumerate((("GOLD", 60), ("BTC", 30), ("GOLD", 30))):
        observed = now - timedelta(minutes=3 - index)
        candidate = CandidateSignal(
            candidate_id=f"operator-fixture-candidate-{index}",
            snapshot_id=str(index) * 64,
            asset=asset,
            symbol="XAUTUSD" if asset == "GOLD" else "BTCUSD",
            engine=f"{asset}_FAST" if horizon == 30 else "GOLD_HOURLY",
            horizon_minutes=horizon,
            candle_close_utc=observed,
            observed_at_utc=observed,
            expires_at_utc=observed + timedelta(minutes=horizon),
            direction="BULLISH",
            trigger="hypothetical fixture",
            entry=100,
            invalidation=95,
            targets=(110,),
            feature_evidence=("fixture",),
        )
        event = lifecycle_event(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            from_state=None,
            to_state=SignalState.CANDIDATE,
            occurred_at=observed,
            reason="hypothetical",
        )
        store.add_candidate_with_lifecycle(candidate, event)
    client = TestClient(create_app(settings, store))
    auth = ("operator", "test-only-password")
    rows = client.get("/api/candidates?asset=GOLD&horizon_minutes=60&limit=1", auth=auth)
    assert rows.status_code == 200
    assert len(rows.json()) == 1
    assert rows.json()[0]["candidate"]["candidate_id"] == "operator-fixture-candidate-0"
    assert client.get("/api/candidates?asset=UNKNOWN", auth=auth).status_code == 422
    assert client.get("/api/candidates?horizon_minutes=7", auth=auth).status_code == 422


def test_candle_endpoint_returns_factual_series_daily_stats_and_resampled_hours(tmp_path):
    settings = settings_for(tmp_path)
    store = Store(settings.database_path)
    available = datetime(2026, 11, 24, 2, 0, tzinfo=UTC)
    previous_close_time = datetime(2026, 11, 23, 23, 59, tzinfo=UTC)
    current_open = datetime(2026, 11, 24, 0, 0, tzinfo=UTC)
    candles = [
        Candle(
            symbol="XAUTUSD",
            resolution="1m",
            open_time=previous_close_time,
            open=99,
            high=101,
            low=98,
            close=100,
            volume_contracts=2,
            source="TEST_FIXTURE_NOT_LIVE",
            available_at_utc=available,
        )
    ]
    candles.extend(
        Candle(
            symbol="XAUTUSD",
            resolution="1m",
            open_time=current_open + timedelta(minutes=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume_contracts=1,
            source="TEST_FIXTURE_NOT_LIVE",
            available_at_utc=available,
        )
        for index in range(60)
    )
    store.journal_rest_candles(
        source="TEST_FIXTURE_NOT_LIVE",
        symbol="XAUTUSD",
        resolution="1m",
        request_start=previous_close_time,
        request_end=available,
        response_available_at=available,
        candles=candles,
    )
    client = TestClient(create_app(settings, store))
    auth = ("operator", "test-only-password")

    one_minute = client.get("/api/market/candles?asset=GOLD&resolution=1m&limit=100", auth=auth)
    assert one_minute.status_code == 200
    payload = one_minute.json()
    assert payload["symbol"] == "XAUTUSD"
    assert payload["data_state"] == "AVAILABLE"
    assert len(payload["candles"]) == 61
    assert payload["daily"]["open"] == 100
    assert payload["daily"]["previous_close"] == 100
    assert payload["daily"]["high"] == 161
    assert payload["daily"]["low"] == 99
    assert payload["daily"]["change"] == 60
    assert payload["daily"]["change_percent"] == 60

    hourly = client.get("/api/market/candles?asset=GOLD&resolution=1h&limit=10", auth=auth)
    assert hourly.status_code == 200
    assert len(hourly.json()["candles"]) == 1
    assert datetime.fromisoformat(hourly.json()["candles"][0]["open_time"]) == current_open


def test_candle_endpoint_reports_unavailable_instead_of_inventing_data(tmp_path):
    settings = settings_for(tmp_path)
    client = TestClient(create_app(settings, Store(settings.database_path)))
    response = client.get(
        "/api/market/candles?asset=BTC&resolution=15m", auth=("operator", "test-only-password")
    )
    assert response.status_code == 200
    assert response.json()["data_state"] == "UNAVAILABLE"
    assert response.json()["candles"] == []
    assert response.json()["daily"]["open"] is None


def test_operator_settings_endpoint_is_safe_and_slack_is_optional(tmp_path):
    settings = settings_for(tmp_path).model_copy(
        update={
            "openai_api_key": "must-not-leak",
            "anthropic_api_key": "must-not-leak",
            "openai_model": "gpt-fixture",
            "anthropic_model": "claude-fixture",
            "alerts_enabled": False,
        }
    )
    client = TestClient(create_app(settings, Store(settings.database_path)))
    response = client.get("/api/operator/settings", auth=("operator", "test-only-password"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["models"] == {"openai": "gpt-fixture", "anthropic": "claude-fixture"}
    assert payload["features"]["alerts_enabled"] is False
    assert payload["features"]["trading_enabled"] is False
    assert payload["notifications"]["dashboard_only_supported"] is True
    assert "must-not-leak" not in response.text
