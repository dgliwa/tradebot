# Phase 2 Plan: Ingestion Layer (Price + Insider)

---
phase: 02-ingestion-layer-price-insider
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - tradebot/config.py
  - tradebot/fetchers/price.py
  - tradebot/fetchers/insider.py
  - tradebot/db/writer.py
  - tests/fetchers/__init__.py
  - tests/fetchers/test_price.py
  - tests/fetchers/test_insider.py
  - tests/test_db/test_writer.py
autonomous: true
requirements:
  - INGEST-01
  - INGEST-02
  - INGEST-05
must_haves:
  truths:
    - Price fetcher returns (List[RawRecord], FetchResult) for all tickers; FetchResult.is_valid=True when rows present, False when zero rows
    - EDGAR fetcher returns only code-P purchases; every request carries User-Agent header; filed_at comes from filingDate (not transactionDate)
    - writer.py inserts raw_prices and raw_insider idempotently — a double-run with identical data produces no duplicates
    - All tests pass with zero live network calls; yfinance mocked via monkeypatch, httpx mocked via respx_mock
  artifacts:
    - tradebot/config.py — Settings.universe field present, reads TRADEBOT_UNIVERSE env var
    - tradebot/fetchers/price.py — fetch_prices(universe) implemented
    - tradebot/fetchers/insider.py — fetch_insider(universe) implemented
    - tradebot/db/writer.py — write_raw_records(conn, table, records) implemented
    - tests/fetchers/test_price.py — happy path + empty response + field mapping tests
    - tests/fetchers/test_insider.py — happy path + non-P filter + User-Agent + zero-row tests
    - tests/test_db/test_writer.py — insert prices + insert insider + idempotency tests
  key_links:
    - Settings.universe consumed by both fetchers; must be a list[str]
    - RawRecord.data keys must match writer.py column extraction exactly (open/high/low/close/volume for prices; accession/transaction_index/filer_name/transaction_code/shares/price_per_share for insider)
    - _price_id(ticker, trade_date) must be called identically in writer.py and tested in test_writer.py to confirm idempotency
    - respx_mock fixture (pytest-plugin auto-registered) intercepts only httpx; yfinance must be patched separately
---

<objective>
Implement the full ingestion layer for Phase 2: a yfinance OHLCV price fetcher (per D-02, D-03), an EDGAR Form 4 insider-buy fetcher (per D-04 through D-08), and a DuckDB write layer with ON CONFLICT DO NOTHING idempotency (per D-11). Add missing runtime dependencies to pyproject.toml and the `universe` field to Settings (per D-01).

Purpose: Populate raw_prices and raw_insider tables so Phase 3 signal computation has data to work from. Every acceptance criterion for Phase 2 is satisfied in this single plan.

Output: Seven files created or modified (pyproject.toml, config.py, price.py, insider.py, writer.py, test_price.py, test_insider.py, test_writer.py) plus one empty __init__.py for test discovery.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-ingestion-layer-price-insider/02-CONTEXT.md
@.planning/phases/02-ingestion-layer-price-insider/02-RESEARCH.md
@tradebot/models/raw_record.py
@tradebot/db/schema.py
@tradebot/config.py
@tradebot/db/connection.py
@tests/conftest.py
</context>

<tasks>

<!-- ═══════════════════════════════════════════════════════════════════════════
     P01 — Add dependencies + universe to Settings
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="false">
  <name>P01 — Add runtime dependencies and Settings.universe</name>
  <files>pyproject.toml, tradebot/config.py</files>
  <action>
**pyproject.toml — add missing runtime and dev dependencies.**

In `[project].dependencies`, add after `"python-dotenv==1.2.2"`:

```
"httpx>=0.28.1,<0.29",
"tenacity>=9.1.0,<10",
"yfinance>=1.5.1,<2",
```

In `[dependency-groups].dev`, add after `"freezegun==1.5.5"`:

```
"respx>=0.22.0,<0.24",
"hypothesis>=6.0",
"pytest-mock>=3.15",
```

Note: `pytest-mock` is already listed — skip if already present to avoid duplicates. `hypothesis` and `respx` are new.

After editing pyproject.toml, run:
```
uv sync
```
to lock and install all new packages into the venv.

---

**tradebot/config.py — add `universe` field to the Settings dataclass (per D-01).**

Add `import os` at the top if not already imported (it is not — add it). Then add the `universe` field to the `Settings` dataclass after the `alpaca_base_url` field:

```python
universe: list[str] = field(
    default_factory=lambda: os.environ.get(
        "TRADEBOT_UNIVERSE",
        "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,V,UNH,JNJ,XOM,WMT,PG,MA,HD,CVX,MRK,ABBV,PEP",
    ).split(",")
)
```

The `field(default_factory=...)` pattern is already used for every other Settings field — follow the same pattern exactly. No class-level type annotation without `field()` — the dataclass uses `field(default_factory=...)` uniformly.

