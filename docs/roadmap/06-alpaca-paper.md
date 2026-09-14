# Step 6: Alpaca paper trading

## Objective

Mirror approved recommendations into Alpaca's fake-money environment while treating broker state as authoritative for execution.

## Work

1. Define a broker interface for account, position, order, cancellation, and fill operations.
2. Implement `ShadowBroker` against the local ledger and `AlpacaPaperBroker` using `alpaca-py`.
3. Add an explicit approval lifecycle: proposed → approved/rejected → submitted → partially filled/filled/canceled/rejected.
4. Use deterministic client order IDs and reject stale or already-submitted recommendations.
5. Poll or stream order status and store every broker event.
6. Reconcile local orders, fills, positions, and cash against Alpaca before and after submission.
7. Print PAPER prominently and hard-block any live endpoint in this stage.
8. Implement and separately verify paper stop orders.
9. Add commands:
   - `tradebot paper pending`
   - `tradebot paper approve <intent-id>`
   - `tradebot paper reject <intent-id>`
   - `tradebot paper reconcile`
   - `tradebot paper kill`
10. Document differences between local assumptions, Alpaca paper fills, and real markets.

## Tests

- All broker calls are mocked in CI.
- Submission replay cannot create duplicate orders.
- Partial fills and broker rejections reconcile correctly.
- Local divergence is detected and blocks new submissions.
- Live URLs and credentials are rejected.
- A manual sandbox checklist verifies the real paper API.

## Suggested commits

1. `refactor: define a broker-neutral execution boundary`
2. `feat: add explicit recommendation approval`
3. `feat: submit idempotent Alpaca paper orders`
4. `feat: reconcile paper broker state`
5. `docs: add Alpaca paper operations checklist`

## Exit criteria

Approved paper orders execute, reconcile, and report correctly across normal fills, partial fills, cancellation, and rejection scenarios.

## Not included

Live endpoints, options, margin, or short selling. Unattended paper submission remains locked until ten fills reconcile and an operator explicitly enables it.
