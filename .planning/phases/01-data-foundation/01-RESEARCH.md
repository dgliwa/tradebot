# Phase 1 Research: Data Foundation

**Researched:** 2026-07-07
**Domain:** DuckDB schema design, Python dataclasses, python-dotenv config loading, pytest fixtures
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Domain-layered subpackage structure: `tradebot/db/`, `tradebot/models/`, `tradebot/fetchers/`, `tradebot/signals/`, `tradebot/report/`, `tradebot/execution/`. Mirrors pipeline stages.
- **D-02:** Technical-layer organization (not business-domain grouping). Keeps DB/model utilities shareable across all fetchers/signals without circular imports.
- **D-03:** CLI entrypoint is `tradebot/__main__.py`, enabling `uv run python -m tradebot`. No root-level `run_weekly.py`.
- **D-04:** Use vanilla `@dataclass` for all cross-layer types (`RawRecord`, `Recommendation`, `Order`, `Trade`, `Instrument`). Zero runtime overhead, no extra dependency.
- **D-05:** Shared dataclasses live in `tradebot/models/` subpackage. One file per entity: `instrument.py`, `signal.py`, `order.py`, `trade.py`.
- **D-06:** DDL (CREATE TABLE statements) lives as inline Python constants in `tradebot/db/schema.py`. No external `.sql` files. Uses `IF NOT EXISTS` for base table creation.
- **D-07:** DuckDB connection shared via module-level singleton: `get_connection()` in `tradebot/db/connection.py`. Returns the same in-process connection. Tests swap it for an in-memory connection.
- **D-08:** Schema migration for future phases uses versioned migration scripts in `tradebot/db/migrations/`. Numbered files (e.g., `001_initial.sql`, `002_add_column.sql`) applied in order at startup.
- **D-09:** Use `python-dotenv` to load separate `.env.paper` and `.env.live` files. Which file loads is determined by the `TRADEBOT_MODE` environment variable.
- **D-10:** Config accessed via `from tradebot.config import settings` — a module-level `Settings` dataclass instance, loaded once at import time.

### Claude's Discretion

- Specific field names within `Settings` dataclass (API keys, DB path, log level) — follow the pattern established by Alpaca SDK conventions and REQUIREMENTS.md references.
- Whether `tradebot/db/migrations/` stores `.sql` files or Python functions — Claude's call based on simplicity.
- Test fixture patterns for DuckDB in-memory connections — standard pytest fixture approach.

### Deferred Ideas (OUT OF SCOPE)

- None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | DuckDB schema separates raw/signal/execution tables | Schema design in `## DuckDB API Patterns` and `## Migration Strategy` |
| DATA-02 | Raw fetches record `fetched_at`; historical rows never overwritten | `raw_prices` / `raw_insider` table design with `fetched_at` in `## Typed Dataclasses` |
| DATA-03 | Fetchers return `row_count` + `freshness_date`; pipeline blocks if invalid | `FetchResult` dataclass in `## Typed Dataclasses` |
| DATA-04 | Disclosures store `transaction_date` AND `filed_at`; signals use `filed_at` | `RawRecord` fields in `## Typed Dataclasses` |
| DATA-05 | Instrument schema supports stocks/calls/puts (`instrument_type`, `expiry`, `strike` — NULL for stocks) | `Instrument` dataclass and DDL in `## Typed Dataclasses` and `## Migration Strategy` |
| DATA-06 | `universe_snapshots` table records tickers in scope per run week | Schema constant in `## Migration Strategy` |
</phase_requirements>

---

## Summary

Phase 1 establishes the DuckDB schema, typed dataclasses, and config loading patterns that the entire pipeline depends on. DuckDB 1.3.x has a stable Python API with no breaking changes from 1.0/1.1/1.2 that affect this phase — `duckdb.connect()`, `execute()`, and `fetchdf()` are unchanged. The key architectural insight is that the module-level singleton (`get_connection()`) must be designed for easy test override: tests should inject an in-memory connection via `monkeypatch.setattr`, keeping production code clean. The CLAUDE.md specifies `duckdb` 1.3.x pinned but PyPI as of 2026-07-07 shows 1.5.4 is latest stable — the project pin should be respected as-is since 1.3.x is available and the CLAUDE.md version data was confirmed live on 2026-07-07.

