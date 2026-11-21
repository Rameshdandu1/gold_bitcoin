"""Authenticated single-operator API. It never exposes order execution."""

from __future__ import annotations

import base64
import binascii
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from marketintel.config import Settings
from marketintel.detectors import describe_engines
from marketintel.storage import Store


def _authorized(request: Request, settings: Settings) -> bool:
    if not settings.operator_auth_enabled:
        return True
    expected_user = settings.operator_username
    expected_password = settings.operator_password.get_secret_value()
    if not expected_user or not expected_password:
        return False
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return secrets.compare_digest(username.encode("utf-8"), expected_user.encode("utf-8")) and (
        secrets.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8"))
    )


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings()
    store = store or Store(settings.database_path)
    app = FastAPI(title=settings.app_name, version="0.3.0")
    allowed_origins = tuple(
        origin.strip() for origin in settings.cors_allowed_origins_csv.split(",") if origin.strip()
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def operator_authentication(request: Request, call_next):
        if request.url.path == "/healthz" or request.method == "OPTIONS":
            return await call_next(request)
        if not _authorized(request, settings):
            configured = bool(
                settings.operator_username and settings.operator_password.get_secret_value()
            )
            return JSONResponse(
                status_code=401 if configured else 503,
                content={
                    "detail": (
                        "Operator authentication required"
                        if configured
                        else "Operator authentication is not configured"
                    )
                },
                headers={"WWW-Authenticate": 'Basic realm="marketintel-operator"'},
            )
        return await call_next(request)

    @app.get("/healthz")
    def liveness() -> dict:
        return {"service": "marketintel-api", "status": "alive"}

    @app.get("/readyz")
    def readiness() -> JSONResponse:
        now = datetime.now(UTC)
        queue = store.queue_status(now=now)
        budget = store.budget_status(now=now)
        worker = store.source_health("worker")
        worker_current = (
            worker is not None
            and worker["state"] == "AVAILABLE"
            and (now - datetime.fromisoformat(worker["heartbeat_at_utc"])).total_seconds()
            <= settings.delta_discovery_refresh_seconds + 60
        )
        checks = {
            "database_migration": "0003_phase3_review_pipeline" in store.migration_ids(),
            "operator_authentication": (
                not settings.operator_auth_enabled
                or bool(
                    settings.operator_username and settings.operator_password.get_secret_value()
                )
            ),
            "ai_configuration": (
                not settings.ai_enabled
                or bool(
                    settings.openai_api_key
                    and settings.openai_model
                    and settings.anthropic_api_key
                    and settings.anthropic_model
                    and settings.openai_input_microusd_per_million_tokens is not None
                    and settings.openai_output_microusd_per_million_tokens is not None
                    and settings.anthropic_input_microusd_per_million_tokens is not None
                    and settings.anthropic_output_microusd_per_million_tokens is not None
                    and settings.ai_total_cost_limit_microusd_per_day > 0
                    and settings.risk_fee_bps
                    and settings.risk_slippage_bps
                    and settings.slack_bot_token.get_secret_value()
                    and settings.slack_channel_id
                )
            ),
            "alert_configuration": (
                not settings.alerts_enabled
                or bool(settings.slack_bot_token.get_secret_value() and settings.slack_channel_id)
            ),
            "worker_heartbeat": not settings.live_ingestion_enabled or worker_current,
            "required_market_sources": not settings.live_ingestion_enabled
            or all(
                store.source_is_eligible(
                    f"product_discovery:{asset}",
                    now=now,
                    maximum_success_age_seconds=settings.delta_discovery_max_age_seconds,
                )
                for asset in ("BTC", "GOLD")
            ),
            "review_queue_recoverable": (
                queue["stale_review_leases"] == 0 and queue["review_jobs"].get("DISPATCHED", 0) == 0
            ),
            "budget_available": not settings.ai_enabled
            or (
                budget["reserved_calls"] < settings.ai_total_call_limit_per_day
                and budget["reserved_cost_microusd"] < settings.ai_total_cost_limit_microusd_per_day
            ),
        }
        ready = all(checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "ready": ready,
                "checks": checks,
                "live_ingestion_enabled": settings.live_ingestion_enabled,
                "ai_enabled": settings.ai_enabled,
                "alerts_enabled": settings.alerts_enabled,
                "queue": queue,
                "budget": budget,
            },
        )

    @app.get("/api/health")
    def health() -> dict:
        return {
            "service": "marketintel-api",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "live_ingestion_enabled": settings.live_ingestion_enabled,
            "ai_enabled": settings.ai_enabled,
            "alerts_enabled": settings.alerts_enabled,
            "trading_enabled": False,
            "services": store.get_status(),
            "source_health": store.all_source_health(),
            "budget": store.budget_status(),
            "queue": store.queue_status(),
            "warning": "Research service. No order execution. Status is not trading advice.",
        }

    @app.get("/api/engines")
    def engines() -> list[dict]:
        return store.last_engine_states(describe_engines(settings.gold_symbol, settings.btc_symbol))

    @app.get("/api/candidates")
    def candidates(limit: int = 50, offset: int = 0) -> list[dict]:
        return store.recent_candidates(limit, offset)

    @app.get("/api/candidates/{candidate_id}/assessments")
    def assessments(candidate_id: str) -> list[dict]:
        return store.assessments(candidate_id)

    @app.get("/api/candidates/{candidate_id}/lifecycle")
    def candidate_lifecycle(candidate_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        rows = store.candidate_lifecycle(candidate_id)
        bounded = rows[max(offset, 0) : max(offset, 0) + min(max(limit, 1), 200)]
        return [event.model_dump(mode="json") for event in bounded]

    @app.get("/api/candidates/{candidate_id}/revisions")
    def candidate_revisions(candidate_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        rows = store.candidate_revisions(candidate_id)
        return rows[max(offset, 0) : max(offset, 0) + min(max(limit, 1), 200)]

    @app.get("/api/snapshots/{snapshot_id}")
    def feature_snapshot(snapshot_id: str) -> dict | None:
        snapshot = store.feature_snapshot(snapshot_id)
        return snapshot.model_dump(mode="json") if snapshot else None

    @app.get("/api/budget")
    def budget() -> dict:
        return store.budget_status()

    @app.get("/api/queue")
    def queue() -> dict:
        return store.queue_status()

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="operator-dashboard")
    return app


settings = Settings()
store = Store(settings.database_path)
app = create_app(settings, store)
