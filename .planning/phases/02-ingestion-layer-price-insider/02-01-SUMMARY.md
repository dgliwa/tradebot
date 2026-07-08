---
phase: 02-ingestion-layer-price-insider
plan: "01"
subsystem: ingestion
tags: [fetchers, yfinance, edgar, duckdb, writer, price, insider]
status: complete

dependency_graph:
  requires:
    - 01-data-foundation (RawRecord, FetchResult models, DuckDB schema, conftest db fixture)
  provides:
    - tradebot/fetchers/price.py (fetch_prices)
    - tradebot/fetchers/insider.py (fetch_insider)
    - tradebot/db/writer.py (write_raw_records)
    - Settings.universe field
  affects:
    - Phase 3 signal computation (reads from raw_prices and raw_insider)

tech_stack:
  added:
    - httpx 0.28.1 (HTTP client for EDGAR requests)
    - tenacity 9.1.4 (retry with exponential backoff on 429/500/503)
    - yfinance 1.5.1 (OHLCV price data, mocked in tests)
    - respx 0.23.1 (httpx mock fixture for insider tests)
    - hypothesis 6.156.3 (property-based tests for _price_id)
  patterns:
    - Fetchers return (list[RawRecord], FetchResult) — pure fetch+parse, no DB access
    - writer.py uses DuckDB ON CONFLICT DO NOTHING for idempotent append semantics
    - Deterministic BIGINT PK (_price_id) from SHA-256(ticker:date) masked to signed 64-bit range
    - respx_mock auto-registered pytest fixture intercepts all httpx traffic in tests
    - monkeypatch replaces yf.download in price tests — zero live network calls

key_files:
  created:
    - tradebot/fetchers/price.py
    - tradebot/fetchers/insider.py
    - tradebot/db/writer.py
    - tests/fetchers/__init__.py
    - tests/fetchers/test_price.py
    - tests/fetchers/test_insider.py
    - tests/test_db/test_writer.py
  modified:
    - pyproject.toml (added httpx, tenacity, yfinance runtime deps; respx, hypothesis dev deps)
    - tradebot/config.py (added Settings.universe field with TRADEBOT_UNIVERSE env override)

decisions:
  - Used direct EDGAR HTTP (company_tickers.json -> submissions JSON -> form4.xml) instead of sec-edgar-downloader library for full respx mockability
  - yfinance group_by="ticker" produces MultiIndex DataFrame; df[ticker] extraction works for both single and multi-ticker calls
  - writer.py returns len(rows) as attempted count, not actual inserted count (DuckDB executemany does not expose per-row insert count when conflicts are skipped)
  - _price_id uses first 16 hex chars of SHA-256 masked to 0x7FFF_FFFF_FFFF_FFFF for positive signed BIGINT range
  - raw_insider PK is "accession:transaction_index" string — globally unique per SEC accession number + within-filing row index
  - time.sleep(0.12) between EDGAR requests to stay under SEC's 10 req/s rate limit

metrics:
  duration: ~15 minutes
  completed: 2026-07-08
  tasks_completed: 7
  files_created: 7
  files_modified: 2
---

# Phase 2 Plan 01: Ingestion Layer (Price + Insider) Summary

**One-liner:** yfinance OHLCV + EDGAR Form 4 code-P fetchers with DuckDB ON CONFLICT DO NOTHING writer and full mock test coverage.

## Tasks Completed

| Task | Name | Status |
|------|------|--------|
| P01 | Add runtime deps and Settings.universe | Done |
| P02 | Implement tradebot/fetchers/price.py | Done |
| P03 | Implement tradebot/fetchers/insider.py | Done |
| P04 | Implement tradebot/db/writer.py | Done |
| P05 | Write tests/fetchers/test_price.py | Done |
| P06 | Write tests/fetchers/test_insider.py | Done |
| P07 | Write tests/test_db/test_writer.py | Done |

## Files Created / Modified

