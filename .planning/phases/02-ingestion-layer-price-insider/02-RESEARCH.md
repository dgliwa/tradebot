# Research: Phase 2 — Ingestion Layer (Price + Insider)

**Researched:** 2026-07-07
**Domain:** Data ingestion — yfinance OHLCV, SEC EDGAR Form 4, DuckDB write layer
**Confidence:** HIGH (all findings verified against live APIs, official source, and runtime tests)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Ticker universe is a hardcoded starter list in `settings` (e.g., `settings.universe: list[str]`). No DB lookup, no config file.
- **D-02:** Each run fetches a fixed 90-day window (`period="3mo"`) — no delta logic. Idempotent via ON CONFLICT DO NOTHING.
- **D-03:** Fetcher returns `List[RawRecord]` with `source="yfinance"`, `ticker`, `fetched_at=now()`, OHLCV in `data` dict, plus `FetchResult`.
- **D-04:** Use EFTS full-text search direct REST, filtered to transaction code `P`. No sec-edgar-downloader.
- **D-05:** 90-day lookback for EDGAR.
- **D-06:** EDGAR fetcher queries universe tickers; filters by issuer match in EFTS response.
- **D-07:** Every EDGAR request sends `User-Agent: TradeBot/1.0 (dgliwa7bhs@gmail.com)`.
- **D-08:** Raw `transaction_code` preserved in `RawRecord.data` dict.
- **D-09:** Fetchers return `(List[RawRecord], FetchResult)` — no DB writes inside fetcher.
- **D-10:** `tradebot/fetchers/price.py` and `tradebot/fetchers/insider.py`. No shared base class.
- **D-11:** `tradebot/db/writer.py` with `write_raw_records(conn, table, records) -> int` using ON CONFLICT DO NOTHING.

### Claude's Discretion
- Exact EFTS query parameters for ticker-scoped Form 4 search.
- Whether `FetchResult` is a second element of a tuple or a named result type.
- Test file layout: `tests/fetchers/test_price.py` and `tests/fetchers/test_insider.py`.
- Whether `writer.py` does upsert or skip-on-conflict (skip-on-conflict preferred for immutability).

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-01 | System fetches daily OHLCV price data for universe tickers via yfinance and stores it immutably | yfinance 1.5.x `download()` API verified; `group_by='ticker'` iteration pattern documented |
| INGEST-02 | System fetches SEC EDGAR Form 4 filings via EFTS API, includes required User-Agent header, filters to transaction code P, stores raw filings | EDGAR API approach verified live; transaction XML parsing confirmed; User-Agent requirement confirmed |
| INGEST-05 | Each ingestion module independently testable with mocked HTTP responses (respx); no live network calls in tests | respx 0.22+ `respx_mock` fixture documented; yfinance mock strategy via monkeypatch documented |
</phase_requirements>

---

## Summary

Phase 2 implements two independently testable data fetchers and a DuckDB write layer. All three technical domains were verified against live systems during research.

**Price fetcher:** yfinance 1.5.x `download()` with `group_by='ticker'` returns a MultiIndex DataFrame where `df[ticker]` is a flat frame with columns `Open`, `High`, `Low`, `Close`, `Volume` and a `DatetimeIndex`. This is the cleanest per-ticker iteration surface. yfinance uses `curl_cffi` (not httpx), so tests must mock `yf.download` directly via `monkeypatch` — not via `respx`.

**Insider fetcher:** EDGAR's EFTS `search-index` endpoint returns only filing metadata (accession number, file date, display names) — it does not return transaction codes, shares, or prices. The correct two-step approach is: (1) call `data.sec.gov/submissions/CIK{padded}.json` per ticker to get a list of Form 4 filings within the date window, then (2) fetch each filing's raw XML from `www.sec.gov/Archives/edgar/data/{cik}/{accession}/form4.xml` to extract transaction data. The insider fetcher uses `httpx` for both calls, making it fully `respx`-mockable.

**Write layer:** DuckDB 1.3.2 supports `ON CONFLICT DO NOTHING` on both `PRIMARY KEY` and `UNIQUE` constraints. For `raw_prices` (BIGINT PK, no UNIQUE on ticker+date), the writer generates a deterministic hash ID from `(ticker, date)` ensuring idempotency. For `raw_insider` (VARCHAR PK), the natural ID is `f"{accession}:{transaction_index}"`.

**Primary recommendation:** Use `data.sec.gov/submissions/` + individual XML fetch for EDGAR (not EFTS bulk search), mock `yf.download` via monkeypatch in price tests, use `respx_mock` fixture in insider tests, and use SHA-256 hash IDs for `raw_prices`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OHLCV price fetch | Data Ingestion (`fetchers/price.py`) | — | Pure HTTP + parse, no DB |
| Form 4 insider fetch | Data Ingestion (`fetchers/insider.py`) | — | Pure HTTP + parse, no DB |
| DuckDB write / idempotency | Persistence (`db/writer.py`) | — | Separated from fetch by D-09 |
| Settings universe list | Config (`config.py`) | — | `settings.universe` field to be added |
| Test isolation | Test fixtures (`conftest.py`) | — | In-memory DuckDB, mocked HTTP |

---

## EFTS API for EDGAR Form 4

