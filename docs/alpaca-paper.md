# Alpaca paper operations

Alpaca is an optional mirror of the local $10,000 strategy allocation. The local shadow ledger remains the research baseline; Alpaca's extra paper buying power is ignored. The adapter submits only stocks, never options, with the exact fractional quantity from the linked shadow order.

## Safety invariants

- `TRADEBOT_MODE` must be `paper`.
- The configured endpoint must be exactly `https://paper-api.alpaca.markets`.
- The SDK is always constructed with `paper=True`.
- Every order uses a deterministic `tradebot-...` client order ID.
- Existing broker orders are reconciled before a submission.
- Symbol, side, requested quantity, filled quantity, and average fill price are validated against the approved intent.
- `tradebot paper kill` blocks manual and automatic submissions.
- Automatic submission requires ten uniquely counted filled paper orders plus a separate `paper auto-enable` command.

## Initial manual workflow

Run the daily shadow cycle after the market session, then approve before the next open:

```bash
uv run tradebot run-daily --shadow
uv run tradebot paper pending
uv run tradebot paper approve INTENT_ID
uv run tradebot paper reconcile
uv run tradebot paper status
```

Use `paper reject INTENT_ID` to reject an awaiting intent. Canceled, rejected, partial, and completed broker observations remain in the database. If reconciliation detects a missing or divergent broker order, submission fails closed.

## Sandbox checklist (requires credentials)

This was not run during offline implementation because no API key was available.

1. Create fresh paper API credentials and put only those credentials in `.env.paper`.
2. Confirm `paper status` prints the paper endpoint and `auto_enabled: false`.
3. Use a disposable paper database and import current congressional coverage.
4. Run `run-daily --shadow`; inspect the report and intended quantity.
5. Approve one liquid-symbol intent during market hours.
6. In Alpaca, confirm the client ID prefix, side, symbol, quantity, and paper account.
7. Run `paper reconcile`; compare the stored filled quantity and average price.
8. Exercise `paper kill` and confirm approval is blocked.
9. Cancel or reject an intent and confirm its terminal state is retained.
10. Leave automation disabled until ten fills have reconciled without divergence.

## Paper-versus-live limitations

Paper fills may be faster or more favorable than live fills and do not establish production execution quality. Queue position, liquidity, halts, price improvement, partial fills, and buying-power behavior may differ. The local model applies fixed slippage; Alpaca uses its simulated fill model, so the two performance series will not match exactly. Promotion gates must therefore evaluate operational reconciliation separately from investment performance.
