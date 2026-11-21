from marketintel.delta import DeltaPublicStream, trade_aggressor


def test_aggressor_buyer_taker():
    assert trade_aggressor({"r": "t"}) == "BUY"
    assert trade_aggressor({"r": "m"}) == "SELL"
    assert trade_aggressor({"r": "unknown"}) is None


def test_trade_delta_is_contracts_not_usd():
    stream = DeltaPublicStream("wss://example.invalid", ["BTCUSD"])
    stream.ingest_message({"sy": "BTCUSD", "type": "trades", "p": "70000", "s": 4, "r": "t"})
    stream.ingest_message({"sy": "BTCUSD", "type": "trades", "p": "70001", "s": 6, "r": "m"})
    assert stream.trade_delta_contracts("BTCUSD") == -2
    assert stream.trade_delta_contracts("GOLD") is None
