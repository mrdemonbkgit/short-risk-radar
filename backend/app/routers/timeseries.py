from fastapi import APIRouter, Query
from typing import List
from ..models import TimeseriesPoint
from ..services.redis_store import get_timeseries
import time

router = APIRouter(prefix="/timeseries", tags=["timeseries"])


@router.get("/{symbol}")
async def get_timeseries_route(
    symbol: str,
    metric: str = Query("basis"),
    interval: str = Query("1m"),
    window: str = Query("48h"),
):
    # Basic parse of window (e.g., 48h, 72h)
    ms = 48 * 3600 * 1000
    if window.endswith("h"):
        try:
            hours = int(window[:-1])
            ms = hours * 3600 * 1000
        except Exception:
            pass
    since = int(time.time() * 1000) - ms
    points_raw = await get_timeseries(symbol.upper(), metric, since)
    points = [TimeseriesPoint(ts=p[0], value=p[1]).model_dump() for p in points_raw]
    return {"symbol": symbol.upper(), "metric": metric, "interval": interval, "window": window, "points": points}