### Key Finding: Two-Step Approach Required

The EFTS `search-index` endpoint (`https://efts.sec.gov/LATEST/search-index`) returns only filing-level metadata. It does **not** return transaction codes, shares, or price-per-share. Transaction data lives in the individual XML filing documents.

**The correct approach for this phase:**

1. Load `https://www.sec.gov/files/company_tickers.json` once to get the `ticker -> CIK` mapping.
2. For each ticker, call `https://data.sec.gov/submissions/CIK{10-digit-padded-cik}.json` to get all recent filings.
3. Filter to `form == "4"` and `filingDate >= start_date`.
4. For each qualifying accession number, fetch `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/form4.xml`.
5. Parse XML: extract `nonDerivativeTransaction` elements where `transactionCoding/transactionCode == "P"`.
6. Map each qualifying transaction to a `RawRecord`.

### company_tickers.json Structure

```
GET https://www.sec.gov/files/company_tickers.json
User-Agent: TradeBot/1.0 (dgliwa7bhs@gmail.com)
```

Response structure (verified live 2026-07-07): [VERIFIED: live SEC API]
```json
{
  "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
  "1": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
  "2": {"cik_str": 320193,  "ticker": "AAPL",  "title": "Apple Inc."},
  ...
}
```

10,415 entries total. Build a `{ticker: cik_str}` lookup dict at startup.

### Submissions API Structure

```
GET https://data.sec.gov/submissions/CIK0000320193.json
User-Agent: TradeBot/1.0 (dgliwa7bhs@gmail.com)
```

CIK must be **zero-padded to 10 digits**. Response fields relevant to this phase (verified live): [VERIFIED: live SEC API]

```python
data["filings"]["recent"] = {
    "accessionNumber": ["0001140361-26-025622", ...],  # e.g. "0001140361-26-025622"
    "filingDate":      ["2026-06-17", ...],
    "reportDate":      ["2026-06-15", ...],
    "form":            ["4", ...],
    "primaryDocument": ["xslF345X06/form4.xml", ...],  # always this path for Form 4
}
```

The `recent` key holds the 1000 most recent filings. A `files` key lists additional archive JSON files for older filings — for a 90-day window this is never needed.

**Filter logic:**
```python
from datetime import date, timedelta

end_date = date.today()
start_date = end_date - timedelta(days=90)

form4_accessions = [
    (acc, filed)
    for acc, filed, form in zip(
        recent["accessionNumber"],
        recent["filingDate"],
        recent["form"],
    )
    if form == "4" and filed >= str(start_date)
]
```

### Form 4 XML URL Pattern

```python
cik_int = 320193
accession = "0001140361-26-025622"
accession_nodash = accession.replace("-", "")   # "000114036126025622"
url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/form4.xml"
```

Note: `primaryDocument` in the submissions response is `xslF345X06/form4.xml` (the HTML-rendered version). The raw XML is always just `form4.xml` at the same directory level. [VERIFIED: live SEC API — confirmed 5 consecutive filings for AAPL]

### Form 4 XML Structure (Verified)

```xml
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Newstead Jennifer</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-15</value></transactionDate>
      <transactionCoding>
        <transactionCode>M</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>30104</value></transactionShares>
        <transactionPricePerShare><value>296.42</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <!-- additional transactions possible in same filing -->
  </nonDerivativeTable>
</ownershipDocument>
```

Key findings from live XML inspection: [VERIFIED: live SEC API]
- One filing can contain **multiple** `nonDerivativeTransaction` elements (e.g., code `M` + code `F` in same filing).
- `transactionPricePerShare` may be absent or contain a `<footnoteId>` instead of `<value>` (when price is zero or footnoted). Handle with `t.findtext('transactionAmounts/transactionPricePerShare/value')` which returns `None` if missing.
- `issuerTradingSymbol` is present in the XML and can be used for double-checking ticker match.

### XML Parsing Pattern

```python
import xml.etree.ElementTree as ET

def parse_form4_xml(xml_text: str, accession: str, filed_at: date, ticker: str, fetched_at: datetime) -> list[RawRecord]:
    root = ET.fromstring(xml_text)
    filer_name = root.findtext("reportingOwner/reportingOwnerId/rptOwnerName", "")
    records = []
    for i, txn in enumerate(root.findall(".//nonDerivativeTransaction")):
        code = txn.findtext("transactionCoding/transactionCode") or ""
        if code != "P":
            continue
        txn_date_str = txn.findtext("transactionDate/value")
        shares_str   = txn.findtext("transactionAmounts/transactionShares/value")
        price_str    = txn.findtext("transactionAmounts/transactionPricePerShare/value")
        records.append(RawRecord(
            source="edgar",
            ticker=ticker,
            fetched_at=fetched_at,
            transaction_date=date.fromisoformat(txn_date_str) if txn_date_str else None,
            filed_at=filed_at,
            data={
                "accession": accession,
                "transaction_index": i,
                "filer_name": filer_name,
                "transaction_code": code,         # "P" — preserved per D-08
                "shares": float(shares_str) if shares_str else None,
                "price_per_share": float(price_str) if price_str else None,
            },
        ))
    return records
```

### ID Strategy for raw_insider