Do NOT add `universe` as a plain `list[str] = [...]` assignment — that would make it a mutable class-level default and break dataclass semantics.
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run python -c "from tradebot.config import settings; assert isinstance(settings.universe, list); assert 'AAPL' in settings.universe; print('universe OK:', settings.universe[:3])"</automated>
  </verify>
  <done>
    - `uv sync` completes without error
    - `from tradebot.config import settings; settings.universe` returns a list of at least 10 tickers
    - Setting `TRADEBOT_UNIVERSE=AAPL,MSFT` in env produces `settings.universe == ["AAPL", "MSFT"]`
  </done>
</task>


<!-- ═══════════════════════════════════════════════════════════════════════════
     P02 — Implement price fetcher
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="true">
  <name>P02 — Implement tradebot/fetchers/price.py</name>
  <files>tradebot/fetchers/price.py</files>
  <behavior>
    - fetch_prices(["AAPL"]) returns a tuple (list[RawRecord], FetchResult)
    - Each RawRecord has source="yfinance", ticker="AAPL", fetched_at=datetime, transaction_date=date, filed_at=None, data with keys open/high/low/close/volume
    - FetchResult has source="yfinance", ticker="universe", row_count equal to total records across all tickers, freshness_date equal to the maximum transaction_date in all records
    - FetchResult.is_valid is True when row_count > 0 and freshness_date is not None
    - When yf.download returns an empty DataFrame (all tickers missing or no data), returns ([], FetchResult(row_count=0, freshness_date=None)) and FetchResult.is_valid is False
    - volume is cast to int; NaN volume is stored as None (not NaN float)
  </behavior>
  <action>
Create `tradebot/fetchers/price.py` with the following exact implementation.

**Imports:**
```python
from __future__ import annotations
from datetime import datetime
import hashlib

import yfinance as yf

from tradebot.models.raw_record import FetchResult, RawRecord
```

**Public function signature:**
```python
def fetch_prices(universe: list[str]) -> tuple[list[RawRecord], FetchResult]:
```

**Implementation logic:**

1. Record `fetched_at = datetime.utcnow()` before calling yfinance.

2. Call yfinance download:
   ```python
   df = yf.download(
       tickers=universe,
       period="3mo",
       interval="1d",
       auto_adjust=True,
       group_by="ticker",
       progress=False,
   )
   ```
   Wrap this call in a broad `except Exception` that returns `([], FetchResult(source="yfinance", ticker="universe", row_count=0, freshness_date=None))` if yfinance raises (Yahoo can raise without notice).

3. Iterate per ticker. For each `ticker` in `universe`:
   - Check `ticker in df.columns.get_level_values("Ticker")` — skip if not present (invalid/delisted ticker).
   - Extract `ticker_df = df[ticker].dropna(how="all")` — flat DataFrame with columns Open/High/Low/Close/Volume.
   - For each `(ts, row)` in `ticker_df.iterrows()`:
     - `trade_date = ts.date()`
     - Build `RawRecord`:
       - `source="yfinance"`
       - `ticker=ticker`
       - `fetched_at=fetched_at`
       - `transaction_date=trade_date`
       - `filed_at=None` (price data has no filing date)
       - `data={"open": row["Open"], "high": row["High"], "low": row["Low"], "close": row["Close"], "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else None}`
       - The `row["Volume"] == row["Volume"]` idiom is the NaN check (NaN != NaN in IEEE 754).
     - Append to `records`.
     - Update `freshness_date`: if `freshness_date is None or trade_date > freshness_date`, set `freshness_date = trade_date`.

4. Return:
   ```python
   return records, FetchResult(
       source="yfinance",
       ticker="universe",
       row_count=len(records),
       freshness_date=freshness_date,
   )
   ```

**Variable initialization at start of function body (before the loop):**
```python
records: list[RawRecord] = []
freshness_date = None
```

**Edge cases to handle (all come from RESEARCH.md pitfalls):**
- Empty DataFrame: the `ticker in df.columns.get_level_values("Ticker")` guard handles missing tickers gracefully.
- Single-ticker call: `group_by="ticker"` still returns a MultiIndex even for one ticker — `df[ticker]` works identically.
- If `df` is empty (no columns at all), `get_level_values("Ticker")` returns an empty Index and the loop body never executes — `records` stays `[]` and `freshness_date` stays `None`, which correctly produces `FetchResult.is_valid == False`.

Do NOT add any direct DB access, imports from `tradebot.db`, or `settings` reads inside this file. The fetcher is pure fetch+parse; caller provides `universe`.
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run pytest tests/fetchers/test_price.py -x -q</automated>
  </verify>
  <done>
    - `fetch_prices(["AAPL", "MSFT"])` returns tuple (list[RawRecord], FetchResult) when mocked
    - Each RawRecord.data contains keys: open, high, low, close, volume
    - FetchResult.ticker == "universe"
    - FetchResult.is_valid == False when mocked to return empty DataFrame
    - pytest tests/fetchers/test_price.py passes with zero live network calls
  </done>
</task>


