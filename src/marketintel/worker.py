"""Windows-friendly separate worker. Public market feed; NEVER places orders."""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, independent_review
from marketintel.coinglass import CoinGlassV4, unavailable_context
from marketintel.config import Settings
from marketintel.consensus import decide
from marketintel.delta import DeltaPublicStream, DeltaREST, OrderBookAssembler
from marketintel.detectors import BAR_MINUTES, create_candidate
from marketintel.models import Instrument, SignalState, Status
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
        transition = terminal_transition(
            active,
            current_state=SignalState.CANDIDATE,
            now=now,
            latest_price=latest_price or Decimal(str(active.entry)),
            source_fresh=source_fresh,
            evaluation_snapshot_id=snapshot_id,
        )
        if transition is not None:
            store.record_candidate_lifecycle(transition)


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
                history_bars = int(getattr(engine, "min_candles", 65)) + 10
                request_at = datetime.now(UTC)
                history = await rest.historical_candles(
                    symbol,
                    resolution,
                    request_at - timedelta(minutes=base_minutes * history_bars),
                    request_at,
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
                    raw_trades = await asyncio.to_thread(
                        store.raw_events,
                        symbol=symbol,
                        channels=("trades",),
                        start=decision_now - timedelta(minutes=base_minutes * 65),
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
                        first = replayed[0].open_time
                        rest_overlap = [
                            candle for candle in rest_closed if candle.open_time >= first
                        ]
                        result = reconcile_candles(rest_overlap, replayed)
                        detail = (
                            f"matched={result.matched}; "
                            f"missing_stream={len(result.missing_from_stream)}; "
                            f"missing_rest={len(result.missing_from_rest)}; "
                            f"mismatched={len(result.mismatched)}"
                        )
                        store.record_source_status(
                            service, "VALID" if result.valid else "INVALID", detail
                        )
                if isinstance(engine, QuantEngineConfig) and isinstance(market, Instrument):
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
                        initial = lifecycle_event(
                            candidate_id=result.candidate.candidate_id,
                            snapshot_id=result.candidate.snapshot_id,
                            from_state=None,
                            to_state=SignalState.CANDIDATE,
                            occurred_at=result.candidate.observed_at_utc,
                            reason="Deterministic M2 candidate; NOT AI CONFIRMED",
                        )
                        store.add_candidate_with_lifecycle(result.candidate, initial)
                    # M2 deliberately never calls GPT, Claude, alerts, or execution.
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
    def persist_connection_status(state: str, detail: str) -> None:
        if state in {"CONNECTING", "DISCONNECTED"}:
            for book in getattr(stream, "books", {}).values():
                store.save_book_checkpoint(book)
        store.record_source_status("delta_websocket", state, detail)

    stream = DeltaPublicStream(
        settings.delta_ws_url,
        symbols,
        book_max_age_seconds=settings.delta_book_max_age_seconds,
        status_callback=persist_connection_status,
    )
    book_states: dict[str, tuple[bool, str]] = {}

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
                if book_states.get(symbol) != quality:
                    state = "VALID" if quality[0] else "INVALID"
                    store.record_source_status(f"delta_book:{symbol}", state, quality[1])
                    book_states[symbol] = quality

    monitor = asyncio.create_task(monitor_freshness())
    try:
        async for event in stream.messages():
            inserted = await asyncio.to_thread(store.append_raw_event, event)
            if not inserted:
                continue
            if event.channel == "ob_updates":
                book = stream.books.get(event.symbol)
                if book is not None:
                    await asyncio.to_thread(store.save_book_checkpoint, book)
                quality = stream.book_quality(event.symbol)
                if book_states.get(event.symbol) != quality:
                    state = "VALID" if quality[0] else "INVALID"
                    store.record_source_status(f"delta_book:{event.symbol}", state, quality[1])
                    book_states[event.symbol] = quality
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
            store.record_source_status("worker", "ERROR", type(exc).__name__)
            LOGGER.warning("Worker fault: %s; retrying", type(exc).__name__)
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