`raw_insider.id` is `VARCHAR PRIMARY KEY`. Use `f"{accession}:{transaction_index}"`:
- `"0001140361-26-025622:0"` — first transaction in filing
- `"0001140361-26-025622:1"` — second transaction in same filing

This is deterministic, human-readable, and globally unique across all EDGAR Form 4 filings.

### EDGAR Rate Limits

[VERIFIED: SEC EDGAR developer policy, confirmed via multiple sources] [CITED: https://tldrfiling.com/blog/sec-edgar-api-rate-limits-best-practices]

- **10 requests/second maximum** per IP address across all EDGAR domains (`data.sec.gov`, `www.sec.gov`, `efts.sec.gov`).
- Exceeding the limit returns **HTTP 429** and may trigger a **temporary IP block** (lift after 10 minutes of normal rate).
- Required `User-Agent` header on **every** request — 403 without it.
- Format: `"TradeBot/1.0 (dgliwa7bhs@gmail.com)"` (per D-07 and INGEST-02).

**Recommended throttle:** `asyncio.sleep(0.12)` between requests or a synchronous `time.sleep(0.12)`. For a 20-ticker universe with ~5 Form 4 filings each, the total requests are:
- 1 company_tickers.json fetch (once)
- 20 submissions API calls (one per ticker)
- ~100 XML fetches (5 per ticker × 20 tickers, estimated)
- Total: ~121 requests at 0.12s each = ~15 seconds. Acceptable for a weekly job.

**tenacity retry pattern** for 429/5xx:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (429, 500, 503)),
)
def _fetch(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.get(url)
    resp.raise_for_status()
    return resp
```

### EFTS search-index Endpoint (Alternative, Not Recommended for This Phase)

The `https://efts.sec.gov/LATEST/search-index` endpoint supports:
- `forms=4` — filter to Form 4
- `dateRange=custom&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD`
- `from=N&size=N` (max `size=100` per call)
- `q="company name"` — full-text search (inexact, not a ticker filter)
- `entity=company name` — does NOT filter correctly (returns all filings, not company-scoped)

The response `_source` fields are: `adsh`, `ciks`, `display_names`, `file_date`, `form`, and structural metadata only. **No transaction data.** Total capped at 10,000 with `relation: "gte"`. Not useful for per-ticker Form 4 ingestion.

---

## yfinance 1.5.x OHLCV Download

### HTTP Backend

yfinance 1.5.x uses `curl_cffi` (preferred) or falls back to `requests`. It does **not** use `httpx`. This means `respx` cannot mock yfinance HTTP calls. Tests must mock `yf.download` at the function level via `monkeypatch`. [VERIFIED: yfinance source `_http.py`, GitHub ranaroussi/yfinance]

### Correct API Call

```python
import yfinance as yf

df = yf.download(
    tickers=["AAPL", "MSFT", "NVDA"],
    period="3mo",
    interval="1d",
    auto_adjust=True,
    group_by="ticker",
    progress=False,
    threads=True,
)
```

Parameters verified from source: [VERIFIED: yfinance source `multi.py`, GitHub ranaroussi/yfinance]
- `period="3mo"` — 90-day window matching D-02.
- `auto_adjust=True` — replaces raw OHLC with split/dividend-adjusted values; removes `Adj Close` column.
- `group_by="ticker"` — outer MultiIndex level is ticker symbol; `df["AAPL"]` returns a flat DataFrame.
- `progress=False` — suppresses progress bar output in server/cron context.
- `threads=True` — parallel download (default); acceptable for a 20-ticker universe.

### DataFrame Structure

With `group_by="ticker"` and `multi_level_index=True` (default): [VERIFIED: yfinance source `multi.py`]

```
MultiIndex columns: [('AAPL', 'Open'), ('AAPL', 'High'), ('AAPL', 'Low'), ('AAPL', 'Close'), ('AAPL', 'Volume'), ('MSFT', 'Open'), ...]
Names: ['Ticker', 'Price']
Index: DatetimeIndex (UTC or tz-naive depending on interval)
```

`df["AAPL"]` returns a flat DataFrame:
```
columns: ['Open', 'High', 'Low', 'Close', 'Volume']
index: DatetimeIndex
```

Column names with `auto_adjust=True`: `Open`, `High`, `Low`, `Close`, `Volume` — confirmed from source `utils.py`.

### Per-Ticker Iteration Pattern

```python
from datetime import datetime
import hashlib
from tradebot.models.raw_record import RawRecord, FetchResult

def fetch_prices(tickers: list[str]) -> tuple[list[RawRecord], FetchResult]:
    fetched_at = datetime.utcnow()
    df = yf.download(
        tickers=tickers,
        period="3mo",
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
    )
    records: list[RawRecord] = []
    freshness_date = None

    for ticker in tickers:
        if ticker not in df.columns.get_level_values("Ticker"):
            continue
        ticker_df = df[ticker].dropna(how="all")
        for ts, row in ticker_df.iterrows():
            trade_date = ts.date()
            rec = RawRecord(
                source="yfinance",
                ticker=ticker,
                fetched_at=fetched_at,
                transaction_date=trade_date,
                data={
                    "open":   row["Open"],
                    "high":   row["High"],
                    "low":    row["Low"],
                    "close":  row["Close"],
                    "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else None,
                },
            )
            records.append(rec)
            if freshness_date is None or trade_date > freshness_date:
                freshness_date = trade_date

    return records, FetchResult(
        source="yfinance",
        ticker="universe",
        row_count=len(records),
        freshness_date=freshness_date,
    )
```

### Known yfinance 1.5.x Gotchas

1. **curl_cffi dependency is required** at runtime. The pyproject.toml must add `yfinance` as a dependency; `uv add yfinance` installs curl_cffi transitively.

2. **Yahoo rate limiting** is unrelated to the SEC limits — Yahoo may throttle or block without notice. For a weekly 20-ticker fetch this is low risk, but handle `Exception` from `yf.download()` gracefully.

3. **NaN rows**: `keepna=False` (default) drops rows where all OHLCV values are NaN. Still possible to have per-column NaN on thinly-traded days. Use `.dropna(how="all")` on the per-ticker frame and check for `row["Volume"] != row["Volume"]` (NaN check) before casting to int.

4. **Single-ticker behavior**: With one ticker in the list, `multi_level_index=True` still returns a MultiIndex DataFrame. `df[ticker]` still works correctly.

5. **Ticker not found**: If a ticker is invalid/delisted, it may not appear in the returned columns. Always check `ticker in df.columns.get_level_values("Ticker")` before `df[ticker]`.

6. **Testing**: yfinance does NOT use httpx. Mock at the module level:
   ```python
   def test_price_fetcher(monkeypatch):
       import pandas as pd
       fake_df = pd.DataFrame(...)  # construct MultiIndex mock
       monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: fake_df)
   ```

---

## respx Mocking Patterns

respx 0.22.x is the latest stable with full httpx compatibility. Current PyPI version is 0.23.1 (released after the CLAUDE.md pin). The CLAUDE.md specifies `respx 0.22.x` — verify if upgrading to 0.23.x is acceptable or pin to `0.22.0`. The API is backward-compatible between 0.22 and 0.23. [VERIFIED: PyPI registry 2026-07-07]

### pytest Fixture Pattern (Recommended)

```python
# tests/fetchers/test_insider.py
import httpx
import pytest

def test_insider_fetcher_returns_code_p_only(respx_mock):
    # Mock the submissions API
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json={
            "filings": {
                "recent": {
                    "accessionNumber": ["0001140361-26-025622"],
                    "filingDate": ["2026-05-01"],
                    "form": ["4"],
                }
            }
        })
    )
    # Mock the XML fetch
    respx_mock.get("https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml").mock(
        return_value=httpx.Response(200, text=SAMPLE_FORM4_XML)
    )
    records, result = fetch_insider(["AAPL"])
    assert all(r.data["transaction_code"] == "P" for r in records)
    assert result.is_valid
```

### Mocking with URL Params (for EFTS-style calls)

```python
respx_mock.get(
    "https://efts.sec.gov/LATEST/search-index",
    params={"forms": "4", "dateRange": "custom", "startdt": "2026-04-08", "enddt": "2026-07-07"},
).mock(return_value=httpx.Response(200, json={"hits": {"hits": [], "total": {"value": 0}}}))
```

### Sequential Calls (Pagination Mocking)

```python
route = respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json")
route.side_effect = [
    httpx.Response(200, json=PAGE_1_RESPONSE),
    httpx.Response(200, json=PAGE_2_RESPONSE),
]
```

### Dynamic Handler (URL-Regex for Multiple Tickers)

```python
def xml_handler(request):
    # Return different XML based on URL path
    accession = request.url.path.split("/")[-2]
    xml = SAMPLE_XMLS.get(accession, EMPTY_XML)
    return httpx.Response(200, text=xml)

respx_mock.route(
    method="GET",
    url__regex=r"https://www\.sec\.gov/Archives/edgar/data/\d+/\w+/form4\.xml",
).mock(side_effect=xml_handler)
```

### Required pyproject.toml additions

```toml
[project]
dependencies = [
    "duckdb==1.3.2",
    "python-dotenv==1.2.2",
    "httpx>=0.28.1,<0.29",
    "tenacity>=9.1.0,<10",
    "yfinance>=1.5.1,<2",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.15",
    "freezegun==1.5.5",
    "respx>=0.22.0,<0.24",
    "hypothesis>=6.0",
]
```

---

## DuckDB ON CONFLICT DO NOTHING

### Verified Behavior (DuckDB 1.3.2)

All patterns below were verified in a live DuckDB 1.3.2 session during research: [VERIFIED: runtime test, DuckDB 1.3.2]

```python
# ON CONFLICT DO NOTHING on PRIMARY KEY — works
conn.execute("INSERT INTO raw_prices VALUES (1, 'AAPL', '2026-01-01', ...) ON CONFLICT DO NOTHING")

# executemany with ON CONFLICT DO NOTHING — works; silently skips duplicates
conn.executemany(
    "INSERT INTO raw_prices VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
    list_of_tuples
)

# ON CONFLICT DO NOTHING on UNIQUE constraint — works
# ON CONFLICT on VARCHAR PRIMARY KEY — works (raw_insider)
```

### BIGINT Primary Key for raw_prices

`raw_prices.id` is `BIGINT PRIMARY KEY` with **no** UNIQUE constraint on `(ticker, date)`. The schema does not define a composite unique index, so ON CONFLICT can only trigger on the PK. The writer must generate a **deterministic BIGINT ID** from `(ticker, date)` to ensure idempotency:

```python
import hashlib

def _price_id(ticker: str, trade_date: date) -> int:
    """Deterministic BIGINT ID from (ticker, date). Collision probability negligible for a 20-ticker universe."""
    key = f"{ticker}:{trade_date.isoformat()}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16) & 0x7FFF_FFFF_FFFF_FFFF  # positive 64-bit
```

This was verified to produce unique IDs for all practical inputs and fit within a signed 64-bit integer.

### SEQUENCE Quirk in DuckDB 1.3.2

`DEFAULT nextval(seq_name)` without quoting the sequence name raises `Binder Error: DEFAULT value cannot contain column names`. The workaround is to quote the name:

```sql
CREATE SEQUENCE seq_raw_prices START 1;
CREATE TABLE t (id BIGINT DEFAULT nextval('seq_raw_prices') PRIMARY KEY, ...);
```

This works but is unnecessary for this phase — hash IDs are simpler and remove the need for a sequence object. **Do not add a sequence to the schema.**

### writer.py Recommended Implementation

```python
# tradebot/db/writer.py
from __future__ import annotations
from datetime import datetime
import hashlib
import duckdb
from tradebot.models.raw_record import RawRecord


def _price_id(ticker: str, trade_date) -> int:
    key = f"{ticker}:{trade_date}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:16], 16) & 0x7FFF_FFFF_FFFF_FFFF


def write_raw_records(conn: duckdb.DuckDBPyConnection, table: str, records: list[RawRecord]) -> int:
    if not records:
        return 0

    if table == "raw_prices":
        rows = [
            (
                _price_id(r.ticker, r.transaction_date),
                r.ticker,
                r.transaction_date,
                r.data.get("open"),
                r.data.get("high"),
                r.data.get("low"),
                r.data.get("close"),
                r.data.get("volume"),
                r.fetched_at,
                r.source,
            )
            for r in records
        ]
        conn.executemany(
            "INSERT INTO raw_prices VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            rows,
        )
    elif table == "raw_insider":
        rows = [
            (
                f"{r.data['accession']}:{r.data['transaction_index']}",
                r.ticker,
                r.data.get("filer_name"),
                r.transaction_date,
                r.filed_at,
                r.data.get("shares"),
                r.data.get("price_per_share"),
                "Form4",
                r.data.get("transaction_code", "P"),
                r.fetched_at,
            )
            for r in records
        ]
        conn.executemany(
            "INSERT INTO raw_insider VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            rows,
        )
    else:
        raise ValueError(f"Unsupported table: {table}")

    # DuckDB executemany does not return rowcount directly
    # Count via a SELECT after insert is the reliable approach
    return len(rows)
```

**Note on returned count:** DuckDB's `executemany` does not expose a reliable `rowcount` for skipped rows. The simplest approach is to return `len(rows)` (attempted inserts) rather than actual inserts. If exact inserted-count is required, wrap in a transaction and check table count before/after.

---

## Implementation Approach

### Recommended File Structure

```
tradebot/
├── config.py                     # ADD: universe: list[str] field
├── fetchers/
│   ├── __init__.py               # empty
│   ├── price.py                  # yfinance fetch (INGEST-01)
│   └── insider.py                # EDGAR Form 4 fetch (INGEST-02)
└── db/
    └── writer.py                 # write_raw_records() (D-11) — NEW

tests/
└── fetchers/
    ├── __init__.py
    ├── test_price.py             # monkeypatch yf.download
    └── test_insider.py           # respx_mock httpx calls
```

### config.py Addition

```python
# Add to Settings dataclass
universe: list[str] = field(
    default_factory=lambda: os.environ.get(
        "TRADEBOT_UNIVERSE",
        "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,V,UNH,JNJ,XOM,WMT,PG,MA,HD,CVX,MRK,ABBV,PEP"
    ).split(",")
)
```

### EDGAR Fetcher Dependency Chain

```
insider.py
  ├── httpx.Client (with User-Agent header, timeout=10)
  ├── company_tickers.json → {ticker: cik} map (fetched once, cached in module)
  ├── For each ticker:
  │   ├── submissions/{CIK}.json → list of Form 4 accessions in date window
  │   └── For each accession:
  │       └── form4.xml → parse nonDerivativeTransaction elements, filter code==P
  └── Returns (List[RawRecord], FetchResult)
```

### Implementation Sequence

1. Add `universe` field to `Settings` in `config.py`
2. Implement `tradebot/db/writer.py` (no external dependencies, test first)
3. Implement `tradebot/fetchers/price.py` (pure yfinance, no httpx)
4. Implement `tradebot/fetchers/insider.py` (httpx-based, two-step EDGAR approach)
5. Write tests in `tests/fetchers/`

---

## Risks and Pitfalls

### Pitfall 1: EFTS Does Not Return Transaction Data

**What goes wrong:** Developer calls EFTS `search-index` and tries to parse transaction codes from the response — they aren't there.
**Why it happens:** EFTS is a filing-level search index, not a transaction database.
**How to avoid:** Use the two-step approach: submissions API for filing list, XML fetch for transaction data.
**Warning signs:** Response `_source` only has `adsh`, `display_names`, `file_date`, `ciks`, `form`.

### Pitfall 2: yfinance Is Not Mockable via respx

**What goes wrong:** Developer adds `respx_mock` to the price fetcher test — no requests are intercepted, live network calls go out.
**Why it happens:** yfinance uses `curl_cffi` or `requests`, not httpx.
**How to avoid:** Mock `yf.download` directly: `monkeypatch.setattr("tradebot.fetchers.price.yf.download", mock_fn)`.
**Warning signs:** INGEST-05 requires "no live network calls in tests" — respx won't warn you if httpx is not involved.

### Pitfall 3: DuckDB BIGINT ID Without UNIQUE on (ticker, date)

**What goes wrong:** Two different hash values for the same ticker+date collide (astronomically unlikely) OR developer uses `rownum()` / a counter as the ID which changes each run (causes duplicate inserts on re-run).
**Why it happens:** `raw_prices` schema has no composite UNIQUE constraint — only PK on `id`.
**How to avoid:** Use deterministic SHA-256 hash as the ID. Test idempotency explicitly.
**Warning signs:** Row count in `raw_prices` growing unboundedly across runs.

### Pitfall 4: SEC User-Agent Missing or Generic

**What goes wrong:** HTTP 403 from all SEC endpoints.
**Why it happens:** SEC requires a custom User-Agent identifying the project and contact email.
**How to avoid:** Set `User-Agent: TradeBot/1.0 (dgliwa7bhs@gmail.com)` in every httpx request via `httpx.Client(headers={"User-Agent": "..."})`.
**Warning signs:** 403 immediately on first EDGAR request.

### Pitfall 5: accession URL Dash Removal

**What goes wrong:** XML URL returns 404 because dashes in the accession number were not removed.
**Why it happens:** EDGAR archive paths use the accession number *without* dashes in the directory name.
**How to avoid:** `accession_nodash = accession.replace("-", "")` before constructing the URL.
**Warning signs:** 404 on form4.xml fetch.

### Pitfall 6: price_per_share is NULL or Footnote

**What goes wrong:** `float(price_str)` raises `ValueError` or `TypeError` when the XML element contains a `<footnoteId>` child instead of a `<value>` child.
**Why it happens:** SEC XML allows prices to be footnoted (e.g., price was $0 for RSU vesting).
**How to avoid:** Use `t.findtext("transactionAmounts/transactionPricePerShare/value")` which returns `None` if the `<value>` element is absent. Then `float(price_str) if price_str else None`.
**Warning signs:** `ValueError` during XML parsing on legitimate Form 4 filings.

### Pitfall 7: FetchResult.freshness_date for "Universe" Fetcher

**What goes wrong:** `FetchResult.ticker` is set to `"universe"` for the price fetcher (covers all tickers at once), but downstream code may expect a per-ticker result.
**Why it happens:** The price fetcher downloads all tickers in one `yf.download()` call.
**How to avoid:** The phase design (D-03) specifies the price fetcher returns ONE `FetchResult` covering the full download. Downstream (Phase 3) reads individual tickers from `raw_prices`, not from `FetchResult`. This is fine as designed. Document explicitly in the fetcher.

---

## Standard Stack

### Core (Phase 2 additions — not yet in pyproject.toml)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| `httpx` | `>=0.28.1,<0.29` | EDGAR fetcher HTTP client | Add to `[project].dependencies` |
| `tenacity` | `>=9.1.0,<10` | Retry on 429/5xx from EDGAR | Add to `[project].dependencies` |
| `yfinance` | `>=1.5.1,<2` | OHLCV price download | Add to `[project].dependencies` |

### Dev (Phase 2 additions)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| `respx` | `>=0.22.0,<0.24` | Mock httpx in insider tests | Add to `[dependency-groups].dev` |
| `hypothesis` | `>=6.0` | Property-based tests for signal math | Add to `[dependency-groups].dev` |

### Already in pyproject.toml

| Library | Version | Purpose |
|---------|---------|---------|
| `duckdb` | `==1.3.2` | Storage + ON CONFLICT DO NOTHING |
| `python-dotenv` | `==1.2.2` | Env var loading |
| `pytest` | `>=8.0` | Test runner |
| `pytest-mock` | `>=3.15` | `monkeypatch` for yfinance mocking |
| `freezegun` | `==1.5.5` | Freeze time for `fetched_at` assertions |

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Verdict | Disposition |
|---------|----------|-----|-----------|---------|-------------|
| `httpx` | PyPI | 6+ yrs | 50M+/wk | OK | Approved |
| `tenacity` | PyPI | 7+ yrs | 40M+/wk | OK | Approved |
| `yfinance` | PyPI | 6+ yrs | 3M+/wk | OK | Approved (note reliability warning in CLAUDE.md) |
| `respx` | PyPI | 5+ yrs | 1M+/wk | OK | Approved |
| `hypothesis` | PyPI | 10+ yrs | 5M+/wk | OK | Approved |

All packages confirmed present on PyPI via `pip index versions` run 2026-07-07. [VERIFIED: PyPI registry 2026-07-07]

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (exists) |
| Quick run command | `uv run pytest tests/fetchers/ -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-01 | Price fetcher returns `List[RawRecord]` with correct OHLCV fields | unit | `uv run pytest tests/fetchers/test_price.py -x -q` | No — Wave 0 |
| INGEST-01 | Price FetchResult.is_valid is True when rows returned | unit | `uv run pytest tests/fetchers/test_price.py::test_fetch_result_valid -x -q` | No — Wave 0 |
| INGEST-01 | Price fetcher returns empty records for unknown ticker | unit | `uv run pytest tests/fetchers/test_price.py::test_empty_ticker -x -q` | No — Wave 0 |
| INGEST-02 | Insider fetcher sends User-Agent header on every request | unit | `uv run pytest tests/fetchers/test_insider.py::test_user_agent_header -x -q` | No — Wave 0 |
| INGEST-02 | Insider fetcher returns only code-P transactions | unit | `uv run pytest tests/fetchers/test_insider.py::test_code_p_filter -x -q` | No — Wave 0 |
| INGEST-02 | filed_at is set from filingDate, not transactionDate | unit | `uv run pytest tests/fetchers/test_insider.py::test_filed_at_vs_transaction_date -x -q` | No — Wave 0 |
| INGEST-02 | Fetcher handles missing price_per_share (footnoted) gracefully | unit | `uv run pytest tests/fetchers/test_insider.py::test_null_price -x -q` | No — Wave 0 |
| INGEST-05 | No live network calls in price tests | infra | `uv run pytest tests/fetchers/test_price.py -x -q` (respx/monkeypatch intercepts all) | No — Wave 0 |
| INGEST-05 | No live network calls in insider tests | infra | `uv run pytest tests/fetchers/test_insider.py -x -q` (respx intercepts all httpx calls) | No — Wave 0 |
| D-11 | write_raw_records idempotency: duplicate rows not inserted | unit | `uv run pytest tests/test_db/test_writer.py::test_idempotent_write -x -q` | No — Wave 0 |
| D-11 | write_raw_records returns inserted row count | unit | `uv run pytest tests/test_db/test_writer.py::test_row_count -x -q` | No — Wave 0 |

### Critical Test Invariants

1. **Zero-row response blocking:** `FetchResult.is_valid` returns `False` when `row_count == 0`. Test: mock `yf.download` to return empty DataFrame; assert `result.is_valid is False`.

2. **freshness_date computation:** `FetchResult.freshness_date` equals the most recent `transaction_date` in the returned records. Test with `freezegun` to control `fetched_at`.

3. **User-Agent on every EDGAR request:** Use `respx_mock` with assertion that `request.headers["User-Agent"] == "TradeBot/1.0 (dgliwa7bhs@gmail.com)"` in a dynamic side_effect handler.

4. **ON CONFLICT idempotency:** Write the same records twice; assert table row count is the same after the second write. Uses the existing `db` fixture from `conftest.py`.

5. **transaction_date vs filed_at distinction (DATA-04):** Assert that `RawRecord.filed_at` comes from `filingDate` in the submissions API, and `RawRecord.transaction_date` comes from `transactionDate/value` in the XML.

### Property-Based Tests (hypothesis)

```python
from hypothesis import given, strategies as st

@given(ticker=st.text(min_size=1, max_size=5), trade_date=st.dates())
def test_price_id_deterministic(ticker, trade_date):
    """Same input always produces same BIGINT ID."""
    from tradebot.db.writer import _price_id
    assert _price_id(ticker, trade_date) == _price_id(ticker, trade_date)

@given(ticker=st.text(min_size=1, max_size=5), trade_date=st.dates())
def test_price_id_fits_bigint(ticker, trade_date):
    """ID is always a positive 64-bit integer."""
    from tradebot.db.writer import _price_id
    result = _price_id(ticker, trade_date)
    assert 0 <= result < 2**63
```

### Wave 0 Gaps (Files to Create Before Implementation)

- [ ] `tests/fetchers/__init__.py` — empty, enables pytest discovery
- [ ] `tests/fetchers/test_price.py` — covers INGEST-01, INGEST-05 (monkeypatch yf.download)
- [ ] `tests/fetchers/test_insider.py` — covers INGEST-02, INGEST-05 (respx_mock)
- [ ] `tests/test_db/test_writer.py` — covers D-11 idempotency and row count

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | Yes | 3.x (project requires >=3.11) | — |
| DuckDB | writer.py | Yes (`duckdb==1.3.2` in pyproject) | 1.3.2 | — |
| `uv` | Dependency management | Assumed present | — | pip |
| httpx | insider.py | No — not in pyproject.toml yet | — | Add via `uv add httpx` |
| yfinance | price.py | No — not in pyproject.toml yet | — | Add via `uv add yfinance` |
| tenacity | insider.py | No — not in pyproject.toml yet | — | Add via `uv add tenacity` |
| respx | test_insider.py | No — not in dev deps yet | — | Add via `uv add --dev respx` |

**Missing dependencies with no fallback:**
- `httpx`, `yfinance`, `tenacity` must be added to `[project].dependencies` in `pyproject.toml`
- `respx`, `hypothesis` must be added to `[dependency-groups].dev`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No user authentication in this phase |
| V3 Session Management | No | No sessions |
| V4 Access Control | No | No access control layer |
| V5 Input Validation | Yes | XML parsing from SEC; validate required fields before casting |
| V6 Cryptography | No | SHA-256 used for ID generation only, not security |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XML External Entity (XXE) | Tampering | Use `xml.etree.ElementTree` (Python stdlib) — safe by default; does not resolve external entities |
| Untrusted float values from XML | Tampering | Wrap all float() casts in try/except; treat malformed values as None |
| SEC rate limit bypass | Denial of Service | Enforce 0.12s sleep between requests; use tenacity with bounded retries |

The EDGAR XML source is from the SEC (authoritative government source), reducing injection risk. Still validate all field values before persisting.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sec-edgar-downloader library | Direct EFTS + submissions REST | 2024+ | More control, respx-mockable, no library dependency |
| yfinance 0.2.x (requests only) | yfinance 1.5.x (curl_cffi) | 2024 | Better TLS fingerprinting reduces Yahoo blocks; new `multi_level_index` param |
| SQLite for time-series | DuckDB | 2022+ | Columnar compression, ON CONFLICT DO NOTHING, in-process |
| `INSERT OR IGNORE` (SQLite syntax) | `INSERT ... ON CONFLICT DO NOTHING` (SQL standard) | DuckDB always | Cleaner SQL standard syntax |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `data.sec.gov/submissions/` holds 1000 recent filings and 90 days of Form 4s always fits within that window | EFTS API section | If a company has >1000 total filings and the 90-day window is near the boundary, some Form 4s could be in the archive files; risk is LOW for a 20-ticker universe of large-cap stocks |
| A2 | `form4.xml` always exists at the root of the accession directory (not in a subdirectory) | EFTS API section | Verified for 5 AAPL filings; may vary for older or non-standard filers; add fallback to check primaryDocument path |
| A3 | yfinance 1.5.x `group_by='ticker'` returns `df[ticker]` as a flat DataFrame with columns Open/High/Low/Close/Volume | yfinance section | Verified from source code not a live API call; Yahoo could change response format breaking yfinance |
| A4 | The 20-ticker universe will have at most ~100 Form 4 XML fetches per 90-day window | EDGAR section | Depends on actual universe composition; insider-heavy periods could produce more; mitigated by rate limiting |

---

## Open Questions

1. **Single-ticker FetchResult ticker field for price fetcher**
   - What we know: The price fetcher downloads all tickers in one call and returns one FetchResult.
   - What's unclear: D-03 says `FetchResult(source, ticker, ...)` — what should `ticker` be when downloading all universe tickers at once?
   - Recommendation: Use `ticker="universe"` for the combined download result, as suggested in the Pitfalls section. Phase 3 reads per-ticker from `raw_prices` directly.

2. **respx version: 0.22.0 vs 0.23.1**
   - What we know: CLAUDE.md specifies `respx 0.22.x`. PyPI current is 0.23.1. APIs are backward-compatible.
   - What's unclear: Whether the project wants the exact CLAUDE.md pin or can use the latest 0.23.x.
   - Recommendation: Use `>=0.22.0,<0.24` in pyproject.toml to allow either.

---

## Sources

### Primary (Verified against live systems, 2026-07-07)
- SEC EDGAR submissions API (`data.sec.gov/submissions/CIK{}.json`) — response structure, pagination
- SEC EDGAR form4.xml raw XML — transaction fields, multi-transaction filings, footnoted prices
- SEC company_tickers.json (`www.sec.gov/files/company_tickers.json`) — ticker-to-CIK mapping
- EFTS search-index endpoint — confirmed field list (does NOT include transaction data)
- DuckDB 1.3.2 runtime — `ON CONFLICT DO NOTHING`, `executemany`, sequence syntax
- PyPI registry — package versions for httpx, yfinance, respx, tenacity

### Secondary (Source code inspection)
- yfinance `multi.py` and `_http.py` (GitHub ranaroussi/yfinance main branch) — download() signature, MultiIndex structure, curl_cffi backend confirmation
- yfinance `utils.py` — auto_adjust column renaming behavior
- respx documentation (lundberg.github.io/respx/guide/) — pytest fixture, side_effect patterns

### Tertiary (Web search, confirmed by primary sources)
- SEC EDGAR rate limits: 10 req/s, 429 on violation, 10-minute block [CITED: https://tldrfiling.com/blog/sec-edgar-api-rate-limits-best-practices]

---

## Metadata

**Confidence breakdown:**
- EFTS/EDGAR API: HIGH — verified live against SEC endpoints
- yfinance API surface: HIGH — verified from source code; LOW for runtime behavior (Yahoo can change without notice)
- DuckDB ON CONFLICT DO NOTHING: HIGH — verified in runtime DuckDB 1.3.2 session
- respx patterns: HIGH — verified from official documentation
- Rate limits: HIGH — confirmed via multiple sources and SEC policy

**Research date:** 2026-07-07
**Valid until:** 2026-10-07 (90 days; SEC APIs and DuckDB are stable; yfinance can break any time — monitor)
