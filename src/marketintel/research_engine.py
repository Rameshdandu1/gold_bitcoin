"""Shared availability-clock engine path for historical and live-style research.

The service consumes only validated, normalized observations and invokes the same
``detect_signal`` implementation as the production worker. It has no provider,
notification, account, or order transport.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from marketintel.models import BookFeatures, Candle, Instrument, TradeRecord
from marketintel.quantitative import QUANT_ENGINE_CONFIGS, detect_signal
from marketintel.research_evaluation import evaluate_quotes
from marketintel.research_models import (
    RESEARCH_ARMS,
    ArmDecision,
    ArmRecord,
    DatasetManifest,
    ExperimentConfig,
    InstrumentVersion,
    OpportunityRecord,
    ReplayObservation,
    ResearchCandidate,
)
from marketintel.research_storage import ResearchStore

MAX_TRADES_PER_SYMBOL = 5_000
MAX_CANDLES_PER_SERIES = 2_000


class ProviderCompletion(BaseModel):
    """Archived or fixture analyst result; it never triggers a provider request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["GPT", "CLAUDE"]
    candidate_id: str
    revision_id: str
    decision: Literal["CONFIRM", "REJECT", "WAIT"]
    supported_target_indices: tuple[int, ...] = ()
    completed_at_utc: datetime
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_latency_ms: int = Field(ge=0)
    attributable_cost_microusd: int = Field(ge=0)
    evidence_mode: Literal[
        "RECORDED_PROSPECTIVE_MODEL", "RETROSPECTIVE_LLM_EXPLORATORY", "SYNTHETIC_FIXTURE"
    ]

    @model_validator(mode="after")
    def completion_is_aware(self) -> ProviderCompletion:
        if self.completed_at_utc.tzinfo is None or self.completed_at_utc.utcoffset() is None:
            raise ValueError("Provider completion time must be timezone aware")
        if len(set(self.supported_target_indices)) != len(self.supported_target_indices):
            raise ValueError("Provider target identities must be unique")
        if any(index < 1 for index in self.supported_target_indices):
            raise ValueError("Provider target identities are one-based")
        return self


class BookObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=0)
    generation: int = Field(ge=1)
    snapshot: bool
    features: BookFeatures


def _instrument_from_version(version: InstrumentVersion) -> Instrument:
    underlying = version.base_currency.upper()
    return Instrument(
        product_id=version.product_id,
        symbol=version.symbol,
        contract_type="perpetual_futures",
        contract_value=version.contract_multiplier,
        contract_unit_currency=underlying,
        tick_size=version.tick_size,
        underlying_asset=underlying,
        quoting_asset=version.quote_currency,
        settling_asset=version.settlement_currency,
        notional_type="vanilla",
    )


def _revision_id(candidate_id: str, snapshot_id: str, rule_version: str) -> str:
    value = f"{candidate_id}|{snapshot_id}|{rule_version}".encode()
    return hashlib.sha256(value).hexdigest()[:32]


def _to_research_candidate(candidate, instrument: Instrument) -> ResearchCandidate:
    revision_id = _revision_id(
        candidate.candidate_id, candidate.snapshot_id, candidate.rule_version
    )
    return ResearchCandidate(
        opportunity_id=candidate.candidate_id,
        revision_id=revision_id,
        venue=candidate.venue,
        symbol=candidate.symbol,
        product_id=instrument.product_id,
        asset=candidate.asset,
        engine=candidate.engine,
        direction=candidate.direction,
        observed_at_utc=candidate.observed_at_utc,
        expires_at_utc=candidate.expires_at_utc,
        entry=Decimal(str(candidate.entry)),
        invalidation=Decimal(str(candidate.invalidation)),
        targets=tuple(Decimal(str(value)) for value in candidate.targets),
    )


