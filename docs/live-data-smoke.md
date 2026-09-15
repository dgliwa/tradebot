# Live data smoke test

Run this only from a host with outbound HTTPS access. It probes one ticker against Yahoo prices, Yahoo corporate actions, and SEC EDGAR without opening or writing the TradeBot database.

1. Copy `.env.paper.example` to `.env.paper`.
2. Set `SEC_USER_AGENT` to an application name and a real monitored contact email. Alpaca credentials are not required.
3. Run:

```bash
uv run tradebot smoke-data --ticker AAPL
```

Success returns three JSON summaries with no errors and exit code `0`. A source failure returns exit code `2`. Zero insider purchases or corporate actions is healthy when the source coverage date is present.

The test should be run before initial deployment and after dependency upgrades. Do not run it in offline CI: Yahoo is unofficial and network availability is not a deterministic test fixture.

The implementation environment could not reach `fc.yahoo.com` on 2026-09-15, and the probe correctly failed closed without writing a database. A successful operator-host run remains required.
