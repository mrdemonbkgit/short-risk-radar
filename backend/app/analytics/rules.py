from __future__ import annotations

import time
from typing import List, Tuple

from .metrics import calc_dominance_pct
from ..services.redis_store import get_timeseries, get_snapshot

# Thresholds (can be made configurable per symbol via DB/config later)
RED_DOMINANCE_THRESHOLD = 70.0
OI_PERPVOL_MIN_RATIO = 0.25
BASIS_TWAP15_GREEN_MIN = 0.10
FUNDING_VERY_NEGATIVE = -0.15  # per hour
GREEN_FUNDING_NONNEG_HOURS = 3
GREEN_DOMINANCE_MAX = 60.0


async def _price_up_last_hour(symbol: str) -> bool:
    now = int(time.time() * 1000)
    points = await get_timeseries(symbol, "mark", now - 60 * 60 * 1000)
    if len(points) < 2:
        return False
    start = points[0][1]
    end = points[-1][1]
    try:
        return float(end) > float(start)
    except Exception:
        return False


async def _funding_nonnegative_last_n_hours(symbol: str, n: int) -> bool:
    now = int(time.time() * 1000)
    points = await get_timeseries(symbol, "funding", now - n * 60 * 60 * 1000)
    if not points:
        return False
    return all(float(v) >= 0 for _, v in points)


async def evaluate_rules(symbol: str) -> Tuple[str, List[str]]:
    snap = await get_snapshot(symbol)
    if not snap:
        return ("YELLOW", ["no snapshot yet"])

    reasons: List[str] = []

    funding_1h = float(snap.get("funding_1h_pct", 0.0))
    basis_twap15 = float(snap.get("basis_twap15_pct", 0.0))
    dominance = float(snap.get("perp_dominance_pct", 0.0))
    delta_oi_1h = float(snap.get("delta_oi_1h_usdt", 0.0))
    oi_usdt = float(snap.get("oi_usdt", 0.0))
    fut_vol24 = float(snap.get("fut_vol24_usdt", 0.0))

    # Red rules
    if funding_1h < 0 and basis_twap15 <= 0:
        reasons.append("funding_1h < 0 and basis_twap15 ≤ 0 (perp discount)")

    if dominance >= RED_DOMINANCE_THRESHOLD and fut_vol24 > 0 and (oi_usdt / max(fut_vol24, 1e-9)) >= OI_PERPVOL_MIN_RATIO:
        reasons.append("perp_dominance ≥ 70% and oi/usdt_vol24 ≥ 0.25")

    if delta_oi_1h > 0 and await _price_up_last_hour(symbol):
        reasons.append("ΔOI 1h > 0 while price ↑ last hour")

    # Borrowability rule (apply only if known)
    borrow = snap.get("borrow") or {}
    venues = borrow.get("venues") or []
    shortable = bool(borrow.get("shortable", False))
    if venues and (not shortable):
        reasons.append("spot short not borrowable or APR too high")

    if reasons:
        return ("RED", reasons)

    # Yellow (basis-only)
    if funding_1h <= FUNDING_VERY_NEGATIVE and shortable:
        return ("YELLOW", ["funding very negative but spot short borrowable"]) 

    # Green window
    green_reasons: List[str] = []
    funding_ok = await _funding_nonnegative_last_n_hours(symbol, GREEN_FUNDING_NONNEG_HOURS)
    if funding_ok:
        green_reasons.append("funding_1h ≥ 0 for ≥3h")
    if basis_twap15 >= BASIS_TWAP15_GREEN_MIN:
        green_reasons.append("basis_twap15 ≥ +0.10%")
    if delta_oi_1h <= 0:
        green_reasons.append("ΔOI 1h ≤ 0")
    if dominance < GREEN_DOMINANCE_MAX:
        green_reasons.append("perp_dominance < 60%")

    if len(green_reasons) >= 4:
        return ("GREEN", green_reasons)

    return ("YELLOW", ["default state"])  # neutral when neither Red nor Green
