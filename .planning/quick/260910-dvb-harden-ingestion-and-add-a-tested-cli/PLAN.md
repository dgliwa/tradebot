# Reliable ingestion and runnable CLI

Status: complete

GSD quick initialized via `query init.quick`. Plan, implementation and verification are performed directly in this session to honor the user's no-subagent request.

## Scope and decisions

- No signals, brokerage calls or live execution. Preserve the existing local database; test upgrades on temporary copies/fixtures only.
- Fetch health is independent of event count. A successfully scanned insider window with no purchases is valid. Price health requires per-ticker coverage, finite OHLCV, enough history and the latest completed NYSE session.
- Adjusted prices are stored as immutable, complete per-ticker snapshots. A latest view selects one snapshot, never mixes adjustment vintages. Legacy first-write rows are preserved but excluded from this view until refetched.
- Disclosure amendments are detected and reported as unsupported rather than silently scored twice. Actual filing documents and historical submission lists are resolved; raw XML is retained for accepted purchase records.
- Explicit settings loading and database lifecycle, safe mode/endpoint pairing and separate default paper/live databases. UTC-aware timestamps.

## Tasks

1. Harden config, result contracts, record validation and transactional storage/migrations. Test fresh schema, legacy upgrades, rollback and snapshot selection.
2. Harden price/SEC fetchers with deterministic clock/network tests, calendar freshness, coverage reporting and malformed-data handling.
3. Add CLI, fetch-to-write integration tests, README and CI; record actual validation and remaining limitations in planning state. Commit logical chunks; PR targets main.

## Verification

Completed verification:

- `uv run pytest -q -o addopts=''` — 65 passed
- `uv run tradebot --help` — CLI command surface rendered
- fresh temporary-file `tradebot init-db` — succeeded and was removed
- `uv build` — sdist and wheel built
- `python -m compileall -q tradebot` and `git diff --check` — passed

No live ingestion or writes to `data/tradebot.duckdb` were performed. Residual risk: real SEC/Yahoo source compatibility still requires a user-run smoke test; Form 4 amendment reconciliation is intentionally flagged rather than automated.
