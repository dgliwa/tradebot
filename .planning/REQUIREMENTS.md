# Requirements — TradeBot

## v1 Requirements

### Data Foundation

- [x] **DATA-01**: System stores all raw and processed data in DuckDB with a schema that separates raw ingestion tables from scored signal tables from execution tables
- [x] **DATA-02**: Every raw data fetch records a `fetched_at` timestamp alongside the data; historical rows are never overwritten on re-fetch
- [x] **DATA-03**: Every fetcher returns a result that includes `row_count` and `freshness_date`; the pipeline blocks trade generation if either is invalid
- [x] **DATA-04**: All disclosures store both `transaction_date` (when the trade occurred) and `filed_at` (when the filing became public); signals use `filed_at` exclusively
- [x] **DATA-05**: The instrument schema supports stocks, calls, and puts from day one (`instrument_type`, `expiry`, `strike` fields — NULL for stocks)
- [x] **DATA-06**: A weekly `universe_snapshots` table records which tickers were in scope for each run, preventing survivorship bias in retrospective analysis

### Data Ingestion

- [ ] **INGEST-01**: System fetches daily OHLCV price data for universe tickers via yfinance and stores it immutably
- [ ] **INGEST-02**: System fetches SEC EDGAR Form 4 filings via EFTS API, includes the required User-Agent header, filters to transaction code P (open-market purchase) only, and stores raw filings
- [ ] **INGEST-03**: System fetches Congressional trading disclosures via Quiver Quantitative free API (not raw Senate scraping) and stores raw disclosures
- [ ] **INGEST-04**: System fetches FRED macro indicators (federal funds rate, yield curve) and stores with vintage date for look-ahead protection
- [ ] **INGEST-05**: Each ingestion module is independently testable with mocked HTTP responses (respx); no live network calls in tests

### Signal Engine

- [ ] **SIGNAL-01**: System computes a momentum signal per ticker based on price data (20-day and 50-day SMA crossover, RSI)
- [ ] **SIGNAL-02**: System computes an insider signal per ticker based on Form 4 code-P purchases (signal date = `filed_at`, not `transaction_date`)
- [ ] **SIGNAL-03**: System computes a congressional signal per ticker based on Quiver Quantitative disclosures (signal date = `filed_at`)
- [ ] **SIGNAL-04**: System computes a macro regime flag from FRED data (e.g., inverted yield curve = risk-off) that can suppress or dampen other signals
- [ ] **SIGNAL-05**: System produces a composite score per ticker as a weighted blend of active signals (insider 0.4, congressional 0.3, momentum 0.3)
- [ ] **SIGNAL-06**: System ranks tickers by composite score and selects top N candidates for the weekly report

### Shadow Mode & P&L Tracking

- [ ] **SHADOW-01**: System maintains a shadow portfolio that tracks hypothetical positions entered at the open after each weekly signal run
- [ ] **SHADOW-02**: System tracks shadow P&L per position and in aggregate, using actual market prices (not signal prices) for current valuation
- [ ] **SHADOW-03**: System maintains a SPY benchmark position started at the same time as the first shadow trade, for direct performance comparison
- [ ] **SHADOW-04**: Each weekly report shows shadow cumulative return vs SPY cumulative return over the same period

### Report Generation

- [ ] **REPORT-01**: System generates a weekly HTML report via Jinja2 containing: top ranked tickers with signal breakdown, shadow P&L vs SPY, data quality status per source, and any warning flags (wash sale, stale data, market holiday)
- [ ] **REPORT-02**: Report displays the active mode (PAPER / LIVE) prominently at the top
- [ ] **REPORT-03**: Report includes a cost/tax estimate per recommended trade: estimated commission ($0 Alpaca), spread cost estimate, and whether the position is approaching long-term capital gains treatment (365 days)
- [ ] **REPORT-04**: Report flags any proposed trade that would trigger a wash sale (sale at loss within prior 30 days on same ticker)

### Approval Gate & Execution

- [ ] **EXEC-01**: System presents recommended trades via a CLI confirmation prompt before submitting any order; timeout results in skip, never auto-approval
- [ ] **EXEC-02**: System integrates with Alpaca API for order submission; paper vs live mode is controlled by a single environment variable (`TRADEBOT_MODE`) backed by separate API keys in separate env files
- [ ] **EXEC-03**: System maintains separate `orders` (intent) and `trades` (confirmed fills) tables; P&L is computed only from confirmed fills
- [ ] **EXEC-04**: System polls Alpaca for fill confirmations and records actual fill price, not assumed fill price
- [ ] **EXEC-05**: System uses flat fractional position sizing (3% of account per position) for the first 6 months; Kelly criterion is computed and logged for monitoring only, not for actual sizing

