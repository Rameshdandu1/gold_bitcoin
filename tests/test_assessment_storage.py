from marketintel.models import AnalystAssessment
from marketintel.storage import Store


def test_save_individual_assessment_no_overwrite(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    report = AnalystAssessment(
        snapshot_id="s1", direction="NEUTRAL", decision="WAIT",
        supported_target_indices=[], reason="not enough data",
        counter_evidence=[], data_warnings=["no live order flow"],
    )
    store.save_assessment("c1", "GPT", "test-model", report)
    store.save_assessment("c1", "GPT", "test-model", report)
    rows = store.assessments("c1")
    assert len(rows) == 1
    assert rows[0]["assessment"]["decision"] == "WAIT"
