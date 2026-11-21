"""Optional CoinGlass V4 adapter with actual subscription checks by response."""

from typing import Any

import httpx


class CoinGlassError(Exception):
    pass


class CoinGlassV4:
    def __init__(self, key: str, base_url: str = "https://open-api-v4.coinglass.com"):
        if not key:
            raise ValueError("COINGLASS_API_KEY required when enabled")
        self.key = key
        self.base_url = base_url.rstrip("/")

    async def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/api/") or ".." in path:
            raise ValueError("Only explicit CoinGlass /api/ endpoint paths permitted")
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                self.base_url + path,
                params=params,
                headers={"CG-API-KEY": self.key, "Accept": "application/json"},
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict) or str(value.get("code")) != "0":
                # Deliberately omit provider payload to avoid leaking anything sensitive.
                raise CoinGlassError("CoinGlass unavailable, unlicensed, or rate-limited")
            return value.get("data")

    async def supported_coins(self) -> list[str]:
        value = await self.request("/api/futures/supported-coins")
        if not isinstance(value, list):
            raise CoinGlassError("Unexpected supported-coins response")
        return [str(x) for x in value]
