"""Durable Phase 3 review worker. It has no order or execution capability."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from marketintel.ai import ClaudeAnalyst, GPTAnalyst
from marketintel.analysis import canonical_decimal, load_canonical_analysis
from marketintel.config import Settings
from marketintel.consensus import decide_v2
from marketintel.orchestration import ReviewOrchestrator
from marketintel.replay import replay_trade_records
from marketintel.review import AnalystAssessmentV2, EligibilitySnapshot, ProviderResult, TokenUsage
from marketintel.storage import Store

LOGGER = logging.getLogger(__name__)


def current_eligibility(
    store: Store,
    settings: Settings,
    analysis,
    *,
    now: datetime,
) -> EligibilitySnapshot:
    """Build fresh server-owned gates from durable market facts after both reviews."""
    envelope = analysis.envelope
    snapshot = store.eligibility_snapshot_data(
        envelope.candidate_id,
        symbol=envelope.symbol,
        observed_at=envelope.observed_at_utc,
        through=now,
    )
    if snapshot is None:
        raise ValueError("Candidate has no active revision eligibility identity")
    token, evidence, events, book = snapshot
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

    top = book.top_of_book(now=now) if book is not None else None
    book_time = (
        book.last_event_time_utc
        if book is not None and book.last_event_time_utc is not None
        else envelope.observed_at_utc
    )
    bid, ask = top or (Decimal(envelope.entry), Decimal(envelope.entry))
    lifecycle = evidence["lifecycle"]
    lifecycle_state = lifecycle[1] if lifecycle else "INVALIDATED"
    latest_time = latest.received_at_utc if latest else envelope.observed_at_utc
    latest_price = latest.price if latest else Decimal(envelope.entry)
    health = {row[0]: row[1:] for row in evidence["source_health"]}
    websocket = health.get("delta_websocket")
    trade_is_current = (
        latest is not None
        and 0 <= (now - latest.received_at_utc).total_seconds() <= settings.data_max_age_seconds
        and websocket is not None
        and websocket[0] == "CONNECTED"
    )

    def source_current(source: str, accepted: set[str], maximum_age: float) -> bool:
        row = health.get(source)
        if row is None or row[0] not in accepted:
            return False
        timestamp = row[2] or row[1]
        if not timestamp:
            return False
        age = (now - datetime.fromisoformat(timestamp)).total_seconds()
        return 0 <= age <= maximum_age

    def source_deadline(source: str, maximum_age: float) -> datetime:
        row = health.get(source)
        timestamp = (row[2] or row[1]) if row is not None else None
        return (
            datetime.fromisoformat(timestamp) + timedelta(seconds=maximum_age) if timestamp else now
        )

    freshness_deadlines = [
        envelope.expires_at_utc,
        latest_time + timedelta(seconds=settings.data_max_age_seconds),
        source_deadline(
            f"product_discovery:{envelope.asset}",
            settings.delta_discovery_max_age_seconds,
        ),
        source_deadline(
            f"candle_reconciliation:{envelope.symbol}",
            settings.delta_reconciliation_max_age_seconds,
        ),
    ]
    if book is not None and book.last_received_at_utc is not None:
        freshness_deadlines.append(
            book.last_received_at_utc + timedelta(seconds=book.max_age_seconds)
        )

    return EligibilitySnapshot(
        candidate_id=envelope.candidate_id,
        candidate_revision_id=str(evidence["revision_id"]),
        eligibility_token=token,
        active_revision_generation=int(evidence["generation"]),
        lifecycle_state=lifecycle_state,
        evaluated_at_utc=now,
        evidence_valid_until_utc=min(freshness_deadlines),
        latest_trade_price=canonical_decimal(latest_price),
        latest_trade_at_utc=latest_time,
        best_bid=canonical_decimal(bid),
        best_ask=canonical_decimal(ask),
        book_observed_at_utc=book_time,
        discovery_current=source_current(
            f"product_discovery:{envelope.asset}",
            {"AVAILABLE"},
            settings.delta_discovery_max_age_seconds,
        ),
        reconciliation_current=source_current(
            f"candle_reconciliation:{envelope.symbol}",
            {"VALID"},
            settings.delta_reconciliation_max_age_seconds,
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
    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self.store = store
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(UTC))
        self.gpt = GPTAnalyst(settings)
        self.claude = ClaudeAnalyst(settings)
        self.orchestrator = ReviewOrchestrator(
            store,
            settings,
            self.gpt,
            self.claude,
            clock=self.clock,
        )

    @staticmethod
    def _stored_results(rows: list[dict]) -> tuple[ProviderResult, ProviderResult]:
        latest = {
            provider: max(
                (row for row in rows if row["provider"] == provider),
                key=lambda row: row["attempt_number"],
            )
            for provider in ("OPENAI", "ANTHROPIC")
        }

        def load(row: dict) -> ProviderResult:
            return ProviderResult(
                provider=row["provider"],
                status=row["status"],
                requested_model=row["requested_model"],
                returned_model=row["returned_model"],
                request_id=row["request_id"],
                response_id=row["response_id"],
                sdk_version=row["metadata"].get("sdk", "stored"),
                started_at_utc=datetime.fromisoformat(row["started_at_utc"]),
                completed_at_utc=datetime.fromisoformat(row["completed_at_utc"]),
                latency_ms=max(
                    0,
                    round(
                        (
                            datetime.fromisoformat(row["completed_at_utc"])
                            - datetime.fromisoformat(row["started_at_utc"])
                        ).total_seconds()
                        * 1_000
                    ),
                ),
                attempt_number=row["attempt_number"],
                finish_reason=row["finish_reason"],
                usage=TokenUsage(
                    input_tokens=row["input_tokens"], output_tokens=row["output_tokens"]
                ),
                failure_code=row["failure_code"],
                assessment=(
                    AnalystAssessmentV2.model_validate_json(json.dumps(row["assessment"]))
                    if row["assessment"]
                    else None
                ),
                safe_metadata=tuple(sorted(row["metadata"].items())),
            )

        return load(latest["OPENAI"]), load(latest["ANTHROPIC"])

    async def run_once(self, *, owner: str, now: datetime | None = None) -> bool:
        now = now or self.clock()
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
            if claim.get("claimed_from_status") == "RESULTS_READY":
                openai, anthropic = self._stored_results(
                    self.store.provider_results(claim["run_id"])
                )
            else:
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
            evaluated_at = self.clock()
            deadline_at = datetime.fromisoformat(run["deadline_at_utc"])
            if evaluated_at >= deadline_at:
                self.store.record_review_disposition(
                    run_id=claim["run_id"],
                    job_id=claim["job_id"],
                    code="REVIEW_DEADLINE_EXPIRED",
                    now=evaluated_at,
                    detail={"redispatched": False},
                )
                self.store.complete_review_job(
                    claim["job_id"],
                    owner=owner,
                    generation=claim["generation"],
                    status="WAIT",
                    now=evaluated_at,
                )
                return True
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
                job_id=claim["job_id"],
                lease_owner=owner,
                lease_generation=claim["generation"],
                deadline_at=deadline_at,
                now=evaluated_at,
            )
            if not committed:
                self.store.record_review_disposition(
                    run_id=claim["run_id"],
                    job_id=claim["job_id"],
                    code="FINAL_EVIDENCE_CHANGED",
                    now=evaluated_at,
                    detail={"redispatched": False},
                )
                self.store.complete_review_job(
                    claim["job_id"],
                    owner=owner,
                    generation=claim["generation"],
                    status="WAIT",
                    now=evaluated_at,
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
                now=self.clock(),
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