class SharedResearchEngine:
    """Bounded normalized evidence state used by replay and live-style tests."""

    def __init__(self, manifest: DatasetManifest) -> None:
        self.instruments = {
            row.symbol: _instrument_from_version(row) for row in manifest.instruments
        }
        self.instrument_versions = {row.symbol: row for row in manifest.instruments}
        self.trades: dict[str, deque[TradeRecord]] = defaultdict(
            lambda: deque(maxlen=MAX_TRADES_PER_SYMBOL)
        )
        self.candles: dict[tuple[str, str], deque[Candle]] = defaultdict(
            lambda: deque(maxlen=MAX_CANDLES_PER_SERIES)
        )
        self.books: dict[str, BookFeatures] = {}
        self.book_sequences: dict[str, tuple[int, int]] = {}
        self.provider_completions: dict[tuple[str, str, str], ProviderCompletion] = {}
        self.dirty_symbols: set[str] = set()
        self.maximum_trade_state = 0
        self.maximum_candle_state = 0

    def apply(self, row: ReplayObservation) -> None:
        """Validate a normalized observation before it can affect engine state."""
        payload = dict(row.payload)
        if row.kind == "TRADE":
            payload.setdefault("event_id", row.observation_id)
            payload.setdefault("symbol", row.symbol)
            payload.setdefault("event_time_utc", row.exchange_time_utc)
            payload.setdefault("received_at_utc", row.available_at_utc)
            trade = TradeRecord.model_validate(payload)
            if trade.symbol != row.symbol or trade.received_at_utc > row.available_at_utc:
                raise ValueError("Trade envelope identity/availability mismatch")
            self.trades[row.symbol].append(trade)
            self.maximum_trade_state = max(self.maximum_trade_state, len(self.trades[row.symbol]))
            self.dirty_symbols.add(row.symbol)
            return
        if row.kind == "CANDLE_OBSERVATION":
            payload.setdefault("symbol", row.symbol)
            payload.setdefault("open_time", row.exchange_time_utc)
            payload.setdefault("available_at_utc", row.available_at_utc)
            candle = Candle.model_validate(payload)
            if candle.symbol != row.symbol or candle.available_at_utc != row.available_at_utc:
                raise ValueError("Candle envelope identity/availability mismatch")
            key = (row.symbol, candle.resolution)
            existing = {item.open_time: item for item in self.candles[key]}
            prior = existing.get(candle.open_time)
            if prior is not None and prior != candle:
                raise ValueError("Conflicting candle revision requires a new dataset identity")
            if prior is None:
                self.candles[key].append(candle)
            self.maximum_candle_state = max(self.maximum_candle_state, len(self.candles[key]))
            self.dirty_symbols.add(row.symbol)
            return
        if row.kind in {"BOOK_SNAPSHOT", "BOOK_DELTA"}:
            update = BookObservation.model_validate(payload)
            if update.features.observed_at_utc != row.exchange_time_utc:
                raise ValueError("Book feature time does not match its envelope")
            prior = self.book_sequences.get(row.symbol)
            if update.snapshot:
                self.book_sequences[row.symbol] = (update.generation, update.sequence)
                self.books[row.symbol] = update.features
            elif prior != (update.generation, update.sequence - 1):
                self.books[row.symbol] = BookFeatures(
                    available=False,
                    observed_at_utc=row.exchange_time_utc,
                    reason="BOOK_SEQUENCE_GAP_REQUIRES_SNAPSHOT",
                )
                self.book_sequences.pop(row.symbol, None)
            else:
                self.book_sequences[row.symbol] = (update.generation, update.sequence)
                self.books[row.symbol] = update.features
            self.dirty_symbols.add(row.symbol)
            return
        if row.kind == "INSTRUMENT_VERSION":
            instrument = Instrument.model_validate(payload)
            if instrument.symbol != row.symbol:
                raise ValueError("Instrument envelope symbol mismatch")
            self.instruments[row.symbol] = instrument
            self.dirty_symbols.add(row.symbol)
            return
        if row.kind == "PROVIDER_COMPLETION":
            completion = ProviderCompletion.model_validate(payload)
            if completion.completed_at_utc > row.available_at_utc:
                raise ValueError("Provider completion cannot be available before completion")
            key = (completion.candidate_id, completion.revision_id, completion.provider)
            prior = self.provider_completions.get(key)
            if prior is not None and prior != completion:
                raise ValueError("Conflicting provider completion identity")
            self.provider_completions[key] = completion
            return
        if row.kind == "EXECUTABLE_QUOTE":
            # The journal-backed outcome evaluator validates the full quote contract.
            return
        if row.kind in {"SOURCE_TRANSITION", "EXPIRY"}:
            return
        if row.kind == "CANDIDATE":
            raise ValueError("Normal workflow derives candidates; archive import is separate")
        raise ValueError(f"Unsupported replay observation kind: {row.kind}")

    def evaluate(self, at: datetime) -> list[tuple[object, Instrument]]:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Evaluation clock must be timezone aware")
        rows: list[tuple[object, Instrument]] = []
        for config in QUANT_ENGINE_CONFIGS:
            symbol = "XAUTUSD" if config.asset == "GOLD" else "BTCUSD"
            instrument = self.instruments.get(symbol)
            if instrument is None:
                continue
            result = detect_signal(
                config,
                candles=tuple(self.candles[(symbol, config.primary_resolution)]),
                trades=tuple(self.trades[symbol]),
                instrument=instrument,
                now=at,
                book_override=self.books.get(symbol),
                reference_available=False,
            )
            rows.append((result, instrument))
        self.dirty_symbols.clear()
        return rows

    def memory_evidence(self) -> dict:
        return {
            "maximum_trades_per_symbol": self.maximum_trade_state,
            "trade_limit_per_symbol": MAX_TRADES_PER_SYMBOL,
            "maximum_candles_per_series": self.maximum_candle_state,
            "candle_limit_per_series": MAX_CANDLES_PER_SERIES,
        }


