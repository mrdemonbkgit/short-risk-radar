# Short-Risk Radar Dashboard

Short-Risk Radar is a FastAPI + Next.js dashboard that helps short desks understand when the perpetual futures market is too crowded to enter a trade. It continuously ingests Binance USDT-M data, enriches it with analytics (basis, funding, dominance, orderbook imbalance, squeeze risk score) and exposes the results to a responsive UI and alerting pipeline.

## Repository Layout

`
backend/   FastAPI app, collectors, analytics, Redis/Timescale adapters
frontend/  Next.js app with watchlist, tiles, detail pages
deploy/    Docker Compose, infra helpers (WIP)
*.md       PRD and implementation plan
`

Key backend modules:
- pp/collectors/binance_collector.py – REST polling collector with multi-host spot fallback, 24h ticker batching, and Redis timeseries writes.
- pp/services/binance_client.py – Thin Binance REST client (futures + spot) with retry-aware helpers and batch endpoints.
- pp/services/redis_store.py – Snapshot/time-series accessors and cached spot availability flags.
- pp/routers – FastAPI routers for symbols, metrics, timeseries, rules, alerts, and debug mode.

Frontend highlights:
- Watchlist management with SWR polling against /symbols.
- Real-time metric tiles (rontend/app/page.tsx) that show SRS, dominance, and spot/borrow status.
- Detail view pages (see rontend/app/symbol/[symbol]/page.tsx, WIP) for charts and rule explanations.

## Requirements

- Python 3.11+
- Node.js 18+
- Redis (local instance or container)
- Optional: PostgreSQL/TimescaleDB for historical storage (future milestone)

Python dependencies are listed in ackend/requirements.txt; Node packages are managed via rontend/package.json.

## Environment Variables

Copy .env.example (coming soon) or set the following variables before running the stack:

| Variable | Description |
| --- | --- |
| BINANCE_API_KEY / BINANCE_API_SECRET | Optional – only needed for higher rate limits. |
| REDIS_URL | Redis connection string (default edis://localhost:6379/0). |
| APP_NAME | Display name for FastAPI docs. |
| NEXT_PUBLIC_API_BASE | Base URL the frontend uses to talk to FastAPI (http://localhost:8000). |
| COLLECT_INTERVAL_SEC | Collector loop cadence (defaults to 10 seconds). |

Place these vars into .env in the repo root or export them in your shell before running the processes below.

## Running Locally

### 1. Start Redis

`
# simplest option
docker run -p 6379:6379 redis:7-alpine
`

### 2. Backend (FastAPI)

`
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1   # PowerShell (use source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
`

The collector loop is launched as part of the FastAPI startup event. It writes snapshots to Redis and exposes routes such as:
- GET /symbols – watchlist
- GET /symbols/available – cached list of USDT-M contracts with spot availability (15-minute memory cache + Redis flags)
- GET /metrics/{symbol} – current snapshot for a symbol
- GET /timeseries/{symbol}?metric=basis – recent timeseries points

### 3. Frontend (Next.js)

`
cd frontend
npm install
npm run dev
`

By default the web app expects the API at http://localhost:8000. Adjust NEXT_PUBLIC_API_BASE in .env.local if needed.

### 4. Docker Compose (optional)

An integrated Compose file is planned for the deploy/ folder. Once available you will be able to run docker compose up to launch Redis, backend, and frontend together.

## Testing

Backend modules can be sanity-checked with Python’s bytecode compilation and upcoming pytest suites:
`
cd backend
py -m py_compile app/**/*.py
`
Frontend unit tests (React Testing Library/Jest) will be added in a future milestone. For now you can run 
pm run lint to ensure TypeScript/ESLint cleanliness.

## Operational Notes

- /symbols/available uses an in-memory cache guarded by an async lock and also stores spot-availability flags in Redis with short TTLs (1 hour for negative results) to avoid Binance bans.
- Spot ticker requests rotate among pi.binance.com, pi1, pi2, and pi3 hosts; 418/451 responses trigger automatic host failover.
- If you run the collector without Redis, the API will return 404 for metrics – ensure Redis is available before starting.
- When testing new symbols set COLLECT_INTERVAL_SEC higher (30s+) to simulate lower rate usage.

## Roadmap & References

- [Product Requirements Document](short_risk_radar_dashboard_prd_v_1.md)
- [Implementation Plan](IMPLEMENTATION_PLAN.md)
- deploy/README.md (future) for infrastructure/deployment automation.

Upcoming milestones:
1. TimescaleDB historian + charts from historical data.
2. Alert delivery (Telegram bot) and UI for rule explanations.
3. Cross-venue borrowability sourcing and CSV exports.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Binance endpoints return 418/451 | Wait a few minutes (IP throttled). Ensure /symbols/available is not hit repeatedly (it's cached by design). |
| UI shows Not available for spot despite known market | Clear Redis keys srr:has_spot:* or wait for TTL; collector now refreshes flags once spot volume is observed. |
| FastAPI fails to connect to Redis | Verify REDIS_URL and that the container/service is reachable. |

## Contributing

Open PRs against main. Please run linting/formatting in both backend and frontend, and update docs when touching rate-limit logic or external integrations.
