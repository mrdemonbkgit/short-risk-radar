from fastapi import APIRouter

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/sentry")
async def trigger_sentry_exception():
    # Raise an error to be captured by Sentry if DSN configured
    raise RuntimeError("Sentry backend test error")


@router.get("/message")
async def capture_sentry_message():
    try:
        import sentry_sdk
        sentry_sdk.capture_message("Sentry backend test message")
        return {"ok": True, "sent": True}
    except Exception:
        return {"ok": False, "sent": False}