def _provider_decision(
    candidate: ResearchCandidate,
    config: ExperimentConfig,
    completion: ProviderCompletion | None,
    arm: Literal["RULES_PLUS_GPT", "RULES_PLUS_CLAUDE"],
) -> ArmDecision:
    if completion is None or completion.completed_at_utc > candidate.expires_at_utc:
        return ArmDecision(
            arm=arm,
            state="UNAVAILABLE",
            ready_at_utc=candidate.expires_at_utc,
            reason="No matching contemporary archived assessment",
        )
    if completion.decision == "CONFIRM" and config.target_index not in (
        completion.supported_target_indices
    ):
        state = "REJECTED"
        reason = "Provider did not approve the frozen target identity"
    elif completion.decision == "CONFIRM":
        state = "APPROVED"
        reason = "Matching archived assessment approved frozen target"
    else:
        state = "REJECTED" if completion.decision == "REJECT" else "WAIT"
        reason = f"Matching archived assessment returned {completion.decision}"
    return ArmDecision(
        arm=arm,
        state=state,
        ready_at_utc=completion.completed_at_utc,
        reason=reason,
        provider_latency_ms=completion.provider_latency_ms,
        attributable_cost_microusd=completion.attributable_cost_microusd,
    )


def _decisions(
    candidate: ResearchCandidate,
    config: ExperimentConfig,
    completions: dict[tuple[str, str, str], ProviderCompletion],
) -> tuple[ArmDecision, ...]:
    rules = ArmDecision(
        arm="RULES_ONLY",
        state="APPROVED",
        ready_at_utc=candidate.observed_at_utc,
        reason="Production quantitative engine emitted CANDIDATE",
    )
    gpt = _provider_decision(
        candidate,
        config,
        completions.get((candidate.opportunity_id, candidate.revision_id, "GPT")),
        "RULES_PLUS_GPT",
    )
    claude = _provider_decision(
        candidate,
        config,
        completions.get((candidate.opportunity_id, candidate.revision_id, "CLAUDE")),
        "RULES_PLUS_CLAUDE",
    )
    ready = max(gpt.ready_at_utc, claude.ready_at_utc)
    if "UNAVAILABLE" in {gpt.state, claude.state}:
        state = "UNAVAILABLE"
        reason = "Both matching contemporary provider assessments were not available"
    elif "REJECTED" in {gpt.state, claude.state}:
        state = "REJECTED"
        reason = "At least one independent provider rejected the frozen target"
    elif "WAIT" in {gpt.state, claude.state}:
        state = "WAIT"
        reason = "At least one independent provider returned WAIT"
    else:
        state = "APPROVED"
        reason = "Both independent archived assessments approved the frozen target"
    dual = ArmDecision(
        arm="RULES_PLUS_DUAL",
        state=state,
        ready_at_utc=ready,
        reason=reason,
        provider_latency_ms=max(gpt.provider_latency_ms, claude.provider_latency_ms),
        attributable_cost_microusd=(
            gpt.attributable_cost_microusd + claude.attributable_cost_microusd
        ),
    )
    return rules, gpt, claude, dual


def _arm_state(decision: ArmDecision, code: str) -> str:
    if decision.state != "APPROVED":
        return decision.state
    if code == "NO_ENTRY":
        return "NO_ENTRY"
    if code in {"TARGET_BEFORE_STOP", "STOP_BEFORE_TARGET", "TIME_EXIT"}:
        return "EXECUTABLE"
    return "APPROVED"


