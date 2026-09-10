# TradeBot proof-of-concept roadmap

## Goal

Run a reproducible weekly strategy with fake money over time, first through a deterministic local shadow portfolio and then through Alpaca paper trading. Every recommendation, order, fill, and performance result must be reconstructable from stored data.

## Current baseline

- Validated Yahoo daily-price ingestion with complete per-ticker snapshots
- Validated SEC Form 4 purchase ingestion with source provenance
- Transactional DuckDB migrations and writes
- Isolated paper/live configuration
- `tradebot init-db` and `tradebot ingest` commands
- Offline test suite and CI

No signal, simulated portfolio, report, scheduler, approval, or broker integration exists yet.

## Delivery sequence

| Step | Deliverable | Main exit condition |
|---|---|---|
| [1](01-experiment-contract.md) | Frozen experiment contract | Every trading and measurement rule is explicit and versioned |
| [2](02-weekly-signals.md) | Weekly signals and rankings | Dry run creates reproducible, explainable recommendations |
| [3](03-shadow-portfolio.md) | Local fake-money brokerage | Orders fill at later market opens and accounting reconciles |
| [4](04-performance-reporting.md) | Audit and performance report | Every result can be traced to inputs, decisions, and fills |
| [5](05-automation.md) | Idempotent scheduled operation | Four unattended weekly cycles complete without duplicate work |
| [6](06-alpaca-paper.md) | Alpaca paper execution | Approved paper orders and broker reconciliation work reliably |
| [7](07-forward-evaluation.md) | Forward-test evaluation | Frozen strategy accumulates enough evidence for a go/no-go review |

## Engineering rules

- Implement steps in order; later steps depend on earlier invariants.
- Use numbered transactional migrations for schema changes.
- Keep data availability time separate from event time to prevent look-ahead bias.
- Never write recommendations when required source coverage is incomplete.
- Make every weekly run and broker request idempotent.
- Store `strategy_version` on runs and decisions.
- Use deterministic IDs derived from stable business keys.
- Keep local shadow, Alpaca paper, and eventual live state explicitly separated.
- Add integration tests for each happy path and important failure boundary.
- Deliver each step through small conventional commits.

## Proof-of-concept boundary

A successful PoC runs the frozen strategy weekly with local fake money, produces an auditable report, and can optionally mirror approved orders into Alpaca paper. It does **not** prove durable alpha, permit live trading, trade options, or automatically tune strategy parameters.
