"""Read-only localhost API. Add authenticated reverse proxy before public exposure."""

from datetime import UTC, datetime

from fastapi import FastAPI

from marketintel.config import Settings
from marketintel.detectors import describe_engines
from marketintel.storage import Store

settings = Settings()
store = Store(settings.database_path)
app = FastAPI(title=settings.app_name, version="0.2.0")


@app.get("/api/health")
def health() -> dict:
    return {
        "service": "marketintel-api",
        "timestamp_utc": datetime.now(UTC).isoformat(),
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


@app.get("/api/candidates/{candidate_id}/lifecycle")
def candidate_lifecycle(candidate_id: str) -> list[dict]:
    """Append-only M2 transitions; candidates are explicitly not AI confirmed."""
    return [event.model_dump(mode="json") for event in store.candidate_lifecycle(candidate_id)]


@app.get("/api/candidates/{candidate_id}/revisions")
def candidate_revisions(candidate_id: str) -> list[dict]:
    """Immutable candidate revisions, newest source snapshot still explicitly unconfirmed."""
    return store.candidate_revisions(candidate_id)


@app.get("/api/snapshots/{snapshot_id}")
def feature_snapshot(snapshot_id: str) -> dict | None:
    snapshot = store.feature_snapshot(snapshot_id)
    return snapshot.model_dump(mode="json") if snapshot else None
