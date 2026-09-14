# Approved PoC decisions

These decisions define strategy version `0.1.0` and remain frozen during forward evaluation. Changes require a new strategy version and configuration hash.

## Operation

- Evaluate after every completed US trading session at 18:00 America/New_York.
- Orders generated from that evaluation are eligible for the next trading session's open.
- Evaluate exits daily.
- Add $250 of simulated capital once per week.
- Fail the whole daily decision run when required source or ticker coverage is incomplete.

## Candidate universe

- Begin with disclosures attributed to Nancy Pelosi, including spouse-owned transactions reported under her disclosure.
- Include qualifying purchase disclosures from the prior 180 calendar days.
- Keep owned symbols eligible until their positions close even if their disclosure ages out.
- Use manual CSV import for the first PoC behind a provider interface; add Quiver when credentials and free-tier coverage are confirmed.
- Convert purchased calls into bullish signals for the underlying stock.
- Sold calls reduce eligibility; purchased puts do not create long candidates.
- Trade underlying shares only. Options execution is outside the PoC.
- SPY is benchmark-only and is never ranked as a candidate.

## Strategy

- Start local shadow accounting with $10,000.
- Permit fractional shares, no margin, and no short selling.
- Select up to three highest-ranked unowned candidates per entry cycle.
- Size each new position at 3% of current strategy equity.
- Hold at most ten positions.
- Momentum raw score: 40% of 21-session return plus 60% of 63-session return.
- Insider raw score combines disclosed purchase value, distinct purchasers, and filing recency.
- Composite score: corporate-insider 4/7 and momentum 3/7 after cross-sectional normalization.
- Generate a new entry only for a new qualifying political disclosure or a rank improvement of at least two places.

## Exits and fills

- Fill at the next available market open with 10 basis points of unfavorable slippage.
- Charge zero commissions.
- Exit at an 8% stop-loss, after a 12-week maximum hold, or after two consecutive negative composite scores.
- Prevent re-entry for four weeks after a stop-loss.
- Account for splits and dividends when source data is available; surface missing action coverage.

## Alpaca paper

- Compute quantities from the $10,000 strategy allocation and mirror those quantities into the dedicated $100,000 Alpaca paper account.
- Ignore excess Alpaca paper buying power for sizing.
- Require manual approval initially.
- Permit automatic paper submission only after ten successfully submitted and reconciled paper orders.
- Always require paper endpoint locking, exposure limits, reconciliation, deterministic client order IDs, and a kill switch.
- Live submission is outside the PoC.

## Reports and service

- Generate local HTML and JSON reports; no notifications initially.
- Provide a platform-agnostic foreground service command.
- Let an external supervisor such as systemd, launchd, Docker, or another process manager restart and schedule the service.
- Keep strategy scheduling in America/New_York independent of host timezone.
