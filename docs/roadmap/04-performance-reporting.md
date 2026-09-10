# Step 4: Performance and reporting

## Objective

Make strategy behavior understandable and compare it fairly with SPY over the same cash-flow timeline.

## Work

1. Create a benchmark ledger using the same initial capital, contributions, decision dates, dividends, and valuation dates as the strategy.
2. Calculate:
   - Account equity and cash
   - Realized and unrealized P&L
   - Time-weighted and money-weighted return as appropriate
   - SPY return over matching cash flows
   - Excess return
   - Maximum drawdown
   - Turnover, exposure, hit rate, average win/loss, and slippage
   - Contribution by signal and position
3. Generate a local HTML report with a compact machine-readable JSON companion.
4. Include recommendations, explanations, data quality, warnings, orders, fills, positions, and run failures.
5. Add `tradebot report weekly` and `tradebot report open`.
6. Preserve report inputs so an old report can be regenerated exactly.

## Tests

- Return and drawdown calculations match hand-worked fixtures.
- Contributions are treated identically in strategy and benchmark.
- Dividends and splits do not create artificial alpha.
- Failed or incomplete runs are visible rather than omitted.
- Report totals reconcile to ledger totals.

## Suggested commits

1. `feat: track a cash-flow-matched SPY benchmark`
2. `feat: calculate shadow performance metrics`
3. `feat: render auditable weekly reports`

## Exit criteria

A weekly report answers what the bot knew, what it decided, what filled, why it decided it, and how the account performed versus SPY.

## Not included

Scheduling, notifications, or paper-broker execution.
