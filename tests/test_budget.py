from marketintel.storage import Store


def test_budget_persists_across_store_instances(tmp_path):
    db = tmp_path / "audit.sqlite3"
    one = Store(db)
    assert one.reserve_ai_calls(2, 3) is True
    two = Store(db)
    assert two.reserve_ai_calls(2, 3) is False
    assert two.reserve_ai_calls(1, 3) is True
    assert one.reserve_ai_calls(1, 3) is False
