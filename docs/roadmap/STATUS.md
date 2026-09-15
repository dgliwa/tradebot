# PoC implementation status

## Implemented

1. **Frozen experiment contract** — typed TOML configuration, immutable hashes, daily run keys, and paper/live database isolation.
2. **Pluggable research strategies** — infrastructure depends on `TradingStrategy`; `PelosiStrategy` implements politician-led candidates, momentum, corporate-insider scoring, and entry triggers.
3. **Political data boundary** — strict, atomic, idempotent manual CSV imports with explicit source-coverage dates and stocks/options direction handling.
4. **Daily recommendations** — completed-NYSE-session evaluation, no look-ahead snapshots, required SPY coverage, explainable component scores, and replay-safe persistence.
5. **Local shadow trading** — $10,000 allocation, $250 weekly contributions, 3% fractional positions, no margin/shorting, next-open slippage, stop/max-hold/negative-score exits, cooldowns, immutable fills, and automated Yahoo split/dividend ingestion and application.
6. **Performance reports** — cash-flow-matched SPY ledger, time/money-weighted metrics, drawdown, P&L, turnover/exposure/win metrics, JSON/HTML artifacts, and exact stored report payloads.
7. **Platform-neutral operation** — foreground one-shot/loop service, market-calendar scheduling, leases, retries/backoff, health/status, Docker packaging, and an operations runbook.
8. **Guarded Alpaca paper path** — exact-quantity intents, explicit approve/reject, paper-endpoint lock, deterministic client IDs, stale/divergent-order rejection, reconciliation events, kill switch, and automation locked behind ten reconciled fills plus explicit enablement.
9. **Forward evaluation gates** — 12-week minimum/26-week target shadow period, SPY outperformance, 15% drawdown abort, session/source reliability, and separate 8-week paper/10-fill gates. No gate promotes to live automatically.

## Outstanding operational work

- Obtain a fresh, complete politician-disclosure CSV and keep its coverage date current. Implement and validate the Quiver provider only after credentials and free-tier coverage are available.
- Set a real contact `SEC_USER_AGENT`, then run `tradebot smoke-data --ticker AAPL` from a networked operator host. The command performs no database writes; CI intentionally uses mocks. The implementation host could not reach Yahoo, so a successful live probe remains outstanding.
- Obtain Alpaca paper API credentials and complete [`docs/alpaca-paper.md`](../alpaca-paper.md)'s sandbox checklist. No real broker call has been made.
- Deploy the service on the chosen host, configure backups/clock monitoring, and observe daily reports.
- Accumulate the required 12–26 weeks of frozen forward data and at least 8 weeks of reconciled Alpaca paper operation. These durations cannot be compressed by implementation work.

## Deliberately not implemented

- Live brokerage endpoints or live-money order submission.
- Options trading, margin, short selling, automatic parameter tuning, or report notifications.
- Claims of strategy profitability. The current weights, thresholds, and politician thesis remain hypotheses until the forward gates have enough evidence.
