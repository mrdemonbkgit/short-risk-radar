from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "live"}


@router.get("/ready")
def ready():
    # In MVP, always ready; later, check DB/Redis freshness
    return {"status": "ready"}