<!-- ═══════════════════════════════════════════════════════════════════════════
     P03 — Implement insider fetcher
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="true">
  <name>P03 — Implement tradebot/fetchers/insider.py</name>
  <files>tradebot/fetchers/insider.py</files>
  <behavior>
    - fetch_insider(["AAPL"]) returns (list[RawRecord], FetchResult)
    - Every httpx request carries User-Agent header "TradeBot/1.0 (dgliwa7bhs@gmail.com)"
    - Only transactions where transactionCode == "P" are returned; others are filtered
    - RawRecord.filed_at is set from filingDate in the submissions API response (not from transactionDate in XML)
    - RawRecord.transaction_date is set from transactionDate/value in the form4.xml XML
    - RawRecord.data contains: accession, transaction_index (int), filer_name, transaction_code ("P"), shares (float or None), price_per_share (float or None)
    - When no Form 4 filings exist in the 90-day window, returns ([], FetchResult(row_count=0, freshness_date=None)) and FetchResult.is_valid is False
    - transactionPricePerShare absent or footnoted (no value child) results in price_per_share=None, not an exception
  </behavior>
  <action>
Create `tradebot/fetchers/insider.py`. This fetcher uses three-step HTTP: company_tickers.json → submissions/{CIK}.json per ticker → form4.xml per accession. All HTTP is via `httpx.Client` with a shared `User-Agent` header, making it fully mockable via `respx_mock`.

**Imports:**
```python
from __future__ import annotations
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from tradebot.models.raw_record import FetchResult, RawRecord
```

**Constants:**
```python
_USER_AGENT = "TradeBot/1.0 (dgliwa7bhs@gmail.com)"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik_padded}.json"
_FORM4_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/form4.xml"
_RATE_SLEEP = 0.12  # seconds between requests to stay under 10 req/s SEC limit
_LOOKBACK_DAYS = 90
```

**HTTP client factory:**
```python
def _make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": _USER_AGENT},
        timeout=15.0,
    )
```

**Tenacity retry decorator for 429/5xx:**
```python
def _is_retryable(exc: BaseException) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in (429, 500, 503)
    )

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable),
)
def _get(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.get(url)
    resp.raise_for_status()
    return resp
```

**Ticker-to-CIK map loader:**
```python
def _load_cik_map(client: httpx.Client) -> dict[str, int]:
    resp = _get(client, _TICKERS_URL)
    payload = resp.json()
    return {
        entry["ticker"].upper(): int(entry["cik_str"])
        for entry in payload.values()
    }
```

**Form 4 XML parser — returns list of RawRecord (code-P only):**
```python
def _parse_form4_xml(
    xml_text: str,
    accession: str,
    filed_at: date,
    ticker: str,
    fetched_at: datetime,
) -> list[RawRecord]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    filer_name = root.findtext(
        "reportingOwner/reportingOwnerId/rptOwnerName", ""
    ) or ""

    records: list[RawRecord] = []
    for i, txn in enumerate(root.findall(".//nonDerivativeTransaction")):
        code = txn.findtext("transactionCoding/transactionCode") or ""
        if code != "P":
            continue

        txn_date_str = txn.findtext("transactionDate/value")
        shares_str = txn.findtext("transactionAmounts/transactionShares/value")
        price_str = txn.findtext(
            "transactionAmounts/transactionPricePerShare/value"
        )

        txn_date: Optional[date] = None
        if txn_date_str:
            try:
                txn_date = date.fromisoformat(txn_date_str)
            except ValueError:
                pass

        shares: Optional[float] = None
        if shares_str:
            try:
                shares = float(shares_str)
            except ValueError:
                pass

        price: Optional[float] = None
        if price_str:
            try:
                price = float(price_str)
            except ValueError:
                pass

        records.append(
            RawRecord(
                source="edgar",
                ticker=ticker,
                fetched_at=fetched_at,
                transaction_date=txn_date,
                filed_at=filed_at,
                data={
                    "accession": accession,
                    "transaction_index": i,
                    "filer_name": filer_name,
                    "transaction_code": code,
                    "shares": shares,
                    "price_per_share": price,
                },
            )
        )
    return records
```

