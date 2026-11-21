"""Generate deterministic Phase 5 software-verification streams.

Every generated artifact is labelled ``SYNTHETIC_FIXTURE``. The generator invokes
the production detector only to bind fixture provider/quote records to the candidate
identities that the public workflow must independently reproduce.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from marketintel.models import BookFeatures, Candle, Instrument, TradeRecord
from marketintel.quantitative import QUANT_ENGINE_CONFIGS, detect_signal
from marketintel.research_engine import ProviderCompletion, _revision_id
from marketintel.research_models import (
    CostPolicy,
    DatasetManifest,
    EvidenceFile,
    ExperimentConfig,
    InstrumentVersion,
    ReplayObservation,
    SourceCoverage,
)

FIXTURE_NOW = datetime(2026, 11, 19, 1, 0, tzinfo=UTC)


def _instrument(asset: str) -> Instrument:
    underlying = "XAUT" if asset == "GOLD" else "BTC"
    return Instrument(
        product_id=131253 if asset == "GOLD" else 27,
        symbol="XAUTUSD" if asset == "GOLD" else "BTCUSD",
        contract_type="perpetual_futures",
        contract_value=Decimal("0.001"),
        contract_unit_currency=underlying,
        tick_size=Decimal("0.01" if asset == "GOLD" else "0.5"),
        underlying_asset=underlying,
        quoting_asset="USD",
        settling_asset="USD",
        notional_type="vanilla",
    )


def _book(now: datetime) -> BookFeatures:
    return BookFeatures(
        available=True,
        observed_at_utc=now,
        best_bid=Decimal("100"),
        best_ask=Decimal("100.1"),
        spread=Decimal("0.1"),
        bid_depth_quote=Decimal("1400"),
        ask_depth_quote=Decimal("600"),
        imbalance=Decimal("0.40"),
        absorption="NONE",
        reason="SYNTHETIC_FIXTURE_NOT_LIVE",
    )


def _trades(symbol: str, now: datetime, count: int = 5_100) -> list[TradeRecord]:
    price = Decimal("2600" if symbol == "XAUTUSD" else "70000")
    return [
        TradeRecord(
            event_id=f"{symbol}-fixture-trade-{index}",
            symbol=symbol,
            price=price,
            contracts=Decimal("1"),
            aggressor="BUY" if index % 5 else "SELL",
            event_time_utc=now - timedelta(seconds=count - index),
            received_at_utc=now - timedelta(seconds=count - index - 0.1),
        )
        for index in range(count)
    ]


def _bars(config, now: datetime) -> list[Candle]:
    symbol = "XAUTUSD" if config.asset == "GOLD" else "BTCUSD"
    base = 2600.0 if config.asset == "GOLD" else 70000.0
    half_range = 3.0 if config.asset == "GOLD" else 250.0
    minutes = {"1m": 1, "5m": 5, "15m": 15}[config.primary_resolution]
    interval = timedelta(minutes=minutes)
    core_start = now - interval * config.min_candles
    session_start = datetime.combine(
        (now - timedelta(microseconds=1)).date(), datetime.min.time(), tzinfo=UTC
    )
    start = min(core_start, session_start)
    count = int((now - start) / interval)
    rows = [
        Candle(
            symbol=symbol,
            resolution=config.primary_resolution,
            open_time=start + interval * index,
            open=base,
            high=base + half_range,
            low=base - half_range,
            close=base,
            volume_contracts=100,
            source="SYNTHETIC_FIXTURE_NOT_LIVE",
            available_at_utc=start + interval * (index + 1),
        )
        for index in range(count)
    ]
    move = 7.0 if config.asset == "GOLD" else 600.0
    if config.trigger_family == "FAST":
        rows[-1] = rows[-1].model_copy(
            update={
                "high": base + move,
                "low": base - half_range - 1,
                "close": base + half_range + 1,
                "volume_contracts": 220,
            }
        )
    elif config.trigger_family == "HOURLY":
        rows[-2] = rows[-2].model_copy(
            update={
                "high": base + move,
                "low": base,
                "close": base + half_range + 2,
                "volume_contracts": 200,
            }
        )
        rows[-1] = rows[-1].model_copy(
            update={
                "open": base + half_range + 2,
                "high": base + move + half_range,
                "low": base + half_range - 0.02,
                "close": base + move + 1,
                "volume_contracts": 210,
            }
        )
    else:
        pivot_index = len(rows) - 8
        rows[pivot_index] = rows[pivot_index].model_copy(
            update={"high": base + half_range + 2, "low": base - half_range, "close": base + 1}
        )
        for index in range(len(rows) - 5, len(rows) - 1):
            rows[index] = rows[index].model_copy(
                update={
                    "open": base + 2,
                    "high": base + half_range + 1,
                    "low": base,
                    "close": base + 2,
                }
            )
        rows[-1] = rows[-1].model_copy(
            update={
                "open": base + 2,
                "high": base + move + 2,
                "low": base + 1,
                "close": base + move,
                "volume_contracts": 220,
            }
        )
    return rows


def generate_fixture(asset: str, output: Path) -> tuple[Path, Path]:
    asset = asset.upper()
    if asset not in {"GOLD", "BTC"}:
        raise ValueError("Fixture asset must be GOLD or BTC")
    output.mkdir(parents=True, exist_ok=True)
    symbol = "XAUTUSD" if asset == "GOLD" else "BTCUSD"
    instrument = _instrument(asset)
    trades = _trades(symbol, FIXTURE_NOW)
    book = _book(FIXTURE_NOW)
    configs = [row for row in QUANT_ENGINE_CONFIGS if row.asset == asset]
    bars_by_engine = {row.engine: _bars(row, FIXTURE_NOW) for row in configs}
    candidates = {}
    for engine_config in configs:
        result = detect_signal(
            engine_config,
            candles=bars_by_engine[engine_config.engine],
            trades=trades,
            instrument=instrument,
            now=FIXTURE_NOW,
            book_override=book,
            reference_available=False,
        )
        if result.candidate is None:
            raise ValueError(f"Synthetic fixture failed {engine_config.engine}: {result.reason}")
        candidates[engine_config.engine] = result.candidate

    dataset_id = f"phase5-{asset.lower()}-synthetic-v1"
    experiment_id = f"phase5-{asset.lower()}-workflow-v1"
    config = ExperimentConfig(
        experiment_id=experiment_id,
        dataset_id=dataset_id,
        created_at_utc=FIXTURE_NOW - timedelta(days=1),
        evaluation_start_utc=FIXTURE_NOW,
        evaluation_end_utc=FIXTURE_NOW + timedelta(minutes=240),
        evaluation_cadence_seconds=60,
        code_commit="PHASE5_WORKTREE",
        cost_policy=CostPolicy(
            policy_id="phase5-synthetic-cost-v1",
            quantity_contracts=Decimal("1"),
            fee_bps_per_side=Decimal("1"),
            slippage_bps_per_side=Decimal("1"),
            funding_bps=Decimal("0"),
            maximum_quote_gap_seconds=60,
        ),
    )
    observations: list[ReplayObservation] = []
    sequence = 0
    for trade in trades:
        sequence += 1
        observations.append(
            ReplayObservation(
                observation_id=trade.event_id,
                kind="TRADE",
                symbol=symbol,
                venue="delta_india",
                exchange_time_utc=trade.event_time_utc,
                available_at_utc=trade.received_at_utc,
                persistence_sequence=sequence,
                payload=trade.model_dump(mode="json"),
            )
        )
    for engine_config in configs:
        for index, candle in enumerate(bars_by_engine[engine_config.engine]):
            sequence += 1
            observations.append(
                ReplayObservation(
                    observation_id=f"{engine_config.engine}-candle-{index:04d}",
                    kind="CANDLE_OBSERVATION",
                    symbol=symbol,
                    venue="delta_india",
                    exchange_time_utc=candle.open_time,
                    available_at_utc=candle.available_at_utc,
                    persistence_sequence=sequence,
                    payload=candle.model_dump(mode="json"),
                )
            )
    sequence += 1
    observations.append(
        ReplayObservation(
            observation_id=f"{asset.lower()}-book-snapshot",
            kind="BOOK_SNAPSHOT",
            symbol=symbol,
            venue="delta_india",
            exchange_time_utc=FIXTURE_NOW,
            available_at_utc=FIXTURE_NOW,
            persistence_sequence=sequence,
            payload={
                "sequence": 1,
                "generation": 1,
                "snapshot": True,
                "features": book.model_dump(mode="json"),
            },
        )
    )
    for engine_config in configs:
        candidate = candidates[engine_config.engine]
        revision_id = _revision_id(
            candidate.candidate_id, candidate.snapshot_id, candidate.rule_version
        )
        for provider, seconds in (("GPT", 2), ("CLAUDE", 3)):
            sequence += 1
            completion = ProviderCompletion(
                provider=provider,
                candidate_id=candidate.candidate_id,
                revision_id=revision_id,
                decision="CONFIRM",
                supported_target_indices=(1,),
                completed_at_utc=FIXTURE_NOW + timedelta(seconds=seconds),
                request_digest=hashlib.sha256(
                    f"{candidate.candidate_id}|{provider}|fixture".encode()
                ).hexdigest(),
                configuration_digest=config.canonical_config_hash(),
                provider_latency_ms=seconds * 100,
                attributable_cost_microusd=0,
                evidence_mode="SYNTHETIC_FIXTURE",
            )
            observations.append(
                ReplayObservation(
                    observation_id=f"{candidate.candidate_id}-{provider.lower()}-fixture",
                    kind="PROVIDER_COMPLETION",
                    symbol=symbol,
                    venue="delta_india",
                    exchange_time_utc=completion.completed_at_utc,
                    available_at_utc=completion.completed_at_utc,
                    persistence_sequence=sequence,
                    payload=completion.model_dump(mode="json"),
                )
            )
        entry = Decimal(str(candidate.entry))
        target = Decimal(str(candidate.targets[0]))
        tick = instrument.tick_size
        for label, seconds, bid, ask in (
            ("entry", 4, entry - tick, entry),
            ("target", 20, target + tick, target + tick * 2),
        ):
            sequence += 1
            observations.append(
                ReplayObservation(
                    observation_id=f"{candidate.candidate_id}-{label}-quote",
                    kind="EXECUTABLE_QUOTE",
                    symbol=symbol,
                    venue="delta_india",
                    exchange_time_utc=FIXTURE_NOW + timedelta(seconds=seconds),
                    available_at_utc=FIXTURE_NOW + timedelta(seconds=seconds),
                    persistence_sequence=sequence,
                    payload={
                        "opportunity_id": candidate.candidate_id,
                        "bid": str(bid),
                        "ask": str(ask),
                    },
                )
            )
    observations.sort(
        key=lambda row: (row.available_at_utc, row.persistence_sequence, row.observation_id)
    )
    source = output / f"{asset.lower()}-observations.jsonl"
    source.write_text(
        "".join(row.model_dump_json() + "\n" for row in observations), encoding="utf-8"
    )
    evidence = EvidenceFile(
        path=source.name,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        record_count=len(observations),
    )
    version = InstrumentVersion(
        venue="delta_india",
        symbol=symbol,
        product_id=instrument.product_id,
        valid_from_utc=FIXTURE_NOW - timedelta(days=7),
        contract_multiplier=instrument.contract_value,
        tick_size=instrument.tick_size,
        quote_currency="USD",
        base_currency=instrument.underlying_asset,
        settlement_currency="USD",
    )
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        content_hash="0" * 64,
        code_commit="PHASE5_WORKTREE",
        rule_version="m3a-v2",
        feature_version="phase5-feature-state-v1",
        created_at_utc=FIXTURE_NOW - timedelta(days=1),
        data_mode="SYNTHETIC_FIXTURE",
        provenance="Deterministic Phase 5 software-verification stream; not live market data.",
        license_notes="Repository-generated synthetic fixture only.",
        files=(evidence,),
        instruments=(version,),
        coverage=(
            SourceCoverage(
                source="phase5_synthetic_stream",
                symbol=symbol,
                start_utc=min(row.available_at_utc for row in observations),
                end_utc=max(row.available_at_utc for row in observations) + timedelta(seconds=1),
                record_count=len(observations),
                exclusions=("Synthetic fixture; no empirical market coverage",),
            ),
        ),
    )
    manifest = manifest.model_copy(update={"content_hash": manifest.canonical_content_hash()})
    manifest_path = output / f"{asset.lower()}-manifest.json"
    config_path = output / f"{asset.lower()}-experiment.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path, config_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m marketintel.research_fixtures")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    for asset in ("GOLD", "BTC"):
        generate_fixture(asset, output)
    print(f"Generated explicitly synthetic Gold/BTC fixtures in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