### Scheduler & Reliability

- [ ] **SCHED-01**: System runs the full pipeline on a weekly schedule via APScheduler 3.11 (pinned to `>=3.11,<4.0`)
- [ ] **SCHED-02**: Before running any pipeline logic, the scheduler checks whether the target week has valid market days using `pandas-market-calendars`; if not, it logs and skips without error
- [ ] **SCHED-03**: All scheduled runs produce a structured log entry recording: sources fetched, row counts, freshness dates, signals computed, recommendations generated, and whether a trade was approved or skipped

### Stop-Loss

- [ ] **RISK-01**: System monitors open positions and automatically submits a stop-loss order (no manual gate) when a position declines more than 8% from entry; this is the only automated order path

## v2 Requirements (Deferred)

- Backtesting engine against historical signal data
- Options execution (calls/puts) — architecture supports it; execution deferred until signals are validated
- Kelly position sizing — after 30+ completed round trips
- Multi-asset class support (ETFs alongside individual stocks)
- Web dashboard (v1 uses CLI + HTML report opened locally)
- Email/push notification delivery of weekly report
- Portfolio-level risk management (correlation, sector concentration)
- Shorting / inverse positions

## Out of Scope

- Paid data sources (Polygon.io, Bloomberg, Refinitiv) — cost eats into alpha; all v1 signals use free public data
- Fully autonomous execution without manual confirmation — too risky at early stage
- High-frequency or intraday trading — not viable at $100-500/week and weekly cadence
- Raw Senate HTML/PDF disclosure parsing — Quiver Quantitative API handles this more reliably
- Backtesting as a primary validation method — forward shadow mode is the primary validation approach
- Social sentiment signals (Twitter, Reddit) — not grounded in the academic alpha sources the project targets

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| DATA-01 | Phase 1: Data Foundation | Complete |
| DATA-02 | Phase 1: Data Foundation | Complete |
| DATA-03 | Phase 1: Data Foundation | Complete |
| DATA-04 | Phase 1: Data Foundation | Complete |
| DATA-05 | Phase 1: Data Foundation | Complete |
| DATA-06 | Phase 1: Data Foundation | Complete |
| INGEST-01 | Phase 2: Ingestion Layer (Price + Insider) | Pending |
| INGEST-02 | Phase 2: Ingestion Layer (Price + Insider) | Pending |
| INGEST-05 | Phase 2: Ingestion Layer (Price + Insider) | Pending |
| SIGNAL-01 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SIGNAL-02 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SIGNAL-05 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SIGNAL-06 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SHADOW-01 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SHADOW-02 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SHADOW-03 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SHADOW-04 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SCHED-01 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| SCHED-02 | Phase 3: Signal Engine + Shadow Pipeline | Pending |
| REPORT-01 | Phase 4: Report + Approval Gate | Pending |
| REPORT-02 | Phase 4: Report + Approval Gate | Pending |
| REPORT-03 | Phase 4: Report + Approval Gate | Pending |
| REPORT-04 | Phase 4: Report + Approval Gate | Pending |
| EXEC-01 | Phase 4: Report + Approval Gate | Pending |
| INGEST-03 | Phase 5: Congressional Signal + FRED Macro | Pending |
| INGEST-04 | Phase 5: Congressional Signal + FRED Macro | Pending |
| SIGNAL-03 | Phase 5: Congressional Signal + FRED Macro | Pending |
| SIGNAL-04 | Phase 5: Congressional Signal + FRED Macro | Pending |
| EXEC-02 | Phase 6: Alpaca Paper Execution | Pending |
| EXEC-03 | Phase 6: Alpaca Paper Execution | Pending |
| EXEC-04 | Phase 6: Alpaca Paper Execution | Pending |
| EXEC-05 | Phase 6: Alpaca Paper Execution | Pending |
| SCHED-03 | Phase 6: Alpaca Paper Execution | Pending |
| RISK-01 | Phase 6: Alpaca Paper Execution | Pending |
