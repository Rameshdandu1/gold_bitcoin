"""Windows-friendly separate worker. Public market feed; NEVER places orders."""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, independent_review
from marketintel.analysis import build_analysis_envelope, material_proposal_digest
from marketintel.coinglass import CoinGlassV4, unavailable_context
from marketintel.config import Settings
from marketintel.consensus import decide
from marketintel.delta import (
    DeltaDataIntegrityError,
    DeltaPublicStream,
    DeltaREST,
    OrderBookAssembler,
)
from marketintel.detectors import BAR_MINUTES, create_candidate
from marketintel.models import Instrument, SignalState, Status
from marketintel.orchestration import frozen_provider_config
from marketintel.quantitative import (
    QUANT_ENGINE_CONFIGS,
    QuantEngineConfig,
    detect_signal,
    lifecycle_event,
    terminal_transition,
)
from marketintel.replay import (
    aggregate_trade_candles,
    finalized_candles,
    reconcile_candles,
    replay_trade_records,
)
from marketintel.storage import Store

LOGGER = logging.getLogger(__name__)
ENGINE_CONFIGS = QUANT_ENGINE_CONFIGS
MAX_DELTA_CANDLES_PER_RESPONSE = 2_000


def _resolution(engine: object) -> str:
    return str(getattr(engine, "primary_resolution", getattr(engine, "resolution", "")))


def _engine_id(engine: object) -> str:
    return str(getattr(engine, "engine", getattr(engine, "engine_id", "unknown")))


def _market_symbol(market: str | Instrument) -> str:
    return market.symbol if isinstance(market, Instrument) else market


def _sweep_quant_candidates(
    store: Store,
    engine: QuantEngineConfig,
    *,
    now: datetime,
    source_fresh: bool,
    symbol: str | None = None,
    latest_price: Decimal | None = None,
    snapshot_id: str | None = None,
) -> None:
    """Close persisted candidates even when their required market source is unavailable."""
    for active in store.active_candidates(engine=engine.engine, symbol=symbol):
        breached = False
        for raw_event in store.candidate_trade_events(active, through=now):
            replayed = replay_trade_records([raw_event], symbol=active.symbol, through=now)
            if not replayed:
                store.advance_candidate_price_watermark(active.candidate_id, raw_event)
                continue
            trade = replayed[0]
            transition = terminal_transition(
                active,
                current_state=SignalState.CANDIDATE,
                now=max(trade.event_time_utc, trade.received_at_utc),
                latest_price=trade.price,
                source_fresh=True,
                evaluation_snapshot_id=snapshot_id,
                price_source="EXECUTED_TRADE",
                source_event_id=raw_event.event_id,
            )
            if transition is not None:
                store.record_candidate_lifecycle(transition)
                breached = True
            store.advance_candidate_price_watermark(active.candidate_id, raw_event)
            if breached:
                break
        if breached:
            continue
        transition = terminal_transition(
            active,
            current_state=SignalState.CANDIDATE,
            now=now,
            latest_price=latest_price or Decimal(str(active.entry)),
            source_fresh=source_fresh,
            evaluation_snapshot_id=snapshot_id,
            price_source="CLOSED_CANDLE" if latest_price is not None else "NONE",
        )
        if transition is not None:
            store.record_candidate_lifecycle(transition)


async def _historical_coverage(
    rest: DeltaREST,
    store: Store,
    *,
    symbol: str,
    resolution: str,
    start: datetime,
    end: datetime,
) -> list:
    """Fetch and journal complete bounded pages within Delta's documented 2,000-row limit."""
    interval = timedelta(minutes=BAR_MINUTES[resolution])
    page_span = interval * MAX_DELTA_CANDLES_PER_RESPONSE
    cursor = start
    by_open_time = {}
    while cursor < end:
        page_end = min(cursor + page_span, end)
        page = await rest.historical_candles(symbol, resolution, cursor, page_end)
        available_at = datetime.now(UTC)
        store.journal_rest_candles(
            source="delta_india_rest_v2_history_candles",
            symbol=symbol,
            resolution=resolution,
            request_start=cursor,
            request_end=page_end,
            response_available_at=available_at,
            candles=page,
        )
        for candle in page:
            by_open_time[candle.open_time] = candle
        cursor = page_end
    return [by_open_time[key] for key in sorted(by_open_time)]


