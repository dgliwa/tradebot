# Project Research Summary — TradeBot

**Project:** TradeBot
**Domain:** Python algorithmic trading bot — multi-signal, weekly cadence, small capital ($100-500/week), Alpaca execution
**Researched:** 2026-07-07
**Confidence:** MEDIUM

## Executive Summary

TradeBot is a weekly-cadence, signal-driven equity trading bot that combines three academically-backed alpha sources — SEC Form 4 insider purchases, congressional STOCK Act disclosures, and price momentum — with a mandatory human approval gate before any order reaches Alpaca. The research consensus is clear: build a simple functional pipeline (Ingest → Score → Act) using DuckDB for storage, Pandas for signal math, APScheduler for scheduling, and alpaca-py for execution. The system must run in shadow mode for at least 8 weeks before paper trading, and in paper mode for at least 8 more weeks before going live. This cadence is not optional — it is the minimum validation window to confirm data pipelines are clean and signals produce genuine alpha rather than backtest artifacts.

The dominant risk is invisible data quality failure. Look-ahead bias (using congressional transaction dates instead of filing dates, or re-downloading retroactively adjusted prices) and silent pipeline failures (empty API responses that look like quiet weeks) are the two failure modes that destroy apparent alpha without any obvious crash. The architecture must bake in freshness validation at every ingestion step and use `filed_at` timestamps, never `transaction_date`, as signal triggers. A second critical risk is paper/live mode contamination — separate Alpaca accounts with separate API keys, never both keys in the same `.env` file, is the only safe approach.

The recommended MVP is deliberately narrow: yfinance price data + EDGAR Form 4 insider buy signal + composite scorer + shadow P&L tracker. Congressional STOCK Act data should be sourced via Quiver Quantitative's free API (not raw Senate/House XML scraping, which is brittle) and added in Phase 2. Everything else — ML models, options trading, a web dashboard, full backtesting engine — is an anti-feature at this stage. Shipping the shadow pipeline first and collecting forward-test data is worth more than any additional signal or infrastructure sophistication.

## Key Findings

### Recommended Stack

Use `uv` for all Python tooling (replaces pip, venv, and pip-tools). The project targets Python 3.11+ with DuckDB 1.3 as the sole datastore — it is columnar, zero-ops, in-process, and handles millions of rows with no server to manage. HTTP ingestion uses `httpx` + `tenacity` for retry/backoff. The scheduler is APScheduler 3.11.x (pin `<4.0` — the 4.x rewrite has an entirely different API). Alpaca execution uses `alpaca-py` 0.43.5 (the old `alpaca-trade-api` is deprecated). Signal math uses Pandas 2.2 with Copy-on-Write enabled; the data scale (5K rows/week across 50-100 tickers) makes Polars performance gains irrelevant and its ecosystem friction costly. Reports are Jinja2 HTML with Plotly charts embedded via `fig.to_html()`.

**Core technologies:**
- `uv`: project tooling — fastest Python package manager, replaces pip/venv/poetry
- `duckdb 1.3`: storage — columnar, zero-ops, single file, superior to SQLite for time-series scans
- `alpaca-py 0.43.5`: broker execution — official current SDK; paper and live via the same interface
- `httpx + tenacity`: data ingestion — async-capable HTTP with declarative retry/backoff
- `pandas 2.2` + `pandas-ta`: signal math — ecosystem integration with yfinance/fredapi outweighs Polars speed
- `apscheduler 3.11`: scheduling — no message broker required; cron-like with Python market-calendar awareness
- `pydantic-settings`: config/secrets — typed env var loading with `.env` file support
- `loguru`: logging — zero-config structured JSON logging
- `jinja2 + plotly`: reporting — HTML reports with embedded interactive charts
- `pytest + freezegun + respx + hypothesis`: testing — time-travel, HTTP mocking, property-based tests

### Expected Features

**Must have (table stakes):**
- Price data pipeline (yfinance weekly OHLCV, stored immutably with `fetched_at` timestamp)
- SEC EDGAR Form 4 ingestion (code P purchases only — filter at query time, not ingestion time)
- Price momentum signal (12-1 momentum: 12-month return excluding most recent month)
- Insider buy signal (open-market purchases weighted by officer rank)
- Composite scorer (weighted combination: 0.4 insider + 0.3 congressional + 0.3 momentum)
- Shadow P&L tracker (hypothetical trades vs SPY, with win rate and drawdown tracking)
- Weekly report (macro status, ranked universe, proposed trades, open positions, portfolio stats)
- Human approval gate (timeout = skip, never auto-approve; approval.yaml or CLI)
- Macro regime filter (yield curve + VIX as a position-size gate, not a ranking signal)

