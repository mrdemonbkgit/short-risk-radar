from __future__ import annotations

import asyncio
import time
from typing import Dict, Any, List, Optional
import logging

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
    get_cached_has_spot,
    set_cached_has_spot,
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
logger = logging.getLogger("srr.collector")
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
    # Determine spot market existence and volume
    # Cache has_spot to avoid flapping when spot exchangeInfo is rate-limited or transient
    cached_has_spot = await get_cached_has_spot(symbol)
    has_spot: Optional[bool]
    if cached_has_spot is not None:
        has_spot = bool(cached_has_spot)
    else:
        try:
            has_spot = await client.spot_symbol_exists(symbol)
        except Exception as exc:
            logger.warning("spot existence probe failed for %s: %s", symbol, exc)
            has_spot = None
        else:
            await set_cached_has_spot(symbol, has_spot)
    spot_vol24 = 0.0
    spot_data_ok = False
    if has_spot is not False:
        try:
            spot_24h = await client.spot_ticker_24h(symbol)
            spot_vol24 = float(spot_24h.get("quoteVolume", 0.0))
            spot_data_ok = True
            if has_spot is not True:
                has_spot = True
                await set_cached_has_spot(symbol, True)
        except Exception as exc:
            logger.debug("spot 24h fetch failed for %s: %s", symbol, exc)
            spot_vol24 = 0.0
    has_spot_flag = bool(has_spot)
    if has_spot_flag and spot_vol24 <= 0.0:
        spot_vol24 = await client.spot_quote_volume_24h_via_klines(symbol)
        spot_data_ok = True
    # If spot is unavailable but perp exists, dominance should be 100 only when fut_vol24>0.
    # Also mark dominance unknown when both sides are zero to avoid a misleading 100.
    dominance_unknown = False
    if (has_spot_flag and not spot_data_ok) or (fut_vol24 <= 0 and spot_vol24 <= 0):
        perp_dominance_pct = 0.0
        dominance_unknown = True
    else:
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
        "borrow": {"shortable": has_spot_flag, "venues": []},
        "fut_vol24_usdt": fut_vol24,
        "spot_vol24_usdt": spot_vol24,
        "next_funding_in_sec": next_funding_in_sec,
        "has_spot": has_spot_flag,
        "dominance_unknown": dominance_unknown,
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

            # Batch fetch 24h tickers to reduce rate/latency
            fut_map: Dict[str, Any] = {}
            spot_map: Dict[str, Any] = {}
            try:
                fut_map = await client.ticker_24h_batch(watchlist)
                logger.debug("fut_map keys=%s", list(fut_map.keys()))
            except Exception as e:
                logger.warning("ticker_24h_batch error: %s", e)
                fut_map = {}
            # Only include symbols that likely have spot
            try:
                spot_map = await client.spot_ticker_24h_batch(watchlist)
                logger.debug("spot_map keys=%s", list(spot_map.keys()))
            except Exception as e:
                logger.warning("spot_ticker_24h_batch error: %s", e)
                spot_map = {}

            async def collect_with_maps(sym: str) -> Dict[str, Any]:
                # Small shim to pass batch data into per-symbol collector
                # Falls back to per-request methods if missing
                nonlocal fut_map, spot_map
                now_ms = int(time.time() * 1000)
                pi = await client.premium_index(sym)
                mark = float(pi.get("markPrice", 0.0))
                index = float(pi.get("indexPrice", 0.0))
                basis = calc_basis_pct(mark, index)
                await push_timeseries_point(sym, "basis_1m", now_ms, basis)

                since_15m = now_ms - 15 * 60 * 1000
                basis_values = await get_metric_values_since(sym, "basis_1m", since_15m)
                basis_twap15 = simple_twap(basis_values[-15:]) if basis_values else basis

                funding_interval_hours = await get_funding_interval_hours(client, sym)
                funding_interval_pct = float(pi.get("lastFundingRate", 0.0)) * 100.0
                funding_1h_pct = funding_interval_pct / max(1, funding_interval_hours)
                next_funding_in_sec = max(0, int((int(pi.get("nextFundingTime", 0)) - now_ms) / 1000))

                oi_hist = await client.open_interest_hist(sym, period="5m", limit=13)
                oi_usdt_now = float(oi_hist[-1]["sumOpenInterestValue"]) if oi_hist else 0.0
                oi_usdt_then = float(oi_hist[0]["sumOpenInterestValue"]) if len(oi_hist) >= 1 else 0.0
                delta_oi_1h_usdt = oi_usdt_now - oi_usdt_then

                fut_24h = fut_map.get(sym) or {}
                fut_vol24 = float((fut_24h or {}).get("quoteVolume", 0.0))
                if not fut_24h:
                    try:
                        one = await client.ticker_24h(sym)
                        fut_vol24 = float(one.get("quoteVolume", 0.0))
                    except Exception:
                        fut_vol24 = 0.0
                cached_has_spot = await get_cached_has_spot(sym)
                has_spot: Optional[bool] = bool(cached_has_spot) if cached_has_spot is not None else None
                spot_24h = spot_map.get(sym) or {}
                spot_vol24 = 0.0
                spot_data_ok = False
                if spot_24h:
                    try:
                        spot_vol24 = float(spot_24h.get("quoteVolume", 0.0))
                        spot_data_ok = True
                    except Exception:
                        spot_vol24 = 0.0
                    if spot_data_ok and has_spot is not True:
                        has_spot = True
                        await set_cached_has_spot(sym, True)
                if has_spot is None:
                    try:
                        has_spot = await client.spot_symbol_exists(sym)
                    except Exception as exc:
                        logger.warning("spot existence probe failed for %s: %s", sym, exc)
                        has_spot = None
                    else:
                        await set_cached_has_spot(sym, has_spot)
                has_spot_flag = bool(has_spot)
                if has_spot_flag and not spot_data_ok:
                    try:
                        spot_single = await client.spot_ticker_24h(sym)
                        spot_vol24 = float(spot_single.get("quoteVolume", 0.0))
                        spot_data_ok = True
                    except Exception as exc:
                        logger.debug("spot 24h single failed for %s: %s", sym, exc)
                if has_spot_flag and spot_vol24 <= 0.0:
                    # Fallback to summing last 24h quote volumes via klines if public 24h ticker is unreliable
                    spot_vol24 = await client.spot_quote_volume_24h_via_klines(sym)
                    spot_data_ok = True
                logger.info("%s volumes fut=%s spot=%s", sym, fut_vol24, spot_vol24)

                dominance_unknown = False
                if (has_spot_flag and not spot_data_ok) or (fut_vol24 <= 0 and spot_vol24 <= 0):
                    perp_dominance_pct = 0.0
                    dominance_unknown = True
                else:
                    perp_dominance_pct = calc_dominance_pct(fut_vol24, spot_vol24)

                depth = await client.depth(sym, limit=DEPTH_LIMIT)
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
                    "symbol": sym,
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
                    "borrow": {"shortable": has_spot_flag, "venues": []},
                    "fut_vol24_usdt": fut_vol24,
                    "spot_vol24_usdt": spot_vol24,
                    "next_funding_in_sec": next_funding_in_sec,
                    "has_spot": has_spot_flag,
                    "dominance_unknown": dominance_unknown,
                }
                srs = compute_srs(snapshot)
                traffic, reasons = await evaluate_rules(sym)
                snapshot["srs"] = srs
                snapshot["traffic_light"] = traffic
                snapshot["rule_reasons"] = reasons
                return snapshot

            tasks = [collect_with_maps(sym) for sym in watchlist]
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
