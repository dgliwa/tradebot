<!-- GSD:project-start source:PROJECT.md -->

## Project

**TradeBot**

A Python-based algorithmic trading system that uses publicly available data to generate a profitable, semi-automated trading strategy targeting alpha over the S&P 500. The system runs in "shadow mode" (paper trading via Alpaca) indefinitely until the user gains confidence in the signals, then can switch to real-money execution with a manual confirmation gate.

**Core value:** A weekly signal report that tells the user exactly what to buy, why, and how much — with one-click paper or real execution via Alpaca API.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## 1. Project Tooling & Packaging

- `uv init tradebot` creates `pyproject.toml` + `.venv` in seconds
- `uv add <package>` handles resolution and lockfile (`uv.lock`)
- `uv run python -m tradebot` runs in the venv without activating it
- Forget virtualenv, pipenv, poetry for new projects — they are slower and more complex

# pyproject.toml (skeleton)

## 2. HTTP Clients & Data Ingestion

### Primary: `httpx` 0.28.x + `tenacity` 9.1.x

### Source-Specific Clients

| Data Source | Library | Version | Notes |
|-------------|---------|---------|-------|
| FRED macros | `fredapi` | 0.5.x | Thin wrapper, returns pandas Series. Works fine. |
| yfinance prices | `yfinance` | 1.5.1 | See reliability warning below |
| SEC EDGAR Form 4 | `sec-edgar-downloader` | 5.1.0 | Downloads raw SGML/XML, you parse it |
| Congress STOCK Act | raw `httpx` | — | No mature library; hit efts.usaspending.gov or senate.gov directly |
| Alpaca execution | `alpaca-py` | 0.43.5 | Official SDK |

### yfinance Reliability Warning (2025)

- Yahoo can change their API at any time with no notice. This has broken yfinance ~3 times in 2022-2024.
- No SLA, no uptime guarantee, reverse-engineered endpoint.
- Intraday data beyond 60 days requires a premium account.
- Options chain data via `Ticker.option_chain()` is available but reliability is lower than price data.

## 3. Data Storage

| Option | Verdict | Why |
|--------|---------|-----|
| SQLite | No | No columnar compression, slow on time-series range scans over millions of rows, no native ARRAY/LIST types |
| PostgreSQL | No | Massive ops overhead for a solo side project; you will spend time on pg_hba.conf, not on signals |
| DuckDB | Yes | Columnar, zero-ops, in-process, native Parquet/CSV import, SQL-complete, fast range scans on time-series |

## 4. Signal Processing: Pandas vs Polars

| Criterion | Pandas 2.2 | Polars 1.42 |
|-----------|-----------|-------------|
| Data size at this scale | 5K rows/week across 50-100 tickers — fits in 10 MB RAM | Same |
| Performance difference | Irrelevant at this scale | 10x faster on 1M+ rows, meaningless here |
| Ecosystem integration | fredapi, yfinance, quantstats all return pandas objects | Must convert from/to pandas at every boundary |
| Learning cost | You already know it | New lazy API, different mental model |
| TA-Lib / pandas-ta | Natively pandas | Requires converting to numpy or pandas |
| alpaca-py | Returns pandas DataFrames | Same |

- `numpy` 2.x — comes with pandas, use for vectorized math
- `pandas-ta` 0.3.14b — technical indicators in pandas; more actively maintained than TA-Lib (which requires a C binary)
- `scipy` — for any statistical tests on signal quality (z-score normalization, etc.)

## 5. Scheduler

# Run every Monday 7:00 AM ET (after weekend, before market open)

## 6. Alpaca SDK

- `OptionHistoricalDataClient` — full support for bars, quotes, trades, snapshots, option chains
- `OptionLiveDataClient` — live streaming options quotes
- `TradingClient` — includes `exercise_options_position()` and contract lookup via `GetOptionContractsRequest`
- Order submission for options: `AssetClass.US_OPTION` enum exists; order types for options (market, limit, stop, stop_limit); time-in-force for options is `day` only
- Multi-leg (spreads): `OrderClass.MLEG` is supported

## 7. Data Source Libraries

### Congressional STOCK Act Disclosures

- **Senate:** `https://efts.usaspending.gov/` or `https://disclosures.house.gov/` (House) or `https://efts.usaspending.gov/` is unreliable; the better maintained source is `https://disclosures-clerk.house.gov/`
- **Senate eFD:** Available as bulk XML downloads at `https://efts.senate.gov/` — download the quarterly ZIP, parse XML

### SEC EDGAR Form 4

### FRED Macroeconomic Data

## 8. Reporting

## 9. Testing Financial Logic

| Library | Version | Purpose |
|---------|---------|---------|
| `pytest` | 8.x | Test runner |
| `pytest-mock` | 3.15.x | Mock/spy fixtures |
| `freezegun` | 1.5.5 | Freeze time for date-sensitive logic |
| `responses` | 0.26.x | Mock HTTP responses for `requests`; use `respx` for `httpx` |
| `hypothesis` | 6.x | Property-based testing for signal math |
| `respx` | 0.22.x | Mock `httpx` calls (responses does not support httpx) |

# test_signals.py

## 10. Logging & Observability

## 11. Configuration & Secrets

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

## 13. Complete Dependency Summary

# Install uv first

# Initialize project

# Core runtime

# Dev

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

## Sources

- PyPI live version data: `pip index versions <package>` run 2026-07-07
- alpaca-py 0.43.5 source inspection: `alpaca/data/historical/option.py`, `alpaca/trading/client.py`, `alpaca/trading/enums.py`
- yfinance 1.5.1 METADATA inspection: confirmed `curl_cffi>=0.15`, `websockets>=13.0` dependencies (1.x rewrite)
- APScheduler changelog: confirmed 3.x stable, 4.x beta/async-only rewrite
- Knowledge cutoff: August 2025; confirmed with live PyPI data July 2026

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