**Main public function:**
```python
def fetch_insider(universe: list[str]) -> tuple[list[RawRecord], FetchResult]:
    fetched_at = datetime.utcnow()
    end_date = date.today()
    start_date = end_date - timedelta(days=_LOOKBACK_DAYS)

    records: list[RawRecord] = []
    freshness_date: Optional[date] = None

    with _make_client() as client:
        # Step 1: load CIK map once
        cik_map = _load_cik_map(client)
        time.sleep(_RATE_SLEEP)

        for ticker in universe:
            cik_int = cik_map.get(ticker.upper())
            if cik_int is None:
                continue  # ticker not found in SEC registry

            cik_padded = str(cik_int).zfill(10)

            # Step 2: fetch submissions list for this ticker
            subs_url = _SUBMISSIONS_URL.format(cik_padded=cik_padded)
            try:
                subs_resp = _get(client, subs_url)
            except Exception:
                time.sleep(_RATE_SLEEP)
                continue
            time.sleep(_RATE_SLEEP)

            recent = subs_resp.json().get("filings", {}).get("recent", {})
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            forms = recent.get("form", [])

            # Filter to Form 4 filings within the 90-day window
            form4_accessions: list[tuple[str, date]] = []
            for acc, filed_str, form in zip(accession_numbers, filing_dates, forms):
                if form != "4":
                    continue
                try:
                    filed = date.fromisoformat(filed_str)
                except ValueError:
                    continue
                if filed < start_date:
                    continue
                form4_accessions.append((acc, filed))

            # Step 3: fetch and parse each Form 4 XML
            for accession, filed_at in form4_accessions:
                accession_nodash = accession.replace("-", "")
                xml_url = _FORM4_URL.format(
                    cik_int=cik_int,
                    accession_nodash=accession_nodash,
                )
                try:
                    xml_resp = _get(client, xml_url)
                except Exception:
                    time.sleep(_RATE_SLEEP)
                    continue
                time.sleep(_RATE_SLEEP)

                new_records = _parse_form4_xml(
                    xml_resp.text, accession, filed_at, ticker, fetched_at
                )
                records.extend(new_records)

                for rec in new_records:
                    if rec.transaction_date is not None:
                        if freshness_date is None or rec.transaction_date > freshness_date:
                            freshness_date = rec.transaction_date

    return records, FetchResult(
        source="edgar",
        ticker="universe",
        row_count=len(records),
        freshness_date=freshness_date,
    )
```

**Critical constraints from RESEARCH.md pitfalls:**
- The `accession_nodash = accession.replace("-", "")` transform is REQUIRED — the archive URL uses the dashes-removed form. Missing this causes 404 on every XML fetch.
- `t.findtext("transactionAmounts/transactionPricePerShare/value")` returns `None` if the element is absent or only has a `<footnoteId>` child — always guard with `if price_str` before `float()`.
- `xml.etree.ElementTree` (stdlib) is safe against XXE by default — do not add any custom entity resolvers.
- The `_get` retry decorator retries on 429/500/503 only. Network errors (`httpx.RequestError`) are NOT retried — they propagate up and are caught by the outer `except Exception` in the per-ticker/per-accession loop.
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run pytest tests/fetchers/test_insider.py -x -q</automated>
  </verify>
  <done>
    - fetch_insider(["AAPL"]) with mocked httpx returns only code-P RawRecords
    - Every mocked request carries User-Agent: TradeBot/1.0 (dgliwa7bhs@gmail.com)
    - RawRecord.filed_at equals filingDate from submissions JSON (not transactionDate from XML)
    - Non-P transaction codes (M, S, F, etc.) are excluded from returned records
    - Missing transactionPricePerShare returns price_per_share=None, not an exception
    - Zero Form 4 filings produces FetchResult.is_valid == False
    - pytest tests/fetchers/test_insider.py passes with zero live network calls
  </done>
</task>


<!-- ═══════════════════════════════════════════════════════════════════════════
     P04 — Implement DB writer
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="true">
  <name>P04 — Implement tradebot/db/writer.py</name>
  <files>tradebot/db/writer.py</files>
  <behavior>
    - write_raw_records(conn, "raw_prices", records) inserts all records; returns len(records) as attempted count
    - write_raw_records(conn, "raw_insider", records) inserts all records; returns len(records) as attempted count
    - Calling write_raw_records twice with identical records produces no duplicate rows in the table (ON CONFLICT DO NOTHING)
    - _price_id(ticker, trade_date) is deterministic: same input always produces same BIGINT
    - _price_id output is always a positive 64-bit integer (0 <= result < 2**63)
    - Passing an empty records list returns 0 immediately without touching the DB
    - Passing an unsupported table name raises ValueError
  </behavior>
  <action>
Create `tradebot/db/writer.py`.

**Imports:**
```python
from __future__ import annotations
import hashlib
from datetime import date

import duckdb

from tradebot.models.raw_record import RawRecord
```

**Private ID helper for raw_prices:**
```python
def _price_id(ticker: str, trade_date: date) -> int:
    """Deterministic BIGINT from (ticker, date). Collision probability negligible for a 20-ticker universe.

    Uses first 16 hex chars of SHA-256, masked to positive signed 64-bit range.
    """
    key = f"{ticker}:{trade_date}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16) & 0x7FFF_FFFF_FFFF_FFFF
```

**Main function:**
```python
def write_raw_records(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    records: list[RawRecord],
) -> int:
    """Bulk-insert records into table with ON CONFLICT DO NOTHING idempotency.

    Returns the number of rows attempted (not necessarily inserted — duplicates are silently skipped).
    """
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
        return len(rows)

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
        return len(rows)

    else:
        raise ValueError(f"Unsupported table: {table!r}. Expected 'raw_prices' or 'raw_insider'.")
```

**Column order mapping — executemany tuple position must exactly match DDL column order:**

For `raw_prices` (from schema.py):
- Position 0: id (BIGINT PK) — from `_price_id(r.ticker, r.transaction_date)`
- Position 1: ticker (VARCHAR)
- Position 2: date (DATE) — from `r.transaction_date`
- Position 3: open (DOUBLE)
- Position 4: high (DOUBLE)
- Position 5: low (DOUBLE)
- Position 6: close (DOUBLE)
- Position 7: volume (BIGINT)
- Position 8: fetched_at (TIMESTAMPTZ)
- Position 9: source (VARCHAR)

