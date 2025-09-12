from __future__ import annotations

import httpx
from typing import Any, Dict, List, Optional

from ..config import get_settings

_settings = get_settings()


class BinanceClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or _settings.binance_base_url
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10)
        self._spot_client = httpx.AsyncClient(base_url=_settings.binance_spot_base_url, timeout=10)

    async def close(self) -> None:
        await self._client.aclose()
        await self._spot_client.aclose()

    async def premium_index(self, symbol: str) -> Dict[str, Any]:
        r = await self._client.get("/fapi/v1/premiumIndex", params={"symbol": symbol})
        r.raise_for_status()
        return r.json()

    async def funding_rate(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        r = await self._client.get("/fapi/v1/fundingRate", params={"symbol": symbol, "limit": limit})
        r.raise_for_status()
        return r.json()

    async def detect_funding_interval_hours(self, symbol: str) -> int:
        # Infer from gaps between successive "fundingTime" (ms)
        hist = await self.funding_rate(symbol, limit=3)
        times = [int(x.get("fundingTime", 0)) for x in hist]
        times = sorted(set(t for t in times if t))
        if len(times) >= 2:
            delta_ms = abs(times[-1] - times[-2])
            hours = round(delta_ms / (3600 * 1000))
            if hours in (1, 4, 8):
                return hours
        # Fallback default 8h for BTCUSDT-like
        return 8

    async def open_interest(self, symbol: str) -> Dict[str, Any]:
        r = await self._client.get("/fapi/v1/openInterest", params={"symbol": symbol})
        r.raise_for_status()
        return r.json()

    async def open_interest_hist(self, symbol: str, period: str = "5m", limit: int = 12) -> List[Dict[str, Any]]:
        # Returns list with sumOpenInterestValue (USDT) at 5m intervals
        r = await self._client.get(
            "/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        r.raise_for_status()
        return r.json()

    async def ticker_24h(self, symbol: str) -> Dict[str, Any]:
        r = await self._client.get("/fapi/v1/ticker/24hr", params={"symbol": symbol})
        r.raise_for_status()
        return r.json()

    async def spot_ticker_24h(self, symbol: str) -> Dict[str, Any]:
        r = await self._spot_client.get("/api/v3/ticker/24hr", params={"symbol": symbol})
        r.raise_for_status()
        return r.json()

    async def depth(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        # Limit 5/10/20/50/100/500/1000
        r = await self._client.get("/fapi/v1/depth", params={"symbol": symbol, "limit": limit})
        r.raise_for_status()
        return r.json()
