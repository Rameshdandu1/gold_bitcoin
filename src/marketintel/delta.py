"""Delta Exchange India public REST/WS connectors. No trading API functions."""

import asyncio
import json
import logging
import random
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets

from marketintel.models import Candle

LOGGER = logging.getLogger(__name__)


class DeltaAPIError(Exception):
    """Transient or invalid public market-data response."""


class DeltaREST:
    def __init__(self, base_url: str, timeout: float = 12):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                self.base_url + path, params=params, headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("success", False):
                raise DeltaAPIError(f"Unsuccessful Delta response from {path}")
            return payload.get("result")

    async def products(self) -> list[dict[str, Any]]:
        value = await self._get("/v2/products")
        if not isinstance(value, list):
            raise DeltaAPIError("Unexpected product-list schema")
        return [p for p in value if isinstance(p, dict)]

    async def valid_symbols(self, wanted: list[str]) -> tuple[list[str], list[str]]:
        actual = {
            str(p["symbol"]) for p in await self.products()
            if p.get("symbol") and p.get("state") not in ("expired", "delisted")
        }
        return [x for x in wanted if x in actual], [x for x in wanted if x not in actual]

    async def historical_candles(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> list[Candle]:
        result = await self._get("/v2/history/candles", {
            "resolution": resolution,
            "symbol": symbol,
            "start": int(start.timestamp()),
            "end": int(end.timestamp()),
        })
        if not isinstance(result, list):
            raise DeltaAPIError("Unexpected historical candle schema")
        candles: list[Candle] = []
        for raw in result:
            if not isinstance(raw, dict):
                continue
            epoch = raw.get("time", raw.get("t"))
            if epoch is None:
                raise DeltaAPIError("Candle has no documented timestamp")
            # REST historical times are seconds since epoch, unlike microsecond WS feed timestamps.
            candles.append(Candle(
                symbol=symbol,
                resolution=resolution,
                open_time=datetime.fromtimestamp(float(epoch), tz=timezone.utc),
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
                volume_contracts=float(raw.get("volume", 0)),
            ))
        return sorted(candles, key=lambda c: c.open_time)


def trade_aggressor(trade: dict[str, Any]) -> str | None:
    """r describes *buyer* role: taker means buy aggressor, maker means sell."""
    role = trade.get("r")
    return "BUY" if role == "t" else "SELL" if role == "m" else None


class DeltaPublicStream:
    """Bounded in-memory stream demonstration; production needs durable event journal."""

    def __init__(self, url: str, symbols: list[str], window: int = 5000):
        self.url = url
        self.symbols = symbols
        self.trades: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=window)
        )
        self.last_ticker: dict[str, dict[str, Any]] = {}
        self.last_book: dict[str, dict[str, Any]] = {}
        self.last_seen_utc: datetime | None = None

    def ingest_message(self, message: dict[str, Any]) -> None:
        symbol = message.get("sy")
        if symbol not in self.symbols:
            return
        msg_type = message.get("type")
        if msg_type == "trades":
            side = trade_aggressor(message)
            if side is None or float(message.get("s", 0)) <= 0:
                return
            self.trades[symbol].append({
                "price": float(message["p"]),
                "contracts": float(message["s"]),
                "aggressor": side,
                "event_time_microseconds": message.get("t"),
            })
        elif msg_type == "ticker":
            self.last_ticker[symbol] = message
        elif msg_type == "ob_l2":
            # Periodic top-15 snapshot is NOT a full orderbook nor persistent liquidity map.
            self.last_book[symbol] = message
        else:
            return
        self.last_seen_utc = datetime.now(timezone.utc)

    def trade_delta_contracts(self, symbol: str, last_n: int = 5000) -> float | None:
        trades = list(self.trades.get(symbol, ()))
        if not trades:
            return None
        return sum(
            t["contracts"] if t["aggressor"] == "BUY" else -t["contracts"]
            for t in trades[-last_n:]
        )

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        if not self.symbols:
            return
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(
                    self.url, ping_interval=20, ping_timeout=15, max_size=4_000_000
                ) as socket:
                    subscription = {"type": "subscribe", "payload": {"channels": [
                        {"name": name, "symbols": self.symbols}
                        for name in ["trades", "ticker", "ob_l2"]
                    ]}}
                    await socket.send(json.dumps(subscription))
                    backoff = 1.0
                    async for raw in socket:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            self.ingest_message(parsed)
                            yield parsed
            except asyncio.CancelledError:
                raise
            except (OSError, ValueError, websockets.exceptions.WebSocketException) as exc:
                LOGGER.warning("Delta public stream disconnected: %s", type(exc).__name__)
            # Reconnect with jitter; do not fire a tight connection loop.
            await asyncio.sleep(backoff + random.uniform(0, min(backoff, 2)))
            backoff = min(backoff * 2, 60.0)
