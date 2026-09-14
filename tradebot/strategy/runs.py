from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

import duckdb

from tradebot.models.validation import require_aware
from tradebot.strategy.config import Strategy


@dataclass(frozen=True)
class StrategyRun:
    id: str
    effective_session: date
    status: str
    created: bool


def run_id(strategy: Strategy, session: date) -> str:
    value = f"{strategy.name}:{strategy.version}:{session.isoformat()}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def start_run(
    conn: duckdb.DuckDBPyConnection, strategy: Strategy, session: date,
    decision_at: datetime | None = None,
) -> StrategyRun:
    decision_at = decision_at or datetime.now(UTC)
    require_aware(decision_at)
    identifier = run_id(strategy, session)
    existing = conn.execute(
        "SELECT config_hash, status FROM strategy_runs WHERE id = ?", [identifier]
    ).fetchone()
    if existing:
        if existing[0] != strategy.config_hash:
            raise ValueError("Strategy version changed without a version bump")
        return StrategyRun(identifier, session, existing[1], False)
    conn.execute(
        """INSERT INTO strategy_runs
        (id, strategy_name, strategy_version, config_hash, config_json,
         decision_at, effective_session, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'started')""",
        [identifier, strategy.name, strategy.version, strategy.config_hash,
         strategy.canonical_json, decision_at.astimezone(UTC), session],
    )
    return StrategyRun(identifier, session, "started", True)


def finish_run(conn: duckdb.DuckDBPyConnection, identifier: str, *, error: str | None = None) -> None:
    status = "failed" if error else "completed"
    diagnostics = json.dumps({"error": error}) if error else "{}"
    row = conn.execute(
        """UPDATE strategy_runs SET status = ?, diagnostics = ?, completed_at = now()
        WHERE id = ? AND status = 'started' RETURNING id""",
        [status, diagnostics, identifier],
    ).fetchone()
    if row is None:
        raise ValueError("Only a started strategy run can be finished")