def run_shared_workflow(
    manifest: DatasetManifest,
    config: ExperimentConfig,
    observations: Iterable[ReplayObservation],
    store: ResearchStore,
    *,
    presorted: bool = False,
) -> dict:
    """Run engines first, then evaluate outcomes from the immutable journal."""
    store.create_experiment(manifest, config)
    state = SharedResearchEngine(manifest)
    ordered: Iterable[ReplayObservation]
    if presorted:
        ordered = observations
    else:
        ordered = sorted(
            observations,
            key=lambda row: (
                row.available_at_utc,
                row.persistence_sequence,
                row.observation_id,
            ),
        )
    next_evaluation = config.evaluation_start_utc
    cadence = timedelta(seconds=config.evaluation_cadence_seconds)
    journal_batch: list[ReplayObservation] = []
    seen = {(row.opportunity_id, row.revision_id) for row in store.candidates(config.experiment_id)}
    generated = 0
    evaluations = 0
    observations_count = 0

    def evaluate(at: datetime) -> None:
        nonlocal generated, evaluations
        for result, instrument in state.evaluate(at):
            store.save_engine_evaluation(
                config.experiment_id,
                engine=result.engine,
                evaluated_at=at,
                result=result.model_dump(mode="json"),
            )
            evaluations += 1
            if result.candidate is None:
                continue
            candidate = _to_research_candidate(result.candidate, instrument)
            identity = (candidate.opportunity_id, candidate.revision_id)
            if identity in seen:
                continue
            store.save_candidate(
                config.experiment_id,
                candidate,
                persisted_at=at,
            )
            rules = _decisions(candidate, config, {})[0]
            store.save_arm_decision(
                config.experiment_id,
                candidate.opportunity_id,
                candidate.revision_id,
                rules,
                persisted_at=at,
            )
            seen.add(identity)
            generated += 1

    for row in ordered:
        observations_count += 1
        if row.available_at_utc < config.evaluation_start_utc:
            state.apply(row)
            journal_batch.append(row)
            continue
        while next_evaluation < row.available_at_utc and (
            next_evaluation <= config.evaluation_end_utc
        ):
            if state.dirty_symbols:
                evaluate(next_evaluation)
            next_evaluation += cadence
        state.apply(row)
        journal_batch.append(row)
        if len(journal_batch) >= 500:
            store.save_observations(config.experiment_id, journal_batch)
            journal_batch.clear()
    if journal_batch:
        store.save_observations(config.experiment_id, journal_batch)
    while next_evaluation <= config.evaluation_end_utc:
        if state.dirty_symbols:
            evaluate(next_evaluation)
        next_evaluation += cadence

    records: list[OpportunityRecord] = []
    for candidate in store.candidates(config.experiment_id):
        decisions = _decisions(candidate, config, state.provider_completions)
        for decision in decisions:
            store.save_arm_decision(
                config.experiment_id,
                candidate.opportunity_id,
                candidate.revision_id,
                decision,
                persisted_at=max(candidate.observed_at_utc, decision.ready_at_utc),
            )
        version = state.instrument_versions[candidate.symbol]
        quotes = store.quotes(
            config.experiment_id,
            candidate.symbol,
            opportunity_id=candidate.opportunity_id,
        )
        arm_rows = []
        label_end = candidate.observed_at_utc
        for decision in decisions:
            outcome = evaluate_quotes(
                candidate,
                decision,
                version,
                quotes,
                config.cost_policy,
                target_index=config.target_index,
                entry_latency_ms=config.entry_latency_ms,
            )
            store.save_outcome(
                config.experiment_id,
                candidate.revision_id,
                outcome,
                persisted_at=config.evaluation_end_utc,
            )
            label_end = max(
                label_end,
                outcome.exit_at_utc or candidate.expires_at_utc,
                decision.ready_at_utc,
            )
            arm_rows.append(
                ArmRecord(
                    arm=decision.arm,
                    state=_arm_state(decision, outcome.code),
                    decision_ready_at_utc=decision.ready_at_utc,
                    provider_latency_ms=decision.provider_latency_ms,
                    attributable_cost_microusd=decision.attributable_cost_microusd,
                    reason=decision.reason,
                    outcome=outcome,
                )
            )
        record = OpportunityRecord(
            opportunity_id=candidate.opportunity_id,
            revision_id=candidate.revision_id,
            asset=candidate.asset,
            engine=candidate.engine,
            direction=candidate.direction,
            observed_at_utc=candidate.observed_at_utc,
            label_information_start_utc=candidate.observed_at_utc,
            label_information_end_utc=label_end,
            quantitatively_eligible=True,
            arms=tuple(arm_rows),
        )
        store.save_opportunity(config.experiment_id, record)
        records.append(record)
    store.record_action_counts(
        config.experiment_id,
        scope="OFFLINE_SHARED_WORKFLOW",
        external_calls=0,
        real_notifications=0,
        orders=0,
        measured_at=config.evaluation_end_utc,
    )
    return {
        "experiment_id": config.experiment_id,
        "dataset_id": manifest.dataset_id,
        "dataset_hash": manifest.content_hash,
        "config_hash": config.canonical_config_hash(),
        "observations": observations_count,
        "engine_evaluations": evaluations,
        "opportunities_generated": generated,
        "opportunities_total": len(records),
        "engine_matrix": store.engine_matrix(config.experiment_id),
        "memory": state.memory_evidence(),
        "arms": list(RESEARCH_ARMS),
        "external_calls": 0,
        "real_notifications": 0,
        "orders": 0,
        "classification": "HYPOTHETICAL_EXPLORATORY",
    }
