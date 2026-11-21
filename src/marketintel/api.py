"""Read-only localhost API. Add authenticated reverse proxy before public exposure."""

from datetime import datetime, timezone

from fastapi import FastAPI

from marketintel.config import Settings
from marketintel.detectors import describe_engines
from marketintel.storage import Store

settings = Settings()
store = Store(settings.database_path)
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {
        "service": "marketintel-api",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "live_ingestion_enabled": settings.live_ingestion_enabled,
        "ai_enabled": settings.ai_enabled,
        "trading_enabled": False,
        "services": store.get_status(),
        "warning": "Research MVP. No order execution. Status is not trading advice.",
    }


@app.get("/api/engines")
def engines() -> list[dict]:
    return store.last_engine_states(describe_engines(settings.gold_symbol, settings.btc_symbol))


@app.get("/api/candidates")
def candidates(limit: int = 50) -> list[dict]:
    return store.recent_candidates(limit)


@app.get("/api/candidates/{candidate_id}/assessments")
def assessments(candidate_id: str) -> list[dict]:
    # Present independent provider evaluations without exposing API keys.
    return store.assessments(candidate_id)
