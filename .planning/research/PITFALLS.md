# Pitfalls Research — TradeBot

**Domain:** Python algorithmic trading bot (multi-signal, weekly cadence, small capital, Alpaca execution)
**Researched:** 2026-07-07
**Confidence:** HIGH for structural/code pitfalls; MEDIUM for signal/alpha pitfalls (academic literature through Aug 2025)

---

## Critical Pitfalls

Mistakes that cause rewrites, silent P&L corruption, or real money losses.

---

### Pitfall 1: Look-Ahead Bias in Signal Computation

**What goes wrong:** The signal computation uses data that would not have been available at the time the trade decision was made. All apparent alpha evaporates once discovered.

**Three common forms:**
1. **Filing date vs transaction date confusion.** A senator bought TSLA on March 1st but did not file until April 15th. If your signal fires on March 1st (the transaction date), you could not have known about it until April 15th. Any strategy using transaction date as signal trigger is a phantom strategy.
2. **Adjusted price retroactivity.** yfinance adjusted prices are recomputed retroactively when corporate actions occur. Re-downloading the same historical period after a stock split gives different numbers than the original download.
3. **Same-day data in forward simulation.** If your weekly script runs Sunday evening using Sunday's closing prices, the valid entry point is Monday's open — not Sunday's close.

**Prevention:**
- Store `filed_at` (when you became aware) separate from `transaction_date` (when the trade occurred). Only trigger signals on `filed_at`.
- Never re-download historical prices to fill gaps. Store every price fetch with a `fetched_at` timestamp and treat it as immutable.
- In shadow mode, record the signal computation timestamp. The trade entry price must be the next available open after that timestamp.
- Write an explicit unit test: `assert signal.latest_price_date <= signal.computation_date - timedelta(days=1)`.
- Use FRED's `realtime_start` and `realtime_end` API parameters to retrieve vintage data.

**Detection warning signs:**
- Shadow P&L looks suspiciously smooth — few losing weeks, consistent outperformance.
- Signal scores correlate strongly with next-day returns rather than returns over the following week.

**Phase:** Data ingestion + signal computation (Phase 1)

---

### Pitfall 2: Silent Data Pipeline Failures

**What goes wrong:** The ingestion pipeline runs without crashing but returns stale, partial, or empty data. The signal layer computes on this degraded data and generates recommendations that appear valid but are based on weeks-old information.

**Why it happens:**
- yfinance returns an empty DataFrame for a delisted ticker with no error.
- EDGAR EFTS rate-limiting returns a 429 that gets caught and logged but results in an empty filing list — indistinguishable from a genuinely quiet week.
- Congressional disclosure sites go offline for maintenance.
- FRED series are updated on a lag.

**Prevention:**
- Every fetcher must return a `FetchResult` that includes a `row_count` and a `freshness_date`.
- Alert if `row_count == 0` for any source that had >0 results in the previous run.
- Alert if `freshness_date` is more than N days behind expected freshness.
- Hard rule: if any critical data source returns zero rows for the week, skip trade generation entirely.

**Detection warning signs:**
- The same tickers appear in recommendations week after week with no variation.
- Signal scores barely change between runs.

**Phase:** Data ingestion (Phase 1-2)

---

### Pitfall 3: Paper/Live Mode Contamination

**What goes wrong:** A configuration error causes the system to submit live orders when intended to run in paper mode — or vice versa. The first variant causes real financial loss.

**Prevention:**
- Use **separate Alpaca accounts** for paper and live — Alpaca natively supports both. Separate API keys physically cannot reach each other's endpoints.
- Never store both paper and live keys in the same `.env` file simultaneously. Use separate `.env.paper` and `.env.live` files.
- Print the active mode prominently at startup: `[PAPER MODE — no real orders will be submitted]`.
- The weekly report must include the mode in the header, in large visible text.

**Detection warning signs:**
- Alpaca dashboard shows fills you did not intend.
- Account balance changes unexpectedly.

**Phase:** Execution layer (Phase 3+)

---

### Pitfall 4: Insider Transaction Code Conflation