def _candidate_current_price_is_eligible(candidate, trades) -> bool:
    if not trades:
        return False
    latest = max(trades, key=lambda trade: (trade.received_at_utc, trade.event_id))
    stop = Decimal(str(candidate.invalidation))
    if candidate.direction == "BULLISH":
        return latest.price > stop
    return latest.price < stop


def _sweep_all_quant_candidates(store: Store, *, now: datetime) -> None:
    for engine in ENGINE_CONFIGS:
        if isinstance(engine, QuantEngineConfig):
            _sweep_quant_candidates(store, engine, now=now, source_fresh=False)


async def poll_closed_candles(
    settings: Settings, store: Store, markets: dict[str, str | Instrument]
) -> None:
    rest = DeltaREST(settings.delta_rest_url)
    while True:
        now = datetime.now(UTC)
        coinglass = unavailable_context("CoinGlass disabled")
        if settings.coinglass_enabled:
            try:
                coinglass = await CoinGlassV4(
                    settings.coinglass_api_key,
                    settings.coinglass_base_url,
                    plan=settings.coinglass_plan,
                ).btc_context(as_of=now)
                store.record_source_status(
                    "coinglass",
                    coinglass.status,
                    "; ".join(coinglass.warnings) or "Entitlement-gated metrics validated",
                )
            except Exception as exc:
                store.record_source_status("coinglass", "UNAVAILABLE", type(exc).__name__)
        for engine in ENGINE_CONFIGS:
            market = markets.get(engine.asset)
            if market is None:
                if isinstance(engine, QuantEngineConfig):
                    unavailable_at = datetime.now(UTC)
                    _sweep_quant_candidates(store, engine, now=unavailable_at, source_fresh=False)
                    store.set_status(engine.engine, "UNAVAILABLE", "Instrument not discovered")
                continue
            symbol = _market_symbol(market)
            try:
                resolution = _resolution(engine)
                base_minutes = BAR_MINUTES[resolution]
                request_at = datetime.now(UTC)
                history_bars = int(getattr(engine, "min_candles", 65)) + 10
                trigger_start = request_at - timedelta(minutes=base_minutes * history_bars)
                previous_day_start = datetime.combine(
                    request_at.astimezone(UTC).date() - timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=UTC,
                )
                request_start = (
                    min(trigger_start, previous_day_start)
                    if isinstance(engine, QuantEngineConfig)
                    else trigger_start
                )
                history = await _historical_coverage(
                    rest,
                    store,
                    symbol=symbol,
                    resolution=resolution,
                    start=request_start,
                    end=request_at,
                )
                # The decision clock is captured only after REST input is available. The
                # checkpoint is read before that clock, while later journal reads are
                # explicitly bounded by both event and receive time.
                book = (
                    await asyncio.to_thread(store.book_checkpoint, symbol)
                    if isinstance(engine, QuantEngineConfig)
                    else None
                )
                decision_now = datetime.now(UTC)
                store.record_source_status(
                    f"delta_rest:{symbol}:{resolution}",
                    "AVAILABLE",
                    "Historical candle response validated",
                )
                # Exclude the in-progress candle; never leak partial bar into calculations.
                closed = [
                    c
                    for c in history
                    if c.open_time + timedelta(minutes=base_minutes) <= decision_now
                ]
                if resolution == "1m":
                    rest_closed = finalized_candles(history, resolution="1m", through=decision_now)
                    closed_minute = decision_now.replace(second=0, microsecond=0)
                    reconciliation_start = closed_minute - timedelta(minutes=65)
                    raw_trades = await asyncio.to_thread(
                        store.raw_events,
                        symbol=symbol,
                        channels=("trades",),
                        start=reconciliation_start,
                        end=decision_now,
                        received_end=decision_now,
                    )
                    replayed = aggregate_trade_candles(
                        raw_trades, symbol=symbol, resolution="1m", through=decision_now
                    )
                    service = f"candle_reconciliation:{symbol}"
                    if not replayed:
                        store.record_source_status(
                            service, "WAIT", "No complete streamed 1m candle available"
                        )
                    else:
                        coverage_end = closed_minute
                        coverage_start = store.continuous_source_coverage_start(
                            "delta_websocket", start=reconciliation_start, end=coverage_end
                        )
                        if coverage_start is None:
                            store.record_source_status(
                                service,
                                "WAIT",
                                "No continuously connected WebSocket suffix reaches the latest "
                                "closed minute",
                            )
                        else:
                            first_complete = coverage_start.replace(second=0, microsecond=0)
                            if coverage_start > first_complete:
                                first_complete += timedelta(minutes=1)
                            covered_replayed = [
                                candle for candle in replayed if candle.open_time >= first_complete
                            ]
                            if not covered_replayed:
                                store.record_source_status(
                                    service,
                                    "WAIT",
                                    "Stream collector coverage is incomplete: WebSocket recovered "
                                    "but no fully covered streamed 1m candle is available; "
                                    f"coverage_start={first_complete.isoformat()}",
                                )
                                continue
                            first = covered_replayed[0].open_time
                            rest_overlap = [
                                candle for candle in rest_closed if candle.open_time >= first
                            ]
                            result = reconcile_candles(rest_overlap, covered_replayed)
                            detail = (
                                f"coverage_start={first.isoformat()}; matched={result.matched}; "
                                f"missing_stream={len(result.missing_from_stream)}; "
                                f"missing_rest={len(result.missing_from_rest)}; "
                                f"mismatched={len(result.mismatched)}"
                            )
                            store.record_source_status(
                                service, "VALID" if result.valid else "INVALID", detail
                            )
                if isinstance(engine, QuantEngineConfig) and isinstance(market, Instrument):
                    discovery_source = f"product_discovery:{engine.asset}"
                    if not store.source_is_eligible(
                        discovery_source,
                        now=decision_now,
                        maximum_success_age_seconds=settings.delta_discovery_max_age_seconds,
                    ):
                        store.set_status(
                            engine.engine,
                            SignalState.WAIT.value,
                            "Verified instrument metadata is missing or expired",
                        )
                        _sweep_quant_candidates(
                            store,
                            engine,
                            now=decision_now,
                            source_fresh=False,
                            symbol=symbol,
                        )
                        continue
                    trade_tail, recent_trades = await asyncio.gather(
                        asyncio.to_thread(
                            store.raw_events,
                            symbol=symbol,
                            channels=("trades",),
                            end=decision_now + timedelta(microseconds=1),
                            received_end=decision_now,
                            limit=5_000,
                        ),
                        asyncio.to_thread(
                            store.raw_events,
                            symbol=symbol,
                            channels=("trades",),
                            start=decision_now - timedelta(minutes=15),
                            end=decision_now + timedelta(microseconds=1),
                            received_end=decision_now,
                        ),
                    )
                    trade_events = list(
                        {event.event_id: event for event in trade_tail + recent_trades}.values()
                    )
                    trades = await asyncio.to_thread(
                        replay_trade_records,
                        trade_events,
                        symbol=symbol,
                        through=decision_now,
                    )
                    result = detect_signal(
                        engine,
                        candles=closed,
                        trades=trades,
                        instrument=market,
                        now=decision_now,
                        book=book,
                        external_metrics=coinglass.metrics if engine.asset == "BTC" else (),
                        reference_available=False,
                    )
                    if result.snapshot is not None:
                        store.add_feature_snapshot(result.snapshot)
                    store.set_status(engine.engine, result.state.value, result.reason)
                    source_fresh = result.snapshot is not None and (
                        result.snapshot.source_quality == "FRESH"
                        and (not engine.requires_book or result.snapshot.book.available)
                    )
                    _sweep_quant_candidates(
                        store,
                        engine,
                        now=decision_now,
                        symbol=symbol,
                        latest_price=(Decimal(str(closed[-1].close)) if closed else None),
                        source_fresh=source_fresh,
                        snapshot_id=(
                            result.snapshot.snapshot_id if result.snapshot is not None else None
                        ),
                    )
                    if result.candidate is not None:
                        reconciliation = store.source_health(f"candle_reconciliation:{symbol}")
                        reconciliation_fresh = (
                            reconciliation is not None
                            and reconciliation["state"] == "VALID"
                            and (
                                decision_now
                                - datetime.fromisoformat(reconciliation["heartbeat_at_utc"])
                            ).total_seconds()
                            <= settings.delta_reconciliation_max_age_seconds
                        )
                        if not reconciliation_fresh:
                            store.set_status(
                                engine.engine,
                                SignalState.WAIT.value,
                                "REST/stream candle reconciliation is not currently valid",
                            )
                            continue
                        if not _candidate_current_price_is_eligible(result.candidate, trades):
                            store.set_status(
                                engine.engine,
                                SignalState.WAIT.value,
                                "Current executed trade is beyond invalidation or unavailable",
                            )
                            continue
                        initial = lifecycle_event(
                            candidate_id=result.candidate.candidate_id,
                            snapshot_id=result.candidate.snapshot_id,
                            from_state=None,
                            to_state=SignalState.CANDIDATE,
                            occurred_at=result.candidate.observed_at_utc,
                            reason="Deterministic M2 candidate; NOT AI CONFIRMED",
                        )
                        if settings.ai_enabled and result.snapshot is not None:
                            analysis = build_analysis_envelope(
                                result.candidate,
                                result.snapshot,
                                market,
                                evaluation_settings={
                                    "fee_bps": settings.risk_fee_bps,
                                    "slippage_bps": settings.risk_slippage_bps,
                                    "maximum_entry_drift_bps": (
                                        settings.risk_maximum_entry_drift_bps
                                    ),
                                    "maximum_spread_bps": settings.risk_maximum_spread_bps,
                                    "minimum_net_reward_risk": (
                                        settings.risk_minimum_net_reward_risk
                                    ),
                                },
                            )
                            deadline = min(
                                result.candidate.expires_at_utc,
                                decision_now
                                + timedelta(seconds=settings.ai_total_deadline_seconds),
                            )
                            if deadline > decision_now:
                                admission, _ = store.admit_candidate_review(
                                    result.candidate,
                                    initial,
                                    analysis,
                                    material_digest=material_proposal_digest(
                                        result.candidate, result.snapshot
                                    ),
                                    provider_config=frozen_provider_config(settings, analysis),
                                    deadline_at=deadline,
                                    now=decision_now,
                                )
                                if admission != "UNCHANGED":
                                    store.set_status(
                                        engine.engine,
                                        "REVIEW_QUEUED",
                                        "Immutable revision queued for dual independent review",
                                    )
                        elif settings.ai_enabled:
                            created = store.add_candidate_with_lifecycle(result.candidate, initial)
                            if not created:
                                continue
                            store.set_status(
                                engine.engine,
                                "CANDIDATE_UNREVIEWED",
                                "Canonical feature snapshot unavailable; no AI call scheduled",
                            )
                        else:
                            store.add_candidate_with_lifecycle(result.candidate, initial)
                    # No order execution exists; review and alerts run in durable workers.
                    continue

                candidate = create_candidate(engine, closed, now=decision_now)
                if candidate is None or not store.add_candidate(candidate):
                    continue
                if candidate.source_quality != "FRESH":
                    store.set_status(
                        engine.engine_id, "WAIT", "Incomplete data: research candidate only"
                    )
                    continue
                if not settings.ai_enabled:
                    store.set_status(engine.engine_id, "CANDIDATE_UNREVIEWED", "AI disabled")
                    continue
                if not store.reserve_ai_calls(2, settings.max_ai_calls_per_day):
                    store.set_status(engine.engine_id, "WAIT", "Daily AI API call budget reached")
                    continue
                gpt, claude, errors = await independent_review(
                    candidate, GPTAnalyst(settings), ClaudeAnalyst(settings)
                )
                if gpt is not None:
                    store.save_assessment(candidate.candidate_id, "GPT", settings.openai_model, gpt)
                if claude is not None:
                    store.save_assessment(
                        candidate.candidate_id, "Claude", settings.anthropic_model, claude
                    )
                decision = decide(
                    candidate,
                    gpt,
                    claude,
                    now=datetime.now(UTC),
                    max_age_seconds=settings.data_max_age_seconds,
                    min_reward_risk=settings.min_reward_risk,
                )
                store.add_decision(decision)
                store.set_status(
                    engine.engine_id,
                    decision.status.value,
                    "; ".join(errors) if errors else decision.reason,
                )
                if decision.status == Status.CONFIRMED:
                    LOGGER.warning(
                        "Research alert only %s %s %s %s",
                        candidate.asset,
                        candidate.direction,
                        candidate.horizon_minutes,
                        candidate.candidate_id,
                    )
            except Exception as exc:
                # Fail closed: expose only error type to avoid leaking external payload.
                LOGGER.warning("Engine %s unavailable: %s", _engine_id(engine), type(exc).__name__)
                symbol = _market_symbol(markets.get(engine.asset, engine.asset))
                store.record_source_status(
                    f"delta_rest:{symbol}:{_resolution(engine)}",
                    "UNAVAILABLE",
                    type(exc).__name__,
                )
                store.set_status(_engine_id(engine), "UNAVAILABLE", type(exc).__name__)
                if isinstance(engine, QuantEngineConfig):
                    _sweep_quant_candidates(
                        store,
                        engine,
                        now=datetime.now(UTC),
                        source_fresh=False,
                        symbol=symbol,
                    )
        await asyncio.sleep(settings.poll_seconds)


