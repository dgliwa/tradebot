# Roadmap: TradeBot

## Overview

TradeBot is built in seven vertical slices, each delivering a runnable, verifiable increment. The pipeline flows Ingest → Score → Act, connected by DuckDB. Shadow mode starts in Phase 3 and must accumulate 8+ weeks of forward-test data before paper trading is enabled in Phase 6. Every phase leaves the system in a working state; no phase is a horizontal layer that only pays off later.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Foundation** - DuckDB schema, typed dataclasses, options-aware instrument table, idempotent DDL
- [ ] **Phase 2: Ingestion Layer (Price + Insider)** - yfinance OHLCV and EDGAR Form 4 fetchers with freshness validation
- [ ] **Phase 3: Signal Engine + Shadow Pipeline** - Momentum + insider signals, composite scorer, shadow P&L tracker, weekly runner
- [ ] **Phase 4: Report + Approval Gate** - Jinja2 HTML report with Plotly charts, CLI approval gate (timeout = skip)
- [ ] **Phase 5: Congressional Signal + FRED Macro** - Quiver Quantitative congressional signal, FRED macro regime filter, updated composite weights
- [ ] **Phase 6: Alpaca Paper Execution** - Alpaca paper trading integration, fill polling, stop-loss auto-execution, structured run logs
- [ ] **Phase 7: Live Trading Promotion** - Mode flip to live, safety validation checklist, position sizing confirmation

## Phase Details

### Phase 1: Data Foundation
**Goal**: The DuckDB schema exists, is options-aware from day one, and the ingestion-signal-execution contract is defined in typed dataclasses so every downstream phase builds on a stable foundation
**Mode**: mvp
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Success Criteria** (what must be TRUE):
  1. Running `python -c "from tradebot.db import init_db; init_db()"` creates all tables idempotently with no errors on a fresh DuckDB file
  2. The `instruments` table has `instrument_type`, `expiry`, and `strike` columns that accept NULL for stocks and non-NULL for options
  3. The `universe_snapshots` table records which tickers were in scope for a given run date, queryable by week
  4. All cross-layer dataclasses (`RawRecord`, `Recommendation`, `Order`, `Trade`) are importable and have typed fields with no dict passing at layer boundaries
  5. Re-running `init_db()` on an existing database produces no duplicate tables and no data loss (idempotent DDL)
**Plans**: 4 (01-PLAN.md — 3 waves, 18 tasks; checker: PASS)

### Phase 2: Ingestion Layer (Price + Insider)
**Goal**: Price data (yfinance OHLCV) and insider data (EDGAR Form 4 code-P purchases) are fetched, validated, and stored immutably — and any zero-row or stale response blocks the pipeline
**Mode**: mvp
**Depends on**: Phase 1
**Requirements**: INGEST-01, INGEST-02, INGEST-05
**Success Criteria** (what must be TRUE):
  1. Running the price fetcher for a list of tickers stores OHLCV rows in the `raw_prices` table with a `fetched_at` timestamp; re-running adds new rows without overwriting existing ones
  2. Running the EDGAR fetcher stores only code-P (open-market purchase) Form 4 filings, with both `transaction_date` and `filed_at` populated; the raw filing code is preserved for auditability
  3. If either fetcher returns zero rows, the pipeline prints an alert and returns a result with `row_count=0` and an invalid `freshness_date` that downstream code can inspect to block trade generation
  4. All fetchers pass their test suite using mocked HTTP responses (respx) with no live network calls required
  5. The EDGAR fetcher sends the required `User-Agent` header on every request
**Plans**: TBD

### Phase 3: Signal Engine + Shadow Pipeline
**Goal**: The weekly runner executes end-to-end (ingest → score → shadow update) producing a ranked ticker list and shadow portfolio update — the shadow clock starts ticking on first successful run
**Mode**: mvp
**Depends on**: Phase 2
**Requirements**: SIGNAL-01, SIGNAL-02, SIGNAL-05, SIGNAL-06, SHADOW-01, SHADOW-02, SHADOW-03, SHADOW-04, SCHED-01, SCHED-02
**Success Criteria** (what must be TRUE):
  1. Running `python run_weekly.py` completes without error and writes a new row to `universe_snapshots` and new rows to the `signals` and `recommendations` tables
  2. The momentum signal (20-day/50-day SMA crossover + RSI) and insider signal (Form 4 code-P, signal date = `filed_at`) each produce per-ticker scores visible in the database
  3. The composite scorer produces a ranked list of top-N tickers using weights insider=0.4, momentum=0.3 (congressional slot placeholder weight=0.3 initially absorbed by the two active signals)
  4. Shadow portfolio updates after each run: hypothetical positions are entered at next-open price, P&L is tracked using actual market prices, and a SPY benchmark position is maintained from the first shadow trade date
  5. APScheduler runs the weekly job on a cron schedule and skips without error when no valid market days exist in the target week (verified via `pandas-market-calendars`)
**Plans**: TBD

