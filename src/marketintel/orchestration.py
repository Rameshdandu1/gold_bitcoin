"""Durable bounded dual-provider review orchestration with persistent spend reservations."""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from marketintel.ai import ClaudeAnalyst, GPTAnalyst, ProviderAdapter
from marketintel.analysis import CanonicalAnalysis
from marketintel.config import Settings
from marketintel.review import ProviderResult
from marketintel.storage import Store

TRANSIENT_PROVIDER_STATUSES = {
    "TIMEOUT",
    "TRANSPORT_ERROR",
    "RATE_LIMITED",
    "PROVIDER_ERROR",
}


class ReviewOrchestrator:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        gpt: GPTAnalyst,
        claude: ClaudeAnalyst,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self.store = store
        self.settings = settings
        self.gpt = gpt
        self.claude = claude
        self.clock = clock or (lambda: datetime.now(UTC))

    def _rates(self, provider: str) -> tuple[int, int] | None:
        values = (
            (
                self.settings.openai_input_microusd_per_million_tokens,
                self.settings.openai_output_microusd_per_million_tokens,
            )
            if provider == "OPENAI"
            else (
                self.settings.anthropic_input_microusd_per_million_tokens,
                self.settings.anthropic_output_microusd_per_million_tokens,
            )
        )
        if values[0] is None or values[1] is None:
            return None
        return int(values[0]), int(values[1])

    def _estimated_cost(self, rates: tuple[int, int]) -> int:
        return math.ceil(
            (
                self.settings.ai_max_input_tokens * rates[0]
                + self.settings.ai_max_output_tokens * rates[1]
            )
            / 1_000_000
        )

    @staticmethod
    def _actual_cost(result: ProviderResult, rates: tuple[int, int]) -> int | None:
        if result.usage.input_tokens is None or result.usage.output_tokens is None:
            return None
        return math.ceil(
            (result.usage.input_tokens * rates[0] + result.usage.output_tokens * rates[1])
            / 1_000_000
        )

    def _not_ready(self, adapter: ProviderAdapter, *, attempt: int, code: str) -> ProviderResult:
        return adapter._result(
            status="NOT_READY",
            started=self.clock(),
            attempt_number=attempt,
            failure_code=code,
        )

    async def _run_provider(
        self,
        adapter: ProviderAdapter,
        analysis: CanonicalAnalysis,
        *,
        run_id: str,
        claim: dict,
        deadline_at: datetime,
    ) -> ProviderResult:
        if not self.settings.ai_enabled or not adapter.api_key or not adapter.requested_model:
            result = await adapter.review(analysis, deadline_at=deadline_at, attempt_number=1)
            self.store.save_provider_result(
                run_id=run_id,
                job_id=claim["job_id"],
                owner=claim["owner"],
                generation=claim["generation"],
                dispatch_id=f"preflight-{adapter.provider.lower()}-{uuid.uuid4().hex}",
                result=result,
            )
            return result
        rates = self._rates(adapter.provider)
        if rates is None:
            result = self._not_ready(adapter, attempt=1, code="MODEL_PRICE_CONFIGURATION_MISSING")
            self.store.save_provider_result(
                run_id=run_id,
                job_id=claim["job_id"],
                owner=claim["owner"],
                generation=claim["generation"],
                dispatch_id=f"not-ready-{adapter.provider.lower()}-{uuid.uuid4().hex}",
                result=result,
            )
            return result

        last: ProviderResult | None = None
        for attempt in range(1, self.settings.ai_max_attempts_per_provider + 1):
            now = self.clock()
            if now >= deadline_at:
                result = adapter._result(
                    status="DEADLINE_EXCEEDED",
                    started=now,
                    attempt_number=attempt,
                    failure_code="TOTAL_DEADLINE_EXCEEDED",
                )
                self.store.save_provider_result(
                    run_id=run_id,
                    job_id=claim["job_id"],
                    owner=claim["owner"],
                    generation=claim["generation"],
                    dispatch_id=f"deadline-{adapter.provider.lower()}-{uuid.uuid4().hex}",
                    result=result,
                )
                return result
            estimated = self._estimated_cost(rates)
            reservation = self.store.reserve_provider_budget(
                run_id=run_id,
                provider=adapter.provider,
                attempt_number=attempt,
                now=now,
                input_tokens=self.settings.ai_max_input_tokens,
                output_tokens=self.settings.ai_max_output_tokens,
                cost_microusd=estimated,
                provider_call_limit=self.settings.ai_provider_call_limit_per_day,
                total_call_limit=self.settings.ai_total_call_limit_per_day,
                total_cost_limit_microusd=self.settings.ai_total_cost_limit_microusd_per_day,
            )
            if reservation is None:
                result = self._not_ready(adapter, attempt=attempt, code="BUDGET_LIMIT_REACHED")
                self.store.save_provider_result(
                    run_id=run_id,
                    job_id=claim["job_id"],
                    owner=claim["owner"],
                    generation=claim["generation"],
                    dispatch_id=f"budget-blocked-{adapter.provider.lower()}-{uuid.uuid4().hex}",
                    result=result,
                )
                return result

            dispatch_id = f"{run_id[:12]}-{adapter.provider.lower()}-{attempt}-{uuid.uuid4().hex}"
            result = await adapter.review(analysis, deadline_at=deadline_at, attempt_number=attempt)
            self.store.save_provider_result(
                run_id=run_id,
                job_id=claim["job_id"],
                owner=claim["owner"],
                generation=claim["generation"],
                dispatch_id=dispatch_id,
                result=result,
            )
            actual_cost = self._actual_cost(result, rates)
            unknown = actual_cost is None
            self.store.reconcile_provider_budget(
                reservation,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                actual_cost_microusd=actual_cost,
                status="USAGE_UNKNOWN" if unknown else "RECONCILED",
                now=self.clock(),
            )
            last = result
            if result.status not in TRANSIENT_PROVIDER_STATUSES:
                return result
            if attempt >= self.settings.ai_max_attempts_per_provider:
                return result
            remaining = (deadline_at - self.clock()).total_seconds()
            delay = min(0.1 * attempt, max(remaining, 0))
            if delay <= 0:
                return result
            await asyncio.sleep(delay)
        assert last is not None
        return last

    async def execute(
        self,
        analysis: CanonicalAnalysis,
        *,
        run_id: str,
        claim: dict,
    ) -> tuple[ProviderResult, ProviderResult]:
        run = self.store.review_run(run_id)
        if run is None or run["envelope_digest"] != analysis.digest:
            raise ValueError("Review run does not match canonical analysis")
        created_at = datetime.fromisoformat(run["created_at_utc"])
        deadline_at = datetime.fromisoformat(run["deadline_at_utc"])
        now = self.clock()
        if (now - created_at).total_seconds() > self.settings.ai_queue_max_age_seconds:
            deadline_at = now

        should_dispatch = (
            self.settings.ai_enabled
            and self.settings.ai_total_cost_limit_microusd_per_day > 0
            and (
                (
                    bool(self.gpt.api_key and self.gpt.requested_model)
                    and self._rates("OPENAI") is not None
                )
                or (
                    bool(self.claude.api_key and self.claude.requested_model)
                    and self._rates("ANTHROPIC") is not None
                )
            )
        )
        if should_dispatch:
            marked = self.store.mark_review_dispatched(
                claim["job_id"],
                owner=claim["owner"],
                generation=claim["generation"],
                dispatch_id=f"run-{run_id[:16]}-{uuid.uuid4().hex}",
                now=now,
            )
            if not marked:
                raise RuntimeError("Review lease was lost before dispatch")

        gpt, claude = await asyncio.gather(
            self._run_provider(
                self.gpt,
                analysis,
                run_id=run_id,
                claim=claim,
                deadline_at=deadline_at,
            ),
            self._run_provider(
                self.claude,
                analysis,
                run_id=run_id,
                claim=claim,
                deadline_at=deadline_at,
            ),
        )
        self.store.complete_review_job(
            claim["job_id"],
            owner=claim["owner"],
            generation=claim["generation"],
            status="COMPLETED",
            now=self.clock(),
        )
        return gpt, claude
