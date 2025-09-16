from __future__ import annotations

import httpx
from typing import Any, Dict, List, Optional
import json
import logging

from ..config import get_settings

_settings = get_settings()


class BinanceClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or _settings.binance_base_url
        headers = {"User-Agent": "short-risk-radar/0.1"}
        if _settings.binance_api_key:
            headers["X-MBX-APIKEY"] = _settings.binance_api_key
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10, headers=headers)
        self._spot_client = httpx.AsyncClient(base_url=_settings.binance_spot_base_url, timeout=10, headers=headers)
        self.logger = logging.getLogger("srr.binance")
        self._spot_hosts = [
            str(self._spot_client.base_url),
            "https://api1.binance.com",
            "https://api2.binance.com",
            "https://api3.binance.com",
        ]

    async def _spot_request(self, path: str, params: Dict[str, Any]) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for idx, host in enumerate(self._spot_hosts):
            try:
                if idx == 0:
                    r = await self._spot_client.get(path, params=params)
                else:
                    async with httpx.AsyncClient(base_url=host, timeout=10, headers=self._spot_client.headers) as c:
                        r = await c.get(path, params=params)
                if r.status_code in (418, 451):
                    self.logger.warning("spot host %s returned %s for %s", host, r.status_code, path)
                    last_exc = httpx.HTTPStatusError("spot banned", request=r.request, response=r)
                    continue
                r.raise_for_status()
                return r
            except Exception as e:
                last_exc = e
                self.logger.warning("spot request failed on host %s for %s: %s", host, path, e)
                continue
        assert last_exc is not None
        raise last_exc

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

    async def ticker_24h_batch(self, symbols: list[str]) -> Dict[str, Dict[str, Any]]:
        """Batch get futures 24h ticker for multiple symbols.

        Returns a map symbol -> payload.
        """
        if not symbols:
            return {}
        try:
            r = await self._client.get("/fapi/v1/ticker/24hr", params={"symbols": json.dumps(symbols)})
            r.raise_for_status()
            arr = r.json() or []
        except Exception as e:
            self.logger.warning("futures batch 24h failed, falling back per-symbol: %s | symbols=%s", e, symbols)
            out_fallback: Dict[str, Dict[str, Any]] = {}
            for s in symbols:
                try:
                    one = await self.ticker_24h(s)
                    out_fallback[s] = one
                except Exception as ee:
                    self.logger.warning("futures 24h single failed for %s: %s", s, ee)
            return out_fallback
        out: Dict[str, Dict[str, Any]] = {}
        for item in arr:
            sym = item.get("symbol")
            if sym:
                out[str(sym)] = item
        self.logger.debug("futures batch 24h symbols=%d", len(out))
        return out

    async def spot_ticker_24h(self, symbol: str) -> Dict[str, Any]:
        r = await self._spot_request("/api/v3/ticker/24hr", params={"symbol": symbol})
        r.raise_for_status()
        return r.json()

    async def spot_ticker_24h_batch(self, symbols: list[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}
        try:
            r = await self._spot_request("/api/v3/ticker/24hr", params={"symbols": json.dumps(symbols)})
            arr = r.json() or []
        except Exception as e:
            self.logger.warning("spot batch 24h failed, falling back per-symbol: %s | symbols=%s", e, symbols)
            out_fallback: Dict[str, Dict[str, Any]] = {}
            for s in symbols:
                try:
                    one = await self.spot_ticker_24h(s)
                    out_fallback[s] = one
                except Exception as ee:
                    self.logger.warning("spot 24h single failed for %s: %s", s, ee)
            return out_fallback
        out: Dict[str, Dict[str, Any]] = {}
        for item in arr:
            sym = item.get("symbol")
            if sym:
                out[str(sym)] = item
        self.logger.debug("spot batch 24h symbols=%d", len(out))
        return out

    async def spot_klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> List[List[Any]]:
        r = await self._spot_request("/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit})
        r.raise_for_status()
        return r.json()

    async def spot_quote_volume_24h_via_klines(self, symbol: str) -> float:
        try:
            klines = await self.spot_klines(symbol, interval="1h", limit=24)
            total = 0.0
            for k in klines:
                # Quote asset volume index 7
                if len(k) >= 8:
                    total += float(k[7])
            return total
        except Exception as e:
            self.logger.warning("spot klines fallback failed for %s: %s", symbol, e)
            return 0.0

    async def depth(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        # Limit 5/10/20/50/100/500/1000
        r = await self._client.get("/fapi/v1/depth", params={"symbol": symbol, "limit": limit})
        r.raise_for_status()
        return r.json()

    async def futures_exchange_info(self) -> Dict[str, Any]:
        """Return futures exchange info to enumerate available contracts.

        Useful to list USDT-M perpetual trading symbols to avoid 404s for unsupported pairs.
        """
        r = await self._client.get("/fapi/v1/exchangeInfo")
        r.raise_for_status()
        return r.json()

    async def spot_exchange_info(self) -> Dict[str, Any]:
        r = await self._spot_client.get("/api/v3/exchangeInfo")
        r.raise_for_status()
        return r.json()

    async def spot_symbol_exists(self, symbol: str) -> bool:
        """Check if a spot symbol exists on the main spot exchange.

        We prefer exchangeInfo for existence (cheap and explicit) rather than relying on
        a 24h ticker that may fail during maintenance or if trading is halted.
        """
        try:
            r = await self._spot_client.get("/api/v3/exchangeInfo", params={"symbol": symbol})
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (400, 404):
                return False
            raise
        data = r.json()
        symbols = data.get("symbols") or []
        return len(symbols) > 0