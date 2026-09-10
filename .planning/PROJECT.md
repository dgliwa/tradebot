# TradeBot

## What This Is

A Python-based algorithmic trading system that uses publicly available data to generate a semi-automated strategy targeting alpha over the S&P 500. It first forward-tests hypothetical next-open positions in a local shadow portfolio, then separately graduates to Alpaca paper trading, and only later to real-money execution with a manual confirmation gate.

**Core value:** A weekly signal report that tells the user exactly what to buy, why, and how much — with one-click paper or real execution via Alpaca API.

## Context

- **Investing style:** Satellite portfolio on top of normal recurring investments. Risk tolerance is high. This competes mentally with poker, MTG cards, horse betting — meaning: asymmetric bets are fine, drawdowns are acceptable, the bar is "beat SPY over 1 year."
- **Capital:** $100–$500 per week investment unit
- **Horizon:** 1-year benchmark period. Beat SPY raw returns.
- **Execution mode:** Report + manual confirm. Bot generates weekly signal report; user approves before any order is placed.
- **Data philosophy:** All free/public sources only. No paid data subscriptions (to avoid eating into returns like Quantbase fees do).

## Signal Stack

Three layered signals, all sourced from free public APIs:

| Signal | Source | Latency | Edge |
|--------|--------|---------|------|
| Congressional disclosures | Quiver Quantitative free API | ~45 days | Political insider knowledge |
| Corporate insider buys (Form 4) | SEC EDGAR | 2 days | Executive skin-in-the-game |
| Macro regime filter | FRED (Federal Reserve) | Daily | Don't buy growth in rate-hike cycles |

Price data: yfinance (free). Momentum as secondary filter on top of disclosure signals.

## Architecture Vision

- **Data ingestion layer:** API clients/pollers for Quiver congressional disclosures, SEC EDGAR Form 4, FRED macro indicators, and yfinance prices
- **Signal engine:** Score and rank tickers based on combined signals
- **Report generator:** Weekly markdown/HTML report with ranked trade recommendations
- **Execution layer:** Alpaca SDK with paper/live toggle — options-aware architecture from day one, stocks-only execution initially
- **Shadow mode:** Local hypothetical next-open positions; P&L tracked and compared to a same-date SPY benchmark before Alpaca paper trading begins

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Alpaca as broker | Free API, built-in paper trading, fractional shares, options-capable | Confirmed |
| Python | Standard for quant/data work, best library ecosystem | Confirmed |
| Free data only | Paid data eats into alpha; public disclosures are the edge | Confirmed |
| Multi-signal blend | Political signal alone is lagged; diversified signals reduce timing risk | Confirmed |
| Report + manual confirm | Avoids runaway automation bugs; user stays in control | Confirmed |
| Options-aware architecture | Design for options (calls/puts) from day one, even if stocks-only at first | Confirmed |
| Staged promotion | Local shadow → 8+ weeks Alpaca paper → live only after defined return, drawdown, and gate checks | Confirmed |

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Ingest Congressional trading disclosures from the Quiver Quantitative free API
- [ ] Ingest SEC EDGAR Form 4 insider buy filings
- [ ] Ingest FRED macro indicators (interest rates, regime classification)
- [ ] Fetch price and momentum data via yfinance
- [ ] Score and rank tickers using combined multi-signal model
- [ ] Generate weekly trade recommendation report (markdown/HTML)
- [ ] Integrate with Alpaca API for paper and live order execution
- [ ] Shadow mode: track hypothetical next-open P&L and compare to a same-date SPY benchmark
- [ ] Manual confirmation gate before any order executes
- [ ] Options-aware data model (support calls/puts in instrument schema)
- [ ] Simple CLI or web dashboard to view report and approve trades
- [ ] Cost/tax modeling: estimate net returns after commissions and short-term capital gains

### Out of Scope

- Paid data sources — adds recurring cost that must be offset by alpha
- Fully autonomous execution without confirmation — too risky for v1
- High-frequency trading — not viable at $100-500/week unit size
- Backtesting engine (v2) — validate signals in shadow mode first, backtest later

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-07 after initialization*
