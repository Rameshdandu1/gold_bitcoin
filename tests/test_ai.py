import asyncio
from datetime import timedelta

import pytest

from marketintel.ai import independent_review
from marketintel.detectors import EngineConfig, create_candidate
from marketintel.models import AnalystAssessment


class StaticAnalyst:
    def __init__(self, decision):
        self.decision = decision

    async def analyze(self, candidate):
        await asyncio.sleep(0)
        return AnalystAssessment(
            snapshot_id=candidate.snapshot_id, direction=candidate.direction,
            decision=self.decision, supported_target_indices=[1],
            reason="fixture", counter_evidence=[], data_warnings=[],
        )


class FailingAnalyst:
    async def analyze(self, candidate):
        raise TimeoutError("Should not leak any credentials")


@pytest.mark.asyncio
async def test_independent_fail_closed(make_bars):
    bars = make_bars(n=35, last_close=125)
    c = create_candidate(EngineConfig("GOLD", "1m", 30), bars, now=bars[-1].open_time + timedelta(minutes=1, seconds=1))
    gpt, claude, errors = await independent_review(c, StaticAnalyst("CONFIRM"), FailingAnalyst())
    assert gpt is not None and claude is None
    assert errors == ["Claude unavailable (TimeoutError)"]
