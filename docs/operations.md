# TradeBot operations

TradeBot is a foreground, platform-neutral process. Run it directly, in Docker, or under any host supervisor (launchd, systemd, OpenRC, Kubernetes, Nomad, or a process manager). The application does not assume a particular operating system.

## Commands

```bash
# Execute one due local-shadow cycle and exit nonzero on failure.
uv run tradebot service run-once

# Poll continuously; only one successful cycle is recorded per market session.
uv run tradebot service run --poll-seconds 60

uv run tradebot service status
uv run tradebot service health
```

The loop holds a renewable DuckDB lease, catches job failures, records diagnostics, backs off, and retries. It derives the effective session from the NYSE calendar and the strategy timezone, so weekends and exchange holidays do not create phantom runs. A cycle missed while the host is down runs on restart.

## Container

```bash
cp .env.paper.example .env.paper
# Set SEC_USER_AGENT and keep TRADEBOT_DB_PATH under /app/data.
docker compose up --build -d
docker compose logs -f tradebot
```

`data/` and `reports/` are host-mounted. The image never contains `.env` files or database contents.

## Clock and timezone

Keep the host clock synchronized with NTP. Decisions are stored in UTC and interpreted using the IANA timezone in `strategy.toml` (`America/New_York` by default). Do not compensate manually for daylight-saving changes.

## Backup and restore

1. Stop the service so DuckDB has no writer.
2. Copy the configured `.duckdb` file and `reports/` directory together.
3. Record the application commit and `strategy.toml` alongside the backup.
4. To restore, keep the service stopped, replace both artifacts, run `tradebot init-db`, then inspect `tradebot service status` before restarting.

Never copy a database while a service process is writing it. Paper and live databases must remain separate.

## Failure recovery

1. Run `tradebot service status` and inspect `diagnostics` and the latest report.
2. Correct source coverage, configuration, disk, network, or credential failures.
3. Run `tradebot service run-once`. Deterministic strategy runs, orders, fills, contributions, benchmark entries, and reports make retries idempotent.
4. If the lock belongs to a dead process, wait for its lease to expire. Do not delete ledger rows manually.

No notification channel is configured by design; operators review status and reports directly.