**Should have (competitive / Phase 2):**
- Congressional STOCK Act signal via Quiver Quantitative free API
- FRED macroeconomic series ingestion (T10Y2Y, VIXCLS, UNRATE, CPIAUCSL)
- Alpaca paper trading integration with fill confirmation polling
- Email/notification delivery of weekly report
- Stop-loss auto-execution at 8% below entry (the one automated action that does not need manual approval)
- Wash sale rule flagging in weekly report

**Defer (v2+):**
- Raw Senate eFD XML/PDF parsing (brittle; Quiver Quantitative is faster)
- Options trading (different risk profile, margin requirements, complex P&L accounting)
- ML signal enhancement (insufficient training data at this scale; overfitting risk)
- Tax-lot optimization (marginal at $500/week)
- Web UI / dashboard (a weekly HTML report is sufficient)
- Full backtesting engine (shadow mode forward-testing replaces this)
- Kelly position sizing (use flat 2-4% fractional until 30+ completed round trips)

### Architecture Approach

Three hard architectural layers — Ingest, Score, Act — connected by the database (DuckDB), not by in-memory objects or message queues. Each layer is independently runnable. The weekly entry point is a plain Python script (`run_weekly.py`) that calls each layer in sequence. No async, no ORM, no dependency injection, no microservices. Fetchers return normalized Python dataclasses; the raw tables are the seam between ingestion and signals; `Recommendation` objects are the seam between signals and execution. Everything that crosses a layer boundary uses a typed dataclass, not a dict.

**Major components:**
1. **Ingestion Layer** (`fetchers/congress.py`, `edgar.py`, `fred.py`, `prices.py`) — fetch, normalize, deduplicate, store raw records; each fetcher returns `list[RawRecord]` and writes nothing itself
2. **Signal Layer** (`signals/congress.py`, `insider.py`, `macro.py`, `momentum.py`, `combiner.py`) — reads raw tables, computes per-ticker signal values, produces ranked `Recommendation` objects
3. **Execution Layer** (`report.py`, `gate.py`, `router.py`, `tracker.py`) — renders report, collects human approval, submits approved orders to Alpaca, polls for fills, tracks P&L vs SPY
4. **Config** (`config.py`) — single `TradingMode` enum (`PAPER` / `LIVE`) selected by env var; same code runs both modes; separate Alpaca accounts enforced by separate API keys

### Top Pitfalls

1. **Look-ahead bias on filing dates** — Store `filed_at` (when you learned about it) separately from `transaction_date` (when the trade happened). Congressional filings can be 45 days late; insider filings can be 2 days late. Signal trigger must use `filed_at` only. Write an explicit unit test asserting `signal.latest_price_date <= signal.computation_date - timedelta(days=1)`. Detection: shadow P&L that looks suspiciously smooth.

2. **Silent data pipeline failures** — Every fetcher must return a `row_count` and `freshness_date`. Alert if `row_count == 0` for any source that had results last run. Hard rule: if any critical source returns zero rows, skip trade generation entirely. Detection: same tickers appearing in recommendations week after week with no variation.

3. **Paper/live mode contamination** — Use separate Alpaca accounts with separate API keys stored in separate env files (`.env.paper` and `.env.live`). Print active mode prominently at startup. Include mode in the report header. Detection: account balance changes you did not intend.

4. **Form 4 transaction code conflation** — Only code P (open-market purchase) is a buy signal. Code M (option exercise), A (award), G (gift), S (sale) have different or opposite implications. Filter to code P at query time, not at ingestion time (keep raw code in DB for auditability). Detection: insider signal firing for many tickers every week — true open-market purchases are rare.

5. **APScheduler 4.x API break** — Pin `apscheduler>=3.11,<4.0`. The 4.x rewrite is async-first with a completely different API; `BackgroundScheduler` and `CronTrigger` do not exist in 4.x. Also: scheduler must skip market holidays by checking `pandas-market-calendars` inside the job function, not in the trigger.

## Implications for Roadmap

