# Phase 2: Ingestion Layer (Price + Insider) - Context

**Gathered:** 2026-07-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement two independently testable fetchers — a yfinance OHLCV price fetcher and an EDGAR Form 4 insider-buy fetcher — that write `List[RawRecord]` for a persistence layer to insert into `raw_prices` and `raw_insider`. Include freshness validation via `FetchResult.is_valid`. No live network calls in tests (respx mocks). No signal computation, no report, no scheduler.

</domain>

<decisions>
## Implementation Decisions

### Universe Definition
- **D-01:** Ticker universe is a hardcoded starter list in `settings` (e.g., `settings.universe: list[str]`). No DB lookup, no config file. Phase 3 signal engine ranks from this pool; the list can be extended in config as signals are validated.

### yfinance Price Fetcher
- **D-02:** Each run fetches a fixed 90-day window (`period="3mo"`) — no "first run vs subsequent run" delta logic. Simpler code; REQUIREMENTS.md INGEST-01 requires immutable append (rows with same ticker+date won't be duplicated if persistence layer uses INSERT OR IGNORE / ON CONFLICT DO NOTHING).
- **D-03:** Fetcher returns `List[RawRecord]` with `source="yfinance"`, `ticker`, `fetched_at=now()`, and OHLCV in `data` dict. Returns a `FetchResult` summary alongside.

### EDGAR Form 4 Fetcher
- **D-04:** Use EFTS full-text search (`https://efts.sec.gov/LATEST/search-index?q=%22form+type%22%3D%224%22&dateRange=custom&startdt=...&enddt=...&forms=4`), filtered to transaction code `P` (open-market purchase). Direct REST — no sec-edgar-downloader library (more control, respx-mockable).
- **D-05:** Date window per run: 90 days lookback (same rhythm as price fetcher). Pagination handled with `from` offset until response returns fewer results than page size.
- **D-06:** EDGAR fetcher queries ALL tickers in the universe and filters by `company_tickers` or issuer name match in the EFTS response. Alternatively, iterates per ticker if EFTS supports ticker-scoped search. Claude's call on which EFTS param scopes by ticker (e.g., `entity` param).
- **D-07:** Every EDGAR request sends `User-Agent: TradeBot/1.0 (contact@example.com)` header per SEC policy (INGEST-02 acceptance criterion).
- **D-08:** Raw filing code (`transaction_code`) is preserved in `RawRecord.data` dict for auditability — only code-P rows are returned, but the raw value is stored.

### Fetcher Interface
- **D-09:** Fetchers return `(List[RawRecord], FetchResult)` — no DB writes inside the fetcher. A separate `tradebot/db/writer.py` module handles bulk insert into DuckDB. Separation of concerns: fetch logic is pure HTTP + parse; tests don't need a DuckDB instance.
- **D-10:** One module per fetcher: `tradebot/fetchers/price.py` and `tradebot/fetchers/insider.py`. No shared base class — they share interfaces (same return types) but not inheritance.
- **D-11:** `tradebot/db/writer.py` exposes `write_raw_records(conn, table: str, records: List[RawRecord]) -> int` returning rows inserted. Uses `INSERT OR IGNORE` (DuckDB: `INSERT INTO ... ON CONFLICT DO NOTHING`) keyed on `(ticker, date)` for prices, `id` for insider.

### Claude's Discretion
- Exact EFTS query parameters for ticker-scoped Form 4 search (entity name vs ticker param — test against live API to determine).
- Whether `FetchResult` is returned as a second element of a tuple or wrapped in a named result type.
- Test file layout: `tests/fetchers/test_price.py` and `tests/fetchers/test_insider.py` (or combined `test_fetchers.py`) — standard pytest structure.
- Whether `writer.py` does upsert or skip-on-conflict — skip-on-conflict preferred to preserve immutability (D-02).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — INGEST-01 (price fetcher), INGEST-02 (EDGAR Form 4, code-P only, User-Agent, filed_at), INGEST-05 (respx mocks, no live calls in tests), DATA-02 (immutable append, fetched_at), DATA-03 (FetchResult with row_count + freshness_date), DATA-04 (transaction_date vs filed_at distinction)

### Project Context
- `.planning/PROJECT.md` — Capital constraints, free-data-only constraint (no paid sources), signal stack overview
- `.planning/ROADMAP.md` — Phase 2 acceptance criteria; Phase 3 depends on this phase's tables being populated

### Technology Stack
- `.claude/CLAUDE.md` — httpx + tenacity for HTTP, respx for mocking, yfinance reliability warning, sec-edgar-downloader note (NOT used in favor of direct EFTS), dependency versions

### Phase 1 Decisions (carry forward)
- `.planning/phases/01-data-foundation/01-CONTEXT.md` — D-06 (DDL in schema.py), D-07 (connection singleton), D-09 (dotenv pattern), D-10 (settings singleton)

### Existing Schema
- `tradebot/db/schema.py` — `raw_prices` and `raw_insider` table DDL (fields already defined; fetchers must produce records matching these columns)

### Existing Models
- `tradebot/models/raw_record.py` — `RawRecord` and `FetchResult` dataclasses (fetcher return types)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tradebot/models/raw_record.py` → `RawRecord` (source, ticker, fetched_at, data, transaction_date, filed_at) and `FetchResult` (source, ticker, row_count, freshness_date, is_valid property) — fetchers return these types directly
- `tradebot/db/connection.py` → `get_connection()` singleton — writer.py uses this; tests swap for in-memory
- `tradebot/config.py` → `settings` singleton — fetchers read `settings.universe` for ticker list
- `tradebot/db/schema.py` → `raw_prices` and `raw_insider` DDL — writer.py inserts into these tables

### Established Patterns (from Phase 1)
- Fetchers live in `tradebot/fetchers/` — one file per data source
- Tests use `respx` for httpx mocking; no live network calls allowed
- Return `List[RawRecord]` for data, `FetchResult` for summary — these contracts are set
- DB connection is a module-level singleton swapped in tests for in-memory DuckDB

### Integration Points
- `tradebot/fetchers/price.py` → produces rows consumed by `raw_prices` table (Phase 3 signal reads from here)
- `tradebot/fetchers/insider.py` → produces rows consumed by `raw_insider` table (Phase 3 insider signal reads from here)
- `tradebot/db/writer.py` → NEW in this phase; called by pipeline orchestration to persist fetcher output
- `tradebot/__main__.py` → will eventually orchestrate fetchers; Phase 2 may add a `fetch` CLI subcommand for manual testing

</code_context>

<specifics>
## Specific Ideas

- EDGAR EFTS endpoint: `https://efts.sec.gov/LATEST/search-index` with `forms=4`, `dateRange=custom`, `startdt` / `enddt` params. Filter response to `transaction_code == "P"` after parsing.
- yfinance call: `yf.download(tickers, period="3mo", interval="1d", auto_adjust=True)` — returns MultiIndex DataFrame; iterate per ticker to produce `RawRecord` list.
- `writer.py` insert: DuckDB supports `INSERT OR IGNORE` equivalent via `INSERT INTO table (...) SELECT ... WHERE NOT EXISTS (...)` or `ON CONFLICT DO NOTHING` — use the latter.
- User-Agent header value: `TradeBot/1.0 (dgliwa7bhs@gmail.com)` — email is the contact the SEC expects.

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope.

</deferred>

---

*Phase: 2-Ingestion Layer (Price + Insider)*
*Context gathered: 2026-07-07*
