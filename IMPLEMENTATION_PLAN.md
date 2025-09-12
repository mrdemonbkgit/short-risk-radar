# Short‑Risk Radar – Detailed Implementation Plan

This plan translates the PRD into concrete deliverables, milestones, and tasks.

## Scope (Phase 0 – MVP)
- Binance only (USDT‑M): basis, funding, OI, dominance, orderbook imbalance
- SRS composite and Red/Yellow/Green rules
- Watchlist, tiles, detail charts
- Telegram alerts
- CSV export for last 48h

## Architecture
- Backend: FastAPI app with three subsystems
  - Collectors (httpx, scheduled): premiumIndex (10s), fundingRate (1h), OI hist (5m), ticker24h, depth
  - Analytics: compute basis, TWAPs, dominance, ΔOI, imbalance, SRS; rule engine
  - API: REST per PRD §7.4; Redis cache for hot snapshots; Timescale/Postgres for history
- Frontend: Next.js + Tailwind + Recharts/ECharts
- Infra: Docker, docker‑compose; Redis, TimescaleDB; .env config

## Data Model (Pydantic)
- Symbol: `symbol`, `base`, `quote`, `venue="BINANCEUSDTM"`
- Snapshot: fields per §7.4 example including `srs`, `traffic_light`, `next_funding_in_sec`
- TimeseriesPoint: `ts`, `metric`, `value`
- BorrowInfo: `shortable`, `venues:[{ex, apr_pct}]` (stubbed in MVP)

## Interfaces
- Binance endpoints: §7.1; sampling rules §7.3
- REST API: §7.4
- Alerts: Telegram Bot + webhook

## Milestones & Tasks
1) Project scaffolding (monorepo, Docker, env, CI placeholder)
2) Backend skeleton (FastAPI app, config, health, stub routes)
3) Collectors implementation (premiumIndex 10s; others stub → iterate)
4) Storage layer (Timescale schema, upsert/write API; Redis cache)
5) Analytics engine (TWAPs, dominance, ΔOI, imbalance, SRS; rules)
6) API endpoints (§7.4) with pagination/time filters; CSV export
7) Frontend UI (watchlist, tiles, charts, rule explainability)
8) Alerts service (Telegram), throttling/debounce)
9) Tests (unit for calcs; integration with mocked HTTP)

## Testing Strategy
- Unit: deterministic fixtures for calculations (basis, TWAP, dominance, ΔOI, SRS)
- Integration: mock httpx responses; simulate collector loops; API contract tests
- E2E (light): start stack with Compose; smoke check endpoints and UI

## Performance Targets
- Sampling loop uses async httpx + rate limiting and jitter
- Cache latest snapshot per symbol in Redis; UI reads from API that fans out to Redis
- Batch inserts into Timescale at 1m granularity

## Rollout
- Phase 0: Binance only + Telegram
- Phase 1: Cross‑venue spot volumes & borrowability
- Phase 2: Backtest + CSV export augmentation + profiles

## Risks & Mitigations
- Exchange rate limits → backoff/jitter, cache, staggered schedules
- Data gaps → last‑known value with STALE flag
- Borrow APR missing → UI shows N/A; rule disabled until confirmed

## Deliverables
- Running stack via `docker compose up` (API + UI + DB + Redis)
- Source with unit/integration tests and CI hooks
- `.env.example` with all variables


