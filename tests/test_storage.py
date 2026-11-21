from datetime import timedelta

from marketintel.detectors import EngineConfig, create_candidate
from marketintel.storage import Store


def test_candidate_idempotent_store(tmp_path, make_bars):
    store = Store(tmp_path / "db.sqlite3")
    bars = make_bars(n=35, last_close=125)
    c = create_candidate(
        EngineConfig("GOLD", "1m", 30),
        bars,
        now=bars[-1].open_time + timedelta(minutes=1, seconds=15),
    )
    assert c
    assert store.add_candidate(c) is True
    assert store.add_candidate(c) is False
    assert len(store.recent_candidates()) == 1