**Primary recommendation:** Use `duckdb.connect(database=":memory:")` in fixtures, override `get_connection` via `monkeypatch`, track applied migrations in a `schema_versions` table, and define all DDL as Python string constants — this gives idempotent schema creation with zero external dependencies.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| DuckDB schema initialization | db/ layer (`connection.py`, `schema.py`) | — | DDL is DB infrastructure, not business logic |
| Migration tracking | db/ layer (`migrations/` + `schema_versions` table) | — | Migration state belongs in the database itself |
| Cross-layer typed contracts | models/ layer (dataclasses) | — | Models must be importable by all downstream layers without circular imports |
| Config/secrets loading | `config.py` (module-level singleton) | — | Single load-point prevents repeated disk reads and env var conflicts |
| CLI entry | `__main__.py` | — | Enables `uv run python -m tradebot` as per D-03 |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `duckdb` | 1.3.x (1.3.2 latest in 1.3 line) | In-process columnar DB for all persistence | Zero-ops, fast range scans on time-series, native Parquet/CSV, SQL-complete [VERIFIED: CLAUDE.md — confirmed live PyPI 2026-07-07] |
| `python-dotenv` | 1.2.2 | Load `.env.paper` / `.env.live` into `os.environ` | Minimal dependency, standard Python pattern, `dotenv_path` supports conditional loading [VERIFIED: PyPI registry 2026-07-07] |
| `pytest` | 8.x (8.4.2 latest) | Test runner | Project-mandated in CLAUDE.md [VERIFIED: PyPI registry 2026-07-07] |
| `pytest-mock` | 3.15.x (3.15.1 latest) | `monkeypatch` / mock fixtures | Project-mandated in CLAUDE.md [VERIFIED: PyPI registry 2026-07-07] |
| `freezegun` | 1.5.5 | Freeze `datetime.now()` in date-sensitive tests | Project-mandated in CLAUDE.md [VERIFIED: PyPI registry 2026-07-07] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` | stdlib | Typed dataclasses (`@dataclass`) | All cross-layer data models (D-04) — zero dependency |
| `pathlib` | stdlib | `Path` objects for migration file discovery | Safer than `os.path` for `glob("*.sql")` on migrations/ |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Vanilla `@dataclass` | `pydantic.BaseModel` | Pydantic adds validation at field assignment but is an extra dependency — CLAUDE.md and D-04 lock vanilla dataclasses |
| Inline DDL constants | External `.sql` files in `migrations/` | External files require file discovery logic; D-06 locks inline Python constants for base DDL |
| `python-dotenv` | `dynaconf`, `environs` | More features but heavier; dotenv is sufficient for two-env pattern |

**Installation (uv):**
```bash
uv add duckdb==1.3.2 python-dotenv==1.2.2
uv add --dev pytest pytest-mock freezegun
```

---

## Package Legitimacy Audit

> All packages are from the project's pinned CLAUDE.md stack, confirmed against PyPI as of 2026-07-07.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| duckdb | PyPI | 6+ yrs | Very high | github.com/duckdb/duckdb | OK | Approved |
| python-dotenv | PyPI | 10+ yrs | Very high | github.com/theskumar/python-dotenv | OK | Approved |
| pytest | PyPI | 15+ yrs | Very high | github.com/pytest-dev/pytest | OK | Approved |
| pytest-mock | PyPI | 8+ yrs | Very high | github.com/pytest-dev/pytest-mock | OK | Approved |
| freezegun | PyPI | 10+ yrs | High | github.com/spulec/freezegun | OK | Approved |

**Packages removed due to SLOP verdict:** none
**Packages flagged as suspicious (SUS):** none

---

## DuckDB API Patterns

### Connection Management

DuckDB 1.3.x Python API is stable. The `duckdb.connect()` function signature has not changed from 1.0 through 1.3. [CITED: duckdb.org/docs/stable/clients/python/overview]

**Key distinction for the singleton:**

| Form | Behavior | Use case |
|------|----------|----------|
| `duckdb.sql("SELECT 1")` | Module-level global in-memory DB | Quick scripts only — do NOT use in packages |
| `duckdb.connect()` or `duckdb.connect(":memory:")` | New isolated in-memory instance | Tests — each test gets a clean, throwaway DB |
| `duckdb.connect("path/to/file.db")` | Persistent file-based DB | Production — data survives process restart |
| `duckdb.connect(":default:")` | Same global DB as `duckdb.sql()` | Avoid — causes subtle bugs in packages |

**Singleton implementation for `tradebot/db/connection.py`:**

```python
# Source: DuckDB Python API docs (duckdb.org/docs/stable/clients/python/overview)
from __future__ import annotations
import duckdb

