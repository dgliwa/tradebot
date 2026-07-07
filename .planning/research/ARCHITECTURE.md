# Architecture Research — TradeBot

**Domain:** Python algorithmic trading bot (signal-driven, weekly cadence, paper-first)
**Researched:** 2026-07-07
**Confidence:** MEDIUM (training knowledge on established trading system patterns)

---

## Recommended Architecture

A layered pipeline with three hard seams: **Ingest → Score → Act**. Each layer is independently runnable and testable. No event bus or message queue for a solo side project — a simple scheduled script calling functions in sequence is correct at this scale.

```
┌─────────────────────────────────────────────────────────────┐
│  INGESTION LAYER                                            │
│  congress_fetcher  edgar_fetcher  fred_fetcher  price_fetcher│
│           └──────────────┬──────────────────────┘          │
│                    raw_store (SQLite)                       │
└──────────────────────────┬──────────────────────────────────┘
                           │  raw rows
┌──────────────────────────▼──────────────────────────────────┐
│  SIGNAL LAYER                                               │
│  congress_signal   insider_signal   macro_signal   momentum │
│           └──────────────┬──────────────────────┘          │
│                    signal_store (SQLite)                    │
│                    score_engine (weighted combiner)         │
│                    recommendation_builder                   │
└──────────────────────────┬──────────────────────────────────┘
                           │  ranked recommendations
┌──────────────────────────▼──────────────────────────────────┐
│  EXECUTION LAYER                                            │
│  report_writer (HTML/email)                                 │
│  confirmation_gate  ←── human approval CLI / webhook        │
│  order_router (paper | live)                                │
│  trade_store + pnl_tracker                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

### Ingestion Layer

**Responsibility:** Fetch raw external data, normalize to a canonical schema, persist to the raw table. Nothing else.

Each fetcher is a standalone function (or thin class if it needs session state):

```
fetchers/
  congress.py      # STOCK Act disclosures → RawDisclosure rows
  edgar.py         # SEC EDGAR Form 4 → RawInsiderFiling rows
  fred.py          # FRED macro series → RawMacroPoint rows
  prices.py        # yfinance OHLCV → RawPrice rows
```

The fetcher contract: `fetch(since: datetime) -> list[RawRecord]`. It writes nothing — the caller persists. This makes fetchers independently testable with no DB dependency.

A thin `ingest_runner.py` orchestrates: call each fetcher, deduplicate by (source, external_id), bulk-insert new rows. Run weekly via cron or a simple `python -m tradebot.ingest`.

**Key seam:** Fetchers return normalized Python dataclasses, not raw API dicts. The seam between ingestion and signal is the `raw_*` tables in SQLite, not in-memory objects. This lets you re-run signal generation from stored raw data without re-fetching.

### Signal Layer

**Responsibility:** Read from raw tables, compute signal values, write to signal tables, combine into a ranked recommendation list.

Each signal module reads raw rows for a symbol+date range and returns a `Signal` (ticker, signal_type, value: float, direction: BUY/SELL/NEUTRAL, confidence: float, source_row_ids: list).

```
signals/
  congress.py      # filing recency, party/committee weighting, position size
  insider.py       # Form 4 buy/sell volume, officer vs director weighting
  macro.py         # FRED series delta, yield curve, VIX regime
  momentum.py      # price trend, RSI, relative strength vs SPY
  combiner.py      # weighted average → composite score
```

`combiner.py` holds the weight config (start with equal weights, tune later). It produces a `Recommendation` per symbol: composite_score, direction, individual signal breakdown.

**Key seam:** Signal modules never touch the execution layer. They return `Recommendation` objects. The report and order router consume those objects.

### Execution Layer

**Responsibility:** Present recommendations to humans, accept/reject, route to broker, record outcomes.

Components:

- `report.py` — renders recommendations to Markdown/HTML for weekly email
- `gate.py` — the confirmation interface (CLI prompt, or simple web form)
- `router.py` — sends approved orders to Alpaca (paper or live endpoint)
- `tracker.py` — records executed trades, polls for fills, computes running P&L vs SPY

---

## Paper / Live Mode Toggle

**Use a single environment variable + a config object, not separate codebases.**

```python
# config.py
from dataclasses import dataclass
from enum import Enum
import os

class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"

@dataclass
class Config:
    mode: TradingMode = TradingMode(os.getenv("TRADEBOT_MODE", "paper"))
    alpaca_key: str = os.getenv("ALPACA_KEY", "")
    alpaca_secret: str = os.getenv("ALPACA_SECRET", "")

    @property
    def alpaca_base_url(self) -> str:
        if self.mode == TradingMode.PAPER:
            return "https://paper-api.alpaca.markets"
        return "https://api.alpaca.markets"
