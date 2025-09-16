from __future__ import annotations

import asyncio
import json
from typing import List, Dict, Any

import websockets

from ..config import get_settings
from ..services.redis_store import (
    ensure_default_watchlist,
    get_watchlist,
    put_snapshot,
    push_timeseries_point,
)
from ..analytics.metrics import calc_dominance_pct

settings = get_settings()


async def _fapi_stream(symbols: List[str], state: Dict[str, Dict[str, float]]):
    # Aggregate streams: !markPrice@arr for mark/index/funding; ticker for volumes
    streams = []
    for s in symbols:
        s_lower = s.lower()
        streams.append(f"{s_lower}@ticker")
    url = "wss://fstream.binance.com/stream?streams=" + "/".join(streams)
    async for ws in websockets.connect(url, ping_interval=20, ping_timeout=20):
        try:
            async for msg in ws:
                data = json.loads(msg)
                payload = data.get("data") or {}
                sym = str(payload.get("s") or "").upper()
                if not sym:
                    continue
                # Ticker payload fields
                mark = float(payload.get("c") or 0.0)  # last price as proxy
                # Futures doesn't provide index in this stream; leave index=mark for UI continuity
                index = mark
                fut_vol24 = float(payload.get("q") or 0.0)  # quoteVolume

                s = state.setdefault(sym, {"fut_vol24": 0.0, "spot_vol24": 0.0, "mark": 0.0})
                s["fut_vol24"] = fut_vol24
                s["mark"] = mark

                ts = int(payload.get("E") or 0)
                spot_vol = s.get("spot_vol24", 0.0)
                dom_unknown = fut_vol24 <= 0 and spot_vol <= 0
                dom = 0.0 if dom_unknown else calc_dominance_pct(fut_vol24, spot_vol)
                snap = {
                    "symbol": sym,
                    "ts": ts,
                    "mark": mark,
                    "index": index,
                    "basis_pct": 0.0,
                    "basis_twap15_pct": 0.0,
                    "funding_1h_pct": 0.0,
                    "funding_interval_hours": None,
                    "funding_daily_est_pct": 0.0,
                    "oi_usdt": 0.0,
                    "delta_oi_1h_usdt": 0.0,
                    "perp_dominance_pct": dom,
                    "orderbook_imbalance": 0.0,
                    "borrow": {"shortable": s.get("spot_vol24", 0.0) > 0, "venues": []},
                    "fut_vol24_usdt": fut_vol24,
                    "spot_vol24_usdt": spot_vol,
                    "next_funding_in_sec": 0,
                    "has_spot": s.get("spot_vol24", 0.0) > 0,
                    "dominance_unknown": dom_unknown,
                }
                await put_snapshot(sym, snap)
                await push_timeseries_point(sym, "mark", ts, mark)
        except Exception:
            await asyncio.sleep(2)
            continue


async def _spot_stream(symbols: List[str], state: Dict[str, Dict[str, float]]):
    streams = []
    for s in symbols:
        streams.append(f"{s.lower()}@ticker")
    url = "wss://stream.binance.com:9443/stream?streams=" + "/".join(streams)
    async for ws in websockets.connect(url, ping_interval=20, ping_timeout=20):
        try:
            async for msg in ws:
                data = json.loads(msg)
                payload = data.get("data") or {}
                sym = str(payload.get("s") or "").upper()
                if not sym:
                    continue
                spot_vol24 = float(payload.get("Q") or 0.0)  # quoteVolume on spot
                s = state.setdefault(sym, {"fut_vol24": 0.0, "spot_vol24": 0.0, "mark": 0.0})
                s["spot_vol24"] = spot_vol24
                # Let futures stream drive mark, just update dominance here by writing snapshot quickly using last mark
                mark = s.get("mark", 0.0)
                fut = s.get("fut_vol24", 0.0)
                dom_unknown = fut <= 0 and spot_vol24 <= 0
                dom = 0.0 if dom_unknown else calc_dominance_pct(fut, spot_vol24)
                ts = int(payload.get("E") or 0)
                snap = {
                    "symbol": sym,
                    "ts": ts,
                    "mark": mark,
                    "index": mark,
                    "basis_pct": 0.0,
                    "basis_twap15_pct": 0.0,
                    "funding_1h_pct": 0.0,
                    "funding_interval_hours": None,
                    "funding_daily_est_pct": 0.0,
                    "oi_usdt": 0.0,
                    "delta_oi_1h_usdt": 0.0,
                    "perp_dominance_pct": dom,
                    "orderbook_imbalance": 0.0,
                    "borrow": {"shortable": spot_vol24 > 0, "venues": []},
                    "fut_vol24_usdt": fut,
                    "spot_vol24_usdt": spot_vol24,
                    "next_funding_in_sec": 0,
                    "has_spot": spot_vol24 > 0,
                    "dominance_unknown": dom_unknown,
                }
                await put_snapshot(sym, snap)
        except Exception:
            await asyncio.sleep(2)
            continue


async def run_ws_collector(stop_event: asyncio.Event) -> None:
    await ensure_default_watchlist()
    state: Dict[str, Dict[str, float]] = {}
    while not stop_event.is_set():
        watch = await get_watchlist()
        try:
            await asyncio.wait_for(
                asyncio.gather(_fapi_stream(watch, state), _spot_stream(watch, state)),
                timeout=60,
            )
        except asyncio.TimeoutError:
            continue

