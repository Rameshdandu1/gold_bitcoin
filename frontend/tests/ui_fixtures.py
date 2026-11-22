"""Hypothetical API responses for browser tests; never used by the application."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

WARNING = "Illustrative UI test data — hypothetical prices and provider responses. Not live."
GOLD_SWEEP = "ui-gold-fast-bull-sweep"
GOLD_INVALIDATED = "ui-gold-hourly-breakout"
GOLD_EXPIRED = "ui-gold-session-structure"
BTC_SWEEP = "ui-btc-fast-bear-sweep"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _flow(count: int, observed: datetime, bullish: bool, price: float) -> dict[str, Any]:
    buy, sell = (count * 8, count * 2) if bullish else (count * 2, count * 8)
    return {
        "label": f"last_{count}",
        "requested_trade_count": count,
        "trade_count": count,
        "classified_trade_count": count,
        "unclassified_trade_count": 0,
        "elapsed_seconds": "120",
        "trades_per_second": str(count / 120),
        "latest_event_time_utc": _iso(observed),
        "latest_received_at_utc": _iso(observed),
        "buy_contracts": str(buy),
        "sell_contracts": str(sell),
        "unclassified_contracts": "0",
        "cvd_contracts": str(buy - sell),
        "cvd_base_units": str((buy - sell) / 1000),
        "cvd_quote_notional": str(Decimal(buy - sell) / 1000 * Decimal(str(price))),
    }


def _review(candidate: dict[str, Any], revision: str, confirmed: bool) -> dict[str, Any]:
    observed = datetime.fromisoformat(candidate["observed_at_utc"])
    digest = _digest("hypothetical-envelope:" + revision)
    attempts = []
    for index, provider in enumerate(("OPENAI", "ANTHROPIC")):
        assessment = {
            "schema_version": "2",
            "candidate_id": candidate["candidate_id"],
            "candidate_revision_id": revision,
            "snapshot_id": candidate["snapshot_id"],
            "analysis_input_hash": digest,
            **{
                key: candidate[key]
                for key in ("asset", "symbol", "engine", "horizon_minutes", "direction")
            },
            "decision": "CONFIRM" if confirmed else "WAIT",
            "supported_target_indices": [1] if confirmed else [],
            "agrees_with_invalidation": True,
            "reason": f"Hypothetical {provider} UI-test response; not a real provider result.",
            "counter_evidence": ["Illustrative evidence only; no measured predictive performance."],
            "data_warnings": [WARNING],
        }
        attempts.append(
            {
                "attempt_id": f"hypothetical-{provider.lower()}-{revision}",
                "provider": provider,
                "attempt_number": 1,
                "requested_model": f"hypothetical-{provider.lower()}-model",
                "returned_model": f"hypothetical-{provider.lower()}-model",
                "status": "SUCCEEDED",
                "started_at_utc": _iso(observed + timedelta(seconds=1)),
                "completed_at_utc": _iso(observed + timedelta(seconds=2 + index)),
                "request_id": f"hypothetical-{provider.lower()}-request",
                "response_id": f"hypothetical-{provider.lower()}-response",
                "finish_reason": "hypothetical_complete",
                "input_tokens": 300,
                "output_tokens": 100,
                "failure_code": None,
                "assessment": assessment,
                "metadata": {"fixture": WARNING},
            }
        )
    return {
        "run_id": "hypothetical-run-" + revision,
        "status": "COMPLETED",
        "created_at_utc": _iso(observed),
        "deadline_at_utc": _iso(observed + timedelta(seconds=30)),
        "envelope_digest": digest,
        "attempts": attempts,
    }


@dataclass
class UiFixtures:
    """The real read API shape, with prices and all evidence explicitly hypothetical."""

    health: dict[str, Any]
    engines: list[dict[str, Any]]
    entries: list[dict[str, Any]]
    snapshots: dict[str, dict[str, Any]]
    research: dict[str, Any]

    def snapshot_id(self, candidate_id: str) -> str:
        return next(
            row["candidate"]["snapshot_id"]
            for row in self.entries
            if row["candidate"]["candidate_id"] == candidate_id
        )

    def payload(self, path: str, mode: str = "normal") -> Any:
        """Resolve only explicit fixture endpoints; unknown paths raise KeyError."""
        if path.startswith("/api/snapshots/"):
            snapshot = self.snapshots[path.rsplit("/", 1)[1]]
            return None if mode == "missing_snapshot" else snapshot
        return {
            "/api/health": self.health,
            "/api/engines": self.engines,
            "/api/candidates": [] if mode == "empty" else self.entries,
            "/api/budget": self.health["budget"],
            "/api/queue": self.health["queue"],
            "/api/research/summary": self.research,
            "/api/research/experiments": [],
            "/api/research/paper/transitions": [],
        }[path]


def build_fixtures(now: datetime | None = None) -> UiFixtures:
    """Build six records relative to this run, including deliberate terminal histories."""
    now = (now or datetime.now(UTC)).replace(microsecond=0)
    if now.tzinfo is None:
        raise ValueError("UI fixture clock must be timezone aware")
    specs = (
        (GOLD_SWEEP, "GOLD", 30, "BULLISH", "CANDIDATE", False),
        (GOLD_INVALIDATED, "GOLD", 60, "BEARISH", "INVALIDATED", True),
        (GOLD_EXPIRED, "GOLD", 240, "BEARISH", "EXPIRED", True),
        (BTC_SWEEP, "BTC", 30, "BEARISH", "CANDIDATE", True),
        ("ui-btc-hourly-breakout", "BTC", 60, "BULLISH", "CANDIDATE", False),
        ("ui-btc-session-structure", "BTC", 240, "BULLISH", "CANDIDATE", False),
    )
    entries, engines, snapshots = [], [], {}
    for candidate_id, asset, horizon, direction, lifecycle, confirmed in specs:
        family, resolution = {30: ("FAST", "1m"), 60: ("HOURLY", "5m"), 240: ("SESSION", "15m")}[
            horizon
        ]
        observed = now - timedelta(minutes=horizon + 5 if lifecycle == "EXPIRED" else 2)
        bullish = direction == "BULLISH"
        entry, risk, distance = (2632.4, 6.0, 10.0) if asset == "GOLD" else (97420.0, 210.0, 500.0)
        sign = 1 if bullish else -1
        candidate = {
            "schema_version": "2",
            "candidate_id": candidate_id,
            "snapshot_id": _digest("hypothetical-snapshot:" + candidate_id),
            "asset": asset,
            "symbol": "XAUTUSD" if asset == "GOLD" else "BTCUSD",
            "venue": "delta_india",
            "engine": f"{asset}_{family}",
            "horizon_minutes": horizon,
            "candle_close_utc": _iso(observed),
            "observed_at_utc": _iso(observed),
            "expires_at_utc": _iso(observed + timedelta(minutes=horizon)),
            "direction": direction,
            "state": "CANDIDATE",
            "trigger": {
                30: "1m liquidity sweep and closed-candle reclaim",
                60: "5m breakout with closed-candle follow-through/retest",
                240: "higher-timeframe BOS",
            }[horizon],
            "entry": entry,
            "invalidation": entry - sign * risk,
            "targets": [entry + sign * distance * index for index in (1, 2, 3)],
            "feature_evidence": [
                "HYPOTHETICAL UI TEST",
                "relative_volume=1.7",
                "range_expansion=1.4",
            ],
            "counter_evidence": [WARNING],
            "explanation": WARNING,
            "source_quality": "FRESH",
            "rule_version": "hypothetical-ui-fixture-v1",
            "not_ai_confirmed": True,
        }
        flow = {f"last_{count}": _flow(count, observed, bullish, entry) for count in (500, 5000)}
        for minutes in (5, 15):
            flow[f"last_{minutes}m"] = {
                **_flow(minutes * 100, observed, bullish, entry),
                "label": f"last_{minutes}m",
                "requested_trade_count": None,
                "window_seconds": minutes * 60,
            }
        snapshots[candidate["snapshot_id"]] = {
            **{
                key: candidate[key]
                for key in (
                    "schema_version",
                    "snapshot_id",
                    "asset",
                    "symbol",
                    "venue",
                    "engine",
                    "horizon_minutes",
                    "candle_close_utc",
                    "observed_at_utc",
                    "source_quality",
                )
            },
            "regime": "TRENDING" if bullish else "RANGING",
            "structures": [],
            "liquidity_levels": [
                {
                    "schema_version": "1",
                    "kind": "SESSION_LOW" if bullish else "SESSION_HIGH",
                    "price": str(entry - sign * 4),
                    "observed_at_utc": _iso(observed - timedelta(minutes=1)),
                    "source": "hypothetical_utc_session",
                    "touches": 2,
                }
            ],
            "order_flow": flow,
            "book": {
                "available": True,
                "observed_at_utc": _iso(observed),
                "best_bid": str(entry - 0.1),
                "best_ask": str(entry + 0.1),
                "spread": "0.2",
                "bid_depth_quote": "140000" if bullish else "60000",
                "ask_depth_quote": "60000" if bullish else "140000",
                "imbalance": "0.4" if bullish else "-0.4",
                "absorption": "NONE",
                "reason": WARNING,
            },
            "volatility": {
                "atr": str(risk),
                "projected_move": str(distance * 4),
                "relative_volume": "1.7",
                "range_expansion": "1.4",
                "method": "Hypothetical UI test, not a forecast",
            },
            "vwap": str(entry - sign * 2),
            "coverage": [],
            "warnings": [WARNING],
            "external_metrics": [],
        }
        revision = "hypothetical-revision-" + candidate_id
        review = _review(candidate, revision, confirmed)
        decision_time = observed + timedelta(seconds=4)
        consensus = {
            "schema_version": "2",
            "decision_id": "hypothetical-decision-" + candidate_id,
            "run_id": review["run_id"],
            "candidate_id": candidate_id,
            "candidate_revision_id": revision,
            "envelope_digest": review["envelope_digest"],
            "status": "CONFIRMED" if confirmed else "WAIT",
            "reason": "Hypothetical historical review; check current lifecycle separately.",
            "supported_target_indices": [1] if confirmed else [],
            "provider_attempt_ids": [attempt["attempt_id"] for attempt in review["attempts"]],
            "gates": [{"code": "HYPOTHETICAL_UI_FIXTURE", "passed": confirmed, "detail": WARNING}],
            "eligibility": {
                "schema_version": "1",
                "candidate_id": candidate_id,
                "candidate_revision_id": revision,
                "eligibility_token": "hypothetical-eligibility-token",
                "active_revision_generation": 1,
                "lifecycle_state": "CANDIDATE",
                "evaluated_at_utc": _iso(decision_time),
                "evidence_valid_until_utc": _iso(decision_time + timedelta(seconds=10)),
                "latest_trade_price": str(entry),
                "latest_trade_at_utc": _iso(decision_time),
                "best_bid": str(entry - 0.1),
                "best_ask": str(entry + 0.1),
                "book_observed_at_utc": _iso(decision_time),
                "discovery_current": True,
                "reconciliation_current": True,
                "trade_stream_current": True,
                "book_current": True,
                "stop_breached": False,
                "target_crossed_indices": [],
                "event_order_ambiguous": False,
                "required_costs_known": True,
                "fee_bps": "1",
                "slippage_bps": "1",
                "maximum_entry_drift_bps": "10",
                "maximum_spread_bps": "10",
                "minimum_net_reward_risk": "1.2",
                "calendar_policy": "TOKEN_MARKET_ONLY",
                "notification_ready": False,
            },
            "decided_at_utc": _iso(decision_time),
        }
        entries.append(
            {
                "candidate": candidate,
                "candidate_revision_id": revision,
                "review": review,
                "consensus": consensus,
                "current_lifecycle_state": lifecycle,
                "current_lifecycle_reason": f"Hypothetical {lifecycle.lower()} lifecycle event.",
                "current_lifecycle_at_utc": _iso(
                    now - timedelta(seconds=15) if lifecycle != "CANDIDATE" else observed
                ),
            }
        )
        engines.append(
            {
                "id": candidate["engine"],
                "asset": asset,
                "symbol": candidate["symbol"],
                "resolution": resolution,
                "horizon_minutes": horizon,
                "state": lifecycle,
                "observed_at_utc": _iso(now),
                "reason": WARNING,
            }
        )
    budget = {
        "day_utc": now.date().isoformat(),
        "reserved_calls": 0,
        "reserved_cost_microusd": 0,
        "reported_actual_cost_microusd": 0,
        "usage_unknown_count": 0,
        "admission_cost_microusd": 0,
    }
    queue = {
        "review_jobs": {},
        "stale_review_leases": 0,
        "alert_items": {},
        "stale_alert_leases": 0,
    }
    health = {
        "service": "marketintel-api",
        "timestamp_utc": _iso(now),
        "live_ingestion_enabled": False,
        "ai_enabled": False,
        "alerts_enabled": False,
        "paper_collection_enabled": False,
        "trading_enabled": False,
        "warning": WARNING,
        "services": [
            {"service": "worker", "updated_at": _iso(now), "state": "DISABLED", "detail": WARNING}
        ],
        "source_health": [],
        "budget": budget,
        "queue": queue,
    }
    research = {
        "status": "NOT_STARTED",
        "experiment_count": 0,
        "report_count": 0,
        "opportunity_count": 0,
        "latest_experiment": None,
        "selected_experiment_id": None,
        "data_mode": "NO_DATASET_SELECTED",
        "external_calls_performed": None,
        "real_notifications_sent": None,
        "orders_placed": None,
        "counter_scope": "NOT_MEASURED",
        "warning": WARNING,
        "paper": {
            "status": "NOT_STARTED",
            "decisions": 0,
            "outcomes": 0,
            "explicit_gaps": 0,
            "evidence_modes": {},
            "warning": WARNING,
        },
    }
    return UiFixtures(health, engines, entries, snapshots, research)


def serve_preview(port: int, mode: str = "normal") -> None:
    """Explicit local preview adapter for Vite's /api proxy; no production imports."""
    fixtures = build_fixtures()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            path = urlsplit(self.path).path
            status = 200
            if mode in {"auth", "unavailable"}:
                status = 401 if mode == "auth" else 503
                payload = {
                    "detail": "Hypothetical authentication required"
                    if status == 401
                    else "Hypothetical service unavailable"
                }
            else:
                try:
                    payload = fixtures.payload(path, mode)
                except KeyError:
                    status, payload = 404, {"detail": "No hypothetical fixture for this API route"}
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    print(WARNING, flush=True)
    print(f"Fixture API only: http://127.0.0.1:{port}; mode={mode}", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Explicit hypothetical fixture API for local UI preview; never live data."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--mode",
        choices=("normal", "empty", "missing_snapshot", "auth", "unavailable"),
        default="normal",
    )
    arguments = parser.parse_args()
    serve_preview(arguments.port, arguments.mode)
