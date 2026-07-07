# Features Research — TradeBot

**Domain:** Python algorithmic trading bot (multi-signal, weekly cadence, small capital)
**Researched:** 2026-07-07
**Overall confidence:** MEDIUM (training knowledge through Aug 2025; no live search available)

---

## Table Stakes — The System Is Useless Without These

### 1. Data Pipelines (Non-Negotiable)

#### Congressional STOCK Act Disclosures
- **Source:** House disclosure CSVs at disclosures.house.gov + Senate eFD at efts.senate.gov
- **Non-negotiable behavior:** Disclosures have a 45-day filing window after the transaction. You must record the **filing date** separately from the **transaction date** and never use transaction date as signal trigger (look-ahead bias). Any signal must be based on information available at filing time.
- **Practical reality:** House disclosures come as periodic CSV dumps. Senate filings are HTML/PDF with no structured API. Plan for HTML parsing + PDF extraction for Senate. Quiver Quantitative aggregates both into a clean API (free tier available) — strongly consider using it instead of raw scraping.
- **Minimum pipeline:** Fetch new filings weekly, normalize to schema (legislator, ticker, transaction_type, amount_range, filed_date, transaction_date), deduplicate, store.

#### SEC EDGAR Form 4 Insider Filings
- **Source:** EDGAR full-text search (EFTS) at efts.sec.gov/LATEST/search-index?q=%22form-type%3A4%22 + individual filing XML
- **Non-negotiable behavior:** Distinguish buy types: open market purchases (Table I, code P) are the high-value signal. Option exercises (code M), gifts (code G), and automatic plan purchases (code A) have much weaker or negative signal. Filter to purchase code P only for primary signal.
- **Rate limit:** EDGAR enforces 10 req/sec max and requires a User-Agent header identifying your app. Violating this gets your IP blocked.
- **Minimum pipeline:** Poll EFTS for new Form 4s weekly, parse XML for transaction type code and shares/value, store normalized records with CIK, ticker, filing date, transaction date, transaction code, shares, price.

#### FRED Macroeconomic Indicators
- **Source:** api.stlouisfed.org/fred/series/observations — free API key from fred.stlouisfed.org
- **Non-negotiable behavior:** FRED data is revised retroactively. Use the `realtime_start` and `realtime_end` parameters to get vintage data (what was known at a given point in time) to avoid look-ahead bias in macro signals.
- **Key series:** FEDFUNDS (fed rate), T10Y2Y (yield curve inversion), UMCSENT (consumer sentiment), VIXCLS (VIX from FRED), UNRATE (unemployment), CPI.
- **Minimum pipeline:** Weekly fetch of ~6-8 series, store with retrieval timestamp, compute simple regime flags (yield curve inverted Y/N, VIX above 20 Y/N, etc.).

#### Price Data (yfinance)
- **Non-negotiable behavior:** yfinance returns adjusted prices by default for historical data. Critically: adjusted prices are retroactively recalculated on splits/dividends. If you download today's historical data and again in 6 months, prices for the same dates may differ. This means you must snapshot prices at download time and never re-download history to "fill gaps" — you'll get subtly different numbers.
- **Minimum pipeline:** Weekly OHLCV download for universe of ~50-200 tickers, store immutably with download timestamp, compute 12-month and 1-month returns for momentum, 20-day and 200-day SMA.

---

### 2. Minimum Viable Signal Model

Three signals combined linearly is sufficient to start. More is overfitting risk.

**Signal A — Insider Purchase Score (Form 4)**
- Count of open-market buy transactions (code P) in the last 30 days for the ticker
- Weight by insider rank: CEO/CFO buys count more than VP buys
- Normalize to 0-1 across universe

**Signal B — Congressional Buy Score (STOCK Act)**
- Count of net buy disclosures in the last 60 days (use filing date, not transaction date)
- Raw count is sufficient; cluster buys (multiple legislators buying same ticker) amplify signal
- Normalize to 0-1

**Signal C — Price Momentum Score**
- 12-1 momentum: return from 12 months ago to 1 month ago (drop most recent month to avoid short-term reversal noise)
- Rank within universe, normalize to 0-1

**Composite Score:** 0.4 * Signal_A + 0.3 * Signal_B + 0.3 * Signal_C

Macro regime filter (not a signal, a gate): if yield curve inverted AND VIX > 25, reduce all position sizes by 50%. This is a veto on the model, not a ranking input.

**Do not add more signals until you have 3 months of forward-testing data.** Every additional signal is a new overfitting vector.

---

### 3. Confirmation / Approval Gate (Non-Negotiable)

