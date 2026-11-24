"""Read-only local operator diagnostics; never makes external requests or confirms signals."""

import re
from datetime import datetime, timedelta

from marketintel.config import Settings
from marketintel.delta import DeltaDataIntegrityError
from marketintel.detectors import describe_engines
from marketintel.replay import replay_trade_records
from marketintel.storage import Store


def _fresh(timestamp: str | None, now: datetime, maximum_age: float) -> bool:
    if not timestamp:
        return False
    observed = datetime.fromisoformat(timestamp)
    if observed.tzinfo is None or observed.utcoffset() is None:
        return False
    return 0 <= (now - observed).total_seconds() <= maximum_age


def _status(
    sources: dict[str, dict], name: str, state: str, now: datetime, maximum_age: float
) -> bool:
    row = sources.get(name, {})
    return row.get("state") == state and _fresh(row.get("heartbeat_at_utc"), now, maximum_age)


def _market(
    store: Store, settings: Settings, sources: dict[str, dict], asset: str, now: datetime
) -> dict:
    discovery = sources.get(f"product_discovery:{asset}", {})
    # The current worker records this exact provenance string after product validation.
    # Do not silently substitute the configured preference or an older snapshot.
    match = re.fullmatch(r"verified ([A-Z0-9_-]+) product metadata", discovery.get("detail", ""))
    discovered = match.group(1) if match else None
    preferred = settings.gold_symbol if asset == "GOLD" else settings.btc_symbol
    symbol = discovered or preferred
    discovery_ok = bool(discovered) and _status(
        sources,
        f"product_discovery:{asset}",
        "AVAILABLE",
        now,
        settings.delta_discovery_max_age_seconds,
    )
    ws_connected = sources.get("delta_websocket", {}).get("state") == "CONNECTED"
    worker_current = _status(
        sources, "worker", "AVAILABLE", now, settings.delta_discovery_refresh_seconds + 60
    )
    enabled = settings.live_ingestion_enabled
    events = store.raw_events(
        symbol=symbol,
        channels=("trades",),
        end=now + timedelta(microseconds=1),
        received_end=now,
        limit=1,
    )
    try:
        records = replay_trade_records(events, symbol=symbol, through=now)
    except (DeltaDataIntegrityError, ValueError):
        records = []
    trade = records[-1] if records else None
    price_fresh = bool(
        enabled
        and discovery_ok
        and worker_current
        and ws_connected
        and trade
        and _fresh(trade.event_time_utc.isoformat(), now, settings.data_max_age_seconds)
        and _fresh(trade.received_at_utc.isoformat(), now, settings.data_max_age_seconds)
    )
    book = store.book_checkpoint(symbol)
    book_valid, book_reason = book.quality(now=now) if book else (False, "snapshot_required")
    top = book.top_of_book(now=now) if book and book_valid else None
    book_fresh = bool(
        enabled
        and discovery_ok
        and worker_current
        and ws_connected
        and book
        and top
        and _fresh(
            book.last_event_time_utc.isoformat() if book.last_event_time_utc else None,
            now,
            settings.delta_book_max_age_seconds,
        )
        and _fresh(
            book.last_received_at_utc.isoformat() if book.last_received_at_utc else None,
            now,
            settings.delta_book_max_age_seconds,
        )
        and top[0] < top[1]
    )
    reconciliation_name = f"candle_reconciliation:{symbol}"
    reconciliation_ok = _status(
        sources, reconciliation_name, "VALID", now, settings.delta_reconciliation_max_age_seconds
    )
    snapshot = store.latest_feature_snapshot(f"{asset}_FAST", symbol, through=now)
    snapshot_state = (
        "RECORDED"
        if snapshot
        and price_fresh
        and _fresh(
            snapshot.observed_at_utc.isoformat(),
            now,
            max(settings.poll_seconds * 2, settings.data_max_age_seconds),
        )
        else "STALE"
        if snapshot
        else "UNAVAILABLE"
    )
    checks = {
        "worker_current": worker_current,
        "discovery_verified": discovery_ok,
        "websocket_connected": ws_connected,
        "executed_trade_fresh": price_fresh,
        "book_fresh": book_fresh,
        "reconciliation_valid": reconciliation_ok,
    }
    state = "OFF" if not enabled else "HEALTHY" if all(checks.values()) else "DEGRADED"
    return {
        "asset": asset,
        "symbol": symbol,
        "symbol_verified": discovery_ok,
        "state": state,
        "checks": checks,
        "price": str(trade.price) if trade else None,
        "price_state": "FRESH" if price_fresh else "STALE" if trade else "UNAVAILABLE",
        "price_source": "delta_india_executed_trade",
        "price_event_time_utc": trade.event_time_utc.isoformat() if trade else None,
        "price_received_at_utc": trade.received_at_utc.isoformat() if trade else None,
        "book": {
            "state": "FRESH" if book_fresh else "UNAVAILABLE",
            "reason": book_reason
            if not book_valid
            else "valid"
            if book_fresh
            else ("source, symbol, freshness or top-of-book check failed"),
            "best_bid": str(top[0]) if book_fresh and top else None,
            "best_ask": str(top[1]) if book_fresh and top else None,
            "event_time_utc": (
                book.last_event_time_utc.isoformat() if book and book.last_event_time_utc else None
            ),
            "sequence": book.last_sequence if book else None,
        },
        "reconciliation": sources.get(reconciliation_name),
        "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
        "snapshot_state": snapshot_state,
    }


def operator_overview(store: Store, settings: Settings, *, now: datetime) -> dict:
    """A bounded read model, separate from the decision and dispatch authorization gates."""
    sources = {row["source"]: row for row in store.all_source_health()}
    engines = store.last_engine_states(describe_engines(settings.gold_symbol, settings.btc_symbol))
    markets = [_market(store, settings, sources, asset, now) for asset in ("GOLD", "BTC")]
    for engine in engines:
        market = next(row for row in markets if row["asset"] == engine["asset"])
        engine["evaluation_fresh"] = settings.live_ingestion_enabled and _fresh(
            engine.get("updated_at_utc"),
            now,
            max(settings.poll_seconds * 3, settings.data_max_age_seconds),
        )
        if engine["symbol"] != market["symbol"] or not market["symbol_verified"]:
            engine["evaluation_fresh"] = False
        rows = store.recent_candidates(
            1, asset=engine["asset"], horizon_minutes=engine["horizon_minutes"]
        )
        engine["latest_record"] = rows[0] if rows else None
    return {
        "timestamp_utc": now.isoformat(),
        "live_ingestion_enabled": settings.live_ingestion_enabled,
        "ai_enabled": settings.ai_enabled,
        "alerts_enabled": settings.alerts_enabled,
        "paper_collection_enabled": settings.paper_collection_enabled,
        "integrations": {
            "openai_configured": bool(settings.openai_api_key and settings.openai_model),
            "anthropic_configured": bool(settings.anthropic_api_key and settings.anthropic_model),
            "coinglass_enabled": settings.coinglass_enabled,
            "coinglass_configured": bool(settings.coinglass_api_key),
            "slack_configured": bool(
                settings.slack_bot_token.get_secret_value() and settings.slack_channel_id
            ),
        },
        "markets": markets,
        "engines": engines,
        "sources": list(sources.values()),
        "budget": store.budget_status(now=now),
        "queue": store.queue_status(now=now),
        "daily_ai_budget_microusd": settings.ai_total_cost_limit_microusd_per_day,
    }
