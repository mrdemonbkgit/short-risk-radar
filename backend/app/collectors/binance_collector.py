from __future__ import annotations

import asyncio
import time
from typing import Dict, Any, List

from ..config import get_settings
from ..services.binance_client import BinanceClient
from ..services.redis_store import (
    get_watchlist,
    ensure_default_watchlist,
    put_snapshot,
    push_timeseries_point,
    get_cached_funding_interval_hours,
    set_cached_funding_interval_hours,
    get_metric_values_since,
)
from ..analytics.metrics import (
    calc_basis_pct,
    calc_dominance_pct,
    calc_orderbook_imbalance,
    simple_twap,
)
from ..analytics.rules import evaluate_rules
from ..analytics.srs import compute_srs


settings = get_settings()
DEPTH_LIMIT = 100
DEPTH_WINDOW_PCT = 0.02


async def get_funding_interval_hours(client: BinanceClient, symbol: str) -> int:
    cached = await get_cached_funding_interval_hours(symbol)
    if cached:
        return cached
    hours = await client.detect_funding_interval_hours(symbol)
    await set_cached_funding_interval_hours(symbol, hours)
    return hours


async def collect_once(client: BinanceClient, symbol: str) -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)
    # premium index
    pi = await client.premium_index(symbol)
    mark = float(pi.get("markPrice", 0.0))
    index = float(pi.get("indexPrice", 0.0))
    basis = calc_basis_pct(mark, index)

    # push to basis timeseries at 1m resolution
    await push_timeseries_point(symbol, "basis_1m", now_ms, basis)

    # TWAP15
    since_15m = now_ms - 15 * 60 * 1000
    basis_values = await get_metric_values_since(symbol, "basis_1m", since_15m)
    basis_twap15 = simple_twap(basis_values[-15:]) if basis_values else basis

    # Funding
    funding_interval_hours = await get_funding_interval_hours(client, symbol)
    funding_interval_pct = float(pi.get("lastFundingRate", 0.0)) * 100.0
    funding_1h_pct = funding_interval_pct / max(1, funding_interval_hours)
    next_funding_in_sec = max(0, int((int(pi.get("nextFundingTime", 0)) - now_ms) / 1000))

    # OI / ΔOI 1h
    oi_hist = await client.open_interest_hist(symbol, period="5m", limit=13)
    oi_usdt_now = float(oi_hist[-1]["sumOpenInterestValue"]) if oi_hist else 0.0
    oi_usdt_then = float(oi_hist[0]["sumOpenInterestValue"]) if len(oi_hist) >= 1 else 0.0
    delta_oi_1h_usdt = oi_usdt_now - oi_usdt_then

    # Dominance
    fut_24h = await client.ticker_24h(symbol)
    fut_vol24 = float(fut_24h.get("quoteVolume", 0.0))
    spot_24h = await client.spot_ticker_24h(symbol)
    spot_vol24 = float(spot_24h.get("quoteVolume", 0.0))
    perp_dominance_pct = calc_dominance_pct(fut_vol24, spot_vol24)

    # Orderbook imbalance within ±2% mid
    depth = await client.depth(symbol, limit=DEPTH_LIMIT)
    bids: List[List[str]] = depth.get("bids", [])
    asks: List[List[str]] = depth.get("asks", [])
    best_bid = float(bids[0][0]) if bids else mark
    best_ask = float(asks[0][0]) if asks else mark
    mid = (best_bid + best_ask) / 2.0 if best_bid and best_ask else mark
    lo = mid * (1.0 - DEPTH_WINDOW_PCT)
    hi = mid * (1.0 + DEPTH_WINDOW_PCT)

    sum_bids = 0.0
    for p, q, *_ in bids:
        price = float(p)
        if lo <= price <= hi:
            sum_bids += float(q)
    sum_asks = 0.0
    for p, q, *_ in asks:
        price = float(p)
        if lo <= price <= hi:
            sum_asks += float(q)
    orderbook_imbalance = calc_orderbook_imbalance(sum_bids, sum_asks)

    snapshot = {
        "symbol": symbol,
        "ts": now_ms,
        "mark": mark,
        "index": index,
        "basis_pct": basis,
        "basis_twap15_pct": basis_twap15,
        "funding_1h_pct": funding_1h_pct,
        "funding_interval_hours": funding_interval_hours,
        "funding_daily_est_pct": funding_1h_pct * 24,
        "oi_usdt": oi_usdt_now,
        "delta_oi_1h_usdt": delta_oi_1h_usdt,
        "perp_dominance_pct": perp_dominance_pct,
        "orderbook_imbalance": orderbook_imbalance,
        "borrow": {"shortable": False, "venues": []},
        "fut_vol24_usdt": fut_vol24,
        "next_funding_in_sec": next_funding_in_sec,
    }

    # Compute SRS & rules
    srs = compute_srs(snapshot)
    traffic, reasons = await evaluate_rules(symbol)
    snapshot["srs"] = srs
    snapshot["traffic_light"] = traffic
    snapshot["rule_reasons"] = reasons

    return snapshot


async def run_collector_loop(stop_event: asyncio.Event) -> None:
    await ensure_default_watchlist()
    client = BinanceClient()
    try:
        while not stop_event.is_set():
            watchlist = await get_watchlist()
            tasks = [collect_once(client, sym) for sym in watchlist]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            now_ms = int(time.time() * 1000)
            for sym, res in zip(watchlist, results):
                if isinstance(res, Exception):
                    continue
                await put_snapshot(sym, res)
                await push_timeseries_point(sym, "mark", now_ms, float(res.get("mark", 0.0)))
                await push_timeseries_point(sym, "basis", now_ms, float(res.get("basis_pct", 0.0)))
                await push_timeseries_point(sym, "funding", now_ms, float(res.get("funding_1h_pct", 0.0)))
                await push_timeseries_point(sym, "oi", now_ms, float(res.get("oi_usdt", 0.0)))
                await push_timeseries_point(sym, "dominance", now_ms, float(res.get("perp_dominance_pct", 0.0)))
                await push_timeseries_point(sym, "imbalance", now_ms, float(res.get("orderbook_imbalance", 0.0)))
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=settings.collect_interval_sec)
            except asyncio.TimeoutError:
                pass
    finally:
        await client.close()
