# Step 3: Local shadow portfolio

## Objective

Simulate fake-money trading in DuckDB without using broker APIs or same-bar information.

## Work

1. Introduce a broker-neutral order and fill domain model.
2. Add shadow accounts, cash ledger, positions, orders, fills, and corporate-action records.
3. Generate orders from approved recommendation sets and the strategy sizing rules.
4. Fill market orders at the next completed market session's open plus configured slippage.
5. Support rejected orders, insufficient cash, fractional quantities, partial exits, and deterministic order IDs.
6. Mark positions at coherent latest prices and calculate realized/unrealized P&L.
7. Implement stop-loss evaluation without using prices unavailable at evaluation time.
8. Apply splits and cash dividends consistently to positions and the benchmark.
9. Add commands:
   - `tradebot shadow create`
   - `tradebot shadow submit <run-id>`
   - `tradebot shadow settle`
   - `tradebot shadow status`
10. Ensure replaying any command cannot duplicate cash movements, orders, or fills.

## Tests

- Buy, sell, rejection, stop, split, and dividend scenarios reconcile to the cent.
- Recommendations never fill on their decision bar.
- Slippage is applied in the unfavorable direction.
- Cash cannot become negative unless margin is explicitly enabled.
- Position quantity equals the fill ledger.
- Repeated settlement is idempotent.
- A multi-week integration fixture produces an exact ending balance.

## Suggested commits

1. `feat: add shadow account and immutable ledger`
2. `feat: generate sized shadow orders`
3. `feat: settle next-open simulated fills`
4. `feat: track positions stops and corporate actions`
5. `test: verify multi-week shadow accounting`

## Exit criteria

A deterministic multi-week scenario starts with cash, executes recommendations at later opens, and exactly reconciles cash, positions, and P&L.

## Not included

Alpaca calls or unattended scheduling.
