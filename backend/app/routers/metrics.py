from fastapi import APIRouter, HTTPException
from ..models import Snapshot
from ..services.redis_store import get_snapshot

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/{symbol}", response_model=Snapshot)
async def get_metrics(symbol: str):
    sym = symbol.upper()
    snap = await get_snapshot(sym)
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot yet")
    return snap