**What goes wrong:** The signal treats all Form 4 transactions as bullish insider buying, including option exercises, stock awards, and gifts. These have very different (or opposite) signal implications.

**Form 4 transaction codes:**
- Code **P** (open market purchase) — genuine signal: insider voluntarily buying at market price
- Code **M** (option exercise) — neutral: insider acquiring shares they already had the right to buy
- Code **A** (award/grant) — neutral: shares received as compensation, no cash outlay
- Code **G** (gift) — not a buy signal
- Code **S** (open market sale) — not a buy at all

**Prevention:**
- Filter to transaction code **P only** for the primary signal (Lakonishok & Lee 2001, Jeng et al. 2003).
- Store the raw transaction code in your `raw_disclosures` table and filter at query time, not at ingestion time.
- Completely ignore insider sells (code S) — insiders sell for many reasons unrelated to outlook.
- Validate: inspect first week's raw EDGAR data manually. Code P should be a minority of total rows.

**Detection warning signs:**
- Insider signal firing for many tickers every week (true open-market purchases are rare).
- Signal correlating with quarterly earnings or stock grant cycles.

**Phase:** Signal computation (Phase 2)

---

## Moderate Pitfalls

---

### Pitfall 5: Survivorship Bias in Universe Construction

**What goes wrong:** You define your stock universe as "current S&P 500 members." Tickers that were removed (due to poor performance, mergers, bankruptcies) are excluded even though they were valid members when the signal fired.

**Prevention:**
- Fetch the universe each week from a current-members list. Each week's universe is what was in scope that week, not today.
- Store the weekly universe in a `universe_snapshots` table with a run_id.

**Phase:** Signal computation setup (Phase 2)

---

### Pitfall 6: EDGAR User-Agent Header Omission

**What goes wrong:** SEC EDGAR requires a `User-Agent` header containing your name and contact email. Omitting it results in IP-level throttling or bans.

**Prevention:**
- Add to every httpx request to any `*.sec.gov` endpoint:
  ```
  User-Agent: TradeBot your-email@example.com
  ```
- Store this as a config value, not a hardcoded string.

**Phase:** Data ingestion (Phase 1)

---

### Pitfall 7: APScheduler Job Mis-Trigger on Non-Market Days

**What goes wrong:** Scheduler fires on a US market holiday. Orders fail or queue for the next market day with stale sizing.

**Prevention:**
- Use `pandas-market-calendars` to check whether the run date is a valid market day before executing the pipeline.
- If scheduled Monday is a holiday, skip the week or defer to next valid market day.
- Implement inside the job function, not in the scheduler trigger — easier to test.

**Phase:** Scheduler setup (Phase 2)

---

### Pitfall 8: Kelly Criterion Oversizing Early

**What goes wrong:** You implement Kelly position sizing before having statistically meaningful data. Early shadow data has high variance — a 5-week run is not enough to estimate edge. Kelly computed on this data generates wildly large position sizes.

**Prevention:**
- Use flat fractional sizing (2-4% of account per position) for the first 6 months minimum.
- Do not calculate or apply Kelly until you have at least 30 completed round-trip trades.
- When introduced, use quarter-Kelly (25% of full Kelly) as the ceiling.

**Phase:** Execution (Phase 3+)

---

### Pitfall 9: Wash Sale Rule Violation

**What goes wrong:** Bot sells a position at a loss and then recommends buying the same ticker within 30 days. Under IRC Section 1091, this disallows the loss deduction.

**Prevention:**
- Order tracker must flag any proposed buy where a loss sale of the same ticker occurred within the previous 30 calendar days.
- Surface as a warning in the weekly report. Let the human decide — do not auto-block.
- Track acquisition dates and cost basis per lot, not just average cost.

**Phase:** P&L tracking (Phase 3)

---

### Pitfall 10: Single Table for Orders and Trades

**What goes wrong:** Using one table to represent both submitted orders (intent) and confirmed fills (execution). A submitted order may partially fill, fill at a different price, or be rejected.

