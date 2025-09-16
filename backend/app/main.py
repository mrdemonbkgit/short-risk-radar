from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import health, symbols, metrics, timeseries, rules, alerts
from .lifecycle import on_startup, on_shutdown
import os
import logging

# Sentry init (optional)
SENTRY_DSN = os.getenv("SENTRY_DSN_BACKEND")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        integrations=[FastApiIntegration()],
        environment=os.getenv("ENV", "development"),
        release=os.getenv("APP_VERSION", "0.1.0"),
    )

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

# Basic logging config (can be overridden by server flags)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(symbols.router)
app.include_router(metrics.router)
app.include_router(timeseries.router)
app.include_router(rules.router)
app.include_router(alerts.router)

# Debug
try:
    from .routers import debug as debug_router
    app.include_router(debug_router.router)
except Exception:
    pass


@app.on_event("startup")
async def _startup():
    await on_startup()


@app.on_event("shutdown")
async def _shutdown():
    await on_shutdown()


@app.get("/")
def root():
    return {"name": settings.app_name, "status": "ok"}
