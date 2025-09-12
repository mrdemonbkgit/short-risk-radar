from fastapi import APIRouter

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("")
async def configure_alerts(payload: dict):
    # Placeholder for configuring channels & thresholds
    return {"ok": True, "config": payload}
