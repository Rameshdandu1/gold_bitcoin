"""Windows-friendly separate worker. Public market feed; NEVER places orders."""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, independent_review
from marketintel.config import Settings
from marketintel.consensus import decide
from marketintel.delta import DeltaPublicStream, DeltaREST
from marketintel.detectors import BAR_MINUTES, ENGINE_CONFIGS, create_candidate
from marketintel.models import Status
from marketintel.replay import aggregate_trade_candles, finalized_candles, reconcile_candles
from marketintel.storage import Store

LOGGER = logging.getLogger(__name__)


async def poll_closed_candles(settings: Settings, store: Store, symbols: dict[str, str]) -> None:
    rest = DeltaREST(settings.delta_rest_url)
    while True:
        now = datetime.now(UTC)
        for engine in ENGINE_CONFIGS:
            symbol = symbols.get(engine.asset)
            if symbol is None:
                continue
            try:
                base_minutes = BAR_MINUTES[engine.resolution]
                history = await rest.historical_candles(
                    symbol,
                    engine.resolution,
                    now - timedelta(minutes=base_minutes * 65),
                    now,
                )
                store.record_source_status(
                    f"delta_rest:{symbol}:{engine.resolution}",
                    "AVAILABLE",
                    "Historical candle response validated",
                )
                # Exclude the in-progress candle; never leak partial bar into calculations.
                closed = [
                    c for c in history if c.open_time + timedelta(minutes=base_minutes) <= now
                ]
                if engine.resolution == "1m":
                    rest_closed = finalized_candles(history, resolution="1m", through=now)
                    raw_trades = store.raw_events(
                        symbol=symbol,
                        channels=("trades",),
                        start=now - timedelta(minutes=base_minutes * 65),
                        end=now,
                    )
                    replayed = aggregate_trade_candles(
                        raw_trades, symbol=symbol, resolution="1m", through=now
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
                candidate = create_candidate(engine, closed, now=now)
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
                LOGGER.warning("Engine %s unavailable: %s", engine.engine_id, type(exc).__name__)
                symbol = symbols.get(engine.asset, engine.asset)
                store.record_source_status(
                    f"delta_rest:{symbol}:{engine.resolution}",
                    "UNAVAILABLE",
                    type(exc).__name__,
                )
                store.set_status(engine.engine_id, "UNAVAILABLE", type(exc).__name__)
        await asyncio.sleep(settings.poll_seconds)


async def public_market_stream(settings: Settings, store: Store, symbols: list[str]) -> None:
    def persist_connection_status(state: str, detail: str) -> None:
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
        LOGGER.warning("Live ingestion is DISABLED; set LIVE_INGESTION_ENABLED=true to start")
        return
    rest = DeltaREST(settings.delta_rest_url)
    active_symbols: dict[str, str] = {}
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
            symbols = {
                asset: instrument.symbol
                for asset, instrument in (("BTC", discovery.btc), ("GOLD", discovery.gold))
                if instrument is not None
            }
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
            if symbols != active_symbols:
                await stop_market_tasks()
                active_symbols = symbols
                if symbols:
                    market_tasks = {
                        asyncio.create_task(poll_closed_candles(settings, store, symbols)),
                        asyncio.create_task(
                            public_market_stream(settings, store, list(symbols.values()))
                        ),
                    }
            if not symbols:
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
                active_symbols = {}
                if failure is not None:
                    raise failure
        except asyncio.CancelledError:
            await stop_market_tasks()
            raise
        except Exception as exc:
            store.record_source_status("worker", "ERROR", type(exc).__name__)
            LOGGER.warning("Worker fault: %s; retrying", type(exc).__name__)
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
