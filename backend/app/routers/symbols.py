from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from ..services.redis_store import get_watchlist, add_symbol as add_sym, remove_symbol as rem_sym
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


@router.get("/available")
async def list_available_symbols(quote: str = "USDT", contract_type: str = "PERPETUAL", verify: bool = False, include_spot: bool = True):
    """List available Binance USDT-M futures contracts.

    Filters symbols by quote asset and contractType (defaults: USDT PERPETUAL).
    Returns a compact list of tradable symbol strings.
    """
    client = BinanceClient()
    try:
        info = await client.futures_exchange_info()
        symbols = info.get("symbols", [])
        out: List[str] = []
        for s in symbols:
            try:
                if s.get("status") != "TRADING":
                    continue
                if s.get("contractType") != contract_type:
                    continue
                if s.get("quoteAsset") != quote:
                    continue
                sym = str(s.get("symbol", ""))
                if not sym:
                    continue
                if include_spot:
                    try:
                        has_spot = await client.spot_symbol_exists(sym)
                    except Exception:
                        has_spot = False
                    out.append({"symbol": sym, "has_spot": has_spot})
                else:
                    out.append(sym)
            except Exception:
                continue
        # Sort consistently
        if include_spot:
            out.sort(key=lambda x: x["symbol"])  # type: ignore[index]
        else:
            out.sort()

        if not verify:
            return {"quote": quote, "contract_type": contract_type, "symbols": out}

        # Verify that our collector can actually retrieve data for the symbol
        # by probing a subset of required endpoints.
        import asyncio

        sem = asyncio.Semaphore(8)

        async def probe(sym: str) -> bool:
            async with sem:
                try:
                    # premium index + a tiny OI sample are enough to ensure basic coverage
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
