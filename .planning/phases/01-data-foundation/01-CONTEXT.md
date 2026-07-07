# Phase 1: Data Foundation - Context

**Gathered:** 2026-07-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish the DuckDB schema, typed dataclasses, project package structure, and config loading pattern that every downstream phase builds on. Deliver: `init_db()` (idempotent schema + versioned migrations), `tradebot/models/` dataclasses, `tradebot/db/` connection singleton, and `tradebot/config.py` settings — all with mocked HTTP test coverage. No live network calls, no fetchers yet.

</domain>

<decisions>
## Implementation Decisions

### Package Layout
- **D-01:** Domain-layered subpackage structure: `tradebot/db/`, `tradebot/models/`, `tradebot/fetchers/`, `tradebot/signals/`, `tradebot/report/`, `tradebot/execution/`. Mirrors pipeline stages (ingest → score → act).
- **D-02:** Technical-layer organization (not business-domain grouping). Keeps DB/model utilities shareable across all fetchers/signals without circular imports.
- **D-03:** CLI entrypoint is `tradebot/__main__.py`, enabling `uv run python -m tradebot`. No root-level `run_weekly.py`.

### Dataclass Library
- **D-04:** Use vanilla `@dataclass` for all cross-layer types (`RawRecord`, `Recommendation`, `Order`, `Trade`, `Instrument`). Zero runtime overhead, no extra dependency. Validation happens at the data source boundary in fetchers.
- **D-05:** Shared dataclasses live in `tradebot/models/` subpackage. One file per entity: `instrument.py`, `signal.py`, `order.py`, `trade.py`. Avoids circular import risk.

### DDL Organization
- **D-06:** DDL (CREATE TABLE statements) lives as inline Python constants in `tradebot/db/schema.py`. No external `.sql` files. Uses `IF NOT EXISTS` for base table creation.
- **D-07:** DuckDB connection shared via module-level singleton: `get_connection()` in `tradebot/db/connection.py`. Returns the same in-process connection. Tests swap it for an in-memory connection.
- **D-08:** Schema migration for future phases uses **versioned migration scripts** in `tradebot/db/migrations/`. Numbered files (e.g., `001_initial.sql`, `002_add_column.sql`) applied in order at startup. More rigorous than try/except ALTER TABLE; ensures reproducible schema state.

### Config & Secrets
- **D-09:** Use `python-dotenv` to load separate `.env.paper` and `.env.live` files. Which file loads is determined by the `TRADEBOT_MODE` environment variable. Aligns with REQUIREMENTS.md EXEC-02.
- **D-10:** Config accessed via `from tradebot.config import settings` — a module-level `Settings` dataclass instance, loaded once at import time. Simple and conventional for a solo project.

### Claude's Discretion
- Specific field names within `Settings` dataclass (API keys, DB path, log level) — follow the pattern established by Alpaca SDK conventions and REQUIREMENTS.md references.
- Whether `tradebot/db/migrations/` stores `.sql` files or Python functions — Claude's call based on simplicity.
- Test fixture patterns for DuckDB in-memory connections — standard pytest fixture approach.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Requirements
- `.planning/REQUIREMENTS.md` — All DATA-*, EXEC-02 (env file pattern), EXEC-03 (orders vs trades separation), SIGNAL-02 (filed_at usage), SIGNAL-05 (composite scoring weights)
- `.planning/PROJECT.md` — Capital constraints ($100–$500), risk tolerance, shadow mode gate criteria, deferred items

### Roadmap
- `.planning/ROADMAP.md` — Phase 1 acceptance criteria (DATA-01 through DATA-06), dependency chain across all 7 phases

### Technology Stack (in CLAUDE.md)
- `.claude/CLAUDE.md` — Full dependency pinning, what NOT to use, DuckDB rationale, Alpaca SDK feature inventory, yfinance reliability warning

### No external ADRs or specs yet — all requirements captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet — project directory contains only `.claude/`, `.git/`, `.planning/`. Phase 1 creates all foundational code.

### Established Patterns
- None yet — patterns will be established in this phase and documented in CLAUDE.md Conventions section.

### Integration Points
- `tradebot/db/connection.py` → imported by every downstream fetcher, signal, and execution module
- `tradebot/models/` → imported by fetchers (produce), signals (consume), report (consume), execution (consume)
- `tradebot/config.py` → imported everywhere; must be importable without live env vars for tests

</code_context>

<specifics>
## Specific Ideas

- Migration numbering: `001_initial.sql` establishes base schema. Future phases add `002_add_universe_snapshots.sql` etc.
- `TRADEBOT_MODE` env var selects which dotenv file loads: `paper` → `.env.paper`, `live` → `.env.live`. Default to `paper` if unset.
- DuckDB file path comes from `settings.db_path` — defaults to `data/tradebot.duckdb`.

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Data Foundation*
*Context gathered: 2026-07-07*