```

The router receives a `Config` at construction. Flip `TRADEBOT_MODE=live` in `.env` to go live — no code changes.

Alpaca provides separate paper and live API endpoints with the same SDK interface, so the same `router.py` code works for both. Keep separate Alpaca accounts (Alpaca supports this natively) so paper P&L is never contaminated by live fills.

Do NOT use dependency injection containers or abstract broker interfaces at this scale. One concrete `AlpacaRouter` class, one config flag.

### The Confirmation Gate

The gate lives between the signal layer output and the `router.py` call. It is the last component before money moves.

For a solo weekly workflow, a CLI gate is sufficient and correct:

```
Gate options (in order of complexity):
1. CLI prompt      — print ranked list, ask Y/N per ticker, proceed
2. Email approval  — send report, reply "APPROVE TSLA AAPL" to trigger execution
3. Minimal web UI  — Flask/FastAPI single page, approve/reject buttons
```

Start with option 1. The gate is architecturally a function:

```python
def confirm(recommendations: list[Recommendation]) -> list[Recommendation]:
    """Returns the subset the human approves."""
    ...
```

It is synchronous and blocking. The weekly script calls it, waits, then passes approved recommendations to the router. This is the right abstraction for a side project — no async approval queue needed until you want to automate execution.

---

## Data Flow

```
Raw disclosure arrives
  → fetcher normalizes to RawDisclosure dataclass
    → ingest_runner deduplicates and inserts to raw_disclosures table
      → congress signal module reads raw_disclosures for last N days
        → returns Signal(ticker, value, direction, confidence)
          → combiner weights and merges all signals per ticker
            → Recommendation(ticker, score, direction, signal_breakdown, timestamp)
              → report renders top-N as weekly report
                → confirmation gate filters to approved subset
                  → router submits order to Alpaca (paper or live)
                    → tracker polls for fill confirmation
                      → trade recorded in trades table
                        → pnl_tracker computes return vs SPY benchmark
```

### Pipeline Representation

**Use a simple functional pipeline driven by a weekly script.** Event-driven architecture (Kafka, Redis Streams, Celery) is 10x the operational overhead with no benefit at weekly cadence and $100-500/week capital.

The weekly runner is a plain Python script:

```python
# run_weekly.py
def main():
    config = Config()
    
    # Phase 1: Ingest
    ingest_all(since=last_week())
    
    # Phase 2: Score
    recs = build_recommendations(as_of=today())
    
    # Phase 3: Report + Confirm + Execute
    report = render_report(recs)
    send_report_email(report)
    approved = confirm(recs)           # blocks for human input
    orders = [build_order(r) for r in approved]
    router.submit(orders)
    tracker.record_pending(orders)

if __name__ == "__main__":
    main()
```

Run via cron on Monday morning. Shadow mode = run the script, skip the `router.submit()` call (but keep `confirm()` and `record_pending()` to validate the gate logic).

---

## Storage Schema

SQLite is correct for this project. Postgres is over-engineered for a single-user weekly bot. If you ever need concurrent writers or >1GB of tick data, migrate then.

### Tables

```sql
-- Raw ingested data
CREATE TABLE raw_disclosures (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,       -- 'congress' | 'edgar'
    external_id TEXT NOT NULL,       -- filing ID from source
    ticker      TEXT NOT NULL,
    filed_at    TEXT NOT NULL,       -- ISO8601
    action      TEXT,                -- 'purchase' | 'sale' | 'option_exercise'
    amount_usd  REAL,
    filer_name  TEXT,
    filer_role  TEXT,                -- 'senator' | 'ceo' | 'director' etc
    raw_json    TEXT,                -- original payload, unparsed
    ingested_at TEXT NOT NULL,
    UNIQUE(source, external_id)
);

CREATE TABLE raw_prices (
    id          INTEGER PRIMARY KEY,
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,       -- YYYY-MM-DD
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      INTEGER,
    UNIQUE(ticker, date)
);

CREATE TABLE raw_macro (
    id          INTEGER PRIMARY KEY,
    series_id   TEXT NOT NULL,       -- FRED series, e.g. 'DGS10'
    date        TEXT NOT NULL,
    value       REAL,
    UNIQUE(series_id, date)
);

-- Signal layer output
CREATE TABLE signals (
    id              INTEGER PRIMARY KEY,
    run_id          TEXT NOT NULL,   -- UUID per weekly run
    ticker          TEXT NOT NULL,
    signal_type     TEXT NOT NULL,   -- 'congress' | 'insider' | 'macro' | 'momentum'
    value           REAL NOT NULL,   -- normalized -1.0 to 1.0
    direction       TEXT NOT NULL,   -- 'BUY' | 'SELL' | 'NEUTRAL'
    confidence      REAL NOT NULL,   -- 0.0 to 1.0
    computed_at     TEXT NOT NULL,
    source_ids      TEXT            -- JSON array of raw row IDs used
);

