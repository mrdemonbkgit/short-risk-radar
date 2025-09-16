# Short‑Risk Radar Dashboard – PRD v1.0

> Goal: Give a large short seller the **right to NOT trade** unless the market structure is favourable. The dashboard must warn against crowded shorts, perpetual‑led price action, and expensive funding before a short entry on Binance (and optionally other venues).

---

## 1) Product Summary
**Problem.** Shorting meme/low‑fundamental coins during perp‑led pumps causes catastrophic squeezes and heavy funding costs.

**Solution.** A real‑time dashboard that aggregates futures/spot signals and converts them into clear **go/neutral/no‑go** guidance for short entries, plus alerts for delta‑neutral opportunities (funding farming) and exits.

**Primary exchange:** Binance USDT‑M Perpetuals.  
**Secondary (optional):** Bybit, Bitget, Gate, MEXC, HTX (for cross‑venue context and spot borrow checks).

**Output forms:**
- Tiles for each symbol (watchlist). 
- Detail view with time series, order book stats, and crowding metrics.
- A single number **SRS – Squeeze Risk Score (0–100)** and **Traffic Light**: *Green (short ok), Yellow (basis only), Red (no short).* 
- Alerts to Telegram/Discord/Email.

**Non‑goals:** Automated trading; market manipulation; DEX routing; portfolio accounting.

---

## 2) Target Users
- Professional short seller/desk wanting pre‑trade intelligence on perp‑led coins.
- Basis/arbitrage trader assessing funding carry versus hedge feasibility.

---

## 3) Key Concepts (must be implemented and displayed)
- **Mark vs Index vs Last** (Binance): `basis = (Mark − Index) / Index`.
- **Funding 1h** (Binance interval) and **Daily Estimate** ≈ `funding_1h × 24`.
- **Basis TWAP** over 5m/15m/60m (sampled per minute from premiumIndex endpoint).
- **Perp Dominance** = `FuturesVol24h / (FuturesVol24h + SpotVol24h_all)`.
- **Open Interest (OI)** and **ΔOI** (1h/4h/24h).  
- **OI/PerpVol Ratio** – how “sticky” the positions are.
- **Orderbook Imbalance** within ±2% of mid (perp & spot).
- **Borrowability & Borrow APR** for spot short (per exchange).
- **Funding Cap/Floor** & countdown to next funding.
- **SRS – Squeeze Risk Score** (weighted composite; see §9).
- **has_spot**: whether a matching spot market exists for the perp symbol (e.g., `MYXUSDT` spot). If `false`, hedging/borrowing is not possible.

---

## 4) Core User Stories
1. **As a trader**, I add a symbol (e.g., `MYXUSDT`) and immediately see if **shorting is prohibited** (Red), **basis‑only** (Yellow), or **allowed small size** (Green).  
2. **As a trader**, I can open a detail page with funding history (24–72 hours), basis TWAP, OI trend, dominance, and depth metrics to justify/deny an entry.  
3. **As a basis trader**, I get alerts when funding is sufficiently negative while spot short is borrowable at an acceptable APR.
4. **As a risk manager**, I can backtest alerts and export a CSV of signals and metrics.

---

## 5) Functional Requirements
### 5.1 Watchlist
- Add/remove symbols (Binance symbols, e.g., `MYXUSDT`).
- Persist watchlist (local storage + optional backend user profile).

### 5.2 Summary Tiles (per symbol)
Each tile must show, updated at least every 10–30s:
- **Price (Mark & Index)**; **Basis% (current)** and **TWAP15**.
- **Funding 1h (derived)**, **Funding interval (1h/4h/8h)**; **Daily estimate**; **Next funding countdown**.
- **OI (USDT)** and **ΔOI 1h**.
- **Perp Dominance**.
- **Spot Shortable?** (Yes/No + APR + venue). If no spot market exists (has_spot = false), display “No spot market”.
- **Traffic Light** + **SRS**.
- Hover tooltip: last 6 readings of funding/basis/OI.

