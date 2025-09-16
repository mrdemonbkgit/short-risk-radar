import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.redis_store import (
    get_watchlist,
    add_symbol as add_sym,
    remove_symbol as rem_sym,
    get_cached_has_spot,
    set_cached_has_spot,
)
from ..services.binance_client import BinanceClient

router = APIRouter(prefix="/symbols", tags=["symbols"])


class SymbolIn(BaseModel):
    symbol: str


@router.get("")
async def list_symbols():
    wl = await get_watchlist()
    return {"watchlist": wl}


@router.post("")
async def add_symbol(body: SymbolIn):
    sym = body.symbol.upper()
    wl = await add_sym(sym)
    return {"ok": True, "watchlist": wl}


@router.delete("")
async def remove_symbol(body: SymbolIn):
    sym = body.symbol.upper()
    wl = await rem_sym(sym)
    return {"ok": True, "watchlist": wl}


_AVAILABLE_CACHE_TTL_SEC = 900
_available_cache: Dict[Tuple[str, str, bool, bool], Dict[str, Any]] = {}
_available_cache_lock = asyncio.Lock()


def _get_cached_available(key: Tuple[str, str, bool, bool]) -> Optional[Dict[str, Any]]:
    entry = _available_cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _AVAILABLE_CACHE_TTL_SEC:
        _available_cache.pop(key, None)
        return None
    return entry["payload"]


def _set_cached_available(key: Tuple[str, str, bool, bool], payload: Dict[str, Any]) -> None:
    _available_cache[key] = {"ts": time.time(), "payload": payload}


async def _fetch_available_symbols(
    quote: str,
    contract_type: str,
    verify: bool,
    include_spot: bool,
) -> Dict[str, Any]:
    client = BinanceClient()
    try:
        info = await client.futures_exchange_info()
        symbols = info.get("symbols", [])
        out: List[Any] = []
        spot_symbol_set: Set[str] = set()

        if include_spot:
            try:
                spot_info = await client.spot_exchange_info()
                spot_symbol_set = {
                    str(s.get("symbol", "")).upper()
                    for s in spot_info.get("symbols", [])
                    if s.get("status") == "TRADING"
                }
            except Exception:
                spot_symbol_set = set()

        for s in symbols:
            try:
                if s.get("status") != "TRADING":
                    continue
                if s.get("contractType") != contract_type:
                    continue
                if s.get("quoteAsset") != quote:
                    continue
                sym = str(s.get("symbol", "")).upper()
                if not sym:
                    continue

                if include_spot:
                    cached_spot = await get_cached_has_spot(sym)
                    if cached_spot is not None:
                        has_spot = bool(cached_spot)
                    elif spot_symbol_set:
                        has_spot = sym in spot_symbol_set
                        await set_cached_has_spot(sym, has_spot)
                    else:
                        try:
                            has_spot = await client.spot_symbol_exists(sym)
                        except Exception:
                            has_spot = False
                        else:
                            await set_cached_has_spot(sym, has_spot)
                    out.append({"symbol": sym, "has_spot": has_spot})
                else:
                    out.append(sym)
            except Exception:
                continue

        if include_spot:
            out.sort(key=lambda x: x["symbol"])  # type: ignore[index]
        else:
            out.sort()

        if not verify:
            return {"quote": quote, "contract_type": contract_type, "symbols": out}

        sem = asyncio.Semaphore(8)

        async def probe(sym: str) -> bool:
            async with sem:
                try:
                    await client.premium_index(sym)
                    await client.open_interest_hist(sym, period="5m", limit=1)
                    return True
                except Exception:
                    return False

        if include_spot:
            syms_only = [x["symbol"] for x in out]  # type: ignore[index]
            checks = await asyncio.gather(*(probe(s) for s in syms_only))
            live = [o for o, ok in zip(out, checks) if ok]
            missing = [o for o, ok in zip(out, checks) if not ok]
        else:
            checks = await asyncio.gather(*(probe(s) for s in out))
            live = [s for s, ok in zip(out, checks) if ok]
            missing = [s for s, ok in zip(out, checks) if not ok]

        return {"quote": quote, "contract_type": contract_type, "symbols": live, "unavailable": missing}
    finally:
        await client.close()


@router.get("/available")
async def list_available_symbols(
    quote: str = "USDT",
    contract_type: str = "PERPETUAL",
    verify: bool = False,
    include_spot: bool = True,
):
    quote_norm = quote.upper()
    contract_type_norm = contract_type.upper()
    cache_key = (quote_norm, contract_type_norm, bool(include_spot), bool(verify))

    cached = _get_cached_available(cache_key)
    if cached:
        return cached

    async with _available_cache_lock:
        cached = _get_cached_available(cache_key)
        if cached:
            return cached
        payload = await _fetch_available_symbols(
            quote=quote_norm,
            contract_type=contract_type_norm,
            verify=verify,
            include_spot=include_spot,
        )
        _set_cached_available(cache_key, payload)
        return payload
