"""Windows-friendly separate worker. Public market feed; NEVER places orders."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, independent_review
from marketintel.config import Settings
from marketintel.consensus import decide
from marketintel.delta import DeltaPublicStream, DeltaREST
from marketintel.detectors import BAR_MINUTES, ENGINE_CONFIGS, create_candidate
from marketintel.models import Status
from marketintel.storage import Store

LOGGER = logging.getLogger(__name__)


async def poll_closed_candles(settings: Settings, store: Store, symbols: dict[str, str]) -> None:
    rest = DeltaREST(settings.delta_rest_url)
    while True:
        now = datetime.now(timezone.utc)
        for engine in ENGINE_CONFIGS:
            symbol = symbols.get(engine.asset)
            if symbol is None:
                continue
            try:
                base_minutes = BAR_MINUTES[engine.resolution]
                history = await rest.historical_candles(
                    symbol, engine.resolution,
                    now - timedelta(minutes=base_minutes * 65), now,
                )
                # Exclude the in-progress candle; never leak partial bar into calculations.
                closed = [c for c in history if c.open_time + timedelta(
                    minutes=base_minutes
                ) <= now]
                candidate = create_candidate(engine, closed, now=now)
                if candidate is None or not store.add_candidate(candidate):
                    continue
                if candidate.source_quality != "FRESH":
                    store.set_status(engine.engine_id, "WAIT", "Incomplete data: research candidate only")
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
                    store.save_assessment(candidate.candidate_id, "Claude", settings.anthropic_model, claude)
                decision = decide(
                    candidate, gpt, claude, now=datetime.now(timezone.utc),
                    max_age_seconds=settings.data_max_age_seconds,
                    min_reward_risk=settings.min_reward_risk,
                )
                store.add_decision(decision)
                store.set_status(
                    engine.engine_id, decision.status.value,
                    "; ".join(errors) if errors else decision.reason,
                )
                if decision.status == Status.CONFIRMED:
                    LOGGER.warning(
                        "Research alert only %s %s %s %s",
                        candidate.asset, candidate.direction,
                        candidate.horizon_minutes, candidate.candidate_id,
                    )
            except Exception as exc:
                # Fail closed: expose only error type to avoid leaking external payload.
                LOGGER.warning("Engine %s unavailable: %s", engine.engine_id, type(exc).__name__)
                store.set_status(engine.engine_id, "UNAVAILABLE", type(exc).__name__)
        await asyncio.sleep(settings.poll_seconds)


async def public_trade_stream(settings: Settings, store: Store, symbols: list[str]) -> None:
    stream = DeltaPublicStream(settings.delta_ws_url, symbols)
    last_status_at = datetime.min.replace(tzinfo=timezone.utc)
    async for message in stream.messages():
        # This bounded stream demonstrates live collection. Production phase must persist events.
        if message.get("type") == "trades" and (
            datetime.now(timezone.utc) - last_status_at
        ).total_seconds() >= 30:
            store.set_status("delta_websocket", "CONNECTED", "Public trades streaming")
            last_status_at = datetime.now(timezone.utc)
            # Avoid publishing unverified "whale" interpretation from contract counts.


async def main() -> None:
    settings = Settings()
    store = Store(settings.database_path)
    logging.basicConfig(level=logging.INFO)
    if not settings.live_ingestion_enabled:
        LOGGER.warning("Live ingestion is DISABLED; set LIVE_INGESTION_ENABLED=true to start")
        return
    rest = DeltaREST(settings.delta_rest_url)
    while True:
        try:
            active, missing = await rest.valid_symbols([settings.btc_symbol, settings.gold_symbol])
            if missing:
                store.set_status("product_discovery", "PARTIAL", "Unavailable: " + ",".join(missing))
            if active:
                symbols = {
                    asset: symbol for asset, symbol in (
                        ("BTC", settings.btc_symbol), ("GOLD", settings.gold_symbol)
                    ) if symbol in active
                }
                await asyncio.gather(
                    poll_closed_candles(settings, store, symbols),
                    public_trade_stream(settings, store, active),
                )
            else:
                store.set_status("product_discovery", "UNAVAILABLE", "Neither configured symbol active")
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            store.set_status("worker", "ERROR", type(exc).__name__)
            LOGGER.warning("Worker fault: %s; retrying", type(exc).__name__)
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
