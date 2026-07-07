# Stack Research — TradeBot

**Domain:** Python algorithmic trading bot (public signals, weekly recommendations, Alpaca execution)
**Researched:** 2026-07-07
**Overall confidence:** MEDIUM (PyPI version data is live; ecosystem judgments are knowledge-cutoff August 2025 + confirmed package inspection)

---

## 1. Project Tooling & Packaging

**Use `uv` for everything.** It replaces pip, venv, and pip-tools in one fast binary. The 2025 Python ecosystem has converged on `uv` for solo projects and startups.

- `uv init tradebot` creates `pyproject.toml` + `.venv` in seconds
- `uv add <package>` handles resolution and lockfile (`uv.lock`)
- `uv run python -m tradebot` runs in the venv without activating it
- Forget virtualenv, pipenv, poetry for new projects — they are slower and more complex

**Do NOT use** `setup.py` or `requirements.txt` as the primary package management. They are the old way and older tutorials will send you there.

```toml
# pyproject.toml (skeleton)
[project]
name = "tradebot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "alpaca-py>=0.43",
    "httpx>=0.28",
    "tenacity>=9.1",
    "polars>=1.42",
    "duckdb>=1.3",
    "apscheduler>=3.11",
    "fredapi>=0.5",
    "yfinance>=1.5",
    "sec-edgar-downloader>=5.1",
    "jinja2>=3.1",
    "loguru>=0.7",
    "pydantic>=2.9",
    "pandas-market-calendars>=5.4",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8",
    "pytest-mock>=3.15",
    "freezegun>=1.5",
    "responses>=0.26",
    "hypothesis>=6",
    "ruff>=0.9",
    "mypy>=1.13",
]
```

**Python version:** Use 3.11 minimum. 3.12 is fine. The full ecosystem (alpaca-py, polars, DuckDB) supports both. Do not use 3.10 — some type hint syntax you'll want requires 3.11+.

---

## 2. HTTP Clients & Data Ingestion

### Primary: `httpx` 0.28.x + `tenacity` 9.1.x

Use `httpx` (not `requests`) for all data ingestion you write yourself. It has native async support and a cleaner API. The sync API is identical to requests for simple cases.

**Why not `requests`:** `requests` is synchronous-only and has no retry primitives built in. It's not wrong, but `httpx` is strictly better for this use case.

**tenacity** is the standard retry/backoff library. Combine them:

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
)
def fetch_with_retry(url: str, params: dict) -> dict:
    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()