CREATE TABLE recommendations (
    id              INTEGER PRIMARY KEY,
    run_id          TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    composite_score REAL NOT NULL,   -- weighted combination of signals
    direction       TEXT NOT NULL,
    signal_breakdown TEXT NOT NULL,  -- JSON: {signal_type: value, ...}
    rank            INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'approved'|'rejected'
    approved_at     TEXT,
    created_at      TEXT NOT NULL
);

-- Execution layer
CREATE TABLE instruments (
    id              INTEGER PRIMARY KEY,
    ticker          TEXT NOT NULL,   -- underlying symbol
    instrument_type TEXT NOT NULL,   -- 'stock' | 'call' | 'put'
    expiry          TEXT,            -- NULL for stocks
    strike          REAL,            -- NULL for stocks
    UNIQUE(ticker, instrument_type, expiry, strike)
);

CREATE TABLE orders (
    id              INTEGER PRIMARY KEY,
    recommendation_id INTEGER REFERENCES recommendations(id),
    instrument_id   INTEGER REFERENCES instruments(id),
    side            TEXT NOT NULL,   -- 'buy' | 'sell'
    quantity        REAL NOT NULL,
    order_type      TEXT NOT NULL,   -- 'market' | 'limit'
    limit_price     REAL,
    alpaca_order_id TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    mode            TEXT NOT NULL,   -- 'paper' | 'live'
    submitted_at    TEXT,
    filled_at       TEXT,
    fill_price      REAL
);

CREATE TABLE trades (
    id              INTEGER PRIMARY KEY,
    order_id        INTEGER REFERENCES orders(id),
    ticker          TEXT NOT NULL,
    side            TEXT NOT NULL,
    quantity        REAL NOT NULL,
    fill_price      REAL NOT NULL,
    filled_at       TEXT NOT NULL,
    cost_basis      REAL NOT NULL    -- quantity * fill_price + fees
);

CREATE TABLE pnl_snapshots (
    id              INTEGER PRIMARY KEY,
    snapshot_date   TEXT NOT NULL,
    portfolio_value REAL NOT NULL,
    spy_value       REAL NOT NULL,   -- normalized to same starting capital
    cash            REAL NOT NULL,
    created_at      TEXT NOT NULL
);
```

### Key Design Choices

- `raw_json` column on `raw_disclosures`: store the original payload so you can re-derive fields without re-fetching if your parsing logic changes.
- `run_id` on signals and recommendations: groups everything from a single weekly run. Makes retrospective analysis trivial ("what did we think last week?").
- `instruments` table: generic from day one (see Options-Aware Design below). For stocks, expiry and strike are NULL.
- Separate `orders` and `trades`: an order is intent; a trade is a confirmed fill. These are not the same and conflating them is a common source of P&L calculation bugs.

---

## Options-Aware Design

Model instruments generically from day one with minimal extra code.

The `instruments` table above handles it. In Python:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class InstrumentType(Enum):
    STOCK = "stock"
    CALL = "call"
    PUT = "put"

@dataclass(frozen=True)
class Instrument:
    ticker: str
    instrument_type: InstrumentType
    expiry: Optional[str] = None    # "2026-01-16" for options
    strike: Optional[float] = None  # 150.0 for options

    @property
    def is_option(self) -> bool:
        return self.instrument_type in (InstrumentType.CALL, InstrumentType.PUT)

    @property
    def symbol(self) -> str:
        """OCC symbol for options, plain ticker for stocks."""
        if not self.is_option:
            return self.ticker
        # TSLA  260116C00150000
        expiry_fmt = self.expiry.replace("-", "")[2:]
        side = "C" if self.instrument_type == InstrumentType.CALL else "P"
        strike_fmt = f"{int(self.strike * 1000):08d}"
        return f"{self.ticker:<6}{expiry_fmt}{side}{strike_fmt}"
```

The `Recommendation` object holds `ticker` (the underlying). The `Order` object holds an `Instrument`. When you're stocks-only, every order is `Instrument(ticker, InstrumentType.STOCK)`. When you add options later, the signal layer can recommend an option instrument instead — everything downstream already handles it.

Do NOT build an options pricing engine (Black-Scholes, Greeks) yet. That belongs in a future phase when you have a clear reason to trade options. The data model just needs to not rule it out.

---

## Build Order

Build bottom-up, verify each layer before adding the next.

### Phase 1: Data Foundation
Build the SQLite schema + migration runner first. Everything else depends on storage.
- `db.py`: connection, schema migrations (use a simple version table, not Alembic yet)
- `models.py`: dataclasses for RawDisclosure, Signal, Recommendation, Instrument, Order, Trade
- Seed with one week of historical data to validate the schema

