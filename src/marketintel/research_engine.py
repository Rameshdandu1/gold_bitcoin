"""Shared availability-clock engine path for historical and live-style research.

The service consumes only validated, normalized observations and invokes the same
``detect_signal`` implementation as the production worker. It has no provider,
notification, account, or order transport.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from marketintel.application_policy import ApplicationPolicyInput, evaluate_application_policy
from marketintel.models import (
    BookFeatures,
    Candle,
    DetectionResult,
    Instrument,
    SignalState,
    TradeRecord,
)
from marketintel.quantitative import QUANT_ENGINE_CONFIGS, detect_signal
from marketintel.research_evaluation import evaluate_quotes
from marketintel.research_models import (
    RESEARCH_ARMS,
    ArmDecision,
    ArmRecord,
    DatasetManifest,
    ExecutableQuote,
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
    available_at_utc: datetime | None = None
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_latency_ms: int = Field(ge=0)
    attributable_cost_microusd: int = Field(ge=0)
    evidence_mode: Literal[
        "RECORDED_PROSPECTIVE_MODEL", "RETROSPECTIVE_LLM_EXPLORATORY", "SYNTHETIC_FIXTURE"
    ]
    requested_model_id: str | None = Field(default=None, min_length=1)
    returned_model_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def completion_is_aware(self) -> ProviderCompletion:
        if self.completed_at_utc.tzinfo is None or self.completed_at_utc.utcoffset() is None:
            raise ValueError("Provider completion time must be timezone aware")
        if self.available_at_utc is not None:
            if self.available_at_utc.tzinfo is None or self.available_at_utc.utcoffset() is None:
                raise ValueError("Provider availability time must be timezone aware")
            if self.available_at_utc < self.completed_at_utc:
                raise ValueError("Provider result cannot be available before completion")
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


class SourceTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: Literal["AVAILABLE", "UNAVAILABLE", "STALE", "GAP"]
    generation: int = Field(ge=1)
    reason: str


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


def candidate_revision_id(candidate_id: str, snapshot_id: str, rule_version: str) -> str:
    value = f"{candidate_id}|{snapshot_id}|{rule_version}".encode()
    return hashlib.sha256(value).hexdigest()[:32]


def provider_request_digest(
    candidate: ResearchCandidate, config: ExperimentConfig, provider: str
) -> str:
    preimage = {
        "candidate": candidate.model_dump(mode="json"),
        "config_hash": config.canonical_config_hash(),
        "provider": provider,
        "schema": "phase5-archived-provider-request-v1",
    }
    return hashlib.sha256(
        json.dumps(preimage, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def to_research_candidate(candidate, instrument: Instrument) -> ResearchCandidate:
    revision_id = candidate_revision_id(
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
        self.manifest = manifest
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
        self.source_states: dict[str, SourceTransition] = {}
        self.source_history: dict[str, deque[tuple[datetime, SourceTransition]]] = defaultdict(
            lambda: deque(maxlen=10_000)
        )
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
            if payload.get("available_at_utc") is None:
                payload["available_at_utc"] = row.available_at_utc
            completion = ProviderCompletion.model_validate(payload)
            if completion.available_at_utc != row.available_at_utc:
                raise ValueError("Provider payload availability conflicts with its envelope")
            if completion.completed_at_utc > row.available_at_utc:
                raise ValueError("Provider completion cannot be available before completion")
            allowed_modes = {
                "SYNTHETIC_FIXTURE": {"SYNTHETIC_FIXTURE"},
                "DOWNLOADED_OHLC": {"RETROSPECTIVE_LLM_EXPLORATORY"},
                "RECORDED_AS_OBSERVED": {
                    "RECORDED_PROSPECTIVE_MODEL",
                    "RETROSPECTIVE_LLM_EXPLORATORY",
                },
                "RECORDED_PROSPECTIVE_MODEL": {"RECORDED_PROSPECTIVE_MODEL"},
                "RETROSPECTIVE_LLM_EXPLORATORY": {"RETROSPECTIVE_LLM_EXPLORATORY"},
            }
            if completion.evidence_mode not in allowed_modes[self.manifest.data_mode]:
                raise ValueError("Provider evidence mode is incompatible with dataset mode")
            key = (completion.candidate_id, completion.revision_id, completion.provider)
            prior = self.provider_completions.get(key)
            if prior is not None and prior != completion:
                raise ValueError("Conflicting provider completion identity")
            self.provider_completions[key] = completion
            return
        if row.kind == "EXECUTABLE_QUOTE":
            payload.setdefault("event_id", row.observation_id)
            payload.setdefault("venue", row.venue)
            payload.setdefault("symbol", row.symbol)
            payload.setdefault("observed_at_utc", row.exchange_time_utc)
            payload.setdefault("available_at_utc", row.available_at_utc)
            payload.pop("opportunity_id", None)
            quote = ExecutableQuote.model_validate(payload)
            if quote.available_at_utc != row.available_at_utc:
                raise ValueError("Quote payload availability conflicts with its envelope")
            return
        if row.kind == "SOURCE_TRANSITION":
            transition = SourceTransition.model_validate(payload)
            prior = self.source_states.get(row.symbol)
            if prior is not None and transition.generation < prior.generation:
                raise ValueError("Source recovery generation moved backward")
            self.source_states[row.symbol] = transition
            self.source_history[row.symbol].append((row.available_at_utc, transition))
            self.dirty_symbols.add(row.symbol)
            return
        if row.kind == "EXPIRY":
            return
        if row.kind == "CANDIDATE":
            raise ValueError("Normal workflow derives candidates; archive import is separate")
        raise ValueError(f"Unsupported replay observation kind: {row.kind}")

    def evaluate(self, at: datetime) -> list[tuple[object, Instrument]]:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Evaluation clock must be timezone aware")
        rows: list[tuple[object, Instrument]] = []
        for config in QUANT_ENGINE_CONFIGS:
            instrument = next(
                (
                    item
                    for item in self.instruments.values()
                    if (
                        item.underlying_asset.upper() == "BTC"
                        if config.asset == "BTC"
                        else item.underlying_asset.upper() in {"XAUT", "PAXG"}
                    )
                ),
                None,
            )
            if instrument is None:
                continue
            symbol = instrument.symbol
            active_coverage = [
                item
                for item in self.manifest.coverage
                if item.symbol == symbol and item.start_utc <= at <= item.end_utc
            ]
            transition = self.source_states.get(symbol)
            coverage_reason = None
            if not active_coverage:
                coverage_reason = "NO_DECLARED_SYMBOL_COVERAGE"
            elif any(
                not item.sequence_valid
                or not item.checksum_valid
                or any(start <= at < end for start, end in item.gaps)
                for item in active_coverage
            ):
                coverage_reason = "DECLARED_SOURCE_COVERAGE_INVALID_OR_GAPPED"
            elif transition is not None and transition.state != "AVAILABLE":
                coverage_reason = f"SOURCE_{transition.state}:{transition.reason}"
            if coverage_reason is not None:
                rows.append(
                    (
                        DetectionResult(
                            engine=config.engine,
                            state=SignalState.WAIT,
                            observed_at_utc=at,
                            reason=coverage_reason,
                        ),
                        instrument,
                    )
                )
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

    def checkpoint_state(self) -> dict:
        """Return the complete bounded scientific state needed for a true resume."""
        return {
            "schema": "phase6-closeout-derived-state-v1",
            "instruments": {
                key: value.model_dump(mode="json") for key, value in self.instruments.items()
            },
            "trades": {
                key: [value.model_dump(mode="json") for value in rows]
                for key, rows in self.trades.items()
            },
            "candles": {
                f"{key[0]}\u001f{key[1]}": [
                    value.model_dump(mode="json") for value in rows
                ]
                for key, rows in self.candles.items()
            },
            "books": {
                key: value.model_dump(mode="json") for key, value in self.books.items()
            },
            "book_sequences": {
                key: list(value) for key, value in self.book_sequences.items()
            },
            "provider_completions": [
                value.model_dump(mode="json") for value in self.provider_completions.values()
            ],
            "source_states": {
                key: value.model_dump(mode="json") for key, value in self.source_states.items()
            },
            "source_history": {
                key: [
                    {
                        "available_at_utc": at.isoformat(),
                        "transition": value.model_dump(mode="json"),
                    }
                    for at, value in rows
                ]
                for key, rows in self.source_history.items()
            },
            "dirty_symbols": sorted(self.dirty_symbols),
            "maximum_trade_state": self.maximum_trade_state,
            "maximum_candle_state": self.maximum_candle_state,
        }

    @classmethod
    def from_checkpoint(cls, manifest: DatasetManifest, payload: dict) -> SharedResearchEngine:
        if payload.get("schema") != "phase6-closeout-derived-state-v1":
            raise ValueError("Unsupported derived workflow checkpoint schema")
        state = cls(manifest)
        state.instruments = {
            key: Instrument.model_validate(value)
            for key, value in payload.get("instruments", {}).items()
        }
        for key, rows in payload.get("trades", {}).items():
            state.trades[key].extend(TradeRecord.model_validate(value) for value in rows)
        for encoded, rows in payload.get("candles", {}).items():
            symbol, resolution = encoded.split("\u001f", 1)
            state.candles[(symbol, resolution)].extend(
                Candle.model_validate(value) for value in rows
            )
        state.books = {
            key: BookFeatures.model_validate(value)
            for key, value in payload.get("books", {}).items()
        }
        state.book_sequences = {
            key: (int(value[0]), int(value[1]))
            for key, value in payload.get("book_sequences", {}).items()
        }
        for raw in payload.get("provider_completions", []):
            completion = ProviderCompletion.model_validate(raw)
            key = (completion.candidate_id, completion.revision_id, completion.provider)
            state.provider_completions[key] = completion
        state.source_states = {
            key: SourceTransition.model_validate(value)
            for key, value in payload.get("source_states", {}).items()
        }
        for key, rows in payload.get("source_history", {}).items():
            state.source_history[key].extend(
                (
                    datetime.fromisoformat(value["available_at_utc"]),
                    SourceTransition.model_validate(value["transition"]),
                )
                for value in rows
            )
        state.dirty_symbols = set(payload.get("dirty_symbols", []))
        state.maximum_trade_state = int(payload.get("maximum_trade_state", 0))
        state.maximum_candle_state = int(payload.get("maximum_candle_state", 0))
        return state


def _provider_decision(
    candidate: ResearchCandidate,
    config: ExperimentConfig,
    completion: ProviderCompletion | None,
    arm: Literal["RULES_PLUS_GPT", "RULES_PLUS_CLAUDE"],
) -> ArmDecision:
    available_at = completion.available_at_utc if completion is not None else None
    if completion is None or available_at is None or available_at > candidate.expires_at_utc:
        return ArmDecision(
            arm=arm,
            state="UNAVAILABLE",
            ready_at_utc=candidate.expires_at_utc,
            reason="No matching contemporary archived assessment",
        )
    if completion.configuration_digest != config.canonical_config_hash() or (
        completion.request_digest != provider_request_digest(candidate, config, completion.provider)
    ):
        return ArmDecision(
            arm=arm,
            state="UNAVAILABLE",
            ready_at_utc=available_at,
            reason="Archived assessment request/configuration identity mismatch",
            provider_latency_ms=completion.provider_latency_ms,
            attributable_cost_microusd=completion.attributable_cost_microusd,
            evidence_mode=completion.evidence_mode,
            provider=completion.provider,
            provider_completed_at_utc=completion.completed_at_utc,
            provider_available_at_utc=available_at,
            request_digest=completion.request_digest,
            configuration_digest=completion.configuration_digest,
            requested_model_id=completion.requested_model_id,
            returned_model_id=completion.returned_model_id,
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
        ready_at_utc=available_at,
        reason=reason,
        provider_latency_ms=completion.provider_latency_ms,
        attributable_cost_microusd=completion.attributable_cost_microusd,
        evidence_mode=completion.evidence_mode,
        provider=completion.provider,
        provider_completed_at_utc=completion.completed_at_utc,
        provider_available_at_utc=available_at,
        request_digest=completion.request_digest,
        configuration_digest=completion.configuration_digest,
        requested_model_id=completion.requested_model_id,
        returned_model_id=completion.returned_model_id,
    )


def _decisions(
    candidate: ResearchCandidate,
    config: ExperimentConfig,
    completions: dict[tuple[str, str, str], ProviderCompletion],
    market_data_mode=None,
    source_history: tuple[tuple[datetime, SourceTransition], ...] = (),
    book: BookFeatures | None = None,
) -> tuple[ArmDecision, ...]:
    rules = ArmDecision(
        arm="RULES_ONLY",
        state="APPROVED",
        ready_at_utc=candidate.observed_at_utc,
        reason="Production quantitative engine emitted CANDIDATE",
        evidence_mode=market_data_mode,
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

    def apply_source_gate(decision: ArmDecision) -> ArmDecision:
        visible = [row for row in source_history if row[0] <= decision.ready_at_utc]
        if decision.state != "APPROVED":
            return decision
        sources_current = not visible or visible[-1][1].state == "AVAILABLE"
        bid = book.best_bid if book is not None and book.available else None
        ask = book.best_ask if book is not None and book.available else None
        stop_breached = bool(
            bid is not None
            and ask is not None
            and (
                bid <= candidate.invalidation
                if candidate.direction == "BULLISH"
                else ask >= candidate.invalidation
            )
        )
        verdict = evaluate_application_policy(
            ApplicationPolicyInput(
                revision_current=True,
                lifecycle_state="CANDIDATE",
                observed_at_utc=candidate.observed_at_utc,
                expires_at_utc=candidate.expires_at_utc,
                evaluated_at_utc=decision.ready_at_utc,
                market_observed_at_utc=(
                    book.observed_at_utc
                    if book is not None and book.observed_at_utc is not None
                    else candidate.observed_at_utc
                ),
                sources_current=sources_current and book is not None and book.available,
                event_order_ambiguous=False,
                stop_breached=stop_breached,
                direction=candidate.direction,
                entry=candidate.entry,
                invalidation=candidate.invalidation,
                best_bid=bid,
                best_ask=ask,
                maximum_spread_bps=config.maximum_spread_bps,
                maximum_entry_drift_bps=config.maximum_entry_drift_bps,
            )
        )
        target = candidate.targets[config.target_index - 1]
        target_exhausted = bool(
            bid is not None
            and ask is not None
            and (bid >= target if candidate.direction == "BULLISH" else ask <= target)
        )
        if verdict.eligible and not target_exhausted:
            return decision
        return decision.model_copy(
            update={
                "state": "WAIT",
                "reason": (
                    "Shared application policy blocked provider-ready entry: "
                    + (
                        "TARGET_EXHAUSTED"
                        if target_exhausted
                        else ",".join(verdict.failed_codes)
                    )
                ),
            }
        )

    gpt = apply_source_gate(gpt)
    claude = apply_source_gate(claude)
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
        evidence_mode=(gpt.evidence_mode if gpt.evidence_mode == claude.evidence_mode else None),
        provider="DUAL",
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
    maximum_observations: int | None = None,
) -> dict:
    """Run engines first, then evaluate outcomes from the immutable journal."""
    if maximum_observations is not None and maximum_observations < 1:
        raise ValueError("Maximum workflow observations must be positive")
    store.create_experiment(manifest, config)
    checkpoint = store.workflow_checkpoint(config.experiment_id)
    config_hash = config.canonical_config_hash()
    if checkpoint is not None and (
        checkpoint["manifest_hash"] != manifest.content_hash
        or checkpoint["config_hash"] != config_hash
    ):
        raise ValueError("Derived workflow checkpoint source/configuration changed")
    state = (
        SharedResearchEngine.from_checkpoint(manifest, checkpoint["state"])
        if checkpoint is not None
        else SharedResearchEngine(manifest)
    )
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
    next_evaluation = (
        datetime.fromisoformat(checkpoint["next_evaluation_utc"])
        if checkpoint is not None
        else config.evaluation_start_utc
    )
    cadence = timedelta(seconds=config.evaluation_cadence_seconds)
    journal_batch: list[ReplayObservation] = []
    seen = {(row.opportunity_id, row.revision_id) for row in store.candidates(config.experiment_id)}
    generated = int(checkpoint["generated_candidates"]) if checkpoint is not None else 0
    evaluations = int(checkpoint["engine_evaluations"]) if checkpoint is not None else 0
    start_offset = int(checkpoint["input_offset"]) if checkpoint is not None else 0
    observations_count = start_offset
    processed_this_run = 0
    expected_observations = sum(row.record_count for row in manifest.files)

    def save_checkpoint(status: str) -> None:
        store.save_workflow_checkpoint(
            config.experiment_id,
            manifest_hash=manifest.content_hash,
            config_hash=config_hash,
            input_offset=observations_count,
            next_evaluation_utc=next_evaluation,
            state=state.checkpoint_state(),
            generated_candidates=generated,
            engine_evaluations=evaluations,
            status=status,
            updated_at_utc=(
                config.evaluation_start_utc
                if observations_count == 0
                else max(
                    (row.available_at_utc for row in journal_batch),
                    default=config.evaluation_start_utc,
                )
            ),
        )

    def persist_available_provider_decisions(at: datetime) -> None:
        for candidate in store.candidates(config.experiment_id):
            rows = _decisions(
                candidate,
                config,
                state.provider_completions,
                manifest.data_mode,
                tuple(state.source_history[candidate.symbol]),
                state.books.get(candidate.symbol),
            )
            keys = {
                "RULES_PLUS_GPT": (candidate.opportunity_id, candidate.revision_id, "GPT"),
                "RULES_PLUS_CLAUDE": (
                    candidate.opportunity_id,
                    candidate.revision_id,
                    "CLAUDE",
                ),
            }
            for decision in rows[1:]:
                required = (
                    tuple(keys.values())
                    if decision.arm == "RULES_PLUS_DUAL"
                    else (keys[decision.arm],)
                )
                if not all(key in state.provider_completions for key in required):
                    continue
                if decision.ready_at_utc > at:
                    continue
                store.save_arm_decision(
                    config.experiment_id,
                    candidate.opportunity_id,
                    candidate.revision_id,
                    decision,
                    persisted_at=at,
                )

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
            candidate = to_research_candidate(result.candidate, instrument)
            identity = (candidate.opportunity_id, candidate.revision_id)
            if identity in seen:
                continue
            store.save_candidate(
                config.experiment_id,
                candidate,
                persisted_at=at,
            )
            rules = _decisions(
                candidate,
                config,
                {},
                manifest.data_mode,
                book=state.books.get(candidate.symbol),
            )[0]
            store.save_arm_decision(
                config.experiment_id,
                candidate.opportunity_id,
                candidate.revision_id,
                rules,
                persisted_at=at,
            )
            seen.add(identity)
            generated += 1

    for input_index, row in enumerate(ordered, start=1):
        if input_index <= start_offset:
            continue
        if maximum_observations is not None and processed_this_run >= maximum_observations:
            break
        observations_count += 1
        processed_this_run += 1
        if row.available_at_utc < config.evaluation_start_utc:
            state.apply(row)
        else:
            while next_evaluation < row.available_at_utc and (
                next_evaluation <= config.evaluation_end_utc
            ):
                evaluate(next_evaluation)
                next_evaluation += cadence
            state.apply(row)
            if row.kind in {"PROVIDER_COMPLETION", "SOURCE_TRANSITION"}:
                persist_available_provider_decisions(row.available_at_utc)
        journal_batch.append(row)
        if len(journal_batch) >= 500:
            store.save_observations(config.experiment_id, journal_batch)
            save_checkpoint("RUNNING")
            journal_batch.clear()
    if journal_batch:
        store.save_observations(config.experiment_id, journal_batch)
    input_complete = (
        observations_count >= expected_observations
        if expected_observations
        else maximum_observations is None
    )
    if not input_complete:
        save_checkpoint("BOUNDED_PARTIAL")
        return {
            "experiment_id": config.experiment_id,
            "dataset_id": manifest.dataset_id,
            "dataset_hash": manifest.content_hash,
            "config_hash": config_hash,
            "classification": "HYPOTHETICAL_EXPLORATORY",
            "status": "DERIVED_WORKFLOW_PARTIAL",
            "observations": observations_count,
            "observations_total": expected_observations,
            "observations_remaining": max(expected_observations - observations_count, 0),
            "opportunities_generated": generated,
            "engine_evaluations": evaluations,
            "memory": state.memory_evidence(),
            "external_calls": 0,
            "real_notifications": 0,
            "orders": 0,
        }
    save_checkpoint("INPUT_COMPLETE")
    while next_evaluation <= config.evaluation_end_utc:
        evaluate(next_evaluation)
        next_evaluation += cadence

    records: list[OpportunityRecord] = []
    for candidate in store.candidates(config.experiment_id):
        decisions = _decisions(
            candidate,
            config,
            state.provider_completions,
            manifest.data_mode,
            tuple(state.source_history[candidate.symbol]),
            state.books.get(candidate.symbol),
        )
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
                source_transitions=tuple(state.source_history[candidate.symbol]),
            )
            outcome = outcome.model_copy(update={"market_data_mode": manifest.data_mode})
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
                    evidence_mode=decision.evidence_mode,
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
            market_data_mode=manifest.data_mode,
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
    save_checkpoint("COMPLETE")
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
        "status": "DERIVED_WORKFLOW_COMPLETE",
    }