### 5.3 Detail Page (per symbol)
- Time series charts (1m sampling where feasible):
  - Mark, Index, Basis (spot overlay optional). 
  - Funding 1h (bars), Daily estimate (line). 
  - OI & ΔOI. 
  - Perp vs. Spot Volume (stacked area) ⇒ Dominance. 
  - Orderbook imbalance (bid/ask within ±2%).
- Cross‑venue table (optional): funding & basis snapshots on Bybit/Bitget/Gate/etc.
- Borrow panel: which exchanges allow borrowing the token spot, APR, and loanable size (if available).
- **Rule explainability**: which conditions make the light Red/Yellow/Green.

### 5.4 Alerts & Rules Engine
- **No‑Short alert** when any *hard rule* is violated (see §8).
- **Basis‑Only alert** when funding is very negative but spot shorting is feasible.
- **Short‑Window alert** when funding flips ≥ 0 for ≥3 consecutive hours AND basis TWAP15 ≥ +0.10% AND ΔOI ≤ 0.
- Channels: Telegram Bot, Discord Webhook, Email. Throttle and cooldown configurable.

### 5.5 Data Export / API
- CSV/JSON export of metrics and rule events.
- REST endpoints for metrics and timeseries (see §7.4) for external tools.

---

## 6) System Architecture
**Option A (robust):**
- **Collector** (Python/FastAPI workers): pulls Binance Futures & Spot with multi-host fallback/backoff; optional CCXT for other venues; push to Redis for hot cache and TimescaleDB/Postgres for history.
- **Analytics Engine**: computes basis TWAPs, dominance, ΔOI, SRS, rule states.
- **API Layer** (FastAPI): aggregates time windows; serves UI + alerts service.
- **Frontend** (Next.js/React + Tailwind + Recharts/ECharts).
- **Task Queue** (RQ/Celery) for schedulers; **Prometheus + Grafana** for ops metrics.

**Option B (MVP fast):** Single Streamlit app + in‑memory caching + optional SQLite; upgrade later.

**Performance targets**
- P50 page load < 1.5s; P50 metric freshness ≤ 20s; sustained 20 symbols in watchlist.

---

## 7) Data Interfaces
### 7.1 Binance Futures (public)
- `GET /fapi/v1/premiumIndex` → markPrice, indexPrice, lastFundingRate, nextFundingTime.  
- `GET /fapi/v1/fundingRate` → historical funding (1h interval).  
- `GET /fapi/v1/openInterest` and `GET /futures/data/openInterestHist` → OI now + history.  
- `GET /fapi/v1/ticker/24hr` → perp quoteVolume etc.  
- `GET /fapi/v1/depth` → orderbook snapshot.

### 7.2 Spot (multi‑venue via CCXT or native)
- 24h volume, orderbook depth (±2%), last price. 
- (Optional) borrow endpoints per venue; if unavailable, store manual APR and update UI as _N/A_.

### 7.3 Sampling & Storage
- **Basis sampling:** call `premiumIndex` every 10s; construct 1m bars; TWAP windows 5m/15m/60m.
- **Funding interval (per symbol):** Binance funding interval varies by contract and may be `1h`, `4h`, or `8h`. Detect per symbol by inspecting gaps in `fundingRate.fundingTime` history and cache the detected interval for ≥24h. Compute `funding_1h` as `funding_interval_rate / interval_hours`, and `Funding Daily Est% = funding_1h × 24`.
- Store last 7–30 days of 1m metrics; archive older to hourly.

