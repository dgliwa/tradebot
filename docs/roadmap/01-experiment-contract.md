# Step 1: Experiment contract

## Objective

Turn the strategy idea into an immutable, machine-readable contract before performance observations can influence its rules.

## Work

1. Add a versioned strategy configuration containing:
   - Strategy name and version
   - Starting cash and optional recurring contribution
   - Universe and benchmark
   - Weekly decision schedule and timezone
   - Signal parameters and weights
   - Selection count or score threshold
   - Position-sizing rule
   - Maximum positions and exposure
   - Entry, exit, stop-loss, and re-entry rules
   - Slippage, fees, dividends, and split handling
2. Add a `strategy_runs` table recording run ID, version, scheduled time, effective session, status, and diagnostics.
3. Validate the contract at startup and fail closed on contradictory settings.
4. Store a canonical configuration hash on each run.
5. Add `tradebot strategy show` to print the effective contract.

## Tests

- Invalid weights, schedules, sizing, and risk limits are rejected.
- Equivalent configuration produces the same hash.
- Any strategy change requires a new version/hash.
- Paper and live settings cannot silently alter strategy semantics.

## Suggested commits

1. `feat: define versioned strategy contract`
2. `feat: persist auditable strategy runs`
3. `test: verify strategy configuration invariants`

## Exit criteria

- No trading rule remains implicit.
- A run can identify exactly which strategy configuration produced it.
- The user approves the initial contract before signal implementation begins.

## Not included

Signal calculations, orders, portfolio accounting, or brokerage calls.