### Phase 1: Data Foundation + Schema
**Rationale:** Everything else depends on the DB schema and models. Build this wrong and you rewrite it twice. Define it once with the instruments table options-aware from day one.
**Delivers:** DuckDB schema (`raw_disclosures`, `raw_prices`, `raw_macro`, `signals`, `recommendations`, `orders`, `trades`, `pnl_snapshots`, `universe_snapshots`), typed dataclasses for all cross-layer objects, DB init with idempotent DDL, seed with one week of historical data.
**Addresses:** Storage foundation for all signals and execution.
**Avoids:** Conflating orders and trades (separate tables from day one); survivorship bias (universe_snapshots table).

### Phase 2: Ingestion Layer (Price + Insider)
**Rationale:** Price data and EDGAR Form 4 are the two highest-confidence, lowest-friction data sources. Start with them to validate the ingestion pattern before tackling congressional data (which requires either brittle HTML/PDF parsing or a third-party API dependency).
**Delivers:** `prices.py` (yfinance weekly OHLCV, immutable storage), `edgar.py` (Form 4 code P purchase filter, EDGAR User-Agent header, deduplication), `ingest_runner.py` with freshness validation and zero-row alerting.
**Avoids:** EDGAR IP ban (User-Agent from day one); adjusted price inconsistency (immutable storage with `fetched_at`); silent failures (freshness validation).

### Phase 3: Signal Layer + Shadow Pipeline
**Rationale:** With two data sources working, build the minimum viable signal pipeline to start collecting forward-test data. The 8-week shadow minimum means you want this running as early as possible.
**Delivers:** `momentum.py` (12-1 momentum signal), `insider.py` (Form 4 code P signal with officer weighting), `combiner.py` (weighted scorer), `run_weekly.py` (ingest → score, no execution), shadow P&L tracker, basic text/Markdown weekly report.
**Uses:** Pandas 2.2, pandas-ta, DuckDB, APScheduler 3.11 with market-calendar holiday check.
**Avoids:** Look-ahead bias (signal computation timestamp, next-open entry price); universe survivorship bias (weekly universe snapshot).

### Phase 4: Report + Approval Gate
**Rationale:** The approval gate is non-negotiable safety infrastructure. It must be solid before any real order paths exist. Build the full report and gate before adding Alpaca.
**Delivers:** Jinja2 HTML report (macro status, ranked universe table, proposed trades, open positions, portfolio stats vs SPY), CLI approval gate (timeout = skip, approval.yaml), email/notification delivery.
**Avoids:** Auto-approval timeout (timeout must skip, not approve); report must display active mode prominently.

### Phase 5: Congressional Signal + FRED Macro
**Rationale:** Third signal and macro filter complete the composite model. Congressional data via Quiver Quantitative free API is significantly faster than raw scraping. FRED macro adds the position-size gate.
**Delivers:** `congress.py` signal (Quiver Quantitative API integration, filing date triggers), `fred.py` ingestion (T10Y2Y, VIXCLS, UNRATE, CPIAUCSL with `realtime_start` vintage parameter), `macro.py` regime filter (yield curve + VIX gate on position sizing), updated composite scorer weights.
**Avoids:** Filing date vs transaction date confusion; FRED vintage data look-ahead (use `realtime_start`).

### Phase 6: Alpaca Paper Trading Integration
**Rationale:** Paper trading via Alpaca is the validation step between shadow mode and live capital. Requires clean signals and approval gate working reliably for 8+ weeks first.
**Delivers:** `router.py` (Alpaca paper mode, order submission, fill confirmation polling), `tracker.py` (P&L vs SPY, stop-loss auto-execution at 8% below entry), wash sale flagging in report, Alpaca paper account integration.
**Avoids:** Paper/live contamination (separate accounts, separate env files, mode printed at startup); conflating order submission with fill confirmation (separate `orders` and `trades` tables).

### Phase 7: Live Trading
**Rationale:** Flip `TRADEBOT_MODE=live` only after 8+ weeks paper with positive alpha, <15% drawdown, 100% gate reliability. Position sizes at 50% for first 4 live weeks.
**Delivers:** Live Alpaca execution with all safety checks from prior phases intact. Flat fractional position sizing (2-4% of account); no Kelly until 30+ completed round trips.
**Avoids:** Kelly oversizing on insufficient data; wash sale violations in live tax reporting.

### Phase Ordering Rationale

