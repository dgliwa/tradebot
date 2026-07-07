---
phase: 1
slug: data-foundation
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-07
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_db/ tests/test_models/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_db/ tests/test_models/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | DATA-01 | T-SQL-inject | Parameterized queries only — no f-string SQL | unit | `uv run pytest tests/test_db/test_schema.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | DATA-02 | — | N/A | unit | `uv run pytest tests/test_db/test_schema.py::test_raw_prices_immutable -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | DATA-03 | — | N/A | unit | `uv run pytest tests/test_models/test_raw_record.py::test_fetch_result_validity -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | DATA-04 | — | N/A | unit | `uv run pytest tests/test_db/test_schema.py::test_disclosure_dates -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | DATA-05 | — | N/A | unit | `uv run pytest tests/test_db/test_schema.py::test_instruments_options_aware -x` | ❌ W0 | ⬜ pending |
| 1-01-06 | 01 | 1 | DATA-06 | — | N/A | unit | `uv run pytest tests/test_db/test_schema.py::test_universe_snapshots_queryable -x` | ❌ W0 | ⬜ pending |
| 1-01-07 | 01 | 1 | SC-5 | — | N/A | unit | `uv run pytest tests/test_db/test_init_db.py::test_init_db_idempotent -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — `db` fixture (in-memory DuckDB + full schema applied)
- [ ] `tests/test_db/__init__.py` — package init
- [ ] `tests/test_db/test_schema.py` — stubs for DATA-01, DATA-02, DATA-04, DATA-05, DATA-06
- [ ] `tests/test_db/test_init_db.py` — idempotency test (Success Criterion 5)
- [ ] `tests/test_models/__init__.py` — package init
- [ ] `tests/test_models/test_raw_record.py` — FetchResult validity test (DATA-03)
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — set `testpaths = ["tests"]`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `python -c "from tradebot.db import init_db; init_db()"` runs with no errors on fresh DB | SC-1 | Requires a real file-system DB creation + Python import path | Run in project root after `uv sync`: `uv run python -c "from tradebot.db import init_db; init_db(); print('OK')"` |
| `.env.paper` and `.env.live` absent from git tracking | Security / ASVS V8 | Cannot assert gitignore state in a unit test | Check `git status` shows both files untracked (or confirm `.gitignore` excludes `.env.*`) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