async def public_market_stream(settings: Settings, store: Store, symbols: list[str]) -> None:
    persistence_queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue(
        maxsize=settings.delta_persistence_queue_size
    )
    last_status_at: datetime | None = None

    def persist_connection_status(state: str, detail: str) -> None:
        nonlocal last_status_at
        occurred_at = datetime.now(UTC)
        if last_status_at is not None and occurred_at <= last_status_at:
            occurred_at = last_status_at + timedelta(microseconds=1)
        last_status_at = occurred_at
        persistence_queue.put_nowait(("status", (state, detail, occurred_at)))

    stream = DeltaPublicStream(
        settings.delta_ws_url,
        symbols,
        book_max_age_seconds=settings.delta_book_max_age_seconds,
        status_callback=persist_connection_status,
    )
    book_states: dict[str, tuple[bool, str]] = {}
    persistence_books = {
        symbol: OrderBookAssembler(symbol, max_age_seconds=settings.delta_book_max_age_seconds)
        for symbol in symbols
    }
    producer_done = asyncio.Event()

    async def monitor_freshness() -> None:
        interval = max(min(settings.delta_book_max_age_seconds / 2, 5.0), 0.1)
        while True:
            await asyncio.sleep(interval)
            now = datetime.now(UTC)
            if (
                stream.last_seen_utc is not None
                and (now - stream.last_seen_utc).total_seconds()
                > settings.delta_book_max_age_seconds
            ):
                stream.mark_stale("No recent validated public market event")
            for symbol in symbols:
                quality = stream.book_quality(symbol, now=now)
                state = "VALID" if quality[0] else "INVALID"
                await asyncio.to_thread(
                    store.record_source_status, f"delta_book:{symbol}", state, quality[1]
                )
                book_states[symbol] = quality

    async def produce() -> None:
        try:
            async for event in stream.messages():
                try:
                    persistence_queue.put_nowait(("event", event))
                except asyncio.QueueFull as exc:
                    stream.invalidate_books("local_persistence_backpressure")
                    await asyncio.to_thread(
                        store.record_source_status,
                        "delta_websocket",
                        "DISCONNECTED",
                        "Local persistence queue reached its configured bound",
                    )
                    raise DeltaDataIntegrityError("Local persistence queue is full") from exc
        finally:
            producer_done.set()

    async def persist_event_batch(events: list) -> None:
        await asyncio.to_thread(store.append_raw_events, events)
        changed: set[str] = set()
        for event in events:
            if event.channel == "ob_updates" and event.symbol in persistence_books:
                persistence_books[event.symbol].apply(event)
                changed.add(event.symbol)
        for symbol in changed:
            await asyncio.to_thread(store.save_book_checkpoint, persistence_books[symbol])

    async def consume() -> None:
        while not producer_done.is_set() or not persistence_queue.empty():
            try:
                first = await asyncio.wait_for(persistence_queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            chunk = [first]
            while len(chunk) < settings.delta_persistence_batch_size:
                try:
                    chunk.append(persistence_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            event_batch = []
            for kind, payload in chunk:
                if kind == "event":
                    event_batch.append(payload)
                    continue
                if event_batch:
                    await persist_event_batch(event_batch)
                    event_batch = []
                state, detail, occurred_at = payload
                if state in {"CONNECTING", "DISCONNECTED", "STALE"}:
                    reason = (
                        "fresh_snapshot_required_after_connect"
                        if state == "CONNECTING"
                        else "fresh_snapshot_required_after_disconnect"
                    )
                    for book in persistence_books.values():
                        book.invalidate(reason)
                        await asyncio.to_thread(store.save_book_checkpoint, book)
                await asyncio.to_thread(
                    store.record_source_status,
                    "delta_websocket",
                    state,
                    detail,
                    occurred_at=occurred_at,
                )
            if event_batch:
                await persist_event_batch(event_batch)

    monitor = asyncio.create_task(monitor_freshness())
    try:
        await asyncio.gather(produce(), consume())
    finally:
        monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor


async def main() -> None:
    settings = Settings()
    store = Store(settings.database_path)
    logging.basicConfig(level=logging.INFO)
    if not settings.live_ingestion_enabled:
        _sweep_all_quant_candidates(store, now=datetime.now(UTC))
        LOGGER.warning("Live ingestion is DISABLED; set LIVE_INGESTION_ENABLED=true to start")
        return
    rest = DeltaREST(settings.delta_rest_url)
    active_markets: dict[str, Instrument] = {}
    market_tasks: set[asyncio.Task[None]] = set()

    async def stop_market_tasks() -> None:
        for task in market_tasks:
            task.cancel()
        if market_tasks:
            await asyncio.gather(*market_tasks, return_exceptions=True)
        market_tasks.clear()

    while True:
        try:
            discovery = await rest.discover_instruments(
                btc_symbol=settings.btc_symbol,
                preferred_gold_symbol=settings.gold_symbol,
            )
            markets = {
                asset: instrument
                for asset, instrument in (("BTC", discovery.btc), ("GOLD", discovery.gold))
                if instrument is not None
            }
            symbols = {asset: instrument.symbol for asset, instrument in markets.items()}
            if discovery.unavailable:
                detail = "; ".join(
                    f"{asset}: {reason}" for asset, reason in discovery.unavailable.items()
                )
                store.record_source_status("product_discovery", "PARTIAL", detail)
            else:
                detail = ", ".join(f"{asset}={symbol}" for asset, symbol in symbols.items())
                if discovery.invalid_product_count:
                    detail += f"; ignored invalid rows={discovery.invalid_product_count}"
                store.record_source_status("product_discovery", "AVAILABLE", detail)
            store.record_source_status("worker", "AVAILABLE", "Discovery cycle completed")
            for asset in ("BTC", "GOLD"):
                instrument = markets.get(asset)
                if instrument is not None:
                    store.record_source_status(
                        f"product_discovery:{asset}",
                        "AVAILABLE",
                        f"verified {instrument.symbol} product metadata",
                    )
                else:
                    store.record_source_status(
                        f"product_discovery:{asset}",
                        "UNAVAILABLE",
                        discovery.unavailable.get(asset, "No verified instrument"),
                    )
            if markets != active_markets:
                await stop_market_tasks()
                active_markets = markets
                if symbols:
                    # A process or connection generation cannot inherit sequence continuity.
                    for symbol in symbols.values():
                        store.save_book_checkpoint(
                            OrderBookAssembler(
                                symbol, max_age_seconds=settings.delta_book_max_age_seconds
                            )
                        )
                    market_tasks = {
                        asyncio.create_task(poll_closed_candles(settings, store, markets)),
                        asyncio.create_task(
                            public_market_stream(settings, store, list(symbols.values()))
                        ),
                    }
            if not symbols:
                _sweep_all_quant_candidates(store, now=datetime.now(UTC))
                store.record_source_status(
                    "product_discovery", "UNAVAILABLE", "No verified BTC or Gold market"
                )
                await asyncio.sleep(settings.delta_discovery_refresh_seconds)
                continue

            done, _ = await asyncio.wait(
                market_tasks,
                timeout=settings.delta_discovery_refresh_seconds,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            if done:
                failure: BaseException | None = None
                for task in done:
                    if task.cancelled():
                        failure = RuntimeError("Market-data collector was cancelled unexpectedly")
                        break
                    failure = task.exception() or RuntimeError(
                        "Market-data collector stopped unexpectedly"
                    )
                    break
                await stop_market_tasks()
                active_markets = {}
                if failure is not None:
                    raise failure
        except asyncio.CancelledError:
            await stop_market_tasks()
            raise
        except Exception as exc:
            _sweep_all_quant_candidates(store, now=datetime.now(UTC))
            store.record_source_status("product_discovery", "DEGRADED", type(exc).__name__)
            for asset in active_markets:
                store.record_source_status(
                    f"product_discovery:{asset}", "DEGRADED", type(exc).__name__
                )
            store.record_source_status("worker", "ERROR", type(exc).__name__)
            LOGGER.warning("Worker fault: %s; retrying", type(exc).__name__)
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
