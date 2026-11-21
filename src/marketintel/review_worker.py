"""Durable Phase 3 review worker. It has no order or execution capability."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from marketintel.ai import ClaudeAnalyst, GPTAnalyst
from marketintel.analysis import canonical_decimal, load_canonical_analysis
from marketintel.config import Settings
from marketintel.consensus import decide_v2
from marketintel.orchestration import ReviewOrchestrator
from marketintel.replay import replay_trade_records
from marketintel.review import EligibilitySnapshot
from marketintel.storage import Store

LOGGER = logging.getLogger(__name__)


def _current_source(
    store: Store,
    source: str,
    *,
    now: datetime,
    accepted_states: set[str],
    maximum_age_seconds: float,
) -> bool:
    health = store.source_health(source)
    if health is None or health["state"] not in accepted_states:
        return False
    timestamp = health["last_success_at_utc"] or health["heartbeat_at_utc"]
    if not timestamp:
        return False
    age = (now - datetime.fromisoformat(timestamp)).total_seconds()
    return 0 <= age <= maximum_age_seconds


def current_eligibility(
    store: Store,
    settings: Settings,
    analysis,
    *,
    now: datetime,
) -> EligibilitySnapshot:
    """Build fresh server-owned gates from durable market facts after both reviews."""
    envelope = analysis.envelope
    events = store.raw_events(
        symbol=envelope.symbol,
        channels=("trades",),
        start=envelope.observed_at_utc,
        end=now + timedelta(microseconds=1),
        received_end=now,
    )
    trades = replay_trade_records(events, symbol=envelope.symbol, through=now)
    latest = max(trades, key=lambda item: (item.received_at_utc, item.event_id), default=None)
    stop = Decimal(envelope.invalidation)
    targets = tuple(Decimal(value) for value in envelope.targets)

    def stop_hit(price: Decimal) -> bool:
        return price <= stop if envelope.direction == "BULLISH" else price >= stop

    def target_hits(price: Decimal) -> tuple[int, ...]:
        return tuple(
            index
            for index, target in enumerate(targets, start=1)
            if (price >= target if envelope.direction == "BULLISH" else price <= target)
        )

    stop_keys = {
        (trade.event_time_utc, trade.received_at_utc) for trade in trades if stop_hit(trade.price)
    }
    target_keys = {
        (trade.event_time_utc, trade.received_at_utc)
        for trade in trades
        if target_hits(trade.price)
    }
    crossed = tuple(sorted({index for trade in trades for index in target_hits(trade.price)}))

    book = store.book_checkpoint(envelope.symbol)
    top = book.top_of_book(now=now) if book is not None else None
    book_time = (
        book.last_event_time_utc
        if book is not None and book.last_event_time_utc is not None
        else envelope.observed_at_utc
    )
    bid, ask = top or (Decimal(envelope.entry), Decimal(envelope.entry))
    token_result = store.eligibility_token(envelope.candidate_id)
    if token_result is None:
        raise ValueError("Candidate has no active revision eligibility identity")
    token, evidence = token_result
    lifecycle = evidence["lifecycle"]
    lifecycle_state = lifecycle[1] if lifecycle else "INVALIDATED"
    latest_time = latest.received_at_utc if latest else envelope.observed_at_utc
    latest_price = latest.price if latest else Decimal(envelope.entry)
    websocket = store.source_health("delta_websocket")
    trade_is_current = (
        latest is not None
        and 0 <= (now - latest.received_at_utc).total_seconds() <= settings.data_max_age_seconds
        and websocket is not None
        and websocket["state"] == "CONNECTED"
    )
    return EligibilitySnapshot(
        candidate_id=envelope.candidate_id,
        candidate_revision_id=str(evidence["revision_id"]),
        eligibility_token=token,
        active_revision_generation=int(evidence["generation"]),
        lifecycle_state=lifecycle_state,
        evaluated_at_utc=now,
        latest_trade_price=canonical_decimal(latest_price),
        latest_trade_at_utc=latest_time,
        best_bid=canonical_decimal(bid),
        best_ask=canonical_decimal(ask),
        book_observed_at_utc=book_time,
        discovery_current=_current_source(
            store,
            f"product_discovery:{envelope.asset}",
            now=now,
            accepted_states={"AVAILABLE"},
            maximum_age_seconds=settings.delta_discovery_max_age_seconds,
        ),
        reconciliation_current=_current_source(
            store,
            f"candle_reconciliation:{envelope.symbol}",
            now=now,
            accepted_states={"VALID"},
            maximum_age_seconds=settings.delta_reconciliation_max_age_seconds,
        ),
        trade_stream_current=trade_is_current,
        book_current=top is not None,
        stop_breached=bool(stop_keys),
        target_crossed_indices=crossed,
        event_order_ambiguous=bool(stop_keys & target_keys),
        required_costs_known=bool(settings.risk_fee_bps and settings.risk_slippage_bps),
        fee_bps=settings.risk_fee_bps or None,
        slippage_bps=settings.risk_slippage_bps or None,
        maximum_entry_drift_bps=settings.risk_maximum_entry_drift_bps,
        maximum_spread_bps=settings.risk_maximum_spread_bps,
        minimum_net_reward_risk=settings.risk_minimum_net_reward_risk,
        calendar_policy="TOKEN_MARKET_ONLY",
        notification_ready=bool(
            settings.slack_channel_id and settings.slack_bot_token.get_secret_value()
        ),
    )


class ReviewWorker:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings
        self.gpt = GPTAnalyst(settings)
        self.claude = ClaudeAnalyst(settings)
        self.orchestrator = ReviewOrchestrator(
            store,
            settings,
            self.gpt,
            self.claude,
        )

    async def run_once(self, *, owner: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        claim = self.store.claim_review_job(
            owner,
            now=now,
            lease_seconds=self.settings.ai_job_lease_seconds,
        )
        if claim is None:
            return False
        run = self.store.review_run(claim["run_id"])
        if run is None:
            self.store.complete_review_job(
                claim["job_id"],
                owner=owner,
                generation=claim["generation"],
                status="FAILED",
                now=now,
            )
            return True
        payload = self.store.analysis_envelope_bytes(run["envelope_digest"])
        if payload is None:
            self.store.complete_review_job(
                claim["job_id"],
                owner=owner,
                generation=claim["generation"],
                status="FAILED",
                now=now,
            )
            return True
        analysis = load_canonical_analysis(payload, run["envelope_digest"])
        try:
            openai, anthropic = await self.orchestrator.execute(
                analysis,
                run_id=claim["run_id"],
                claim=claim,
            )
            attempts = self.store.provider_results(claim["run_id"])
            attempt_ids = tuple(
                max(
                    (item for item in attempts if item["provider"] == provider),
                    key=lambda item: item["attempt_number"],
                )["attempt_id"]
                for provider in ("OPENAI", "ANTHROPIC")
            )
            evaluated_at = datetime.now(UTC)
            eligibility = current_eligibility(
                self.store,
                self.settings,
                analysis,
                now=evaluated_at,
            )
            decision = decide_v2(
                analysis,
                openai,
                anthropic,
                eligibility,
                run_id=claim["run_id"],
                provider_attempt_ids=attempt_ids,
            )
            destination = (
                f"slack:{self.settings.slack_channel_id}"
                if decision.status == "CONFIRMED"
                else None
            )
            committed = self.store.commit_consensus_decision_and_outbox(
                decision,
                destination_id=destination,
            )
            self.store.record_source_status(
                "review_worker",
                decision.status if committed else "WAIT",
                decision.reason if committed else "Eligibility changed before atomic commit",
            )
        except Exception as exc:
            self.store.complete_review_job(
                claim["job_id"],
                owner=owner,
                generation=claim["generation"],
                status="FAILED",
                now=datetime.now(UTC),
            )
            self.store.record_source_status("review_worker", "ERROR", type(exc).__name__)
            LOGGER.warning("Review job failed closed: %s", type(exc).__name__)
        return True


async def main() -> None:
    settings = Settings()
    store = Store(settings.database_path)
    logging.basicConfig(level=logging.INFO)
    if not settings.ai_enabled:
        LOGGER.warning("AI review is DISABLED; set AI_ENABLED=true only after configuring gates")
        return
    owner = f"review-{uuid.uuid4().hex}"
    worker = ReviewWorker(store, settings)
    while True:
        worked = await worker.run_once(owner=owner)
        if not worked:
            store.record_source_status("review_worker", "AVAILABLE", "Queue idle")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