### 7.4 REST API (for UI/agents)
- `GET /symbols` → list watchlist and metadata.
- `GET /symbols/available?include_spot=true&verify=true` → list of tradable future symbols with `{ symbol, has_spot }` and optionally `unavailable`.
- `GET /metrics/{symbol}` → latest snapshot:
```json
{
  "symbol":"MYXUSDT",
  "ts": 1736160000000,
  "mark": 1.9164,
  "index": 1.9192,
  "basis_pct": -0.145,
  "basis_twap15_pct": -0.220,
  "funding_interval_hours": 8,
  "funding_1h_pct": -0.0398,
  "funding_daily_est_pct": -7.63,
  "oi_usdt": 4.899e7,
  "delta_oi_1h_usdt": -1.2e6,
  "perp_dominance_pct": 86.3,
  "orderbook_imbalance": 0.76,
  "borrow": {"shortable": false, "venues": []},
  "has_spot": false,
  "srs": 68,
  "traffic_light": "RED",
  "next_funding_in_sec": 2100
}
```
- `GET /timeseries/{symbol}?metric=basis,funding,oi&interval=1m&window=48h` → arrays of `[ts,value]`.
- `GET /rules/{symbol}` → rule state & explanation.
- `POST /alerts` (configure channels & thresholds).

---

## 8) Trading Rules (hard gates)
**NO‑SHORT (Red) if any condition holds:**
1) `funding_1h < 0` AND `basis_twap15 ≤ 0` (**perp discount**).  
2) `perp_dominance ≥ 70%` **and** `oi/usdt_vol24 ≥ 0.25`.  
3) `delta_oi_1h > 0` while **price ↑** in last hour.  
4) **No spot market exists** (`has_spot = false`) or spot short not borrowable/APR > threshold.

**BASIS‑ONLY (Yellow):** funding very negative (≤ −0.15%/h) **but** spot short borrowable with acceptable APR.

**SHORT‑WINDOW (Green):**
- `funding_1h ≥ 0` for ≥ 3 consecutive hours, **and** `basis_twap15 ≥ +0.10%`, **and** `delta_oi_1h ≤ 0`, **and** `perp_dominance < 60%`.

All thresholds configurable per symbol.

---

## 9) SRS – Squeeze Risk Score
Composite 0–100. Higher = more likely to squeeze shorts.
```
Inputs (normalized via z‑score against 30‑day history of the same symbol):
A = |funding_1h|           (weight 0.25)
B = |basis_twap15|         (0.20)
C = perp_dominance         (0.20)
D = max(0, delta_oi_1h)    (0.20)
E = depth_perp/depth_spot  (0.15)

SRS = 100·(0.25·σ(A) + 0.20·σ(B) + 0.20·σ(C) + 0.20·σ(D) + 0.15·σ(E))
```
**Bands:** `≥70 Red`, `40–69 Yellow`, `≤39 Green`.

---

## 10) UI/UX Specification
- **Header:** account/profile (local only), global refresh toggle, theme.
- **Left panel:** watchlist with SRS badges, quick filters (Red/Yellow/Green). 
- **Main grid:** summary tiles. Click opens detail drawer.
- **Detail view:** 4 charts (Price/Index/Basis; Funding; OI; Dominance) + two side cards (Borrowability; Orderbook Imbalance). Show `has_spot` prominently.
- **Explainable rules:** chip list “Why RED?” with exact conditions that fired (e.g., “no spot market available for borrow/hedge”).
- **Performance hints:** show API latency and data freshness per symbol.

---

## 11) Calculations (precise)
- **Basis%** = `(mark − index) / index × 100`.
- **TWAP(w)** of basis: average of per‑minute basis over the last `w` minutes.
- **Funding Daily Est%** = `funding_1h × 24` (display with caveat that it varies by hour).
- **Perp Dominance%** = `fut_vol24 / (fut_vol24 + spot_vol24_agg) × 100` (spot from top N venues, default N=5; if `has_spot=false`, treat `spot_vol24_agg=0`).
- **ΔOI** = `OI_now − OI_{t−window}` (windows: 1h, 4h, 24h using openInterestHist).
- **Orderbook Imbalance** = `Σ bid_qty(≤+2%) / Σ ask_qty(≤+2%)` (perp default).
- **OI/PerpVol** = `OI_usdt / fut_vol24_usdt`.

---

## 12) Technology Choices
- **Backend:** Python 3.11, FastAPI, `httpx`, `pandas`, `pydantic`.  
- **Scheduler/Workers:** RQ/Celery + Redis.  
- **Storage:** TimescaleDB/Postgres for timeseries; Redis for cache.  
- **Frontend:** Next.js/React, TailwindCSS, Recharts or ECharts.  
- **Packaging:** Docker + Compose; `.env` for keys.  
- **Observability:** Prometheus exporters + Grafana dashboards.

