# Step 2: Daily signals and recommendations

## Objective

Produce reproducible rankings after each completed trading session using only information available at the decision timestamp.

## Work

1. Persist the daily politician-led universe snapshot before calculating signals.
2. Implement momentum features from coherent `latest_prices` snapshots:
   - Short and medium lookback returns
   - Optional volatility penalty
   - Explicit handling of insufficient history
3. Implement insider features using `filed_at` as the availability date:
   - Purchase value when price is available
   - Number of distinct purchasers
   - Filing recency
   - Neutral result for a healthy scan with no purchases
4. Normalize component scores cross-sectionally without allowing future data into the run.
5. Combine active signals using the approved strategy contract.
6. Persist component values, normalized scores, weights, composite score, rank, and explanation.
7. Add `tradebot run-daily --dry-run` and `tradebot recommendations show`.
8. Refuse recommendation creation when required ticker/source coverage is incomplete.

## Tests

- Known fixtures produce exact feature and rank outputs.
- Data filed after the decision timestamp is excluded.
- Equal values and empty insider activity are deterministic.
- Missing or stale prices invalidate the run.
- Re-running the same strategy/session is idempotent.
- Ranking explanations reconcile to the composite score.

## Suggested commits

1. `feat: snapshot the weekly strategy universe`
2. `feat: compute momentum signals`
3. `feat: compute availability-safe insider signals`
4. `feat: rank and explain weekly recommendations`
5. `feat: expose weekly dry-run commands`

## Exit criteria

A dry run creates one immutable recommendation set whose inputs, timing, and score arithmetic can be independently reconstructed.

## Not included

Orders, fills, cash accounting, or broker integration.
