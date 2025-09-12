from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import orjson
from redis.asyncio import Redis

from ..config import get_settings


_settings = get_settings()
_redis: Optional[Redis] = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(_settings.redis_url, decode_responses=False)
    return _redis


# Keys
KEY_WATCHLIST = "srr:watchlist"
KEY_SNAPSHOT = "srr:snapshot:{symbol}"
KEY_TS = "srr:ts:{symbol}:{metric}"
KEY_FUNDING_INTERVAL = "srr:funding_interval:{symbol}"


async def ensure_default_watchlist() -> List[str]:
    redis = get_redis()
    symbols = await redis.smembers(KEY_WATCHLIST)
    if not symbols:
        defaults = [s.strip().upper() for s in ("BTCUSDT,ETHUSDT").split(",") if s.strip()]
        if defaults:
            await redis.sadd(KEY_WATCHLIST, *defaults)
            return defaults
    return sorted(s.decode() for s in symbols)


async def get_watchlist() -> List[str]:
    redis = get_redis()
    symbols = await redis.smembers(KEY_WATCHLIST)
    return sorted(s.decode() for s in symbols)


async def add_symbol(symbol: str) -> List[str]:
    redis = get_redis()
    await redis.sadd(KEY_WATCHLIST, symbol.upper())
    return await get_watchlist()


async def remove_symbol(symbol: str) -> List[str]:
    redis = get_redis()
    await redis.srem(KEY_WATCHLIST, symbol.upper())
    return await get_watchlist()


async def put_snapshot(symbol: str, snapshot: Dict[str, Any]) -> None:
    redis = get_redis()
    key = KEY_SNAPSHOT.format(symbol=symbol.upper())
    await redis.set(key, orjson.dumps(snapshot))


async def get_snapshot(symbol: str) -> Optional[Dict[str, Any]]:
    redis = get_redis()
    key = KEY_SNAPSHOT.format(symbol=symbol.upper())
    raw = await redis.get(key)
    return orjson.loads(raw) if raw else None


async def push_timeseries_point(symbol: str, metric: str, ts_ms: int, value: float) -> None:
    redis = get_redis()
    key = KEY_TS.format(symbol=symbol.upper(), metric=metric)
    member = orjson.dumps([ts_ms, value])
    await redis.zadd(key, {member: ts_ms})


async def get_timeseries(symbol: str, metric: str, since_ms: int) -> List[Tuple[int, float]]:
    redis = get_redis()
    key = KEY_TS.format(symbol=symbol.upper(), metric=metric)
    members = await redis.zrangebyscore(key, since_ms, _now_ms())
    points: List[Tuple[int, float]] = []
    for m in members:
        ts, val = orjson.loads(m)
        points.append((int(ts), float(val)))
    return points


async def get_metric_values_since(symbol: str, metric: str, since_ms: int) -> List[float]:
    points = await get_timeseries(symbol, metric, since_ms)
    return [float(v) for _, v in points]


async def get_cached_funding_interval_hours(symbol: str) -> Optional[int]:
    redis = get_redis()
    val = await redis.get(KEY_FUNDING_INTERVAL.format(symbol=symbol.upper()))
    if not val:
        return None
    try:
        return int(val.decode() if isinstance(val, (bytes, bytearray)) else val)
    except Exception:
        return None


async def set_cached_funding_interval_hours(symbol: str, hours: int, ttl_seconds: int = 86400) -> None:
    redis = get_redis()
    await redis.setex(KEY_FUNDING_INTERVAL.format(symbol=symbol.upper()), ttl_seconds, str(int(hours)).encode())
