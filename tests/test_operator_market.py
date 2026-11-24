"""Local observability contracts; fixtures do not call providers or exchanges."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.delta import parse_trade_message
from marketintel.models import CandidateSignal, SignalState
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