For `raw_insider` (from schema.py):
- Position 0: id (VARCHAR PK) — `f"{accession}:{transaction_index}"`
- Position 1: ticker (VARCHAR)
- Position 2: filer_name (VARCHAR)
- Position 3: transaction_date (DATE)
- Position 4: filed_at (DATE)
- Position 5: shares (DOUBLE)
- Position 6: price_per_share (DOUBLE)
- Position 7: form_type (VARCHAR) — hardcoded "Form4"
- Position 8: transaction_code (VARCHAR)
- Position 9: fetched_at (TIMESTAMPTZ)

**Why ON CONFLICT DO NOTHING:** D-11 and D-02 require immutable-append semantics. Re-running the fetcher on a day where prices already exist must not overwrite or duplicate rows. The deterministic `_price_id` hash ensures the same (ticker, date) pair always produces the same PK, so the conflict fires and the row is silently skipped.

**Note on returned count:** DuckDB's `executemany` does not expose a per-row inserted count when conflicts are skipped. Returning `len(rows)` (attempted inserts) is intentional and documented in the function docstring. Tests that verify idempotency must use `conn.execute("SELECT COUNT(*) FROM ...").fetchone()[0]` rather than comparing the return value.
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run pytest tests/test_db/test_writer.py -x -q</automated>
  </verify>
  <done>
    - write_raw_records(conn, "raw_prices", records) inserts rows into raw_prices
    - write_raw_records(conn, "raw_insider", records) inserts rows into raw_insider
    - Calling write_raw_records twice with the same records leaves row count unchanged in both tables
    - write_raw_records(conn, "raw_prices", []) returns 0 without executing any SQL
    - write_raw_records(conn, "bad_table", [...]) raises ValueError
    - pytest tests/test_db/test_writer.py passes
  </done>
</task>


<!-- ═══════════════════════════════════════════════════════════════════════════
     P05 — Tests for price fetcher
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>P05 — Write tests/fetchers/test_price.py</name>
  <files>tests/fetchers/__init__.py, tests/fetchers/test_price.py</files>
  <action>
**Create `tests/fetchers/__init__.py`** — empty file, enables pytest discovery.

**Create `tests/fetchers/test_price.py`** with the following tests. All tests mock `yf.download` via `monkeypatch`. No live network calls.

**Imports:**
```python
from __future__ import annotations
from datetime import date, datetime

import pandas as pd
import pytest

from tradebot.fetchers.price import fetch_prices
```

**Helper — build a minimal MultiIndex DataFrame that mimics yfinance output:**
```python
def _make_mock_df(tickers: list[str], num_rows: int = 3) -> pd.DataFrame:
    """Create a MultiIndex DataFrame matching yfinance group_by='ticker' output."""
    dates = pd.date_range("2026-04-01", periods=num_rows, freq="B")
    columns = pd.MultiIndex.from_product(
        [tickers, ["Open", "High", "Low", "Close", "Volume"]],
        names=["Ticker", "Price"],
    )
    import numpy as np
    data = {
        (ticker, col): (
            [float(100 + i) for i in range(num_rows)]
            if col != "Volume"
            else [1_000_000 + i * 100 for i in range(num_rows)]
        )
        for ticker in tickers
        for col in ["Open", "High", "Low", "Close", "Volume"]
    }
    return pd.DataFrame(data, index=dates, columns=columns)
```

**Test 1 — happy path: two tickers, correct RawRecord field mapping:**
```python
def test_fetch_prices_happy_path(monkeypatch):
    mock_df = _make_mock_df(["AAPL", "MSFT"], num_rows=3)
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: mock_df)

    records, result = fetch_prices(["AAPL", "MSFT"])

    assert len(records) == 6  # 3 rows × 2 tickers
    assert result.source == "yfinance"
    assert result.ticker == "universe"
    assert result.row_count == 6
    assert result.is_valid is True

    aapl_records = [r for r in records if r.ticker == "AAPL"]
    assert len(aapl_records) == 3
    assert all(r.source == "yfinance" for r in aapl_records)
    assert all(r.filed_at is None for r in aapl_records)
    assert all(isinstance(r.transaction_date, date) for r in aapl_records)
    assert all("open" in r.data for r in aapl_records)
    assert all("high" in r.data for r in aapl_records)
    assert all("low" in r.data for r in aapl_records)
    assert all("close" in r.data for r in aapl_records)
    assert all("volume" in r.data for r in aapl_records)
    assert all(isinstance(r.data["volume"], int) for r in aapl_records)
```

**Test 2 — empty DataFrame: FetchResult.is_valid is False:**
```python
def test_fetch_prices_empty_response(monkeypatch):
    empty_df = pd.DataFrame(
        columns=pd.MultiIndex.from_tuples([], names=["Ticker", "Price"])
    )
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: empty_df)

    records, result = fetch_prices(["FAKE_TICKER"])

    assert records == []
    assert result.row_count == 0
    assert result.freshness_date is None
    assert result.is_valid is False
```