**Created:**
- `/Users/derekgliwa/dev/tradebot/tradebot/fetchers/price.py` — fetch_prices(universe) using yfinance MultiIndex DataFrame
- `/Users/derekgliwa/dev/tradebot/tradebot/fetchers/insider.py` — fetch_insider(universe) using three-step EDGAR HTTP
- `/Users/derekgliwa/dev/tradebot/tradebot/db/writer.py` — write_raw_records(conn, table, records) with idempotent DuckDB inserts
- `/Users/derekgliwa/dev/tradebot/tests/fetchers/__init__.py` — empty file for pytest discovery
- `/Users/derekgliwa/dev/tradebot/tests/fetchers/test_price.py` — 5 tests, monkeypatch yf.download
- `/Users/derekgliwa/dev/tradebot/tests/fetchers/test_insider.py` — 6 tests, respx_mock for httpx
- `/Users/derekgliwa/dev/tradebot/tests/test_db/test_writer.py` — 9 tests including hypothesis property tests

**Modified:**
- `/Users/derekgliwa/dev/tradebot/pyproject.toml` — added httpx, tenacity, yfinance to runtime deps; respx, hypothesis to dev deps
- `/Users/derekgliwa/dev/tradebot/tradebot/config.py` — added Settings.universe field with TRADEBOT_UNIVERSE env var override

## Key Implementation Decisions

1. **EDGAR HTTP approach:** Used direct three-step HTTP (company_tickers.json → submissions/{CIK}.json → form4.xml) rather than the sec-edgar-downloader library. This gives full control over request headers and makes the entire fetch chain mockable via respx_mock without any import patching.

2. **yfinance MultiIndex handling:** `yf.download(..., group_by="ticker")` always returns a MultiIndex DataFrame with ("Ticker", "Price") column levels, even for a single ticker. `df[ticker]` extraction works identically for 1 or N tickers. The `get_level_values("Ticker")` guard skips invalid/delisted tickers gracefully.

3. **_price_id determinism:** SHA-256 of "ticker:date" string, first 16 hex chars converted to int, masked to `0x7FFF_FFFF_FFFF_FFFF` for positive signed 64-bit range. Verified by 200 hypothesis examples.

4. **Writer returns attempted count:** `write_raw_records` returns `len(rows)` (attempted), not actual inserted rows. DuckDB's `executemany` with ON CONFLICT DO NOTHING does not expose per-row inserted count. Tests that verify idempotency use `SELECT COUNT(*)` directly rather than comparing the return value.

5. **raw_insider PK format:** `"{accession}:{transaction_index}"` string — accession numbers are globally unique per SEC filing; transaction_index is the within-XML row index (0-based), making the composite key unique per transaction within a filing.

6. **Tenacity retry scope:** Retries only on `httpx.HTTPStatusError` with status 429/500/503. Network errors (`httpx.RequestError`) are not retried — they propagate to the outer `except Exception` in the per-ticker/per-accession loop, which logs and continues to the next item.

## Test Coverage Summary

| Test File | Tests | Coverage |
|-----------|-------|----------|
| tests/fetchers/test_price.py | 5 | Happy path (2 tickers), empty DataFrame, freshness_date, exception handling, fetched_at type check |
| tests/fetchers/test_insider.py | 6 | Code-P happy path, non-P filter, User-Agent header on all requests, filed_at vs transaction_date distinction, null price_per_share, unknown ticker |
| tests/test_db/test_writer.py | 9 | raw_prices insert, raw_insider insert, raw_prices idempotency, raw_insider idempotency, empty list early exit, unsupported table ValueError, raw_insider ID format, hypothesis determinism (200 examples), hypothesis BIGINT range (200 examples) |

**Total: 29 tests pass (20 new + 9 pre-existing Phase 1 tests). Zero live network calls.**

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all fetchers return real data structures (mocked in tests only). No hardcoded empty values or placeholders in implementation.

## Threat Flags

No new security-relevant surface introduced beyond what was in the plan's threat model. All STRIDE mitigations in the plan are implemented:
- T-02-01: `xml.etree.ElementTree` (stdlib, XXE-safe) + all float() casts wrapped in try/except
- T-02-02: `time.sleep(0.12)` between every EDGAR request + tenacity exponential backoff on 429/500/503
- T-02-05: price_per_share absent or footnoted returns None, not an exception

## Self-Check

### Files exist:
- [x] tradebot/fetchers/price.py
- [x] tradebot/fetchers/insider.py
- [x] tradebot/db/writer.py
- [x] tests/fetchers/__init__.py
- [x] tests/fetchers/test_price.py
- [x] tests/fetchers/test_insider.py
- [x] tests/test_db/test_writer.py

### Test results:
- [x] 29/29 tests pass
- [x] uv run pytest -x -q exits 0

## Self-Check: PASSED