```

**Rate limiting:** Do not use `aiolimiter` (async only, overkill). Use `time.sleep()` between calls with a token-bucket pattern you control, or use `limits` 5.8.x with its `MovingWindowRateLimiter` for sources with explicit rate limits (e.g., FRED API: 120 req/min). For a weekly-batch bot, simple per-call sleeps are fine.

### Source-Specific Clients

| Data Source | Library | Version | Notes |
|-------------|---------|---------|-------|
| FRED macros | `fredapi` | 0.5.x | Thin wrapper, returns pandas Series. Works fine. |
| yfinance prices | `yfinance` | 1.5.1 | See reliability warning below |
| SEC EDGAR Form 4 | `sec-edgar-downloader` | 5.1.0 | Downloads raw SGML/XML, you parse it |
| Congress STOCK Act | raw `httpx` | — | No mature library; hit efts.usaspending.gov or senate.gov directly |
| Alpaca execution | `alpaca-py` | 0.43.5 | Official SDK |

### yfinance Reliability Warning (2025)

yfinance 1.x (released mid-2024) is a near-total rewrite. It now uses `curl_cffi` to mimic a browser and bypass Yahoo's anti-scraping. This fixed the "401 errors" that plagued 0.2.x in 2023-2024. The 1.5.x series is stable for daily OHLCV pulls.

**Known limitations that still apply:**
- Yahoo can change their API at any time with no notice. This has broken yfinance ~3 times in 2022-2024.
- No SLA, no uptime guarantee, reverse-engineered endpoint.
- Intraday data beyond 60 days requires a premium account.
- Options chain data via `Ticker.option_chain()` is available but reliability is lower than price data.

**For a weekly-batch bot, yfinance is acceptable.** The failure mode is silent stale data, not crashes. Mitigate by:
1. Storing every fetched price with a `fetched_at` timestamp.
2. Alerting if no new data after expected market close.
3. Adding Alpaca's own historical data client as a fallback (covered under Alpaca below).

**polygon.io free tier:** The free tier gives end-of-day data with a 15-minute delay plus full historical. It is more reliable than yfinance but has tighter rate limits (5 req/min on free). It requires registration. For price data reliability, use polygon.io as a backup validator rather than primary source.

---

## 3. Data Storage

**Use DuckDB 1.3+.** This is the right choice for this project. Here is why each alternative is wrong:

| Option | Verdict | Why |
|--------|---------|-----|
| SQLite | No | No columnar compression, slow on time-series range scans over millions of rows, no native ARRAY/LIST types |
| PostgreSQL | No | Massive ops overhead for a solo side project; you will spend time on pg_hba.conf, not on signals |
| DuckDB | Yes | Columnar, zero-ops, in-process, native Parquet/CSV import, SQL-complete, fast range scans on time-series |

DuckDB stores everything in a single file (`tradebot.duckdb`). Backup is `cp`. No server to manage. Scales to hundreds of millions of rows before you'd need to think about it.

**Schema approach:** Use SQLAlchemy **only** if you want schema migration tooling (Alembic). For this project, define your DDL in plain DuckDB SQL strings and run them at startup:

```python
import duckdb