**Test 3 — freshness_date equals max transaction_date:**
```python
def test_fetch_prices_freshness_date(monkeypatch):
    mock_df = _make_mock_df(["AAPL"], num_rows=5)
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: mock_df)

    records, result = fetch_prices(["AAPL"])

    expected_freshness = max(r.transaction_date for r in records)
    assert result.freshness_date == expected_freshness
```

**Test 4 — yfinance exception: returns empty result without raising:**
```python
def test_fetch_prices_yfinance_exception(monkeypatch):
    def broken_download(**kw):
        raise ConnectionError("Yahoo blocked")

    monkeypatch.setattr("tradebot.fetchers.price.yf.download", broken_download)

    records, result = fetch_prices(["AAPL"])

    assert records == []
    assert result.is_valid is False
```

**Test 5 — fetched_at is a datetime (not date):**
```python
def test_fetch_prices_fetched_at_is_datetime(monkeypatch):
    mock_df = _make_mock_df(["NVDA"], num_rows=1)
    monkeypatch.setattr("tradebot.fetchers.price.yf.download", lambda **kw: mock_df)

    records, _ = fetch_prices(["NVDA"])

    assert len(records) == 1
    assert isinstance(records[0].fetched_at, datetime)
```
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run pytest tests/fetchers/test_price.py -x -q</automated>
  </verify>
  <done>
    - All 5 tests pass
    - No live network calls (monkeypatch intercepts all yf.download calls)
    - pytest output shows 5 passed, 0 failed
  </done>
</task>


<!-- ═══════════════════════════════════════════════════════════════════════════
     P06 — Tests for insider fetcher
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>P06 — Write tests/fetchers/test_insider.py</name>
  <files>tests/fetchers/test_insider.py</files>
  <action>
Create `tests/fetchers/test_insider.py`. All httpx calls are intercepted by the `respx_mock` pytest fixture (auto-available when `respx` is installed — no import needed beyond `import respx` for type hints if used). No live network calls.

**Imports:**
```python
from __future__ import annotations
from datetime import date

import httpx
import pytest

from tradebot.fetchers.insider import fetch_insider
```

**Shared test data — minimal XML strings:**
```python
_XML_WITH_P = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Test Buyer</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>175.50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_XML_WITH_NON_P = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Option Exerciser</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-10</value></transactionDate>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>0.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_XML_NO_PRICE = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Footnote Buyer</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-20</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><footnoteId id="F1"/></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
}

_SUBMISSIONS_JSON = {
    "filings": {
        "recent": {
            "accessionNumber": ["0001140361-26-025622"],
            "filingDate": ["2026-05-16"],
            "form": ["4"],
        }
    }
}
```

**Test 1 — happy path: code-P transaction is returned:**
```python
def test_fetch_insider_returns_code_p(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_WITH_P))

    records, result = fetch_insider(["AAPL"])

    assert len(records) == 1
    assert records[0].ticker == "AAPL"
    assert records[0].source == "edgar"
    assert records[0].data["transaction_code"] == "P"
    assert records[0].data["shares"] == 1000.0
    assert records[0].data["price_per_share"] == 175.50
    assert records[0].data["filer_name"] == "Test Buyer"
    assert result.is_valid is True
    assert result.row_count == 1
```

**Test 2 — non-P transaction is filtered out:**
```python
def test_fetch_insider_filters_non_p(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_WITH_NON_P))

    records, result = fetch_insider(["AAPL"])

    assert records == []
    assert result.row_count == 0
    assert result.is_valid is False
```

**Test 3 — User-Agent header present on every request:**
```python
def test_fetch_insider_user_agent_header(respx_mock):
    seen_headers: list[str] = []

    def capture_header(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("user-agent", ""))
        if "company_tickers" in str(request.url):
            return httpx.Response(200, json=_TICKERS_JSON)
        if "submissions" in str(request.url):
            return httpx.Response(200, json=_SUBMISSIONS_JSON)
        return httpx.Response(200, text=_XML_WITH_P)

    respx_mock.route(method="GET").mock(side_effect=capture_header)

    fetch_insider(["AAPL"])

    assert len(seen_headers) >= 3  # tickers.json + submissions + xml
    for ua in seen_headers:
        assert ua == "TradeBot/1.0 (dgliwa7bhs@gmail.com)", f"Bad User-Agent: {ua!r}"
```

**Test 4 — filed_at from filingDate, transaction_date from XML (DATA-04):**
```python
def test_fetch_insider_filed_at_vs_transaction_date(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_WITH_P))

    records, _ = fetch_insider(["AAPL"])

    assert len(records) == 1
    rec = records[0]
    # filed_at is from submissions filingDate ("2026-05-16")
    assert rec.filed_at == date(2026, 5, 16)
    # transaction_date is from XML transactionDate/value ("2026-05-15")
    assert rec.transaction_date == date(2026, 5, 15)
    assert rec.filed_at != rec.transaction_date
```