### Phase 2: Ingestion Layer
- Congress fetcher (STOCK Act disclosures — quiverquant.com or direct House/Senate XML)
- EDGAR Form 4 fetcher (SEC EDGAR full-text search API)
- yfinance price fetcher
- FRED macro fetcher
- `ingest_runner.py` with deduplication

Verify: can you ingest 90 days of data and inspect it in SQLite Browser?

### Phase 3: Signal Layer (Shadow Mode)
- One signal module (congress is richest signal, start there)
- `combiner.py` with single-signal pass-through initially
- `run_weekly.py` that ingests + scores but does NOT execute
- Manually inspect output: do the tickers and directions make intuitive sense?

This is the minimum viable pipeline that can run end-to-end in shadow mode.

### Phase 4: Report + Gate
- `report.py`: render weekly recommendations as a readable Markdown/text file
- CLI confirmation gate
- Email delivery (even just writing to a file is fine initially)

Verify: run the full pipeline end-to-end. Ingest → score → report → approve in terminal. No real trades yet.

### Phase 5: Execution (Paper)
- Alpaca SDK integration (`alpaca-trade-api` or `alpaca-py`)
- `router.py` paper mode only
- `tracker.py`: poll for fills, record trades
- `pnl_tracker.py`: weekly snapshot vs SPY

Verify: run 4 weeks of paper trades. Confirm fills appear in Alpaca dashboard and in your DB.

### Phase 6: Additional Signals
- Insider signal (EDGAR)
- Macro signal (FRED)
- Momentum signal (yfinance price features)
- Weight tuning

### Phase 7: Live Mode (with capital guard)
- Flip `TRADEBOT_MODE=live`
- Add position-size guard (never risk more than X% of account per trade)
- Manual confirmation required (gate already enforces this)

---

## Right Level of Abstraction for a Solo Dev

**The trap:** Over-engineering the signal framework into a plugin system before you know what signals work.

**The rule:** Abstract when you have three concrete instances of the same pattern. Not before.

Specific guidance:
- No abstract base classes for fetchers or signals until you have 3+ fetchers that share non-trivial logic.
- No dependency injection container. Pass `config` and `db_conn` as parameters to functions.
- No async/await. Weekly batch jobs are synchronous. Async adds complexity with no throughput benefit here.
- No ORM (SQLAlchemy). Use `sqlite3` directly with parameterized queries. 200 lines of SQL is easier to debug than 200 lines of ORM magic.
- No message queue or task scheduler (Celery, RQ). A cron job + Python script is the right tool.
- No microservices. One Python package, one SQLite file, one weekly script.
- Do use dataclasses (not dicts) for the data structures that cross layer boundaries. Type safety at seams catches bugs early without adding infrastructure.

The system should be explainable in 5 minutes to a future-you who forgot everything. If it takes longer, it's over-engineered.

---

## Anti-Patterns to Avoid

### Conflating Raw Data with Signals
Storing a "signal" in the same table as a raw filing row means you can never re-score without re-fetching. Always separate raw storage from computed signals.

### Mutable Recommendations
Once a `Recommendation` is generated for a run, treat it as immutable. Add an `approved_at` timestamp but never change the scores. This preserves the paper trail for retrospective analysis.

### Implicit Mode Switching
Never infer paper/live mode from the presence of test data or ticker names like "PAPER_TSLA". The mode must be explicit in config. A silent mode switch is how real money gets spent accidentally.

### Single `trades` Table for Both Paper and Live
Keep the `mode` column on `orders`. This lets you query paper vs live performance independently and prevents benchmark contamination.

### Re-fetching for Re-scoring
The most expensive operation is network fetching. Always store raw data first, then derive. If your signal logic changes, re-run scoring from stored raw data — don't re-fetch.

---

## Scalability Considerations

This system is designed for weekly batch execution by one person. The following table is reality-check, not a roadmap:

| Concern | At current scale (weekly, $500) | If you wanted daily |
|---------|----------------------------------|---------------------|
| Storage | SQLite, single file | SQLite still fine |
| Fetching | Sequential, synchronous | Add `asyncio` or `ThreadPoolExecutor` |
| Scoring | In-memory, milliseconds | Still fine |
| Execution | One API call | Add order batching |
| Monitoring | Read your DB | Add a simple Flask dashboard |

You will not hit SQLite's limits before you hit regulatory or capital limits. SQLite handles 100K+ rows and concurrent reads fine. The only reason to move to Postgres is if you add a separate web UI that needs concurrent writers.

---

## Sources

- Confidence: MEDIUM (training knowledge on established patterns; cross-verified against known Alpaca SDK behavior, SEC EDGAR API structure, and SQLite scalability characteristics)
- Alpaca Markets API documentation (paper/live endpoint design)
- SEC EDGAR EFTS full-text search API (Form 4 ingestion)
- Python `sqlite3` standard library capabilities
- House and Senate STOCK Act disclosure XML feeds
