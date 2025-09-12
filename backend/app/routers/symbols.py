from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from ..services.redis_store import get_watchlist, add_symbol as add_sym, remove_symbol as rem_sym

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