**Test 5 — missing price_per_share (footnoted): returns None, no exception:**
```python
def test_fetch_insider_null_price_per_share(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_NO_PRICE))

    records, result = fetch_insider(["AAPL"])

    assert len(records) == 1
    assert records[0].data["price_per_share"] is None
    assert records[0].data["shares"] == 500.0
    assert result.is_valid is True
```

**Test 6 — ticker not in SEC registry: returns empty result:**
```python
def test_fetch_insider_unknown_ticker(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    # No submissions or XML calls expected for an unknown ticker

    records, result = fetch_insider(["ZZZNOTREAL"])

    assert records == []
    assert result.is_valid is False
```
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run pytest tests/fetchers/test_insider.py -x -q</automated>
  </verify>
  <done>
    - All 6 tests pass
    - Zero live network calls (respx_mock intercepts all httpx traffic)
    - User-Agent header verified on every request in test 3
    - filed_at vs transaction_date distinction verified in test 4
  </done>
</task>


<!-- ═══════════════════════════════════════════════════════════════════════════
     P07 — Tests for DB writer
     ═══════════════════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>P07 — Write tests/test_db/test_writer.py</name>
  <files>tests/test_db/test_writer.py</files>
  <action>
Create `tests/test_db/test_writer.py`. Uses the `db` fixture from `tests/conftest.py` which provides an in-memory DuckDB connection with all schema tables created. No file-system DB access.

**Imports:**
```python
from __future__ import annotations
from datetime import date, datetime

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from tradebot.db.writer import _price_id, write_raw_records
from tradebot.models.raw_record import RawRecord
```

**Helper — build a price RawRecord:**
```python
def _price_record(
    ticker: str = "AAPL",
    trade_date: date = date(2026, 5, 1),
    close: float = 175.0,
) -> RawRecord:
    return RawRecord(
        source="yfinance",
        ticker=ticker,
        fetched_at=datetime(2026, 7, 7, 12, 0, 0),
        transaction_date=trade_date,
        filed_at=None,
        data={
            "open": 174.0,
            "high": 176.0,
            "low": 173.0,
            "close": close,
            "volume": 50_000_000,
        },
    )
```

**Helper — build an insider RawRecord:**
```python
def _insider_record(
    ticker: str = "AAPL",
    accession: str = "0001140361-26-025622",
    idx: int = 0,
) -> RawRecord:
    return RawRecord(
        source="edgar",
        ticker=ticker,
        fetched_at=datetime(2026, 7, 7, 12, 0, 0),
        transaction_date=date(2026, 5, 15),
        filed_at=date(2026, 5, 16),
        data={
            "accession": accession,
            "transaction_index": idx,
            "filer_name": "Test Buyer",
            "transaction_code": "P",
            "shares": 1000.0,
            "price_per_share": 175.50,
        },
    )
```

**Test 1 — insert raw_prices: rows appear in table:**
```python
def test_write_raw_prices_inserts_rows(db):
    records = [
        _price_record("AAPL", date(2026, 5, 1)),
        _price_record("AAPL", date(2026, 5, 2)),
        _price_record("MSFT", date(2026, 5, 1)),
    ]
    count = write_raw_records(db, "raw_prices", records)

    assert count == 3
    row_count = db.execute("SELECT COUNT(*) FROM raw_prices").fetchone()[0]
    assert row_count == 3
```

**Test 2 — insert raw_insider: rows appear in table:**
```python
def test_write_raw_insider_inserts_rows(db):
    records = [
        _insider_record("AAPL", "0001140361-26-025622", 0),
        _insider_record("MSFT", "0001140361-26-099999", 0),
    ]
    count = write_raw_records(db, "raw_insider", records)

    assert count == 2
    row_count = db.execute("SELECT COUNT(*) FROM raw_insider").fetchone()[0]
    assert row_count == 2
```

**Test 3 — idempotency for raw_prices: double-insert leaves row count unchanged:**
```python
def test_write_raw_prices_idempotent(db):
    records = [
        _price_record("AAPL", date(2026, 5, 1)),
        _price_record("AAPL", date(2026, 5, 2)),
    ]
    write_raw_records(db, "raw_prices", records)
    write_raw_records(db, "raw_prices", records)  # identical second write

    row_count = db.execute("SELECT COUNT(*) FROM raw_prices").fetchone()[0]
    assert row_count == 2  # not 4
```

**Test 4 — idempotency for raw_insider: double-insert leaves row count unchanged:**
```python
def test_write_raw_insider_idempotent(db):
    records = [_insider_record("AAPL", "0001140361-26-025622", 0)]
    write_raw_records(db, "raw_insider", records)
    write_raw_records(db, "raw_insider", records)

    row_count = db.execute("SELECT COUNT(*) FROM raw_insider").fetchone()[0]
    assert row_count == 1  # not 2
```

**Test 5 — empty records list returns 0 without error:**
```python
def test_write_empty_records(db):
    result = write_raw_records(db, "raw_prices", [])
    assert result == 0
    row_count = db.execute("SELECT COUNT(*) FROM raw_prices").fetchone()[0]
    assert row_count == 0
```

