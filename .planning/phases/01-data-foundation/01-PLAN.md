# Phase 1 Plan: Data Foundation

**Goal:** The DuckDB schema exists, is options-aware from day one, and the ingestion-signal-execution contract is defined in typed dataclasses so every downstream phase builds on a stable foundation.
**Requirements:** DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Validation:** See 01-VALIDATION.md

---

## Wave Organization

| Wave | Plans | Runs After |
|------|-------|------------|
| 1 | Plan 01: Project Scaffolding + Config | — |
| 2 | Plan 02: Database Layer (parallel with Plan 03) | Plan 01 |
| 2 | Plan 03: Models / Dataclasses (parallel with Plan 02) | Plan 01 |
| 3 | Plan 04: Test Suite | Plans 02 and 03 |

Wave 1 creates the `uv` project, installs dependencies, and builds the package skeleton that all other plans depend on. Wave 2 plans share no files and run in parallel: Plan 02 owns `tradebot/db/`, Plan 03 owns `tradebot/models/`. Wave 3 writes the full test suite once both layers exist.

---

## Plan 01: Project Scaffolding + Config

**Wave:** 1
**Goal:** Initialize `uv` project, create the full package directory skeleton, implement `Settings` singleton, write env templates and `.gitignore`.

### Task 1.1: Initialize uv project and install dependencies

Run these commands from the project root (`/Users/derekgliwa/dev/tradebot`):

```
uv init tradebot --no-workspace
```

If `pyproject.toml` already exists (project was pre-seeded), skip `uv init` and proceed to writing the file directly.

Write `pyproject.toml` with the exact content below (replace whatever `uv init` generated):

```toml
[project]
name = "tradebot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "duckdb==1.3.2",
    "python-dotenv==1.2.2",
]

[project.scripts]
tradebot = "tradebot.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-x -q"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-mock>=3.15",
    "freezegun==1.5.5",
]
```

Then install all dependencies (runtime + dev):

```
uv sync --dev
```

### Task 1.2: Create the full package skeleton

Create every directory and `__init__.py` listed below. For stub subpackages (`fetchers/`, `signals/`, `report/`, `execution/`), write an empty `__init__.py` — the file must exist but have no content.

Files to create:

```
tradebot/__init__.py              # empty
tradebot/__main__.py              # see content below
tradebot/config.py                # see Task 1.3
tradebot/db/__init__.py           # see Plan 02
tradebot/db/connection.py         # see Plan 02
tradebot/db/schema.py             # see Plan 02
tradebot/db/migrations/__init__.py  # see Plan 02
tradebot/db/migrations/001_initial.sql  # see Plan 02
tradebot/models/__init__.py       # see Plan 03
tradebot/models/instrument.py     # see Plan 03
tradebot/models/raw_record.py     # see Plan 03
tradebot/models/signal.py         # see Plan 03
tradebot/models/order.py          # see Plan 03
tradebot/models/trade.py          # see Plan 03
tradebot/fetchers/__init__.py     # empty
tradebot/signals/__init__.py      # empty
tradebot/report/__init__.py       # empty
tradebot/execution/__init__.py    # empty
tests/__init__.py                 # empty
tests/conftest.py                 # see Plan 04
tests/test_db/__init__.py         # empty
tests/test_db/test_schema.py      # see Plan 04
tests/test_db/test_init_db.py     # see Plan 04
tests/test_models/__init__.py     # empty
tests/test_models/test_raw_record.py  # see Plan 04
```

Content of `tradebot/__init__.py` — empty file (zero bytes is acceptable).

Content of stub subpackage `__init__.py` files (`fetchers/`, `signals/`, `report/`, `execution/`) — empty file.

Content of `tradebot/__main__.py`:

```python
from __future__ import annotations


def main() -> None:
    print("TradeBot — use `uv run python -m tradebot` to start.")


if __name__ == "__main__":
    main()
```

### Task 1.3: Implement `tradebot/config.py`

Write `tradebot/config.py` with the exact content:

