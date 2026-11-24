from datetime import UTC, datetime

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, TransportReply
from marketintel.config import Settings
from marketintel.provider_smoke import run_provider_smoke, smoke_analysis
from marketintel.review import AnalystAssessmentV2, TokenUsage
from marketintel.storage import Store


class SmokeTransport:
    def __init__(self, provider_model: str):
        self.provider_model = provider_model
        self.calls = 0

    async def __call__(self, request_bytes, **_kwargs):
        self.calls += 1
        wrapper = __import__("json").loads(request_bytes)
        analysis = smoke_analysis(datetime(2026, 11, 24, tzinfo=UTC))
        envelope = analysis.envelope
        assessment = AnalystAssessmentV2(
            schema_version="2",
            candidate_id=envelope.candidate_id,
            candidate_revision_id=envelope.candidate_revision_id,
            snapshot_id=envelope.snapshot_id,
            analysis_input_hash=wrapper["analysis_input_hash"],
            asset=envelope.asset,
            symbol=envelope.symbol,
            engine=envelope.engine,
            horizon_minutes=envelope.horizon_minutes,
            direction=envelope.direction,
            decision="WAIT",
            supported_target_indices=(),
            agrees_with_invalidation=True,
            reason="Synthetic connectivity smoke; no market conclusion.",
            counter_evidence=(),
            data_warnings=("SYNTHETIC_PROVIDER_CONNECTIVITY_SMOKE_NOT_MARKET_SIGNAL",),
        )
        return TransportReply(
            parsed=assessment,
            returned_model=self.provider_model,
            response_id=f"response-{self.provider_model}",
            finish_reason="completed" if self.provider_model == "gpt-smoke" else "end_turn",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )


async def test_paid_smoke_is_budgeted_once_per_provider_and_uses_identical_digest(tmp_path):
    now = datetime(2026, 11, 24, tzinfo=UTC)
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "smoke.sqlite3",
        openai_api_key="fixture-openai",
        openai_model="gpt-smoke",
        anthropic_api_key="fixture-anthropic",
        anthropic_model="claude-smoke",
        openai_input_microusd_per_million_tokens=100_000,
        openai_output_microusd_per_million_tokens=500_000,
        anthropic_input_microusd_per_million_tokens=100_000,
        anthropic_output_microusd_per_million_tokens=500_000,
        ai_provider_call_limit_per_day=25,
        ai_total_call_limit_per_day=50,
        ai_total_cost_limit_microusd_per_day=5_000_000,
    )
    store = Store(settings.database_path)
    openai_transport = SmokeTransport("gpt-smoke")
    anthropic_transport = SmokeTransport("claude-smoke")
    enabled = settings.model_copy(update={"ai_enabled": True})
    adapters = (
        GPTAnalyst(enabled, openai_transport, clock=lambda: now),
        ClaudeAnalyst(enabled, anthropic_transport, clock=lambda: now),
    )

    first = await run_provider_smoke(settings, store, now=now, adapters=adapters)
    second = await run_provider_smoke(settings, store, now=now, adapters=adapters)

    assert first["both_succeeded"] is True
    assert {row["status"] for row in second["results"]} == {"BUDGET_OR_CALL_LIMIT_BLOCKED"}
    assert openai_transport.calls == 1
    assert anthropic_transport.calls == 1
    assert store.budget_status(now=now)["reserved_calls"] == 2
    assert store.budget_status(now=now)["reported_actual_cost_microusd"] == 70


def test_smoke_analysis_is_explicitly_synthetic_and_not_a_live_signal():
    analysis = smoke_analysis(datetime(2026, 11, 24, tzinfo=UTC))

    assert "SYNTHETIC_PROVIDER_CONNECTIVITY_SMOKE" in analysis.envelope.trigger
    assert analysis.envelope.required_context == (
        "SYNTHETIC_PROVIDER_CONNECTIVITY_SMOKE_NOT_MARKET_SIGNAL",
    )
