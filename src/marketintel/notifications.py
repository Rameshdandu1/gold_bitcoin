"""Durable Slack alert delivery. Alerts are disabled by default and never place orders."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from marketintel.analysis import load_canonical_analysis
from marketintel.config import Settings
from marketintel.review_worker import current_eligibility
from marketintel.storage import Store

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
LOGGER = logging.getLogger(__name__)


class DeliveryAcceptedUnknown(RuntimeError):
    """Remote acceptance may have happened, but no durable receipt was recorded."""


class SlackTransientError(RuntimeError):
    pass


class AlertTransport(Protocol):
    async def send(
        self,
        *,
        token: str,
        channel_id: str,
        text: str,
        delivery_key: str,
    ) -> str: ...


class SlackWebAPITransport:
    async def send(
        self,
        *,
        token: str,
        channel_id: str,
        text: str,
        delivery_key: str,
    ) -> str:
        # The secret is carried only in the Authorization header, never the URL or payload.
        client_message_id = str(uuid.UUID(delivery_key[:32]))
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                SLACK_POST_MESSAGE_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel": channel_id,
                    "text": text,
                    "mrkdwn": False,
                    "client_msg_id": client_message_id,
                },
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise SlackTransientError(f"slack_http_{response.status_code}")
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            error = str(body.get("error", "unknown_error"))
            if error in {"ratelimited", "internal_error", "fatal_error"}:
                raise SlackTransientError(f"slack_{error}")
            raise RuntimeError(f"slack_{error}")
        receipt = body.get("ts")
        if not isinstance(receipt, str) or not receipt:
            raise DeliveryAcceptedUnknown("Slack response omitted a stable receipt")
        return receipt


def render_alert(payload: dict) -> str:
    targets = ", ".join(f"T{item['index']}={item['price']}" for item in payload.get("targets", ()))
    return "\n".join(
        [
            f"RESEARCH REVIEW {payload['event_type']} — NO ORDER EXECUTION",
            f"{payload['symbol']} ({payload['venue']}) {payload['direction']} "
            f"{payload['horizon_minutes']}m",
            f"Entry={payload['entry']} Invalidation={payload['invalidation']} Targets: {targets}",
            f"Market observed={payload['market_observed_at_utc']}",
            f"Review completed={payload['reviewed_at_utc']} Expires={payload['expires_at_utc']}",
            payload["meaning"],
        ]
    )


class AlertWorker:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        transport: AlertTransport | None = None,
    ):
        self.store = store
        self.settings = settings
        self.transport = transport or SlackWebAPITransport()

    async def run_once(self, *, owner: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if not self.settings.alerts_enabled:
            return False
        token = self.settings.slack_bot_token.get_secret_value()
        if not token or not self.settings.slack_channel_id:
            return False
        item = self.store.claim_outbox_item(
            owner,
            now=now,
            lease_seconds=self.settings.alert_lease_seconds,
        )
        if item is None:
            return False
        expected_destination = f"slack:{self.settings.slack_channel_id}"
        if item["destination_id"] != expected_destination:
            self.store.finish_outbox_attempt(
                item,
                status="SUPPRESSED",
                now=now,
                error="immutable destination is not served by current configuration",
            )
            return True
        eligible, reason = self.store.outbox_delivery_eligible(item, now=now)
        if not eligible:
            self.store.finish_outbox_attempt(
                item,
                status="SUPPRESSED",
                now=now,
                error=reason,
            )
            return True
        if item["event_type"] == "CONFIRMED":
            decision = self.store.consensus_decision_by_id(item["decision_id"])
            payload = (
                self.store.analysis_envelope_bytes(decision["envelope_digest"])
                if decision is not None
                else None
            )
            if decision is None or payload is None:
                self.store.finish_outbox_attempt(
                    item,
                    status="SUPPRESSED",
                    now=now,
                    error="confirmation evidence is unavailable",
                )
                return True
            analysis = load_canonical_analysis(payload, decision["envelope_digest"])
            current = current_eligibility(self.store, self.settings, analysis, now=now)
            current_checks = {
                "stop breach": not current.stop_breached,
                "target exhaustion": not current.target_crossed_indices,
                "event ordering": not current.event_order_ambiguous,
                "instrument discovery": current.discovery_current,
                "candle reconciliation": current.reconciliation_current,
                "trade stream": current.trade_stream_current,
                "validated book": current.book_current,
            }
            failed = [name for name, passed in current_checks.items() if not passed]
            if failed:
                self.store.finish_outbox_attempt(
                    item,
                    status="SUPPRESSED",
                    now=now,
                    error="current confirmation gate failed: " + ", ".join(failed),
                )
                return True
        if not self.store.mark_outbox_dispatch_started(item, now=now):
            return True
        try:
            receipt = await self.transport.send(
                token=token,
                channel_id=item["destination_id"].split(":", 1)[1],
                text=render_alert(item["payload"]),
                delivery_key=item["delivery_key"],
            )
        except DeliveryAcceptedUnknown as exc:
            self.store.finish_outbox_attempt(
                item,
                status="RECEIPT_UNKNOWN",
                now=now,
                error=type(exc).__name__,
            )
        except SlackTransientError as exc:
            next_attempt = item["attempts"] + 1
            if next_attempt >= self.settings.alert_max_attempts:
                self.store.finish_outbox_attempt(
                    item,
                    status="FAILED",
                    now=now,
                    error=type(exc).__name__,
                )
            else:
                self.store.finish_outbox_attempt(
                    item,
                    status="RETRY",
                    now=now,
                    retry_at=now + timedelta(seconds=min(2**next_attempt, 300)),
                    error=type(exc).__name__,
                )
        except Exception as exc:
            self.store.finish_outbox_attempt(
                item,
                status="FAILED",
                now=now,
                error=type(exc).__name__,
            )
        else:
            self.store.finish_outbox_attempt(
                item,
                status="SENT",
                now=now,
                receipt_id=receipt,
            )
        return True


async def main() -> None:
    settings = Settings()
    store = Store(settings.database_path)
    logging.basicConfig(level=logging.INFO)
    if not settings.alerts_enabled:
        LOGGER.warning("Outbound alerts are DISABLED; no notification will be sent")
        return
    owner = f"alert-{uuid.uuid4().hex}"
    worker = AlertWorker(store, settings)
    while True:
        worked = await worker.run_once(owner=owner)
        if not worked:
            store.record_source_status("alert_worker", "AVAILABLE", "Outbox idle")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