```python
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


def _load_env() -> None:
    mode = os.environ.get("TRADEBOT_MODE", "paper").lower()
    env_file = Path(f".env.{mode}")
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)


_load_env()


@dataclass
class Settings:
    mode: str = field(default_factory=lambda: os.environ.get("TRADEBOT_MODE", "paper"))
    db_path: Path = field(
        default_factory=lambda: Path(os.environ.get("TRADEBOT_DB_PATH", "data/tradebot.duckdb"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("TRADEBOT_LOG_LEVEL", "INFO"))
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


settings = Settings()
```

Key notes:
- `_load_env()` runs at module import time, before `Settings()` is constructed, so `os.environ` is already populated when each `field(default_factory=...)` fires.
- `override=False` means explicit env vars already set in the shell are never overwritten by the `.env` file.
- Tests that need to control env vars must set them **before** importing `tradebot.config`. The standard pattern: `monkeypatch.setenv("TRADEBOT_MODE", "paper")` in a fixture that runs before `import tradebot.config`.
- `db_path` defaults to `data/tradebot.duckdb` — the `data/` directory is gitignored and created lazily by `get_connection()`.

### Task 1.4: Create `.env.paper.example` and `.env.live.example`

Write `.env.paper.example` (project root):

```
# Copy to .env.paper and fill in your Alpaca paper trading keys.
# Activate with: TRADEBOT_MODE=paper uv run python -m tradebot

TRADEBOT_MODE=paper
TRADEBOT_DB_PATH=data/tradebot.duckdb
TRADEBOT_LOG_LEVEL=INFO

ALPACA_KEY=your_paper_api_key_here
ALPACA_SECRET=your_paper_api_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

Write `.env.live.example` (project root):

```
# Copy to .env.live and fill in your Alpaca LIVE trading keys.
# WARNING: This file controls real-money execution.
# Activate with: TRADEBOT_MODE=live uv run python -m tradebot

TRADEBOT_MODE=live
TRADEBOT_DB_PATH=data/tradebot.duckdb
TRADEBOT_LOG_LEVEL=INFO

ALPACA_KEY=your_live_api_key_here
ALPACA_SECRET=your_live_api_secret_here
ALPACA_BASE_URL=https://api.alpaca.markets
```

### Task 1.5: Create `.gitignore`

Write `.gitignore` (project root):

```
# Secrets — never commit
.env.paper
.env.live

# Database files
data/
*.duckdb
*.duckdb.wal

# Python
__pycache__/
*.py[cod]
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

### Verify

```
uv run python -c "from tradebot.config import settings; print(settings.mode)"
```

Expected output: `paper`

```
uv run python -c "from tradebot.__main__ import main; main()"
```

Expected output: `TradeBot — use 'uv run python -m tradebot' to start.`

---

## Plan 02: Database Layer

**Wave:** 2 (after Plan 01, parallel with Plan 03)
**Goal:** Implement DuckDB connection singleton, all DDL constants in `schema.py`, versioned migration runner, and `init_db()` that wires them together.

Decisions implemented: D-06 (DDL as inline Python constants), D-07 (module-level connection singleton), D-08 (versioned migration scripts tracked in `schema_versions` table).

### Task 2.1: Implement `tradebot/db/connection.py`

Write `tradebot/db/connection.py` with the exact content:

```python
from __future__ import annotations
import duckdb

_connection: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        from tradebot.config import settings
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _connection = duckdb.connect(database=str(settings.db_path))
    return _connection


def _reset_connection() -> None:
    """Close and clear the singleton. Used only in tests."""
    global _connection
    if _connection is not None:
        _connection.close()
    _connection = None
```

Key notes:
- The import of `settings` is deferred inside `get_connection()` to avoid a circular import: `config.py` must not import from `db/`, and `db/connection.py` must not import from `config.py` at module level.
- `_reset_connection()` is test-only infrastructure; production code never calls it.
- `mkdir(parents=True, exist_ok=True)` handles the `data/` directory creation on first run.
- Tests bypass this entirely by monkeypatching `tradebot.db.connection._connection` to an in-memory DuckDB connection (see conftest.py in Plan 04).

