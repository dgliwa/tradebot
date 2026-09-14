# TradeBot

A local-first daily investing research and simulated-trading pipeline. The execution pipeline accepts pluggable research strategies through `TradingStrategy`; the first implementation is `PelosiStrategy`. The current build ingests validated market data, imports politician disclosures, produces recommendations, and maintains a local shadow portfolio. No command places real or Alpaca orders.

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

### Politician disclosure import

The initial provider is a strict manual CSV adapter. Export or create the disclosure file with these columns:

```text
source_id,politician,owner,ticker,transaction_type,asset_type,option_type,transaction_date,filed_at,amount_min,amount_max
```

Import a complete source extract and state the date through which it was checked:

```bash
uv run tradebot ingest congressional --file disclosures.csv --coverage-through 2026-09-13
```

Incomplete or stale congressional coverage blocks strategy runs.

## Recommendations and local shadow trading

```bash
# Fetch candidate data and store recommendations; never creates orders.
uv run tradebot run-daily --dry-run
uv run tradebot recommendations show

# Initialize and inspect the $10,000 local simulated account.
uv run tradebot shadow init
uv run tradebot shadow status

# Run the same daily research cycle and create/fill local simulated orders.
uv run tradebot run-daily --shadow

# Generate contribution-adjusted SPY comparison in JSON and HTML.
uv run tradebot report generate
```

Shadow orders become eligible at the next market open and include configured unfavorable slippage. Cash, contributions, orders, fills, positions, stops, cooldowns, dividends, and splits are persisted idempotently in DuckDB. The shadow path cannot submit broker orders.

## Alpaca paper orders

After adding paper API credentials to `.env.paper`, inspect and explicitly approve each intent mirrored from the local $10,000 strategy allocation:

```bash
uv run tradebot paper pending
uv run tradebot paper approve INTENT_ID
uv run tradebot paper reconcile
uv run tradebot paper status
```

The adapter is hard-locked to Alpaca's paper endpoint, uses deterministic client order IDs, ignores the paper account's excess buying power, and submits the exact local shadow quantity. `tradebot paper kill` blocks submissions immediately. Automatic submission cannot be enabled until ten fills reconcile successfully; it then requires the explicit `tradebot paper auto-enable` command. No Alpaca credentials are required for ingestion, recommendations, reports, or local shadow trading. See [`docs/alpaca-paper.md`](docs/alpaca-paper.md) for safety invariants and the credentialed sandbox checklist.

## Unattended operation

Run one cycle manually or keep the platform-neutral foreground service under your preferred supervisor:

```bash
uv run tradebot service run-once
uv run tradebot service run
uv run tradebot service status
```

A Docker deployment is included with `compose.yaml`. See [`docs/operations.md`](docs/operations.md) for container setup, health checks, backup/restore, clock requirements, and failure recovery.

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