def init_db(path: str = "data/tradebot.duckdb") -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            symbol VARCHAR,
            date DATE,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            fetched_at TIMESTAMPTZ DEFAULT current_timestamp,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            symbol VARCHAR,
            signal_date DATE,
            congress_score DOUBLE,
            insider_score DOUBLE,
            macro_score DOUBLE,
            momentum_score DOUBLE,
            composite_score DOUBLE,
            computed_at TIMESTAMPTZ DEFAULT current_timestamp,
            PRIMARY KEY (symbol, signal_date)
        )
    """)
    return conn
```

**Do NOT use SQLAlchemy's ORM** for this project. The ORM overhead is not worth it for a signal pipeline. Use DuckDB's native Python API.

**File layout:**
```
data/
  tradebot.duckdb        # main database
  raw/                   # downloaded raw files (EDGAR, congressional disclosures)
    edgar/
    congress/
```

---

## 4. Signal Processing: Pandas vs Polars

**Use Pandas 2.2.x with the Copy-on-Write default enabled.** Do not switch to Polars for this project.

Here is the reasoning:

| Criterion | Pandas 2.2 | Polars 1.42 |
|-----------|-----------|-------------|
| Data size at this scale | 5K rows/week across 50-100 tickers — fits in 10 MB RAM | Same |
| Performance difference | Irrelevant at this scale | 10x faster on 1M+ rows, meaningless here |
| Ecosystem integration | fredapi, yfinance, quantstats all return pandas objects | Must convert from/to pandas at every boundary |
| Learning cost | You already know it | New lazy API, different mental model |
| TA-Lib / pandas-ta | Natively pandas | Requires converting to numpy or pandas |
| alpaca-py | Returns pandas DataFrames | Same |

**The actual 2025 answer:** Polars is better for large-scale ETL. For a weekly-batch bot processing <1 million rows per run, the conversion friction costs more than the speedup gains. Use Pandas.

**DO enable Copy-on-Write in pandas 2.x** (it becomes default in 3.0 but is a warning in 2.x):
```python
import pandas as pd
pd.options.mode.copy_on_write = True
```

**Supporting math libraries:**
- `numpy` 2.x — comes with pandas, use for vectorized math
- `pandas-ta` 0.3.14b — technical indicators in pandas; more actively maintained than TA-Lib (which requires a C binary)
- `scipy` — for any statistical tests on signal quality (z-score normalization, etc.)

---

## 5. Scheduler

**Use APScheduler 3.11.x with the BackgroundScheduler.** This is the right tool for a solo side-project bot.

**Why not Celery:** Celery requires a message broker (Redis or RabbitMQ). That is two more services to run and debug. Celery is designed for distributed task queues with many workers. You have one machine, one process.

**Why not cron:** System cron cannot pass Python objects, has no built-in retry, and cannot be tested in pytest. You also lose the ability to trigger on market-day logic (skip weekends, skip holidays using `pandas-market-calendars`).

**Why not the new APScheduler 4.x:** APScheduler 4.x (currently in beta) is an async-first rewrite with a different API. The 3.x API is stable, documented, and everything you'll find in tutorials for the next two years.

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pandas_market_calendars as mcal

scheduler = BlockingScheduler()

# Run every Monday 7:00 AM ET (after weekend, before market open)
scheduler.add_job(
    run_weekly_pipeline,
    CronTrigger(day_of_week="mon", hour=7, minute=0, timezone="America/New_York"),
    id="weekly_pipeline",
    replace_existing=True,
)

scheduler.start()
```

Add market-calendar awareness inside the job, not in the trigger — simpler to test.

---

## 6. Alpaca SDK

**Use `alpaca-py` 0.43.5.** This is the official, current SDK. The old `alpaca-trade-api` (the one most tutorials pre-2023 use) is deprecated.

**Options support status (confirmed by package inspection):**
- `OptionHistoricalDataClient` — full support for bars, quotes, trades, snapshots, option chains
- `OptionLiveDataClient` — live streaming options quotes
- `TradingClient` — includes `exercise_options_position()` and contract lookup via `GetOptionContractsRequest`
- Order submission for options: `AssetClass.US_OPTION` enum exists; order types for options (market, limit, stop, stop_limit); time-in-force for options is `day` only
- Multi-leg (spreads): `OrderClass.MLEG` is supported

**Architecture recommendation for options-aware from day one:**

Define an abstract `ExecutionClient` interface now so you can slot in options orders later without changing signal code:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TradeOrder:
    symbol: str
    qty: float
    side: str  # "buy" | "sell"
    order_type: str = "market"
    asset_class: str = "us_equity"  # "us_option" when ready

class ExecutionClient(ABC):
    @abstractmethod
    def submit_order(self, order: TradeOrder) -> str: ...
    
    @abstractmethod
    def get_positions(self) -> list[dict]: ...
    
    @abstractmethod
    def get_account(self) -> dict: ...
```

**Paper trading:** Pass `paper=True` to `TradingClient`. Paper and live use different API keys. Store both in environment variables and select at startup.

```python
from alpaca.trading.client import TradingClient

client = TradingClient(
    api_key=os.environ["ALPACA_API_KEY"],
    secret_key=os.environ["ALPACA_SECRET_KEY"],
    paper=True,  # flip to False for live
)
```

---

## 7. Data Source Libraries

### Congressional STOCK Act Disclosures

There is no mature PyPI library for this. Use raw `httpx` to hit the Senate and House disclosure APIs:

- **Senate:** `https://efts.usaspending.gov/` or `https://disclosures.house.gov/` (House) or `https://efts.usaspending.gov/` is unreliable; the better maintained source is `https://disclosures-clerk.house.gov/`
- **Senate eFD:** Available as bulk XML downloads at `https://efts.senate.gov/` — download the quarterly ZIP, parse XML

**Practical approach:** The `quiverquant` data aggregator has a free tier for congressional trades. Alternatively, `OpenSecrets` and `TradeAlert` aggregate this. For a side project, pulling from Quiver Quant's free API is faster than parsing raw SGML.

### SEC EDGAR Form 4

Use `sec-edgar-downloader` 5.1.0 for bulk Form 4 pulls. For individual filings, you can also hit the EDGAR full-text search API directly:

```
https://efts.sec.gov/LATEST/search-index?q=%22Form+4%22&dateRange=custom&startdt=2025-06-01&enddt=2025-07-01&forms=4
```

EDGAR requires a `User-Agent` header with your name and email — failure to provide it results in IP bans. This is documented but many tutorials skip it.

```python
headers = {
    "User-Agent": "TradeBot derek@example.com",  # required by EDGAR
    "Accept-Encoding": "gzip, deflate",
}
```

### FRED Macroeconomic Data

`fredapi` 0.5.x is the standard. It wraps the St. Louis Fed API cleanly. Requires a free API key.

```python
from fredapi import Fred
fred = Fred(api_key=os.environ["FRED_API_KEY"])
gdp = fred.get_series("GDP")  # returns pd.Series
unemployment = fred.get_series("UNRATE")
```

Key series for macro signal: `UNRATE`, `CPIAUCSL`, `DGS10`, `T10Y2Y` (yield curve), `VIXCLS`.

---

## 8. Reporting

**Stack: Jinja2 3.1.6 → HTML → save as file. No PDF required.**

WeasyPrint 69.0 can generate PDFs from HTML but requires system-level `pango`, `cairo`, `fontconfig` dependencies. On macOS this works via Homebrew but adds friction. A weekly report as an `.html` file opened in the browser is sufficient.

```python
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import date

def render_weekly_report(context: dict, output_dir: Path) -> Path:
    env = Environment(loader=FileSystemLoader("templates/"))
    template = env.get_template("weekly_report.html")
    html = template.render(**context)
    
    filename = output_dir / f"report_{date.today().isoformat()}.html"
    filename.write_text(html)
    return filename
```

**Template structure:**
```
templates/
  weekly_report.html     # main report template
  partials/
    signal_table.html    # per-ticker signal breakdown
    recommendation.html  # buy/hold/sell card
```

For charts in the report: Use `plotly` 5.x with `fig.to_html(include_plotlyjs='cdn')` — embeds the chart as a self-contained `<div>` you include in the Jinja template. No matplotlib to file-to-embed pipeline needed.

**Markdown alternative:** Generate a `.md` file with `tabulate` for tables and save alongside the HTML. Useful for archiving in git.

---

## 9. Testing Financial Logic

**Framework:** `pytest` 8.x + `pytest-mock` 3.15.x

**Key testing libraries:**

| Library | Version | Purpose |
|---------|---------|---------|
| `pytest` | 8.x | Test runner |
| `pytest-mock` | 3.15.x | Mock/spy fixtures |
| `freezegun` | 1.5.5 | Freeze time for date-sensitive logic |
| `responses` | 0.26.x | Mock HTTP responses for `requests`; use `respx` for `httpx` |
| `hypothesis` | 6.x | Property-based testing for signal math |
| `respx` | 0.22.x | Mock `httpx` calls (responses does not support httpx) |

**Critical testing rules for financial logic:**

1. **Never test against live API calls in unit tests.** Mock every HTTP call with `respx` or load from fixture files.

2. **Test look-ahead bias explicitly.** Your signal computation must only use data available at the signal date. Write a test that checks no data after `signal_date` appears in signal inputs:

```python
# test_signals.py
from freezegun import freeze_time

@freeze_time("2025-01-06")  # Monday, market open
def test_momentum_signal_uses_no_future_data(price_fixture):
    signal = compute_momentum(price_fixture, signal_date=date(2025, 1, 6))
    # Assert no price data beyond 2025-01-03 (last Friday) was used
    assert signal.latest_price_date <= date(2025, 1, 3)
```

3. **Test score normalization.** Signals that feed into a composite score should be normalized. Test that extreme values (3-sigma outliers) are clamped, not NaN.

4. **Property-based tests for position sizing.** Use `hypothesis` to verify that your position sizer never produces a position larger than max_risk_per_trade regardless of inputs:

```python
from hypothesis import given, strategies as st

@given(
    account_equity=st.floats(min_value=100, max_value=1_000_000),
    signal_score=st.floats(min_value=-1.0, max_value=1.0),
)
def test_position_size_never_exceeds_risk_limit(account_equity, signal_score):
    size = compute_position_size(account_equity, signal_score, max_risk_pct=0.02)
    assert size <= account_equity * 0.02
    assert size >= 0
```

5. **Integration tests over unit tests.** Write one test per pipeline stage that runs the full stage against fixture data (not live). Fixture data = saved copies of real API responses.

---

## 10. Logging & Observability

**Use `loguru` 0.7.x.** It replaces the stdlib `logging` module entirely. No handler configuration boilerplate. Structured JSON output is one line:

```python
from loguru import logger

logger.add("logs/tradebot_{time}.log", rotation="1 week", serialize=True)
logger.info("Pipeline started", week=week_id, tickers=len(universe))
```

**No OpenTelemetry, no Prometheus for a side project.** A log file and a weekly report is observability sufficient for $100-500/week capital.

---

## 11. Configuration & Secrets

**Use `pydantic-settings` 2.x** (it comes with pydantic v2). Load all secrets from environment variables with type validation:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_paper: bool = True
    fred_api_key: str
    polygon_api_key: str = ""  # optional fallback
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

Store `.env` in `.gitignore`. Never hardcode credentials.

---

## 12. What NOT to Use

| Technology | Why Not |
|------------|---------|
| `alpaca-trade-api` | Deprecated; replaced by `alpaca-py` in 2022 |
| `backtrader` | Abandoned (no commits since 2022); do not build on it |
| `zipline-reloaded` | Pandas 1.x only, old event model, overkill for weekly signals |
| `QuantLib` | C++ binding, correct for options pricing, but extreme overhead for a first project |
| `celery` | Requires broker; overkill for one-machine weekly scheduler |
| `PostgreSQL` | Ops overhead unjustified at this scale |
| `SQLite` with pandas `read_sql` | Column-scan bottleneck; DuckDB is strictly better |
| `matplotlib` for reports | File-to-embed pipeline; use plotly instead |
| `requests` (raw) | Use `httpx`; both sync but httpx is async-capable when needed |
| Poetry | Slower than uv; no reason to use in 2025 |
| `pandas-stubs` + mypy strict | Useful but not for MVP; add after core pipeline works |

---

## 13. Complete Dependency Summary

```bash
# Install uv first
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project
uv init tradebot && cd tradebot

# Core runtime
uv add alpaca-py httpx tenacity pandas numpy polars duckdb apscheduler fredapi yfinance sec-edgar-downloader jinja2 loguru pydantic-settings pandas-market-calendars pandas-ta plotly tabulate respx

# Dev
uv add --dev pytest pytest-mock freezegun hypothesis ruff mypy
```

**Pinned versions (as of 2026-07-07 PyPI):**
- `alpaca-py` 0.43.5
- `httpx` 0.28.1
- `tenacity` 9.1.4
- `yfinance` 1.5.1
- `sec-edgar-downloader` 5.1.0
- `duckdb` 1.3.x (latest stable)
- `polars` 1.42.1 (install but use pandas; polars available for heavy transforms if needed)
- `apscheduler` 3.11.3
- `jinja2` 3.1.6
- `loguru` 0.7.x
- `pytest` 8.x
- `freezegun` 1.5.5
- `hypothesis` 6.x

---

## Sources

- PyPI live version data: `pip index versions <package>` run 2026-07-07
- alpaca-py 0.43.5 source inspection: `alpaca/data/historical/option.py`, `alpaca/trading/client.py`, `alpaca/trading/enums.py`
- yfinance 1.5.1 METADATA inspection: confirmed `curl_cffi>=0.15`, `websockets>=13.0` dependencies (1.x rewrite)
- APScheduler changelog: confirmed 3.x stable, 4.x beta/async-only rewrite
- Knowledge cutoff: August 2025; confirmed with live PyPI data July 2026