### Phase 4: Report + Approval Gate
**Goal**: Every weekly run produces a Jinja2 HTML report the user can open in a browser, and no order can be submitted without explicit CLI approval — timeout always means skip
**Mode**: mvp
**Depends on**: Phase 3
**Requirements**: REPORT-01, REPORT-02, REPORT-03, REPORT-04, EXEC-01
**Success Criteria** (what must be TRUE):
  1. Opening the generated HTML report in a browser shows: ranked tickers with signal breakdown, shadow P&L vs SPY cumulative return, data quality status per source, and any active warning flags
  2. The report header prominently displays the active mode (PAPER / LIVE) — this is visually distinct and cannot be missed
  3. The report shows a per-trade cost/tax estimate: estimated commission ($0 Alpaca), spread cost estimate, and whether each position is approaching 365-day long-term capital gains treatment
  4. Any proposed trade on a ticker sold at a loss within the prior 30 days is flagged with a wash sale warning in the report
  5. The CLI approval gate presents each recommended trade and waits for explicit yes/no input; if the timeout elapses with no response, the trade is skipped — never auto-approved
**Plans**: TBD

### Phase 5: Congressional Signal + FRED Macro
**Goal**: The composite model is complete — congressional STOCK Act disclosures (via Quiver Quantitative) and FRED macro regime data are ingested and incorporated into signal scoring, with the yield-curve gate able to suppress sizing
**Mode**: mvp
**Depends on**: Phase 4
**Requirements**: INGEST-03, INGEST-04, SIGNAL-03, SIGNAL-04
**Success Criteria** (what must be TRUE):
  1. The congressional fetcher retrieves disclosures from the Quiver Quantitative free API, stores them with `filed_at` as the signal trigger date (not `transaction_date`), and passes its test suite with mocked HTTP responses
  2. FRED macro indicators (T10Y2Y, VIXCLS, UNRATE, CPIAUCSL) are fetched with `realtime_start` vintage date to prevent look-ahead bias and stored with their vintage date in `raw_macro`
  3. The macro regime flag (inverted yield curve = risk-off) is computed and visible in the weekly report's macro status section; it can suppress or dampen other signals but does not rank tickers independently
  4. The composite scorer applies the full three-signal weights (insider=0.4, congressional=0.3, momentum=0.3) and the weekly report shows all three signal contributions per ticker
**Plans**: TBD

### Phase 6: Alpaca Paper Execution
**Goal**: Approved trades are submitted to Alpaca paper trading, fills are confirmed by polling, stop-losses fire automatically at 8% below entry, and every run produces a structured audit log
**Mode**: mvp
**Depends on**: Phase 5
**Requirements**: EXEC-02, EXEC-03, EXEC-04, EXEC-05, SCHED-03, RISK-01
**Success Criteria** (what must be TRUE):
  1. After CLI approval, the system submits a fractional-share order to Alpaca paper trading using `alpaca-py`; the active mode (PAPER vs LIVE) is printed at startup and controlled by `TRADEBOT_MODE` environment variable backed by separate `.env.paper` and `.env.live` files
  2. The system polls Alpaca for fill confirmation and records actual fill price (not assumed price) in the `trades` table; the `orders` table records intent separately from the `trades` table, which records confirmed fills only
  3. Position sizing uses flat 3% of account per position for all trades; Kelly criterion is computed and written to the log for monitoring but does not affect actual order size
  4. The system monitors open positions and automatically submits a stop-loss order (no manual gate required) when a position declines more than 8% from entry price
  5. Every scheduled run produces a structured log entry recording: sources fetched, row counts, freshness dates, signals computed, recommendations generated, and whether each trade was approved, skipped, or stop-loss triggered
**Plans**: TBD

### Phase 7: Live Trading Promotion
**Goal**: The system is promoted to live capital execution by flipping `TRADEBOT_MODE=live` after verifying 8+ weeks of paper trading with positive alpha, acceptable drawdown, and 100% gate reliability
**Mode**: mvp
**Depends on**: Phase 6
**Requirements**: (no new v1 requirements — this phase delivers operational promotion of all prior requirements to live execution)
**Success Criteria** (what must be TRUE):
  1. A pre-promotion checklist confirms: 8+ weeks of paper trading completed, cumulative shadow/paper return exceeds SPY over the same period, max drawdown is below 15%, and the approval gate has never auto-approved a trade
  2. Running with `TRADEBOT_MODE=live` loads keys from `.env.live` only; the system prints "LIVE MODE" prominently at startup and the HTML report header reflects LIVE in a visually distinct color
  3. The first 4 weeks of live trading use 50% of normal position size (1.5% of account instead of 3%); this is enforced in code, not just documented
  4. All safety mechanisms from prior phases (stop-loss auto-execution, wash sale flagging, timeout-skip gate, structured audit logs) remain active and are verified by a smoke-test run before any live order is submitted
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 0/TBD | Not started | - |
| 2. Ingestion Layer (Price + Insider) | 0/TBD | Not started | - |
| 3. Signal Engine + Shadow Pipeline | 0/TBD | Not started | - |
| 4. Report + Approval Gate | 0/TBD | Not started | - |
| 5. Congressional Signal + FRED Macro | 0/TBD | Not started | - |
| 6. Alpaca Paper Execution | 0/TBD | Not started | - |
| 7. Live Trading Promotion | 0/TBD | Not started | - |