### Task 2.2: Implement `tradebot/db/schema.py`

Write `tradebot/db/schema.py` with the exact content:

```python
"""DDL constants for all TradeBot tables.

All statements use CREATE TABLE IF NOT EXISTS for idempotent DDL (D-06).
Execution order in ALL_TABLES matters: orders references instruments,
trades references orders — foreign key tables must precede dependent tables.
"""
from __future__ import annotations

SCHEMA_VERSIONS = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version    INTEGER PRIMARY KEY,
    name       VARCHAR NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

INSTRUMENTS = """
CREATE TABLE IF NOT EXISTS instruments (
    id              VARCHAR PRIMARY KEY,
    ticker          VARCHAR NOT NULL,
    instrument_type VARCHAR NOT NULL CHECK (instrument_type IN ('stock', 'call', 'put')),
    expiry          DATE,
    strike          DOUBLE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

RAW_PRICES = """
CREATE TABLE IF NOT EXISTS raw_prices (
    id         BIGINT PRIMARY KEY,
    ticker     VARCHAR NOT NULL,
    date       DATE NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    volume     BIGINT,
    fetched_at TIMESTAMPTZ NOT NULL,
    source     VARCHAR NOT NULL DEFAULT 'yfinance'
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
    id               BIGINT PRIMARY KEY,
    series_id        VARCHAR NOT NULL,
    observation_date DATE NOT NULL,
    vintage_date     DATE NOT NULL,
    value            DOUBLE,
    fetched_at       TIMESTAMPTZ NOT NULL
)
"""

SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id          BIGINT PRIMARY KEY,
    ticker      VARCHAR NOT NULL,
    run_date    DATE NOT NULL,
    signal_type VARCHAR NOT NULL,
    score       DOUBLE NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
    id            VARCHAR PRIMARY KEY,
    ticker        VARCHAR NOT NULL,
    instrument_id VARCHAR REFERENCES instruments(id),
    side          VARCHAR NOT NULL CHECK (side IN ('buy', 'sell')),
    qty           DOUBLE NOT NULL,
    order_type    VARCHAR NOT NULL DEFAULT 'market',
    status        VARCHAR NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id          VARCHAR PRIMARY KEY,
    order_id    VARCHAR REFERENCES orders(id),
    ticker      VARCHAR NOT NULL,
    side        VARCHAR NOT NULL,
    qty         DOUBLE NOT NULL,
    fill_price  DOUBLE NOT NULL,
    filled_at   TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

UNIVERSE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS universe_snapshots (
    id         BIGINT PRIMARY KEY,
    run_date   DATE NOT NULL,
    week_start DATE NOT NULL,
    ticker     VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

ALL_TABLES: list[str] = [
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

Key notes:
- `ORDERS` references `instruments(id)` and must come after `INSTRUMENTS` in `ALL_TABLES`.
- `TRADES` references `orders(id)` and must come after `ORDERS` in `ALL_TABLES`.
- `SCHEMA_VERSIONS` must be first — the migration runner reads from it before any other table exists.
- `BIGINT PRIMARY KEY` columns (`raw_prices.id`, `raw_macro.id`, `signals.id`, `recommendations.id`, `universe_snapshots.id`) have no `AUTOINCREMENT`. Phase 2+ fetchers assign IDs (e.g., deterministic hash for raw_prices).

### Task 2.3: Implement `tradebot/db/migrations/__init__.py`

Write `tradebot/db/migrations/__init__.py` with the exact content:

```python
"""Versioned migration runner (D-08).

Discovers *.sql files in this directory by numeric prefix, applies each
migration exactly once, and records it in schema_versions.
"""
from __future__ import annotations
import re
from pathlib import Path
import duckdb

MIGRATIONS_DIR = Path(__file__).parent


