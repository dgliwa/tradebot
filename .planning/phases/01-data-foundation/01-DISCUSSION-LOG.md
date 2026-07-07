# Phase 1: Data Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-07
**Phase:** 1-Data Foundation
**Areas discussed:** Package layout, Dataclass library, DDL organization, Config & secrets approach

---

## Package Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Flat | tradebot/db.py, tradebot/models.py, tradebot/fetchers.py | |
| Domain-layered | tradebot/db/, tradebot/models/, tradebot/fetchers/, tradebot/signals/ | ✓ |
| src-layout | src/tradebot/ — protects against accidental imports | |

**User's choice:** Domain-layered subpackages

| Option | Description | Selected |
|--------|-------------|----------|
| Technical layer | db/, models/, fetchers/, signals/, report/ | ✓ |
| Business domain | insider/, congressional/, macro/, execution/ | |

**User's choice:** Technical layer — mirrors pipeline stages

| Option | Description | Selected |
|--------|-------------|----------|
| tradebot/__main__.py | `uv run python -m tradebot` entrypoint | ✓ |
| run_weekly.py at root | Standalone script importing from package | |
| Both | __main__.py delegates to same logic as run_weekly.py | |

**User's choice:** `tradebot/__main__.py` only

---

## Dataclass Library

| Option | Description | Selected |
|--------|-------------|----------|
| @dataclass | Zero overhead, no extra dependency | ✓ |
| Pydantic BaseModel | Runtime validation, .model_dump(), adds dependency | |
| TypedDict | Pure type annotations, no runtime class | |

**User's choice:** Vanilla `@dataclass`

| Option | Description | Selected |
|--------|-------------|----------|
| tradebot/models/ subpackage | One file per entity | ✓ |
| tradebot/models.py single file | All dataclasses in one file | |
| Co-located with layer | Signal types in signals/, order types in execution/ | |

**User's choice:** `tradebot/models/` subpackage with per-entity files

---

## DDL Organization

| Option | Description | Selected |
|--------|-------------|----------|
| Inline Python strings in tradebot/db/schema.py | DDL as Python constants, IF NOT EXISTS | ✓ |
| External .sql files in schema/ | schema/raw.sql, schema/signals.sql, etc. | |
| DuckDB programmatic DDL | Build schema via Python API calls | |

**User's choice:** Inline Python constants in `tradebot/db/schema.py`

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level singleton: get_connection() | Returns same DuckDB connection | ✓ |
| Pass connection as argument | Explicit dependency injection | |
| Context manager per operation | Open/close per query | |

**User's choice:** Module-level singleton in `tradebot/db/connection.py`

| Option | Description | Selected |
|--------|-------------|----------|
| ALTER TABLE idempotently at startup | try/except per new column | |
| Versioned migration scripts in db/migrations/ | 001_initial.sql, 002_add_column.sql | ✓ |
| Drop and recreate on schema change | Simplest but requires re-fetch | |

**User's choice:** Versioned migration scripts — more rigorous, reproducible schema state

---

## Config & Secrets Approach

| Option | Description | Selected |
|--------|-------------|----------|
| python-dotenv with .env.paper / .env.live | TRADEBOT_MODE selects file | ✓ |
| pydantic-settings with PaperSettings/LiveSettings | Type-safe, validated | |
| Raw os.environ with Settings dataclass | No .env file support | |

**User's choice:** `python-dotenv` with separate `.env.paper` / `.env.live`

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level Settings instance | `from tradebot.config import settings` | ✓ |
| Lazy singleton: get_settings() | Loads on first call, easier to mock | |

**User's choice:** Module-level `settings` instance in `tradebot/config.py`

---

## Claude's Discretion

- Specific field names within `Settings` dataclass (follow Alpaca SDK conventions)
- Whether migrations use `.sql` files or Python functions
- Pytest fixture patterns for DuckDB in-memory connections

## Deferred Ideas

None — discussion stayed within phase scope.