**MVP alternative:** Streamlit app (single file) with `requests`, caching, and minimal plots; same calculations.

---

## 13) Security & Compliance
- Only public endpoints by default. If using API keys (e.g., borrow endpoints), store in vault/.env; never log secrets. 
- Rate‑limit outbound API calls; exponential backoff and jitter. 
- Health checks for data freshness; fail‑open UI with explicit stale badges.

---

## 14) Error Handling & Fallbacks
- If an exchange endpoint fails: use last known value (with STALE flag and timestamp). 
- If spot venues are missing: compute dominance using Binance futures only and mark dominance as **unknown**. 
- If borrow APR unknown: mark **N/A** but keep the rule that requires borrowability disabled until confirmed.

---

## 15) Testing & Validation
- **Unit tests** for basis, TWAP, dominance, ΔOI, SRS. 
- **Integration tests** with mocked Binance responses. 
- **Backtest**: re‑compute SRS and rule states on last 7–30 days to inspect precision/recall of *no‑short* vs. drawdowns.

---

## 16) Roadmap (phased)
- **Phase 0 (MVP):** Binance only; Watchlist, Tiles, Detail charts; SRS; Red/Yellow/Green; Telegram alerts. 
- **Phase 1:** Cross‑venue spot volumes & borrowability; Perp‑perp comparisons. 
- **Phase 2:** Backtest module + CSV export; user profiles. 
- **Phase 3:** Advanced alerts (pattern‑based); liquidity cluster estimator.

---

## 17) Acceptance Criteria (MVP)
- Add a symbol and get a live tile within ≤20s. 
- Basis TWAP15, Funding 1h, OI, Dominance, SRS all compute and update automatically. 
- At least one alert channel works end‑to‑end. 
- Red/Yellow/Green changes state when thresholds crossed; explanation chips display exact triggers. 
- Export CSV from last 48h for any symbol.

---

## 18) Prompts for an AI Code‑Gen Agent
**System/Task prompt:**
- "Build a production‑ready FastAPI + Next.js dashboard named `short‑risk‑radar` following the PRD. Implement collectors for Binance Futures endpoints listed in §7.1, sampling per §7.3. Compute metrics and SRS per §11/§9. Serve REST per §7.4. Create a React UI per §10 with tiles and detail charts. Add Dockerfiles and docker‑compose. Include unit tests for all calculations and integration tests with mocked HTTP responses. Provide `.env.example` with config."

**Sub‑tasks:**
1) **Data models** (`pydantic`): Symbol, Snapshot, TimeseriesPoint, BorrowInfo. 
2) **Collector service** (`httpx`): premiumIndex sampler (10s), fundingRate (hourly), OI hist (5m), ticker24h, depth. Persist to TimescaleDB. 
3) **Analytics**: basis, TWAPs, dominance, ΔOI, imbalance, SRS; rule engine; JSON serializers. 
4) **API**: endpoints in §7.4; pagination and time windows. 
5) **Frontend**: watchlist CRUD; tiles; charts; rule badges; settings; alert forms. 
6) **Alerts**: Telegram bot + webhook sender; debounce/cooldown. 
7) **Tests**: fixtures with canned Binance JSON; unit & integration.

---

## 19) Glossary
- **Basis**: perp vs. spot (index) gap. Negative = perp discount. 
- **Funding**: periodic cash transfer between longs and shorts to close perp/spot gap. 
- **Perp dominance**: futures share of total trading volume (perp vs. spot). 
- **OI**: total open contracts notional. 
- **Borrowability**: ability to borrow the token on spot margin to short/hedge.

---

## 20) Disclaimer
This dashboard gives **market intelligence only**. It does not execute trades, and it must not be used to plan or perform market manipulation. Use at your own risk; funding and liquidity can change abruptly, especially for illiquid meme tokens.