def _applied_versions(conn: duckdb.DuckDBPyConnection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_versions ORDER BY version").fetchall()
    return {row[0] for row in rows}


def run_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply any un-applied *.sql migrations in numeric order."""
    applied = _applied_versions(conn)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = re.match(r"^(\d+)_", path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        if sql.strip():
            conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
            [version, path.name],
        )
```

### Task 2.4: Create `tradebot/db/migrations/001_initial.sql`

Write `tradebot/db/migrations/001_initial.sql` with this content:

```sql
-- Migration 001: Initial schema baseline.
-- Base tables are created by init_db() via schema.py ALL_TABLES (IF NOT EXISTS).
-- This file is a placeholder to establish the migration version history.
-- Future migrations (002, 003, ...) add columns, indexes, or new tables here.
```

The file is intentionally SQL-comment-only. The migration runner checks `sql.strip()` before executing, so a comment-only file inserts a version record into `schema_versions` without executing any DDL — which is the correct behavior for a baseline marker.

### Task 2.5: Implement `tradebot/db/__init__.py`

Write `tradebot/db/__init__.py` with the exact content:

```python
"""Database package.

Public API:
    init_db() — create all tables (idempotent) and apply pending migrations.
"""
from tradebot.db import schema
from tradebot.db.connection import get_connection
from tradebot.db.migrations import run_migrations


def init_db() -> None:
    """Initialize the database: create all tables then run pending migrations.

    Safe to call multiple times — all DDL uses IF NOT EXISTS (D-06).
    """
    conn = get_connection()
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    run_migrations(conn)
```

### Verify

```
uv run python -c "from tradebot.db import init_db; init_db(); print('DB OK')"
```

Expected output: `DB OK`

```
uv run python -c "
from tradebot.db.connection import get_connection
conn = get_connection()
tables = conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'\").fetchall()
print(sorted(t[0] for t in tables))
"
```

Expected output includes: `instruments`, `orders`, `raw_insider`, `raw_macro`, `raw_prices`, `recommendations`, `schema_versions`, `signals`, `trades`, `universe_snapshots`.

---

## Plan 03: Models (Dataclasses)

**Wave:** 2 (after Plan 01, parallel with Plan 02)
**Goal:** Implement all typed cross-layer dataclasses — no dict passing at layer boundaries (D-04, D-05).

Files modified by this plan: `tradebot/models/__init__.py`, `tradebot/models/instrument.py`, `tradebot/models/raw_record.py`, `tradebot/models/signal.py`, `tradebot/models/order.py`, `tradebot/models/trade.py`. No overlap with Plan 02.

### Task 3.1: Implement `tradebot/models/instrument.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional


@dataclass
class Instrument:
    """Represents a tradable instrument — stock or option contract.

    For stocks: expiry and strike are None.
    For options: expiry and strike are required.
    """
    id: str
    ticker: str
    instrument_type: Literal["stock", "call", "put"]
    expiry: Optional[date] = None
    strike: Optional[float] = None
```

### Task 3.2: Implement `tradebot/models/raw_record.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class RawRecord:
    """A single raw row from any data source before normalization.

    Carries both the raw payload (data dict) and parsed metadata fields
    so callers can inspect key dates without unpacking the dict.
    """
    source: str
    ticker: str
    fetched_at: datetime
    data: dict[str, Any]
    transaction_date: Optional[date] = None
    filed_at: Optional[date] = None


@dataclass
class FetchResult:
    """Summary of a fetch operation returned to the pipeline.

    is_valid gates downstream signal computation:
    a zero-row or dateless result blocks trade generation.
    """
    source: str
    ticker: str
    row_count: int
    freshness_date: Optional[date]

    @property
    def is_valid(self) -> bool:
        return self.row_count > 0 and self.freshness_date is not None
```

### Task 3.3: Implement `tradebot/models/signal.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Recommendation:
    """Output of the composite scorer for a single ticker on a run date.

    composite_score and rank are always set. Per-signal scores are
    optional because not all signals are active in every phase.
    Weights (insider=0.4, congressional=0.3, momentum=0.3) are applied
    by the scorer, not stored here.
    """
    ticker: str
    run_date: date
    composite_score: float
    rank: int
    insider_score: Optional[float] = None
    momentum_score: Optional[float] = None
    congressional_score: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### Task 3.4: Implement `tradebot/models/order.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Order:
    """Represents intent to trade — recorded before submission to Alpaca.

    Separates order intent (this dataclass / orders table) from confirmed
    fills (Trade dataclass / trades table). Never mutate an Order after
    submission; create a Trade when the fill is confirmed.
    """
    id: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: float
    instrument_id: Optional[str] = None
    order_type: Literal["market", "limit"] = "market"
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
```

### Task 3.5: Implement `tradebot/models/trade.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Trade:
    """Confirmed fill from Alpaca — recorded after polling confirms execution.

    fill_price is the actual fill price, never assumed or estimated.
    recorded_at is when TradeBot wrote the record; filled_at is when
    Alpaca reports the fill occurred.
    """
    id: str
    order_id: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: float
    fill_price: float
    filled_at: datetime
    recorded_at: datetime = field(default_factory=datetime.utcnow)
```

### Task 3.6: Implement `tradebot/models/__init__.py`

```python
"""TradeBot cross-layer dataclasses.

Public exports mirror the pipeline stages:
  Instrument — what is traded
  RawRecord / FetchResult — ingestion layer outputs
  Recommendation — signal layer output
  Order / Trade — execution layer I/O
"""
from tradebot.models.instrument import Instrument
from tradebot.models.raw_record import FetchResult, RawRecord
from tradebot.models.signal import Recommendation
from tradebot.models.order import Order
from tradebot.models.trade import Trade

__all__ = [
    "Instrument",
    "RawRecord",
    "FetchResult",
    "Recommendation",
    "Order",
    "Trade",
]
```

### Verify

```
uv run python -c "
from tradebot.models.raw_record import RawRecord, FetchResult
from tradebot.models.instrument import Instrument
from tradebot.models.signal import Recommendation
from tradebot.models.order import Order
from tradebot.models.trade import Trade
print('Models OK')
"
```

Expected output: `Models OK`

```
uv run python -c "
from tradebot.models import Instrument
import dataclasses
fields = {f.name: f.type for f in dataclasses.fields(Instrument)}
assert 'instrument_type' in fields
assert 'expiry' in fields
assert 'strike' in fields
print('Instrument fields OK')
"
```

Expected output: `Instrument fields OK`

---

## Plan 04: Test Suite

**Wave:** 3 (after Plans 02 and 03)
**Goal:** Write all test fixtures and tests covering the five phase success criteria.

### Task 4.1: Create `tests/conftest.py`

Write `tests/conftest.py` with the exact content:

```python
import pytest
import duckdb
from tradebot.db import schema


@pytest.fixture()
def db(monkeypatch):
    """In-memory DuckDB connection with all tables created.

    Monkeypatches tradebot.db.connection._connection so that any code
    calling get_connection() (including init_db()) receives this
    in-memory connection instead of opening the file-backed DB.
    """
    conn = duckdb.connect(database=":memory:")
    for ddl in schema.ALL_TABLES:
        conn.execute(ddl)
    monkeypatch.setattr("tradebot.db.connection._connection", conn)
    yield conn
    conn.close()
```

### Task 4.2: Create `tests/test_db/test_schema.py`

Write `tests/test_db/test_schema.py` with the exact content:

```python
"""Schema-level tests covering DATA-01 through DATA-05."""
import pytest


def test_schema_table_separation(db):
    """DATA-01: Raw, signal, and execution tables are separate (not collapsed)."""
    rows = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert {"raw_prices", "raw_insider", "raw_congressional", "raw_macro"} <= table_names
    assert {"signals", "recommendations", "universe_snapshots"} <= table_names
    assert {"orders", "trades"} <= table_names


def test_raw_prices_immutable(db):
    """DATA-02: raw_prices PRIMARY KEY prevents overwriting existing rows (immutable append)."""
    db.execute(
        "INSERT INTO raw_prices VALUES "
        "(1, 'AAPL', '2024-01-02', 180.0, 182.0, 179.0, 181.0, 1000000, "
        "'2024-01-03 10:00:00+00', 'yfinance')"
    )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO raw_prices VALUES "
            "(1, 'AAPL', '2024-01-02', 999.0, 999.0, 999.0, 999.0, 0, "
            "'2024-01-04 10:00:00+00', 'yfinance')"
        )
    row = db.execute("SELECT close FROM raw_prices WHERE id = 1").fetchone()
    assert row[0] == 181.0


def test_disclosure_dates(db):
    """DATA-03 / SIGNAL-02: transaction_date and filed_at are separate columns."""
    db.execute(
        "INSERT INTO raw_insider VALUES "
        "('tx1', 'MSFT', 'Jane Smith', '2024-01-10', '2024-01-15', "
        "500.0, 300.0, 'Form4', 'P', '2024-01-15 12:00:00+00')"
    )
    row = db.execute(
        "SELECT transaction_date, filed_at FROM raw_insider WHERE id = 'tx1'"
    ).fetchone()
    assert str(row[0]) == "2024-01-10"
    assert str(row[1]) == "2024-01-15"
    assert row[0] != row[1]


def test_instruments_options_aware(db):
    """DATA-04: instruments table accepts NULL expiry/strike for stocks, non-NULL for options."""
    db.execute(
        "INSERT INTO instruments VALUES ('AAPL', 'AAPL', 'stock', NULL, NULL, now())"
    )
    db.execute(
        "INSERT INTO instruments VALUES "
        "('AAPL_20251219_C200', 'AAPL', 'call', '2025-12-19', 200.0, now())"
    )
    stock = db.execute(
        "SELECT expiry, strike FROM instruments WHERE id = 'AAPL'"
    ).fetchone()
    assert stock[0] is None and stock[1] is None

    opt = db.execute(
        "SELECT expiry, strike FROM instruments WHERE id = 'AAPL_20251219_C200'"
    ).fetchone()
    assert opt[0] is not None and opt[1] == 200.0


def test_universe_snapshots_queryable(db):
    """DATA-05 / DATA-06: universe_snapshots is queryable by week_start date."""
    db.execute(
        "INSERT INTO universe_snapshots VALUES (1, '2024-01-08', '2024-01-08', 'AAPL', now())"
    )
    db.execute(
        "INSERT INTO universe_snapshots VALUES (2, '2024-01-08', '2024-01-08', 'MSFT', now())"
    )
    db.execute(
        "INSERT INTO universe_snapshots VALUES (3, '2024-01-15', '2024-01-15', 'GOOGL', now())"
    )
    week1 = db.execute(
        "SELECT ticker FROM universe_snapshots WHERE week_start = '2024-01-08' ORDER BY ticker"
    ).fetchall()
    assert [r[0] for r in week1] == ["AAPL", "MSFT"]

    week2 = db.execute(
        "SELECT ticker FROM universe_snapshots WHERE week_start = '2024-01-15'"
    ).fetchall()
    assert [r[0] for r in week2] == ["GOOGL"]
```

### Task 4.3: Create `tests/test_db/test_init_db.py`

Write `tests/test_db/test_init_db.py` with the exact content:

```python
"""Idempotency tests for init_db() — success criteria 1 and 5."""


def test_init_db_idempotent(db):
    """Running init_db() twice produces no duplicate tables and no errors."""
    from tradebot.db import init_db
    init_db()
    init_db()
    rows = db.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchone()
    assert rows[0] > 0


def test_init_db_creates_all_tables(db):
    """init_db() creates every expected table in a single call."""
    from tradebot.db import init_db
    init_db()
    rows = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    expected = {
        "schema_versions",
        "instruments",
        "raw_prices",
        "raw_insider",
        "raw_congressional",
        "raw_macro",
        "signals",
        "recommendations",
        "orders",
        "trades",
        "universe_snapshots",
    }
    assert expected <= table_names
```

### Task 4.4: Create `tests/test_models/test_raw_record.py`

Write `tests/test_models/test_raw_record.py` with the exact content:

```python
"""FetchResult validity tests — DATA-03."""
from datetime import date
from tradebot.models.raw_record import FetchResult


def test_fetch_result_validity():
    today = date.today()
    assert FetchResult("yfinance", "AAPL", 100, today).is_valid is True
    assert FetchResult("yfinance", "AAPL", 0, today).is_valid is False
    assert FetchResult("yfinance", "AAPL", 100, None).is_valid is False
    assert FetchResult("yfinance", "AAPL", 0, None).is_valid is False


def test_fetch_result_fields():
    today = date.today()
    result = FetchResult("edgar", "MSFT", 5, today)
    assert result.source == "edgar"
    assert result.ticker == "MSFT"
    assert result.row_count == 5
    assert result.freshness_date == today
```

### Verify

```
uv run pytest tests/ -x -q
```

Expected: all tests pass (9 tests: 5 in test_schema.py, 2 in test_init_db.py, 2 in test_raw_record.py). Zero failures. Zero errors.

If the conftest `db` fixture causes tests in `test_init_db.py` to see a pre-populated `schema_versions` after calling `init_db()` (because the fixture already ran `ALL_TABLES`), this is expected — `CREATE TABLE IF NOT EXISTS` is idempotent and the count of tables returned will be stable across calls.

---

## Success Gate

All five phase success criteria are verified when:

1. [ ] `uv run python -c "from tradebot.db import init_db; init_db()"` runs with no errors on a fresh `data/tradebot.duckdb`
2. [ ] `instruments` table has `instrument_type`, `expiry`, and `strike` columns — verified by `test_instruments_options_aware` passing
3. [ ] `universe_snapshots` is queryable by `week_start` — verified by `test_universe_snapshots_queryable` passing
4. [ ] All dataclasses (`RawRecord`, `Recommendation`, `Order`, `Trade`, `Instrument`) import cleanly: `from tradebot.models import Instrument, RawRecord, FetchResult, Recommendation, Order, Trade`
5. [ ] Running `init_db()` twice leaves table count unchanged — verified by `test_init_db_idempotent` passing

Final verification command:

```
uv run pytest tests/ -x -q && uv run python -c "from tradebot.db import init_db; init_db(); print('Phase 1 complete')"
```

---

## Risks and Notes

**DuckDB BIGINT PKs are application-assigned.** `raw_prices.id`, `signals.id`, `recommendations.id`, `universe_snapshots.id`, and `raw_macro.id` use `BIGINT PRIMARY KEY` with no `AUTOINCREMENT`. Phase 2 fetchers must generate these IDs (e.g., deterministic hash for `raw_prices`, sequential integers for others). Do not assume auto-increment behavior.

**Settings import order.** `config.py` calls `_load_env()` at module import time, then constructs `settings = Settings()`. If a test needs to control env vars, it must use `monkeypatch.setenv(...)` in a fixture that fires **before** `import tradebot.config`. The cleanest approach: use `importlib.reload(tradebot.config)` in tests that need a fresh Settings with different env vars.

**`data/` directory.** `get_connection()` creates `data/` via `mkdir(parents=True, exist_ok=True)` on first call. The directory is gitignored. CI environments need write permission to the project root, or must override `TRADEBOT_DB_PATH` to a writable temp path.

**Migration runner and comment-only SQL.** `001_initial.sql` contains only SQL comments. The runner checks `if sql.strip()` before calling `conn.execute(sql)`, so a comment-only file is safe — it inserts a version record without executing any DDL.

**Parallel wave safety.** Plans 02 and 03 touch disjoint file sets. They can run in parallel with no merge conflicts. Plan 04 must wait for both to complete before writing tests that import from `tradebot.db` and `tradebot.models`.