- Schema must precede ingestion (storage contract defines everything downstream).
- Ingestion must precede signals (signals read from raw tables).
- Shadow mode must run 8+ weeks before paper trading — build it in Phase 3, not Phase 6.
- Approval gate must be built and verified before any order submission path exists.
- Congressional signal deferred to Phase 5 because raw Senate/House parsing is the hardest ingestion problem; Quiver Quantitative shortcut makes it tractable but still requires API integration work.
- Macro filter is a gate, not a ranking signal — it can be added after the core momentum + insider signals are working.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 5 (Congressional + FRED):** Quiver Quantitative API rate limits and free tier field coverage need validation. FRED `realtime_start` parameter behavior for specific series needs testing.
- **Phase 6 (Alpaca Paper):** Alpaca paper trading fill simulation fidelity vs real market differs; pre-market fills, partial fills, and order rejection behavior need documented testing.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Schema):** DuckDB DDL patterns are well-documented; schema design follows ARCHITECTURE.md directly.
- **Phase 2 (Ingestion):** yfinance and EDGAR patterns are well-documented in STACK.md with specific code examples.
- **Phase 3 (Signals):** Momentum and insider signal formulas are academically established; implementation is Pandas math.
- **Phase 4 (Report + Gate):** Jinja2 + Plotly HTML report is standard; approval gate is a simple file read.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI version data confirmed live 2026-07-07; alpaca-py source inspected directly |
| Features | MEDIUM | Signal existence and alpha evidence based on academic literature through Aug 2025; forward edge level uncertain post-STOCK Act |
| Architecture | MEDIUM | Well-established trading system patterns; DuckDB vs SQLite recommendation is solid; layer boundaries are conventional |
| Pitfalls | HIGH (structural/code); MEDIUM (signal) | Look-ahead bias, pipeline failures, mode contamination are mechanical; alpha decay rates are empirical estimates |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Congressional signal edge magnitude post-2025:** The academic literature documents the STOCK Act signal through ~2018. Whether the edge has further narrowed is unknown. Forward testing is the only resolution.
- **Quiver Quantitative free tier coverage:** Rate limits, field availability, and data freshness lag for the free tier need validation before committing to it as the congressional data source.
- **FRED vintage data for specific series:** Not all FRED series support `realtime_start` equally. Test T10Y2Y and VIXCLS for vintage data availability before building the macro signal.
- **Shadow mode promotion thresholds:** The 8-week / 10 round-trip / 40% win-rate / <15% drawdown criteria are practitioner norms. Treat as starting points, adjust based on risk tolerance.
- **Alpaca paper fill simulation accuracy:** Paper trading fills may differ from live in ways that affect signal evaluation. Document known differences before using paper P&L as the live promotion gate.

## Sources

### Research Files (canonical)
- `.planning/research/STACK.md` — stack recommendations, version pins, library rationale
- `.planning/research/FEATURES.md` — table stakes, differentiators, anti-features, shadow mode transition criteria
- `.planning/research/ARCHITECTURE.md` — component model, schema, build order, abstraction guidelines
- `.planning/research/PITFALLS.md` — critical/moderate/minor pitfalls with prevention strategies

### Academic (HIGH confidence)
- Ziobrowski et al. (2004, 2011) — Congressional trading abnormal returns
- Lakonishok & Lee (2001) — Insider buy signal quality; transaction code specificity
- Jeng, Metrick & Zeckhauser (2003) — Form 4 insider trading returns
- Jegadeesh & Titman (1993) + Carhart (1997) — Momentum factor replication

### Official Documentation (HIGH confidence)
- alpaca-py 0.43.5 source: `alpaca/trading/client.py` — options support and paper/live endpoint confirmed
- SEC EDGAR EFTS API — User-Agent requirement, rate limits, `efts.sec.gov`
- FRED API — `realtime_start` vintage data parameters, `fred.stlouisfed.org/docs/api`
- Alpaca Markets API — paper vs live account isolation, `docs.alpaca.markets`

### Secondary (MEDIUM confidence)
- yfinance 1.5.1 METADATA — `curl_cffi>=0.15` dependency confirming 1.x anti-scraping rewrite
- APScheduler changelog — 3.x stable, 4.x async-only rewrite API break confirmed
- Karadas (2018) — Congressional trading post-STOCK Act edge persistence
- Quiver Quantitative — congressional trading data aggregator (free tier availability)

---
*Research completed: 2026-07-07*
*Ready for roadmap: yes*