**Test 6 — unsupported table raises ValueError:**
```python
def test_write_unsupported_table_raises(db):
    with pytest.raises(ValueError, match="Unsupported table"):
        write_raw_records(db, "signals", [_price_record()])
```

**Test 7 — raw_insider ID is accession:transaction_index:**
```python
def test_write_raw_insider_id_format(db):
    record = _insider_record("AAPL", "0001140361-26-025622", 0)
    write_raw_records(db, "raw_insider", [record])

    row_id = db.execute("SELECT id FROM raw_insider").fetchone()[0]
    assert row_id == "0001140361-26-025622:0"
```

**Test 8 — hypothesis: _price_id is deterministic:**
```python
@given(
    ticker=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",))),
    trade_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
)
@h_settings(max_examples=200)
def test_price_id_deterministic(ticker, trade_date):
    assert _price_id(ticker, trade_date) == _price_id(ticker, trade_date)
```

**Test 9 — hypothesis: _price_id fits signed 64-bit range:**
```python
@given(
    ticker=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu",))),
    trade_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
)
@h_settings(max_examples=200)
def test_price_id_fits_bigint(ticker, trade_date):
    result = _price_id(ticker, trade_date)
    assert 0 <= result < 2**63
```
  </action>
  <verify>
    <automated>cd /Users/derekgliwa/dev/tradebot && uv run pytest tests/test_db/test_writer.py -x -q</automated>
  </verify>
  <done>
    - All 9 tests pass
    - Idempotency confirmed: double-write leaves table row count at 1 for insider and 2 for prices
    - raw_insider ID format is "accession:index"
    - hypothesis: 200 examples confirm _price_id determinism and BIGINT range
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| SEC EDGAR → insider.py | XML from www.sec.gov crosses HTTP boundary; content is authoritative but must still be validated |
| Yahoo Finance → price.py | yfinance response is from a reverse-engineered API; format can change without notice |
| DuckDB → writer.py | Application-layer data enters local DB; no network boundary but float/type coercion must be safe |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-01 | Tampering | insider.py — XML parsing | medium | mitigate | Use stdlib `xml.etree.ElementTree` (safe against XXE by default); wrap all `float()` casts in try/except; treat malformed values as None rather than raising |
| T-02-02 | Denial of Service | insider.py — SEC rate limit | high | mitigate | Enforce `time.sleep(0.12)` between every EDGAR request; tenacity retries with exponential backoff (max 3 attempts, max 10s wait) on 429/500/503 |
| T-02-03 | Information Disclosure | config.py — TRADEBOT_UNIVERSE env var | low | accept | Universe is non-sensitive (public ticker symbols); env var is only read at startup, not logged |
| T-02-04 | Spoofing | insider.py — company_tickers.json | low | accept | Source is SEC's own domain (www.sec.gov); HTTPS enforced by httpx default; data is public |
| T-02-05 | Tampering | writer.py — float coercion from untrusted XML | medium | mitigate | All `float()` casts guarded with try/except ValueError in _parse_form4_xml; None stored instead of crashing |
| T-02-SC | Tampering | pyproject.toml — new package installs | high | mitigate | All 5 new packages (httpx, tenacity, yfinance, respx, hypothesis) are in RESEARCH.md Package Legitimacy Audit with [OK] disposition; no [ASSUMED] or [SUS] packages present |
</threat_model>

<verification>
Run the full test suite to confirm zero regressions and all Phase 2 tests pass:

```bash
cd /Users/derekgliwa/dev/tradebot
uv run pytest -x -q
```

Expected: all tests pass including pre-existing Phase 1 tests (tests/test_db/, tests/test_models/) and new Phase 2 tests.

Spot-check settings:
```bash
uv run python -c "from tradebot.config import settings; print(settings.universe)"
```

Spot-check imports:
```bash
uv run python -c "from tradebot.fetchers.price import fetch_prices; from tradebot.fetchers.insider import fetch_insider; from tradebot.db.writer import write_raw_records; print('all imports OK')"
```
</verification>

<success_criteria>
Phase 2 is complete when ALL of the following are true:

1. `uv run pytest -x -q` exits 0 with no failures across all test files
2. `settings.universe` is a non-empty list of ticker strings; overridable via `TRADEBOT_UNIVERSE` env var
3. `fetch_prices(universe)` returns `(List[RawRecord], FetchResult)` — FetchResult.ticker == "universe", FetchResult.is_valid == True when rows > 0
4. `fetch_insider(universe)` returns only code-P transactions; RawRecord.filed_at comes from filingDate; every httpx request sends the required User-Agent header
5. `write_raw_records(conn, "raw_prices", records)` followed by a second identical call leaves the table row count unchanged (ON CONFLICT DO NOTHING)
6. `write_raw_records(conn, "raw_insider", records)` followed by a second identical call leaves the table row count unchanged
7. No test makes a live network call — yfinance is mocked via monkeypatch, httpx is mocked via respx_mock
</success_criteria>

<output>
When all tasks are complete, create `.planning/phases/02-ingestion-layer-price-insider/02-01-SUMMARY.md` with:
- Files created/modified
- Key implementation decisions made
- Test coverage summary
- Any deviations from this plan and why
</output>