The approval gate is what separates this from a fully automated bot that can lose money while you sleep.

**Minimum gate requirements:**
- Weekly report generated Sunday evening (before Monday open)
- Report lists proposed trades: ticker, direction, size, signal breakdown, reasoning
- Email or Slack message with report summary is sent to you
- A manual YES/NO approval is required before any order is submitted to Alpaca
- The bot must have a hard timeout: if no approval received by Monday 9:30 AM ET, it skips that week entirely — it does not auto-approve
- A "reject individual trade" option (approve 3 of 5 proposed trades, not all-or-nothing)

**Implementation:** A simple HTTPS endpoint that accepts a signed token + approval decision. Or even simpler: a YAML/JSON file on disk that you edit; the bot reads it at 9:00 AM and only proceeds if the file contains a valid approval for that week's batch.

---

### 4. P&L Tracking for Shadow Mode Validation (Non-Negotiable)

Shadow mode means the system generates signals and hypothetical trades but submits nothing to Alpaca. You compare shadow P&L against SPY.

**Minimum tracking:**
- Record every "would have bought" and "would have sold" trade with timestamp, theoretical entry price (next-day open after signal), and theoretical exit (next week's close or stop trigger)
- Track cash separately from positions (don't assume infinite capital)
- Compute weekly return for shadow portfolio vs SPY weekly return
- Track trade win rate, average gain on winners, average loss on losers (expectancy)
- Track maximum drawdown at the shadow portfolio level
- Run minimum 8 weeks of shadow mode before going live — this is not optional

**Promotion criteria to live trading (hard gates):**
- Shadow portfolio beat SPY over the shadow period (any positive alpha)
- Shadow drawdown did not exceed 15% of starting capital
- Win rate >= 40% (with positive expectancy even at 40% if average win > average loss)
- At least 10 completed round-trip trades (not just open positions)

---

## Differentiators — Competitive Advantage vs Just Buying SPY

### Which Alpha Signals Have the Strongest Academic Backing

**Congressional STOCK Act signals (HIGH confidence this exists, level of edge debated)**
- Abnormal returns to congressional trades were documented pre-STOCK Act (Ziobrowski et al. 2004, 2011 found senators beat market by 85 bps/month, representatives by 55 bps/month)
- Post-STOCK Act (effective 2012) the edge narrowed but studies (Eggers & Hainmueller, Karadas 2018) still find statistically significant positive abnormal returns of 3-8% annually for mimicking congressional buys
- The edge is concentrated in: (1) smaller/less-liquid stocks where information advantage is more persistent, (2) committee members trading in their committee's sector, (3) buys clustered across multiple legislators
- Signal decay: returns are elevated for roughly 60-90 days post-filing. After 90 days the edge fades

**SEC Form 4 Insider Buying (HIGH confidence, strong academic literature)**
- Open-market purchases (code P) by corporate officers have persistent positive abnormal returns: Lakonishok & Lee (2001), Jeng et al. (2003) document 5-10% annual alpha for the top quintile of insider buy signals
- Cluster buys (multiple insiders at same firm buying within 30 days) are the strongest sub-signal
- CEO/CFO buys outperform VP/Director buys
- Buys at 52-week lows outperform buys at highs
- Signal decay: strongest in first 30 days, meaningful for 6 months, fades by 12 months
- Sells are much noisier — insiders sell for many reasons (taxes, diversification). Ignore insider sells entirely.

**Price Momentum (MEDIUM-HIGH confidence)**
- One of the most replicated factors in finance: Jegadeesh & Titman (1993), Carhart (1997)
- 12-1 momentum (12-month return excluding most recent month) has generated ~4-6% annual factor premium across many time periods
- Works better in certain regimes (trending markets) and reverses badly in regime shifts
- Combining momentum with a valuation screen reduces crash risk

**Macro regime as a filter (MEDIUM confidence)**
- Yield curve inversion has preceded recessions with ~18 months lead time historically
- VIX above 25 correlates with elevated left-tail risk
- These are not alpha signals — they are risk filters. Using them as gates reduces drawdown without materially reducing upside in normal environments.

**What does NOT have strong backing at small capital:**
- Sentiment analysis of news/Twitter (requires very fast execution to capture, dies on small caps)
- Earnings surprise momentum (earnings calendar timing is complex, options needed for full capture)
- Technical analysis patterns alone (no academic literature shows reproducible edge without combination with fundamentals)

---

### Position Sizing at Small Capital ($100-500/week)

**Use fixed fractional sizing, not Kelly.**
- Full Kelly requires accurate knowledge of edge (win rate × average win - loss rate × average loss). You don't know your edge until you have live data. Kelly will oversize.
- Start with 2-4% of total account per position (if account is $5,000, max $150-200 per position)
- Cap any single trade at 20% of the weekly capital deployment budget
- Never be more than 40% invested at once during shadow mode (leaves room to increase)

**Actual Kelly use (for later):**
- Once you have 30+ completed trades with real P&L, compute quarter-Kelly (25% of full Kelly fraction) as a ceiling
- Never use full Kelly — it maximizes long-run growth but produces horrifying drawdowns in practice
- Half-Kelly is the standard practitioner choice; quarter-Kelly is more conservative and appropriate here

**Concentration vs diversification at $500/week:**
- 2-3 positions per week is optimal at this capital level. 5+ positions means each is too small to matter and you pay spread costs across more trades.
- Pick the top 2 signals each week, pass them through the approval gate, execute those two.

**Stop losses:**
- Hard stop at 8% below entry (this is tight enough to preserve capital, loose enough to avoid noise stops)
- No trailing stops at this cadence — weekly review frequency is the position management mechanism
- If a position drops 8% before the next weekly review, close it automatically (this should be the one automated action that does NOT require manual approval)

---

### Cost and Tax Modeling

**Transaction costs at small scale:**
- Alpaca charges $0 commissions on stock trades. The real cost is the bid-ask spread.
- For liquid large-caps (SPY, AAPL, MSFT): spread cost ≈ 0.01-0.02% per trade (negligible)
- For mid-caps and small-caps: spread cost can be 0.2-0.5% per trade (materially significant at $200 positions)
- Rule: only trade securities with average daily volume > 500k shares. Below this, spread cost likely exceeds edge.
- Market orders should be avoided for small-caps. Use limit orders at midpoint.

**Tax considerations ($500/week capital, US investor assumed):**
- Any position held less than 365 days is a short-term capital gain, taxed as ordinary income
- At a weekly trading cadence, virtually all gains will be short-term
- This means your effective tax drag on profits could be 22-37% depending on bracket
- Concrete impact: if the signal generates 10% annual alpha gross, after tax drag at 30% you net 7% — still worth it, but model this honestly
- Wash sale rule: if you sell at a loss and rebuy the same ticker within 30 days (before or after), the loss is disallowed for tax purposes. The bot must track this.
- Minimum P&L threshold: at $100-200 per position, a 3% winner is $3-6 gain taxed at ordinary rates. Transaction friction (spread) may eat this. Recommend minimum position $200, minimum expected gain target > 5%.

**Cost model to integrate:**
- Estimated round-trip cost per trade = (bid-ask spread %) × position size
- Only enter trade if composite signal is strong enough that expected alpha > 2× estimated round-trip cost
- Track actual fill prices vs mid-price to measure real slippage

---

## Anti-Features — Deliberately Do NOT Build

### What Hobby Traders Overbuild (Time Wasters)

**A beautiful dashboard / web UI**
- You need a weekly PDF or email report, not a live dashboard. Building a React frontend for a weekly bot is scope inflation.
- Use a Jupyter notebook or a PDF-generating script. Ship the report via email.

**Real-time streaming price data**
- This is a weekly-cadence bot. You do not need websocket connections or sub-second data. yfinance on a weekly schedule is perfectly sufficient.
- Real-time data subscriptions cost $50-500/month and add operational complexity you do not need.

**A full backtesting engine**
- Backtrader, Zipline, vectorbt are all great but you will spend 3 months perfecting your backtest framework instead of running forward tests. The academic literature has already backtested insider and congressional signals. Trust it and forward-test.
- Build the minimum: a shadow mode that tracks hypothetical trades going forward. That is your backtester.

**Machine learning models**
- An LSTM or random forest trained on 5 years of data to predict stock returns is an overfitting machine at small datasets.
- With fewer than ~10,000 training examples per feature and 500+ correlated features (all the ways to describe a stock), any ML model will find patterns that are noise.
- Stick to 3-4 hand-crafted signals with clear causal stories. ML is for Phase 3 if ever.

**Options trading**
- Options are a different risk profile, require margin agreement, have early expiration risk, and have complex P&L accounting. Out of scope for v1.

**Short selling**
- Alpaca supports it but the signal model above is buy-only. Short selling doubles your risk surface, requires locating shares, and the congressional/insider signals have directional evidence only for longs.

**Multiple portfolio strategies running simultaneously**
- One strategy, forward-tested, understood. Multiple strategies run simultaneously means you can't tell which one is working.

**Automated rebalancing / portfolio optimization**
- Mean-variance optimization at $500/week with 2-3 positions is mathematical theatre. Just use equal-weight.

---

### Features That Sound Good but Destroy Edge

**Over-parameterized signal thresholds**
- "Only buy if insider bought more than $50,000 AND is the CEO AND the stock has > 20% institutional ownership AND 12-month momentum is in the top 30th percentile AND..."
- Each added condition that improves backtest results should raise suspicion, not confidence.
- Rule: each condition in your filter must have a causal story and must have been defined before looking at data.

**Look-ahead bias (the most common killer)**
- Using transaction date instead of filing date for congressional/insider signals. The transaction happened 30-45 days before you could have known about it.
- Using adjusted closing prices that incorporate future corporate actions.
- Computing signals on data that includes the current day's close when your signal should be computed before market open.
- In shadow mode: recording the trade entry as today's open when you computed the signal after today's close.

**Survivorship bias in the universe**
- Selecting your stock universe from current S&P 500 constituents and backtesting means you excluded all the stocks that were delisted, went bankrupt, or were removed. Every backtest with this construction is too rosy.
- Solution: construct universe from a current-members list fetched weekly, not a static list.

**Chasing signal decay**
- Discovering that the signal worked better in backtests with different parameters and re-fitting parameters to match. The parameters must be set once before any testing.

**Ignoring transaction costs in backtests**
- Even with $0 commissions, ignoring spread costs and market impact makes any backtest look better than reality.

**Checking too often / tinkering**
- Reviewing signal outputs daily and tweaking weights is a bias factory. Weekly cadence means weekly review. Do not look at daily fluctuations.

---

## Shadow Mode → Live Transition

### Structure

**Phase 1 — Pure Shadow (Weeks 1-8 minimum)**
- System generates signals and produces weekly reports
- You manually review reports but no trades are submitted anywhere
- P&L is tracked hypothetically
- Goal: verify data pipelines work, signals produce non-trivial differentiation, report is readable

**Phase 2 — Paper Trading via Alpaca (Weeks 9-16 minimum)**
- Same system, but the approval gate now submits orders to Alpaca paper trading account
- You approve each week's recommendations before submission
- Alpaca paper trading simulates fills at market prices (with some limitations vs real market)
- P&L from Alpaca paper account is the benchmark, not hypothetical fills
- Catch the Alpaca-specific issues: paper trading does not simulate pre-market fills, pattern day trader rule applies ($25k minimum for >3 intraday trades in 5 days — this is a weekly bot so PDT should not be triggered)

**Phase 3 — Live Trading with Manual Confirmation**
- Move approval gate to real Alpaca account
- First 4 weeks: position sizes 50% of normal (half-sizing during transition)
- Revert immediately to paper trading if weekly P&L drawdown exceeds 10% of starting live capital
- Never automate the approval step — keep it manual indefinitely

### Hard Criteria for Phase 2 Promotion

| Criterion | Threshold |
|-----------|-----------|
| Shadow weeks completed | >= 8 |
| Completed round trips | >= 10 |
| Shadow portfolio vs SPY | Any positive alpha |
| Maximum shadow drawdown | < 15% |
| Win rate | >= 40% with positive expectancy |
| No data pipeline failures | Zero missed weeks of data |

### Hard Criteria for Phase 3 Promotion (Paper to Live)

| Criterion | Threshold |
|-----------|-----------|
| Paper trading weeks | >= 8 additional |
| Paper portfolio vs SPY | Positive alpha sustained |
| Maximum paper drawdown | < 15% |
| Approval gate reliability | 100% (never missed a week) |
| Data pipeline reliability | Zero failures for 8 consecutive weeks |

---

## Minimum Viable Weekly Report

The report must answer exactly one question: "Should I approve these trades, and why?"

### Required Sections

**1. Macro Environment Status (3 lines)**
- Yield curve: [normal / inverted / near-flat]
- VIX: [current value] — regime: [low / elevated / high]
- Overall signal flag: [GREEN / YELLOW / RED] — RED means proposed sizes are halved

**2. Universe Snapshot (1 table)**
- All tickers scored this week with composite score
- Shows which signals fired for each (insider: Y/N, congressional: Y/N, momentum: score)
- Sorted by composite score descending
- Not actionable directly — context for the next section

**3. Proposed Trades (the core, 1 table)**

| Ticker | Action | Size ($) | Entry (est.) | Signal Breakdown | Thesis (1 sentence) |
|--------|--------|----------|--------------|-----------------|---------------------|
| AAPL   | BUY    | $200     | ~$185        | Insider: HIGH, Congressional: LOW, Momentum: MED | CEO bought $2M on 6/15; 12-mo momentum top quartile |

- Maximum 3 proposed trades per week. If fewer than 2 qualify, recommend "skip this week."
- Include the approximate entry price and the price at which you'd set a stop (8% below entry)

**4. Open Positions (status)**
- List current holdings with unrealized P&L
- Flag any positions approaching the 8% stop level
- Flag any positions eligible for promotion to long-term gains (approaching 365 days)

**5. Shadow/Paper Portfolio Stats (vs SPY)**
- This week's return: portfolio X%, SPY Y%
- Cumulative return since start: portfolio X%, SPY Y%
- Current drawdown from peak: X%

**6. Approval Instructions**
- Clear "APPROVE / REJECT / MODIFY" instructions with deadline (Monday 9:00 AM ET)
- One-click approve link (or edit the approval.yaml file)

### What to NOT Include in the Report
- Detailed signal methodology explanation (you already know how it works)
- News summaries about the proposed tickers (this introduces confirmation bias — you'll approve what sounds good in the news, not what the signal says)
- Price targets or "expected return" estimates (fabricated precision)
- Charts (overhead for a weekly email; add later if useful)

---

## Feature Dependency Map

```
FRED macro fetch → macro regime flag → position size gate
                                          ↓
EDGAR Form 4 fetch → insider signal → composite scorer → weekly report → approval gate → Alpaca order submission
                                          ↑
STOCK Act fetch → congressional signal
                                          ↑
yfinance price fetch → momentum signal
                     → P&L tracker
                     → stop loss checker
```

The P&L tracker and stop loss checker both depend on price data and the order log. The order log depends on the approval gate. None of the signal computation depends on any other signal — they are independent pipelines that converge at the composite scorer.

---

## MVP Recommendation

### Phase 1 MVP: Shadow Mode Working
1. yfinance price ingestion + momentum signal (1 week to build)
2. EDGAR Form 4 ingestion + insider buy signal (1-2 weeks)
3. Composite scorer + weekly report generator (1 week)
4. Shadow P&L tracker (1 week)

Defer: STOCK Act ingestion (HTML/PDF parsing is the hardest data problem; use Quiver Quantitative API as a shortcut)
Defer: Macro regime filter (add in week 3 once core signals work)
Defer: Alpaca integration (until Phase 2)

### Phase 2 Deferred Items
- STOCK Act congressional signal (via Quiver Quantitative API)
- FRED macro regime filter
- Alpaca paper trading integration
- Approval gate with email notification
- Stop loss auto-execution

### Phase 3 Later / Possibly Never
- Senate eFD raw parsing (expensive, noisy, use Quiver instead)
- ML signal enhancement
- Tax-lot optimization (important at larger capital, marginal at $500/week)
- Multiple signal variants / regime-switching weights

---

## Confidence Notes

| Area | Confidence | Basis |
|------|------------|-------|
| STOCK Act signal existence | MEDIUM | Pre-2025 academic literature well established; post-STOCK Act edge narrowed but persists |
| Form 4 insider signal | HIGH | 25+ years of academic replication, widely accepted |
| Momentum factor | HIGH | Among the most replicated quantitative factors in finance |
| Macro regime filter | MEDIUM | Yield curve and VIX as filters are standard practitioner wisdom, not pure academic |
| Position sizing recommendations | MEDIUM | Fixed fractional / Kelly are standard; specific thresholds are practitioner norms |
| Tax impact estimates | MEDIUM | Based on standard US tax brackets; individual situation varies |
| Shadow mode transition criteria | LOW-MEDIUM | Thresholds are reasonable but not derived from literature; adjust based on your risk tolerance |

---

## Sources

- Ziobrowski et al. (2004, 2011) — Congressional trading abnormal returns
- Lakonishok & Lee (2001) — Insider trading signals and returns
- Jeng, Metrick & Zeckhauser (2003) — Insider trading profits
- Jegadeesh & Titman (1993) — Momentum returns
- Carhart (1997) — Four-factor model including momentum
- Karadas (2018) — Congressional trading post-STOCK Act
- EDGAR EFTS documentation — efts.sec.gov
- Alpaca API documentation — docs.alpaca.markets
- FRED API documentation — fred.stlouisfed.org/docs/api
- yfinance known issues — known limitations with adjusted prices and retroactive recalculation
- Quiver Quantitative — quiverquant.com (congressional trading data aggregator)
