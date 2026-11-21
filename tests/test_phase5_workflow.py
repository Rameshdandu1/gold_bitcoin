from __future__ import annotations

import json
from decimal import Decimal

from fastapi.testclient import TestClient

from marketintel.api import create_app
from marketintel.config import Settings
from marketintel.research import main as research_main
from marketintel.research_fixtures import FIXTURE_NOW, generate_fixture
from marketintel.research_storage import ResearchStore
from marketintel.storage import Store


def test_public_gold_and_btc_workflows_use_all_six_real_engines_and_restart(tmp_path) -> None:
    observed_engines = set()
    for asset in ("GOLD", "BTC"):
        manifest_path, config_path = generate_fixture(asset, tmp_path / asset.lower())
        database = tmp_path / f"{asset.lower()}.sqlite3"
        production = tmp_path / "production.sqlite3"
        experiment_id = f"phase5-{asset.lower()}-workflow-v1"
        command = [
            "run-workflow",
            "--manifest",
            str(manifest_path),
            "--config",
            str(config_path),
            "--database",
            str(database),
            "--production-database",
            str(production),
            "--chunk-size",
            "73",
        ]

        assert research_main(command) == 0
        # A complete restart replays immutable inputs and must be conflict-free/idempotent.
        assert research_main(command) == 0
        assert (
            research_main(
                [
                    "evaluate",
                    "--database",
                    str(database),
                    "--production-database",
                    str(production),
                    "--experiment-id",
                    experiment_id,
                ]
            )
            == 0
        )

        store = ResearchStore(database, production_path=production)
        matrix = store.engine_matrix(experiment_id)
        observed_engines.update(row["engine"] for row in matrix)
        assert len(matrix) == 3
        assert all(row["candidates"] == 1 for row in matrix)
        opportunities = store.opportunities(experiment_id)
        assert len(opportunities) == 3
        assert {row.engine for row in opportunities} == {
            f"{asset}_FAST",
            f"{asset}_HOURLY",
            f"{asset}_SESSION",
        }
        for row in opportunities:
            assert row.observed_at_utc == FIXTURE_NOW
            assert len(row.arms) == 4
            for arm in row.arms:
                assert arm.state == "EXECUTABLE"
                assert arm.outcome is not None
                outcome = arm.outcome
                assert outcome.code == "TARGET_BEFORE_STOP"
                assert outcome.entry_at_utc is not None
                assert outcome.exit_at_utc is not None
                assert outcome.entry_at_utc < outcome.exit_at_utc
                assert outcome.total_cost is not None
                assert outcome.entry_price is not None
                assert outcome.exit_price is not None
                multiplier = Decimal("0.001")
                hand_cost = (
                    (outcome.entry_price + outcome.exit_price) * multiplier * Decimal("0.0001")
                )
                assert outcome.total_cost == hand_cost
                assert outcome.net_pnl == outcome.gross_pnl - hand_cost

        if asset == "GOLD":
            export = tmp_path / "gold-export"
            assert (
                research_main(
                    [
                        "report",
                        "--database",
                        str(database),
                        "--production-database",
                        str(production),
                        "--experiment-id",
                        experiment_id,
                        "--output",
                        str(export),
                    ]
                )
                == 0
            )
            exported_summary = json.loads((export / "summary.json").read_text(encoding="utf-8"))
            assert exported_summary["data_mode"] == "SYNTHETIC_FIXTURE"
            assert exported_summary["opportunities"] == 3
            assert (export / "selected-opportunities.jsonl").is_file()
            assert "summary.json" in (export / "SHA256SUMS").read_text(encoding="utf-8")
            settings = Settings(
                database_path=production,
                research_database_path=database,
                paper_database_path=tmp_path / "paper.sqlite3",
                operator_username="operator",
                operator_password="secret",
            )
            client = TestClient(create_app(settings, Store(production)))
            auth = ("operator", "secret")
            summary = client.get("/api/research/summary", auth=auth)
            experiments = client.get("/api/research/experiments", auth=auth)
            detail = client.get(f"/api/research/experiments/{experiment_id}", auth=auth)
            engine_rows = client.get(
                f"/api/research/experiments/{experiment_id}/engines", auth=auth
            )
            opportunity_rows = client.get(
                f"/api/research/experiments/{experiment_id}/opportunities", auth=auth
            )
            assert summary.status_code == 200
            assert summary.json()["data_mode"] == "SYNTHETIC_FIXTURE"
            assert summary.json()["external_calls_performed"] == 0
            assert summary.json()["counter_scope"] == "OFFLINE_SHARED_WORKFLOW"
            assert len(experiments.json()) == 1
            assert detail.json()["counts"]["opportunities"] == 3
            assert len(engine_rows.json()) == 3
            assert len(opportunity_rows.json()) == 3

    assert observed_engines == {
        "GOLD_FAST",
        "GOLD_HOURLY",
        "GOLD_SESSION",
        "BTC_FAST",
        "BTC_HOURLY",
        "BTC_SESSION",
    }
