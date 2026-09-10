# TradeBot

A local-first weekly investing research pipeline. The current build initializes DuckDB and ingests validated daily prices and SEC Form 4 open-market purchases. Signal generation, reports, approvals, and Alpaca order execution are not implemented yet; no CLI command places trades.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.paper.example .env.paper
# Set SEC_USER_AGENT to an application name plus your real contact email.
uv run tradebot init-db
```

Paper and live modes default to separate databases. A database is permanently bound to the first selected mode, preventing accidental reuse across environments. Credentials are not needed for current ingestion commands.

## Ingestion

```bash
uv run tradebot ingest prices
uv run tradebot ingest insider
uv run tradebot ingest all
```

Commands print JSON and return `0` only when every requested ticker was checked successfully. Exit `2` means configuration or source coverage failed. Invalid or partial source results are not written.

Price ingestion requires 50 completed NYSE daily sessions for every configured ticker. Each fetch is stored as an immutable per-ticker snapshot; `latest_prices` selects a complete latest snapshot rather than mixing Yahoo adjustment vintages.

Insider ingestion scans the prior 90 calendar days using the SEC submissions index, its historical index files when relevant, and each filing's `primaryDocument`. A successful scan with zero code-P purchases is healthy. Malformed filings, unknown tickers, failed requests, and Form 4 amendments are reported as incomplete rather than treated as zero purchases. Accepted records retain the source URL and XML.

## Configuration

Select mode before loading its file:

```bash
TRADEBOT_MODE=paper uv run tradebot init-db  # reads .env.paper
TRADEBOT_MODE=live uv run tradebot init-db   # reads .env.live
```

Process environment values override the selected file. `TRADEBOT_MODE` accepts only `paper` or `live`; the Alpaca URL must match the mode. Files are loaded without modifying process-global environment state.

## Existing databases

`init-db` applies transactional numbered migrations and preserves old first-write price rows in `legacy_raw_prices`. Those rows are intentionally excluded from `latest_prices`; run price ingestion to create coherent snapshots. Back up a valued database before upgrading. Never point paper and live modes at the same file.

## Development

All tests are offline and use temporary/in-memory databases and mocked HTTP:

```bash
uv run pytest -q -o addopts=''
```

Real Yahoo and SEC compatibility still needs an operator smoke test because both external interfaces can change. Run it against a disposable paper database first; do not use `data/tradebot.duckdb` for development validation.