**Prevention:**
- Maintain separate `orders` (status: pending/filled/cancelled/rejected) and `trades` (confirmed fills) tables.
- Compute P&L only from `trades` rows.
- Poll Alpaca for fill confirmations. Never assume a market order fills at the expected price.

**Phase:** Execution (Phase 3)

---

## Minor Pitfalls

---

### Pitfall 11: `responses` Library with `httpx`

**What goes wrong:** You try to mock `httpx` calls with the `responses` library — it doesn't work. `responses` monkeypatches `requests.adapters.HTTPAdapter` which `httpx` doesn't use.

**Prevention:** Use `respx` 0.22.x for mocking `httpx` calls.

---

### Pitfall 12: yfinance Adjusted Price Inconsistency Across Downloads

**What goes wrong:** Re-downloading historical prices to fill gaps yields different adjusted values than the original download due to retroactive split/dividend recalculation. Signals computed at different times use inconsistent price histories.

**Prevention:**
- Treat each price download as immutable. Store with a `fetched_at` timestamp.
- Never overwrite existing price rows. If a row exists for (ticker, date), do not update it.

---

### Pitfall 13: APScheduler 4.x API Break

**What goes wrong:** Installing `apscheduler` without pinning a version picks up 4.x — a near-total rewrite with a new async-first API. `BackgroundScheduler`, `CronTrigger`, and `add_job` don't exist in 4.x.

**Prevention:** Pin `apscheduler>=3.11,<4.0` in your dependencies.

---

### Pitfall 14: Confirmation Gate with Auto-Timeout Approval

**What goes wrong:** You add an auto-approval timeout to avoid missed weeks. This defeats the manual gate. One week you're unavailable and the system auto-approves a bad signal.

**Prevention:** Timeout must result in **skip, never auto-approve**. If no approval arrives by deadline, log "No approval received — skipping this week" and exit cleanly.

---

### Pitfall 15: Missing FRED `realtime_start` Parameter

**What goes wrong:** FRED returns the current best estimate of a series by default. GDP, CPI, and unemployment numbers are revised frequently — the number available in February for January GDP may differ from what was known in real-time.

**Prevention:** Use the `realtime_start` FRED API parameter set to the signal computation date when computing historical macro signals. The `fredapi` library exposes this via `realtime_start`.

---

## Phase-Specific Warning Map

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Data ingestion (EDGAR) | Missing User-Agent header causes IP ban | Add header from day one; store as config |
| Data ingestion (congressional) | Raw Senate XML/PDF parsing is brittle | Use Quiver Quantitative free API tier |
| Signal computation | Look-ahead bias on filing dates | Store `filed_at` separately; trigger on `filed_at` only |
| Signal computation | Form 4 transaction code conflation | Filter to code P at query time, not ingestion time |
| Shadow mode | Universe survivorship bias | Weekly universe snapshot table; no static index constituent list |
| Shadow mode | Stale data looks identical to "quiet week" | Freshness validation on every fetcher result |
| Paper trading | Paper/live mode contamination | Separate Alpaca accounts with separate API keys |
| Paper trading | APScheduler fires on market holidays | Market calendar check inside the job function |
| Execution | Conflating order submission with trade fill | Separate `orders` and `trades` tables |
| Execution | Auto-approval timeout | Timeout must result in skip, not approval |
| P&L tracking | Wash sale violations | Flag potential wash sales in report; per-lot cost basis |
| Position sizing | Kelly oversizing on insufficient data | Flat fractional sizing for first 6 months |

---

## Sources

- Lakonishok & Lee (2001) — Open-market purchase codes and signal quality
- Jeng, Metrick & Zeckhauser (2003) — Form 4 insider trading returns; transaction code specificity
- SEC EDGAR EFTS API documentation — User-Agent requirement, rate limits
- FRED API documentation — realtime_start / vintage data parameters
- yfinance known limitations — adjusted price retroactivity
- APScheduler changelog — 3.x vs 4.x API break
- Alpaca Markets API documentation — paper vs live account isolation
- IRC Section 1091 — US wash sale rule
