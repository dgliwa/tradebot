# Phase 2: Ingestion Layer (Price + Insider) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-07
**Phase:** 02-ingestion-layer-price-insider
**Areas discussed:** Universe definition, yfinance fetch granularity, EDGAR Form 4 API strategy, Fetcher interface contract

---

## Universe Definition

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded starter list in config | Fixed list of ~20-50 tickers in settings. Simple to start — Phase 3 ranks from this pool. | ✓ |
| Config file (tickers.yaml or similar) | Text/YAML file in the repo, version-controlled, editable without touching code. | |
| DB-driven from universe table | Populate universe_snapshots first, then fetchers read from it. Most flexible but adds bootstrap step. | |

**User's choice:** Hardcoded starter list in config
**Notes:** Simplest approach for MVP. Settings already has a clean singleton pattern from Phase 1 (D-10).

---

## yfinance Fetch Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| 1-year backfill, then delta on subsequent runs | Initial run pulls 1 year. Subsequent runs fetch delta since max(fetched_at). | |
| 2-year backfill, then delta on subsequent runs | More historical data for momentum signal (20/50-day SMA needs ~100 days). | |
| Fixed 90-day window every run (no backfill logic) | Always pull last 90 days. Simpler code, no first-run vs subsequent-run branching. | ✓ |

**User's choice:** Fixed 90-day window every run
**Notes:** Simpler. Persistence layer uses INSERT OR IGNORE so re-fetching existing rows is harmless. 90 days covers 20/50-day SMA lookback needed by Phase 3 signal engine.

---

## EDGAR Form 4 API Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| EFTS full-text search (efts.sec.gov/hits.es) | POST with form type=4, date range, ticker filter. Direct REST, respx-mockable. | ✓ |
| EDGAR Submissions API per CIK | Look up CIK per ticker, fetch recent filings. Reliable but requires ticker→CIK mapping step. | |
| sec-edgar-downloader library | Already in pyproject.toml; handles User-Agent, downloads raw SGML/XML to disk. | |

**User's choice:** EFTS full-text search
**Notes:** Most direct approach. Claude to determine exact EFTS query param for ticker-scoping (`entity` param) by testing against the live API.

---

## Fetcher Interface Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Fetchers write to DB directly; return FetchResult only | Fetcher calls source, writes to raw_prices/raw_insider, returns FetchResult. | |
| Fetchers return List[RawRecord]; caller persists | Separation of concerns. Easier to test — no DB needed for fetch unit tests. | ✓ |
| Fetchers write to DB AND return List[RawRecord] | Both — convenient but slightly redundant. | |

**User's choice:** Fetchers return List[RawRecord]; caller persists
**Notes:** Cleaner separation. Tests only need respx mocks, not a DuckDB instance. A new `tradebot/db/writer.py` module handles persistence.

---

## Claude's Discretion

- Exact EFTS query parameters for ticker-scoped Form 4 search (entity vs ticker param)
- Whether FetchResult is a tuple element or named result type
- Test file layout (per-fetcher or combined)
- Whether writer.py uses INSERT OR IGNORE / ON CONFLICT DO NOTHING

## Deferred Ideas

None — discussion stayed within phase scope.