_connection: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the module-level DuckDB connection, creating it on first call."""
    global _connection
    if _connection is None:
        from tradebot.config import settings
        _connection = duckdb.connect(database=str(settings.db_path))
    return _connection


def _reset_connection() -> None:
    """Force-close and reset connection. Used by tests only."""
    global _connection
    if _connection is not None:
        _connection.close()
    _connection = None
```

**Why `_reset_connection()` is included:** Tests need to inject an in-memory connection. `monkeypatch.setattr("tradebot.db.connection._connection", in_mem_conn)` works cleanly without touching the public API, but calling `_reset_connection()` before the test also works. Both patterns are documented below.

**Running SQL from Python strings:**

```python
conn = get_connection()
# DDL — execute returns None
conn.execute("CREATE TABLE IF NOT EXISTS foo (id INTEGER)")

# Parameterized query — use ? placeholders, pass params as list
conn.execute("INSERT INTO foo VALUES (?)", [42])

# Fetch as pandas DataFrame
df = conn.execute("SELECT * FROM foo").fetchdf()

# Fetch all rows as list of tuples
rows = conn.execute("SELECT * FROM foo").fetchall()

# Fetch one row
row = conn.execute("SELECT * FROM foo WHERE id = ?", [42]).fetchone()
```

**DuckDB 1.3.x notable changes (not breaking for this phase):**
- 1.3.0 introduced an external file cache for remote file queries. No Python API changes.
- 1.5.0 (NOT used here) dropped Python 3.9 and removed deprecated `duckdb.typing` / `duckdb.functional` — irrelevant at 1.3.x.
- No changes to `connect()`, `execute()`, `fetchdf()`, or `fetchall()` between 0.9 and 1.3. [ASSUMED — based on release notes scanning; no breaking change notices found for these methods]

### Idempotent DDL

`CREATE TABLE IF NOT EXISTS` is sufficient for base table creation (D-06 locks this). It is idempotent — calling it on an existing table is a no-op. [CITED: DuckDB SQL docs]

**Schema module structure (`tradebot/db/schema.py`):**

```python
# Source: DuckDB SQL docs — IF NOT EXISTS semantics
INSTRUMENTS = """
CREATE TABLE IF NOT EXISTS instruments (
    id                 VARCHAR PRIMARY KEY,
    ticker             VARCHAR NOT NULL,
    instrument_type    VARCHAR NOT NULL CHECK (instrument_type IN ('stock', 'call', 'put')),
    expiry             DATE,
    strike             DOUBLE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

RAW_PRICES = """
CREATE TABLE IF NOT EXISTS raw_prices (
    id              BIGINT PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    open            DOUBLE,
    high            DOUBLE,
    low             DOUBLE,
    close           DOUBLE,
    volume          BIGINT,
    fetched_at      TIMESTAMPTZ NOT NULL,
    source          VARCHAR NOT NULL DEFAULT 'yfinance'
)
"""

RAW_INSIDER = """
CREATE TABLE IF NOT EXISTS raw_insider (
    id               VARCHAR PRIMARY KEY,
    ticker           VARCHAR NOT NULL,
    filer_name       VARCHAR,
    transaction_date DATE NOT NULL,
    filed_at         DATE NOT NULL,
    shares           DOUBLE,
    price_per_share  DOUBLE,
    form_type        VARCHAR NOT NULL DEFAULT 'Form4',
    transaction_code VARCHAR NOT NULL,
    fetched_at       TIMESTAMPTZ NOT NULL
)
"""

RAW_CONGRESSIONAL = """
CREATE TABLE IF NOT EXISTS raw_congressional (
    id               VARCHAR PRIMARY KEY,
    ticker           VARCHAR NOT NULL,
    member_name      VARCHAR,
    transaction_date DATE NOT NULL,
    filed_at         DATE NOT NULL,
    amount_min       DOUBLE,
    amount_max       DOUBLE,
    transaction_type VARCHAR,
    fetched_at       TIMESTAMPTZ NOT NULL
)
"""

RAW_MACRO = """
CREATE TABLE IF NOT EXISTS raw_macro (
    id              BIGINT PRIMARY KEY,
    series_id       VARCHAR NOT NULL,
    observation_date DATE NOT NULL,
    vintage_date    DATE NOT NULL,
    value           DOUBLE,
    fetched_at      TIMESTAMPTZ NOT NULL
)
"""

SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id              BIGINT PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    run_date        DATE NOT NULL,
    signal_type     VARCHAR NOT NULL,
    score           DOUBLE NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

RECOMMENDATIONS = """
CREATE TABLE IF NOT EXISTS recommendations (
    id              BIGINT PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    run_date        DATE NOT NULL,
    composite_score DOUBLE NOT NULL,
    rank            INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id              VARCHAR PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    instrument_id   VARCHAR REFERENCES instruments(id),
    side            VARCHAR NOT NULL CHECK (side IN ('buy', 'sell')),
    qty             DOUBLE NOT NULL,
    order_type      VARCHAR NOT NULL DEFAULT 'market',
    status          VARCHAR NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id              VARCHAR PRIMARY KEY,
    order_id        VARCHAR REFERENCES orders(id),
    ticker          VARCHAR NOT NULL,
    side            VARCHAR NOT NULL,
    qty             DOUBLE NOT NULL,
    fill_price      DOUBLE NOT NULL,
    filled_at       TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

UNIVERSE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS universe_snapshots (
    id              BIGINT PRIMARY KEY,
    run_date        DATE NOT NULL,
    week_start      DATE NOT NULL,
    ticker          VARCHAR NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

SCHEMA_VERSIONS = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version         INTEGER PRIMARY KEY,
    name            VARCHAR NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

ALL_TABLES = [
    SCHEMA_VERSIONS,
    INSTRUMENTS,
    RAW_PRICES,
    RAW_INSIDER,
    RAW_CONGRESSIONAL,
    RAW_MACRO,
    SIGNALS,
    RECOMMENDATIONS,
    ORDERS,
    TRADES,
    UNIVERSE_SNAPSHOTS,
]
```

### Test Fixture

```python
# conftest.py — in-memory DuckDB fixture with singleton override
import pytest
import duckdb
from tradebot.db import schema


@pytest.fixture()
def db(monkeypatch):
    """Provide an isolated in-memory DuckDB connection for each test.

    Overrides tradebot.db.connection._connection so that get_connection()
    returns this in-memory DB for the duration of the test.
    """
    conn = duckdb.connect(database=":memory:")
    # Apply full schema so tests work against a realistic structure
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    monkeypatch.setattr("tradebot.db.connection._connection", conn)
    yield conn
    conn.close()
```

**Why `monkeypatch` not a separate `connect` parameter:** Production code calls `get_connection()` directly throughout the codebase. `monkeypatch.setattr` on the module-level `_connection` variable is the lowest-friction override — no production code changes required, and `monkeypatch` auto-restores after each test. [CITED: pytest docs — monkeypatch.setattr]

---

## Typed Dataclasses

All dataclasses use vanilla `@dataclass` (D-04). `Optional` fields use `field(default=None)`. `dataclasses.field` is used for mutable defaults. `datetime` fields use `datetime.datetime` (timezone-aware where noted).

### Instrument (`tradebot/models/instrument.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional


@dataclass
class Instrument:
    """A tradeable instrument — stock, call option, or put option."""
    id: str                                          # Unique ID (e.g., "AAPL", "AAPL_20251219_C200")
    ticker: str                                      # Underlying ticker symbol
    instrument_type: Literal["stock", "call", "put"] # Data constraint from DATA-05
    expiry: Optional[date] = None                   # NULL for stocks, required for options
    strike: Optional[float] = None                  # NULL for stocks, required for options
```

**Constraint:** `expiry` and `strike` MUST be None for `instrument_type == "stock"`, non-None for calls/puts. Validation logic lives in fetchers (D-04 — dataclasses do no runtime validation).

### RawRecord (`tradebot/models/raw_record.py`)

`RawRecord` is a generic envelope returned from all fetchers. It carries both `transaction_date` and `filed_at` to satisfy DATA-04.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class RawRecord:
    """Immutable raw data record as returned from a data source fetcher."""
    source: str                  # "yfinance", "edgar", "congressional", "fred"
    ticker: str
    fetched_at: datetime         # UTC timestamp when this record was retrieved (DATA-02)
    data: dict[str, Any]         # Raw payload — source-specific fields
    transaction_date: Optional[date] = None  # When the event occurred (DATA-04)
    filed_at: Optional[date] = None          # When the disclosure was filed (DATA-04)
```

### FetchResult (`tradebot/models/raw_record.py` — same file)

Satisfies DATA-03: fetchers return `row_count` + `freshness_date`.

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class FetchResult:
    """Summary returned by every fetcher. Pipeline inspects these to block on invalid data."""
    source: str
    ticker: str
    row_count: int               # 0 triggers pipeline block (DATA-03)
    freshness_date: Optional[date]  # None or stale date triggers pipeline block (DATA-03)

    @property
    def is_valid(self) -> bool:
        """True only when row_count > 0 and freshness_date is set."""
        return self.row_count > 0 and self.freshness_date is not None
```

### Recommendation (`tradebot/models/signal.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Recommendation:
    """A ranked trade candidate produced by the signal engine for a given run week."""
    ticker: str
    run_date: date
    composite_score: float       # Weighted blend of active signals (SIGNAL-05)
    rank: int                    # 1 = highest score in this run
    insider_score: Optional[float] = None
    momentum_score: Optional[float] = None
    congressional_score: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### Order (`tradebot/models/order.py`)

Satisfies EXEC-03: separate `orders` (intent) vs `trades` (confirmed fills).

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Order:
    """Trade intent submitted to Alpaca. P&L is NEVER computed from orders."""
    id: str                                           # Alpaca order ID
    ticker: str
    instrument_id: Optional[str]                      # FK to instruments.id
    side: Literal["buy", "sell"]
    qty: float
    order_type: Literal["market", "limit"] = "market"
    status: str = "pending"                           # pending / filled / cancelled
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### Trade (`tradebot/models/trade.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Trade:
    """Confirmed fill from Alpaca. P&L is computed ONLY from Trade records (EXEC-03, EXEC-04)."""
    id: str                      # Alpaca fill ID
    order_id: str                # FK to orders.id
    ticker: str
    side: Literal["buy", "sell"]
    qty: float
    fill_price: float            # Actual fill price, not assumed (EXEC-04)
    filled_at: datetime          # UTC timestamp from Alpaca
    recorded_at: datetime = field(default_factory=datetime.utcnow)
```

---

## Config Loading

### Settings Dataclass (`tradebot/config.py`)

```python
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


def _load_env() -> None:
    """Load the correct .env file based on TRADEBOT_MODE.

    TRADEBOT_MODE=paper  → loads .env.paper  (default if unset)
    TRADEBOT_MODE=live   → loads .env.live
    """
    mode = os.environ.get("TRADEBOT_MODE", "paper").lower()
    env_file = Path(f".env.{mode}")
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)
    # If .env.paper / .env.live is missing (e.g., in CI), fall through gracefully.
    # Tests set env vars directly; no .env file needed.


_load_env()


@dataclass
class Settings:
    """All runtime configuration. Loaded once at import time (D-10)."""

    # Mode control
    mode: str = field(default_factory=lambda: os.environ.get("TRADEBOT_MODE", "paper"))

    # Database
    db_path: Path = field(
        default_factory=lambda: Path(os.environ.get("TRADEBOT_DB_PATH", "data/tradebot.duckdb"))
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.environ.get("TRADEBOT_LOG_LEVEL", "INFO")
    )

    # Alpaca (populated from .env.paper or .env.live)
    alpaca_key: str = field(default_factory=lambda: os.environ.get("ALPACA_KEY", ""))
    alpaca_secret: str = field(default_factory=lambda: os.environ.get("ALPACA_SECRET", ""))
    alpaca_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        )
    )

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"


# Module-level singleton — imported everywhere as `from tradebot.config import settings`
settings = Settings()
```

### dotenv Loading Pattern

`python-dotenv`'s `load_dotenv(dotenv_path=path, override=False)` reads key=value pairs from the file and sets them via `os.environ.setdefault` (when `override=False`). [CITED: python-dotenv docs]

```
# .env.paper
TRADEBOT_MODE=paper
TRADEBOT_DB_PATH=data/tradebot.duckdb
ALPACA_KEY=pk_paper_xxxx
ALPACA_SECRET=sk_paper_xxxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# .env.live
TRADEBOT_MODE=live
TRADEBOT_DB_PATH=data/tradebot_live.duckdb
ALPACA_KEY=pk_live_xxxx
ALPACA_SECRET=sk_live_xxxx
ALPACA_BASE_URL=https://api.alpaca.markets
```

**Important:** `override=False` means shell-set env vars take precedence over the `.env` file. This is correct — CI/CD can set `TRADEBOT_MODE` without a `.env` file present.

**Test pattern:** Tests do NOT need a `.env` file. They set env vars directly:
```python
@pytest.fixture(autouse=True)
def paper_mode(monkeypatch):
    monkeypatch.setenv("TRADEBOT_MODE", "paper")
    monkeypatch.setenv("TRADEBOT_DB_PATH", ":memory:")
```

---

## Migration Strategy

### Design

Base tables use `CREATE TABLE IF NOT EXISTS` (D-06, D-08). Future schema changes (e.g., adding a column) go into numbered `.sql` files in `tradebot/db/migrations/`. A `schema_versions` table tracks which migrations have been applied — this prevents re-running migrations after restart.

The pattern: "has this migration number already been applied?" eliminates the need for try/except ALTER TABLE hacks.

### Migration Runner (`tradebot/db/migrations/__init__.py`)

```python
from __future__ import annotations
import re
from pathlib import Path
import duckdb


MIGRATIONS_DIR = Path(__file__).parent


def _applied_versions(conn: duckdb.DuckDBPyConnection) -> set[int]:
    """Return set of already-applied migration version numbers."""
    rows = conn.execute("SELECT version FROM schema_versions ORDER BY version").fetchall()
    return {row[0] for row in rows}


def run_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Discover and apply any unapplied numbered .sql migrations in order."""
    applied = _applied_versions(conn)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for path in migration_files:
        match = re.match(r"^(\d+)_", path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
            [version, path.name],
        )
```

### Phase 1 Migration File (`tradebot/db/migrations/001_initial.sql`)

Phase 1 has no post-baseline migrations — the `001_initial.sql` file can be empty or contain a comment:
```sql
-- 001_initial.sql
-- Base schema is established by init_db() inline DDL constants.
-- Future ALTER TABLE / data backfills go in 002_*.sql and later.
```

### `init_db()` function (`tradebot/db/__init__.py`)

```python
from __future__ import annotations
from tradebot.db import schema
from tradebot.db.connection import get_connection
from tradebot.db.migrations import run_migrations


def init_db() -> None:
    """Idempotent database initialization.

    1. Creates all base tables (IF NOT EXISTS — safe to re-run).
    2. Applies any unapplied numbered migration files in order.
    """
    conn = get_connection()
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    run_migrations(conn)
```

---

## Validation Architecture

> `nyquist_validation: true` in config.json — this section is REQUIRED.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_db/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Schema has separate raw/signal/execution tables | unit | `uv run pytest tests/test_db/test_schema.py -x` | Wave 0 |
| DATA-02 | `raw_prices.fetched_at` is set; re-insert does not overwrite existing row | unit | `uv run pytest tests/test_db/test_schema.py::test_raw_prices_immutable -x` | Wave 0 |
| DATA-03 | `FetchResult.is_valid` returns False when `row_count == 0` or `freshness_date is None` | unit | `uv run pytest tests/test_models/test_raw_record.py::test_fetch_result_validity -x` | Wave 0 |
| DATA-04 | `raw_insider` / `raw_congressional` rows store both `transaction_date` and `filed_at` | unit | `uv run pytest tests/test_db/test_schema.py::test_disclosure_dates -x` | Wave 0 |
| DATA-05 | `instruments` table: stock rows have NULL expiry/strike; option rows have non-NULL values | unit | `uv run pytest tests/test_db/test_schema.py::test_instruments_options_aware -x` | Wave 0 |
| DATA-06 | `universe_snapshots` is queryable by `week_start` date | unit | `uv run pytest tests/test_db/test_schema.py::test_universe_snapshots_queryable -x` | Wave 0 |

### Detailed Test Scenarios

**TEST-DATA-01: Schema table separation**
- Fixture: `db` (in-memory, schema applied)
- Exercise: Query `information_schema.tables` for all expected table names
- Assert: Tables `raw_prices`, `raw_insider`, `raw_congressional`, `raw_macro`, `signals`, `recommendations`, `orders`, `trades`, `universe_snapshots` all exist
- Anti-assert: No single "all_data" table — tables are in the correct layer (raw vs signal vs execution)

```python
def test_schema_table_separation(db):
    rows = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    raw_tables = {"raw_prices", "raw_insider", "raw_congressional", "raw_macro"}
    signal_tables = {"signals", "recommendations", "universe_snapshots"}
    exec_tables = {"orders", "trades"}
    assert raw_tables <= table_names
    assert signal_tables <= table_names
    assert exec_tables <= table_names
```

**TEST-DATA-02: Immutable raw rows (no overwrite on re-insert)**
- Fixture: `db`
- Exercise: Insert a `raw_prices` row with a specific `fetched_at`, then attempt to INSERT the same primary key
- Assert: Second insert raises an error (PK constraint); original `fetched_at` is unchanged
- Note: Idempotent "no overwrite" means INSERT, not UPSERT

```python
def test_raw_prices_immutable(db):
    import pytest
    db.execute(
        "INSERT INTO raw_prices VALUES (1, 'AAPL', '2024-01-02', 180.0, 182.0, 179.0, 181.0, 1000000, '2024-01-03 10:00:00+00', 'yfinance')"
    )
    with pytest.raises(Exception):  # DuckDB ConstraintException on PK violation
        db.execute(
            "INSERT INTO raw_prices VALUES (1, 'AAPL', '2024-01-02', 999.0, 999.0, 999.0, 999.0, 0, '2024-01-04 10:00:00+00', 'yfinance')"
        )
    row = db.execute("SELECT close FROM raw_prices WHERE id = 1").fetchone()
    assert row[0] == 181.0  # Original value preserved
```

**TEST-DATA-03: FetchResult validity gate**
- No DB fixture needed (pure dataclass test)
- Exercise: Construct `FetchResult` with various `row_count` / `freshness_date` combinations
- Assert: `is_valid` is True only when both fields are valid

```python
from datetime import date
from tradebot.models.raw_record import FetchResult

def test_fetch_result_validity():
    today = date.today()
    assert FetchResult("yfinance", "AAPL", 100, today).is_valid is True
    assert FetchResult("yfinance", "AAPL", 0, today).is_valid is False
    assert FetchResult("yfinance", "AAPL", 100, None).is_valid is False
    assert FetchResult("yfinance", "AAPL", 0, None).is_valid is False
```

**TEST-DATA-04: Disclosure dual-date storage**
- Fixture: `db`
- Exercise: Insert a `raw_insider` row with both `transaction_date` and `filed_at` set to different dates
- Assert: Both dates are stored and retrievable independently; neither is aliased to the other

```python
def test_disclosure_dates(db):
    db.execute(
        "INSERT INTO raw_insider VALUES ('tx1', 'MSFT', 'Jane Smith', '2024-01-10', '2024-01-15', 500.0, 300.0, 'Form4', 'P', '2024-01-15 12:00:00+00')"
    )
    row = db.execute("SELECT transaction_date, filed_at FROM raw_insider WHERE id = 'tx1'").fetchone()
    assert str(row[0]) == "2024-01-10"
    assert str(row[1]) == "2024-01-15"
    assert row[0] != row[1]  # Distinct dates are stored independently
```

**TEST-DATA-05: Instruments table is options-aware**
- Fixture: `db`
- Exercise: Insert a stock (NULL expiry/strike) and a call option (non-NULL)
- Assert: Stock row has NULL expiry and strike; option row has valid date and price

```python
def test_instruments_options_aware(db):
    # Stock: expiry and strike must be NULL
    db.execute("INSERT INTO instruments VALUES ('AAPL', 'AAPL', 'stock', NULL, NULL, now())")
    # Call option: expiry and strike must be populated
    db.execute("INSERT INTO instruments VALUES ('AAPL_20251219_C200', 'AAPL', 'call', '2025-12-19', 200.0, now())")

    stock = db.execute("SELECT expiry, strike FROM instruments WHERE id = 'AAPL'").fetchone()
    assert stock[0] is None and stock[1] is None

    opt = db.execute("SELECT expiry, strike FROM instruments WHERE id = 'AAPL_20251219_C200'").fetchone()
    assert opt[0] is not None and opt[1] == 200.0
```

**TEST-DATA-06: universe_snapshots queryable by week**
- Fixture: `db`
- Exercise: Insert snapshots for two different weeks; query by `week_start`
- Assert: Week filter returns only tickers from that week

```python
from datetime import date

def test_universe_snapshots_queryable(db):
    db.execute("INSERT INTO universe_snapshots VALUES (1, '2024-01-08', '2024-01-08', 'AAPL', now())")
    db.execute("INSERT INTO universe_snapshots VALUES (2, '2024-01-08', '2024-01-08', 'MSFT', now())")
    db.execute("INSERT INTO universe_snapshots VALUES (3, '2024-01-15', '2024-01-15', 'GOOGL', now())")

    week1 = db.execute(
        "SELECT ticker FROM universe_snapshots WHERE week_start = '2024-01-08' ORDER BY ticker"
    ).fetchall()
    assert [r[0] for r in week1] == ["AAPL", "MSFT"]

    week2 = db.execute(
        "SELECT ticker FROM universe_snapshots WHERE week_start = '2024-01-15'"
    ).fetchall()
    assert [r[0] for r in week2] == ["GOOGL"]
```

**TEST-IDEMPOTENT: init_db() is safe to call twice**
- Fixture: `db`
- Exercise: Call `init_db()` twice in sequence using the in-memory `db` fixture
- Assert: No exception raised; table count is unchanged after second call

```python
def test_init_db_idempotent(db, monkeypatch):
    monkeypatch.setattr("tradebot.db.connection._connection", db)
    from tradebot.db import init_db
    init_db()  # First call
    init_db()  # Second call — must be a no-op
    rows = db.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchone()
    assert rows[0] > 0  # Tables exist
```

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_db/ tests/test_models/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_db/test_schema.py` — covers DATA-01, DATA-02, DATA-04, DATA-05, DATA-06
- [ ] `tests/test_models/test_raw_record.py` — covers DATA-03
- [ ] `tests/test_db/test_init_db.py` — covers idempotency success criterion 5
- [ ] `tests/conftest.py` — `db` fixture (in-memory DuckDB with schema)
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — test path config

---

## Security Domain

> `security_enforcement: true` and `security_asvs_level: 1` in config.json.

### Applicable ASVS Categories (Level 1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No — no user auth in this phase | N/A |
| V3 Session Management | No — CLI tool, no sessions | N/A |
| V4 Access Control | No — single-user local process | N/A |
| V5 Input Validation | Yes — SQL inputs must be parameterized | DuckDB parameterized queries (`?` placeholders) |
| V6 Cryptography | No — no crypto in this phase | N/A |
| V7 Error Handling | Partial — migration errors must not expose paths | Use `loguru` to log, not print to stdout |
| V8 Data Protection | Yes — `.env.paper` / `.env.live` must not be committed | `.gitignore` must exclude both files |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via ticker symbol | Tampering | Always use `conn.execute(sql, [ticker])` parameterized form — never f-string interpolation |
| Secrets in source control | Information Disclosure | `.env.paper` and `.env.live` in `.gitignore`; only `.env.example` committed |
| Migration file path traversal | Tampering | `Path(__file__).parent.glob("*.sql")` — no user-supplied paths in migration runner |
| Connection left open on exception | Denial of Service | `try/finally` in `init_db()` if needed; DuckDB closes on process exit but explicit close in tests is good hygiene |

---

## Implementation Risks

### Risk 1: Settings singleton loaded before .env file

**What goes wrong:** If any module-level code imports `from tradebot.config import settings` before `_load_env()` runs (e.g., during pytest collection), env vars may not be set.

**Why it happens:** Python executes module-level code at import time. If `settings = Settings()` runs before `_load_env()`, all `os.environ.get()` calls in `Settings` field defaults return fallback values.

**How to avoid:** `_load_env()` is called at the top of `config.py` before `settings = Settings()`. This ensures the `.env` file is parsed before the Settings dataclass reads `os.environ`. Tests should also set `TRADEBOT_MODE` before importing `tradebot.config`.

**Warning signs:** `settings.alpaca_key` is empty string in tests, or `settings.db_path` is the default instead of the test override.

### Risk 2: DuckDB singleton holds a file connection in tests

**What goes wrong:** If `get_connection()` is called before `monkeypatch.setattr` in a test, it creates a real file-based connection to `data/tradebot.duckdb`. Subsequent `monkeypatch` override has no effect because the module-level `_connection` is already set.

**Why it happens:** Python caches the module-level `_connection` variable. Once set, `get_connection()` returns it without re-reading the patched value.

**How to avoid:** The `db` fixture in `conftest.py` must call `monkeypatch.setattr("tradebot.db.connection._connection", conn)` before any production code runs. Import `init_db` inside the test body, not at module level.

**Warning signs:** Tests write actual `.duckdb` files to `data/` during test runs, or test data persists between test sessions.

### Risk 3: Migration runner applies same migration twice after connection reset

**What goes wrong:** If `_reset_connection()` is called and `init_db()` is run again, migration runner queries `schema_versions` table — but if the test used an in-memory DB that was closed, the `schema_versions` table is empty in the new connection and migrations re-apply.

**Why it happens:** In-memory DuckDB is ephemeral — closing the connection destroys all data including migration history.

**How to avoid:** This is expected behavior for in-memory test DBs. Migration re-application in tests is harmless because all migrations use `IF NOT EXISTS`. Production file-based DBs retain `schema_versions` across restarts.

### Risk 4: `instrument_type` CHECK constraint not enforced at insert time

**What goes wrong:** DuckDB enforces `CHECK` constraints on INSERT/UPDATE. If a fetcher tries to insert an `instrument_type` value not in `('stock', 'call', 'put')`, it raises a `ConstraintException`.

**Why it happens:** Valid during schema design but easy to forget when adding new instrument categories (e.g., "future", "etf").

**How to avoid:** The `Instrument` dataclass uses `Literal["stock", "call", "put"]` to surface the constraint at the Python type level. Add a test that validates the CHECK constraint is enforced.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DuckDB 1.0–1.3 has no breaking changes to `connect()`, `execute()`, `fetchdf()`, `fetchall()` APIs | DuckDB API Patterns | If a breaking change exists, singleton pattern may need updating before planner finalizes |
| A2 | `BIGINT PRIMARY KEY` is sufficient for `raw_prices`, `signals`, `recommendations` auto-increment | DuckDB API Patterns / Schema | DuckDB uses SEQUENCE for auto-increment; may need `BIGINT DEFAULT nextval('seq')` instead of relying on application-side ID assignment |

**Note on A2:** DuckDB does not have `AUTOINCREMENT` like SQLite. The application must either generate IDs (e.g., hash of source+ticker+date) or use `CREATE SEQUENCE`. The schema above uses `BIGINT PRIMARY KEY` — the implementation will need application-side ID generation or a sequence. Planner should address this.

---

## Open Questions

1. **Auto-increment / sequence for BIGINT PKs**
   - What we know: DuckDB supports `CREATE SEQUENCE` and `nextval()`, but not bare `AUTOINCREMENT`
   - What's unclear: Should `raw_prices.id`, `signals.id`, etc. use application-generated hashes, a DuckDB sequence, or `uuid()`?
   - Recommendation: Use a deterministic hash (e.g., `hash(ticker + date + source)`) for `raw_prices` rows — this also prevents accidental duplicate ingestion. Use `uuid()` for `signals` and `recommendations` where no natural key exists.

2. **`data/` directory creation**
   - What we know: `settings.db_path` defaults to `data/tradebot.duckdb`
   - What's unclear: `init_db()` will fail if `data/` directory does not exist
   - Recommendation: `init_db()` should call `settings.db_path.parent.mkdir(parents=True, exist_ok=True)` before `get_connection()`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | DuckDB 1.3+ minimum | Must verify | check `python3 --version` | — |
| `uv` | Package management | Assumed installed | check `uv --version` | pip |
| `duckdb` 1.3.x | All DB operations | Not yet installed | install via `uv add` | — |
| `python-dotenv` 1.2.x | Config loading | Not yet installed | install via `uv add` | — |

**Missing dependencies with no fallback:**
- `duckdb` and `python-dotenv` must be installed before Phase 1 implementation begins

---

## Sources

### Primary (HIGH confidence)

- [DuckDB Python API Overview](https://duckdb.org/docs/current/clients/python/overview) — connection patterns, `duckdb.connect()` semantics, module-level singleton warning
- [DuckDB Connect Overview](https://duckdb.org/docs/current/connect/overview) — file vs in-memory vs named in-memory distinctions
- CLAUDE.md (project) — pinned versions, DuckDB rationale, test library selection — confirmed live PyPI 2026-07-07

### Secondary (MEDIUM confidence)

- [pytest monkeypatch docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) — `setattr` pattern for singleton override
- [python-dotenv docs](https://pypi.org/project/python-dotenv/) — `load_dotenv(dotenv_path=, override=False)` signature
- [DuckDB GitHub Releases](https://github.com/duckdb/duckdb/releases) — 1.3.x release notes (no Python API breaking changes found)

### Tertiary (LOW confidence)

- WebSearch results on DuckDB singleton and migration patterns — corroborated by official docs
- [MotherDuck DuckDB+Python end-to-end project](https://motherduck.com/blog/duckdb-python-e2e-data-engineering-project-part-1/) — community pattern validation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified against PyPI on 2026-07-07; versions from CLAUDE.md confirmed live
- Architecture: HIGH — DuckDB API patterns confirmed via official docs; singleton/fixture patterns confirmed via pytest docs
- Pitfalls: MEDIUM — settings loading order risk is standard Python import-time behavior (well-known); DuckDB auto-increment gap is ASSUMED based on DuckDB docs scanning

**Research date:** 2026-07-07
**Valid until:** 2026-08-07 (stable libraries; DuckDB API is stable across 1.x)
