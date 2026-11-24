"""Read-only local operator diagnostics; never makes external requests or confirms signals."""

import re
from datetime import UTC, datetime, timedelta

from marketintel.config import Settings
from marketintel.delta import DeltaDataIntegrityError
from marketintel.detectors import describe_engines
from marketintel.features import resample_closed_candles
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


def operator_candles(
    store: Store,
    settings: Settings,
    *,
    asset: str,
    resolution: str,
    limit: int,
    now: datetime,
) -> dict:
    """Bounded chart data derived only from immutable REST observations."""
    sources = {row["source"]: row for row in store.all_source_health()}
    discovery = sources.get(f"product_discovery:{asset}", {})
    match = re.fullmatch(r"verified ([A-Z0-9_-]+) product metadata", discovery.get("detail", ""))
    symbol = (
        match.group(1)
        if match
        else settings.gold_symbol
        if asset == "GOLD"
        else settings.btc_symbol
    )
    base = store.latest_rest_candles(symbol=symbol, resolution="1m", through=now, limit=3000)
    if resolution == "1m":
        series = base
    else:
        series = resample_closed_candles(base, target_resolution=resolution, through=now)
    series = series[-limit:]
    day_start = datetime.combine(now.astimezone(UTC).date(), datetime.min.time(), tzinfo=UTC)
    previous_close_time = day_start - timedelta(minutes=1)
    today = [candle for candle in base if candle.open_time >= day_start]
    previous_close = next(
        (candle.close for candle in reversed(base) if candle.open_time == previous_close_time), None
    )
    daily_open = next((candle.open for candle in today if candle.open_time == day_start), None)
    latest_close = today[-1].close if today else None
    change = (
        latest_close - previous_close
        if latest_close is not None and previous_close is not None
        else None
    )
    change_percent = (
        change / previous_close * 100 if change is not None and previous_close else None
    )
    daily_state = (
        "AVAILABLE"
        if today and daily_open is not None and previous_close is not None
        else "INCOMPLETE"
    )
    return {
        "asset": asset,
        "symbol": symbol,
        "resolution": resolution,
        "data_state": "AVAILABLE" if series else "UNAVAILABLE",
        "candles": [candle.model_dump(mode="json") for candle in series],
        "daily": {
            "state": daily_state if base else "UNAVAILABLE",
            "session_date_utc": day_start.date().isoformat(),
            "open": daily_open,
            "previous_close": previous_close,
            "high": max((candle.high for candle in today), default=None),
            "low": min((candle.low for candle in today), default=None),
            "latest_close": latest_close,
            "change": change,
            "change_percent": change_percent,
        },
        "warning": (
            "Observed Delta candles; unavailable fields are not inferred."
            if base
            else "No factual REST candle observation is available."
        ),
    }


def operator_settings(settings: Settings) -> dict:
    """Return operator-safe configuration metadata; never return secret values."""
    return {
        "features": {
            "live_ingestion_enabled": settings.live_ingestion_enabled,
            "ai_enabled": settings.ai_enabled,
            "alerts_enabled": settings.alerts_enabled,
            "paper_collection_enabled": settings.paper_collection_enabled,
            "trading_enabled": False,
        },
        "models": {
            "openai": settings.openai_model or None,
            "anthropic": settings.anthropic_model or None,
        },
        "providers": {
            "openai_configured": bool(settings.openai_api_key and settings.openai_model),
            "anthropic_configured": bool(settings.anthropic_api_key and settings.anthropic_model),
            "coinglass_enabled": settings.coinglass_enabled,
            "coinglass_configured": bool(settings.coinglass_api_key),
        },
        "notifications": {
            "dashboard_only_supported": True,
            "slack_configured": bool(
                settings.slack_bot_token.get_secret_value() and settings.slack_channel_id
            ),
            "external_notifications_enabled": settings.alerts_enabled,
        },
        "limits": {
            "daily_ai_budget_microusd": settings.ai_total_cost_limit_microusd_per_day,
            "daily_ai_call_limit": settings.ai_total_call_limit_per_day,
            "provider_call_limit": settings.ai_provider_call_limit_per_day,
            "provider_deadline_seconds": settings.ai_total_deadline_seconds,
        },
        "market_data": {
            "book_max_age_seconds": settings.delta_book_max_age_seconds,
            "reconciliation_max_age_seconds": settings.delta_reconciliation_max_age_seconds,
            "persistence_queue_size": settings.delta_persistence_queue_size,
            "persistence_batch_size": settings.delta_persistence_batch_size,
        },
        "risk": {
            "fee_bps": settings.risk_fee_bps or None,
            "slippage_bps": settings.risk_slippage_bps or None,
            "maximum_entry_drift_bps": settings.risk_maximum_entry_drift_bps,
            "maximum_spread_bps": settings.risk_maximum_spread_bps,
            "minimum_net_reward_risk": settings.risk_minimum_net_reward_risk,
        },
    }
