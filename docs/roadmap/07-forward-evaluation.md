# Step 7: Forward evaluation

## Objective

Operate a frozen strategy long enough to evaluate reliability and gather preliminary evidence without fitting rules to recent outcomes.

## Work

1. Freeze the strategy version for a declared evaluation window.
2. Run local shadow for an initial operational period.
3. Run local shadow and Alpaca paper in parallel to measure fill-model differences.
4. Record weekly observations without changing strategy parameters.
5. Hold monthly reviews covering:
   - Data and scheduler reliability
   - Recommendation stability
   - Local versus broker fill differences
   - Return and drawdown versus SPY
   - Turnover, slippage, concentration, and signal contribution
   - Incidents and manual interventions
6. Define change control: proposed changes create a future strategy version and never rewrite prior results.
7. Produce a final go/no-go report for continued paper testing—not automatic live promotion.

## Suggested timeline

- Weeks 1–4: local shadow only; fix operational defects
- Weeks 5–12: shadow and Alpaca paper in parallel
- Weeks 13–26: frozen forward test if earlier operation is stable

Eight weeks can show operational reliability but is generally too short to establish durable alpha.

## PoC success criteria

- At least four consecutive scheduled runs complete without manual database repair.
- Required data coverage and failed-run behavior are visible.
- Recommendation, order, fill, and ledger state are fully auditable.
- Local and Alpaca paper positions reconcile or have explained differences.
- Benchmark calculations use matching dates and cash flows.
- No accidental live submission path exists.

## Before any future live-money discussion

Require a separately approved policy covering minimum paper duration, return versus SPY, maximum drawdown, gate reliability, incident history, position limits, emergency shutdown, taxes, and acceptance of paper/live fill differences.
