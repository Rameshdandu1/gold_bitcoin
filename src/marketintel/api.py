"""Authenticated single-operator API. It never exposes order execution."""

from __future__ import annotations

import base64
import binascii
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from marketintel.config import Settings
from marketintel.detectors import describe_engines
from marketintel.operator_market import operator_overview
from marketintel.research_storage import PaperLedger, ResearchStore
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
    app = FastAPI(title=settings.app_name, version="0.6.0")
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

        def source_current(source: str, accepted: set[str], maximum_age: float) -> bool:
            health = store.source_health(source)
            if (
                health is None
                or health["state"] not in accepted
                or health["last_success_at_utc"] is None
            ):
                return False
            age = (now - datetime.fromisoformat(health["last_success_at_utc"])).total_seconds()
            return 0 <= age <= maximum_age

        gold_symbols = tuple(dict.fromkeys((settings.gold_symbol, "XAUTUSD", "PAXGUSD")))
        gold_book_current = any(
            source_current(
                f"delta_book:{symbol}",
                {"VALID"},
                settings.delta_book_max_age_seconds + 5,
            )
            for symbol in gold_symbols
        )
        gold_reconciliation_current = any(
            source_current(
                f"candle_reconciliation:{symbol}",
                {"VALID"},
                settings.delta_reconciliation_max_age_seconds,
            )
            for symbol in gold_symbols
        )
        required_market_sources = (
            all(
                source_current(source, states, maximum_age)
                for source, states, maximum_age in (
                    (
                        "product_discovery:BTC",
                        {"AVAILABLE"},
                        settings.delta_discovery_max_age_seconds,
                    ),
                    (
                        "product_discovery:GOLD",
                        {"AVAILABLE"},
                        settings.delta_discovery_max_age_seconds,
                    ),
                    ("delta_websocket", {"CONNECTED"}, settings.data_max_age_seconds),
                    (
                        f"delta_book:{settings.btc_symbol}",
                        {"VALID"},
                        settings.delta_book_max_age_seconds + 5,
                    ),
                    (
                        f"candle_reconciliation:{settings.btc_symbol}",
                        {"VALID"},
                        settings.delta_reconciliation_max_age_seconds,
                    ),
                )
            )
            and gold_book_current
            and gold_reconciliation_current
        )
        checks = {
            "database_migration": "0006_phase6_evidence_integrity" in store.migration_ids(),
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
                )
            ),
            "alert_configuration": (
                not settings.alerts_enabled
                or bool(settings.slack_bot_token.get_secret_value() and settings.slack_channel_id)
            ),
            "worker_heartbeat": not settings.live_ingestion_enabled or worker_current,
            "required_market_sources": not settings.live_ingestion_enabled
            or required_market_sources,
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
            "paper_collection_enabled": settings.paper_collection_enabled,
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

    @app.get("/api/market/overview")
    def market_overview() -> dict:
        return operator_overview(store, settings, now=datetime.now(UTC))

    @app.get("/api/candidates")
    def candidates(
        limit: int = 50,
        offset: int = 0,
        asset: Literal["GOLD", "BTC"] | None = None,
        horizon_minutes: int | None = None,
    ) -> list[dict]:
        if horizon_minutes is not None and horizon_minutes not in (30, 60, 240):
            raise HTTPException(status_code=422, detail="Unsupported horizon")
        return store.recent_candidates(limit, offset, asset=asset, horizon_minutes=horizon_minutes)

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

    @app.get("/api/research/summary")
    def research_summary() -> dict:
        research_store = ResearchStore(
            settings.research_database_path, production_path=settings.database_path
        )
        paper_ledger = PaperLedger(
            settings.paper_database_path, production_path=settings.database_path
        )
        summary = research_store.summary()
        latest = summary.get("latest_experiment")
        detail = research_store.experiment_detail(latest["experiment_id"]) if latest else None
        actions = detail.get("action_counts") if detail else None
        paper_summary = paper_ledger.summary()
        if latest and detail:
            paper_summary = paper_ledger.summary(
                experiment_id=latest["experiment_id"],
                include_protected=detail["holdout_state"] != "HOLDOUT_PROTECTED",
            )
        return {
            **summary,
            "paper": paper_summary,
            "data_mode": latest["data_mode"] if latest else "NO_DATASET_SELECTED",
            "selected_experiment_id": latest["experiment_id"] if latest else None,
            "external_calls_performed": actions["external_calls"] if actions else None,
            "real_notifications_sent": actions["real_notifications"] if actions else None,
            "orders_placed": actions["orders"] if actions else None,
            "counter_scope": actions["scope"] if actions else "NOT_MEASURED",
        }

    @app.get("/api/research/experiments")
    def research_experiments(limit: int = 50, offset: int = 0) -> list[dict]:
        return ResearchStore(
            settings.research_database_path, production_path=settings.database_path
        ).experiments(limit=limit, offset=offset)

    @app.get("/api/research/experiments/{experiment_id}")
    def research_experiment(experiment_id: str) -> dict:
        detail = ResearchStore(
            settings.research_database_path, production_path=settings.database_path
        ).experiment_detail(experiment_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Research experiment not found")
        return detail

    @app.get("/api/research/experiments/{experiment_id}/engines")
    def research_engines(experiment_id: str) -> list[dict]:
        research_store = ResearchStore(
            settings.research_database_path, production_path=settings.database_path
        )
        if research_store.experiment(experiment_id) is None:
            raise HTTPException(status_code=404, detail="Research experiment not found")
        return research_store.engine_matrix(experiment_id)

    @app.get("/api/research/experiments/{experiment_id}/opportunities")
    def research_opportunities(experiment_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        research_store = ResearchStore(
            settings.research_database_path, production_path=settings.database_path
        )
        if research_store.experiment(experiment_id) is None:
            raise HTTPException(status_code=404, detail="Research experiment not found")
        return research_store.opportunity_page(experiment_id, limit=limit, offset=offset)

    @app.get("/api/research/paper/transitions")
    def research_paper_transitions(
        limit: int = 100, offset: int = 0, experiment_id: str | None = None
    ) -> list[dict]:
        research_store = ResearchStore(
            settings.research_database_path, production_path=settings.database_path
        )
        if experiment_id is None:
            latest = research_store.summary().get("latest_experiment")
            experiment_id = latest["experiment_id"] if latest else None
        if experiment_id is None:
            return []
        detail = research_store.experiment_detail(experiment_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Research experiment not found")
        return PaperLedger(
            settings.paper_database_path, production_path=settings.database_path
        ).transitions(
            limit=limit,
            offset=offset,
            experiment_id=experiment_id,
            include_protected=detail["holdout_state"] != "HOLDOUT_PROTECTED",
        )

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="operator-dashboard")
    return app


settings = Settings()
store = Store(settings.database_path)
app = create_app(settings, store)
