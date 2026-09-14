from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import duckdb

from tradebot.execution.paper import ensure_paper_state
from tradebot.fetchers.market import sessions_between
from tradebot.report.performance import performance_history
from tradebot.shadow.account import load_account
from tradebot.strategy.base import TradingStrategy


def evaluate_experiment(
    conn: duckdb.DuckDBPyConnection, strategy: TradingStrategy, *,
    account_name: str = "default", evaluated_at: datetime | None = None,
) -> dict:
    evaluated_at = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    account = load_account(conn, account_name)
    history = performance_history(conn, account.id)
    paper = ensure_paper_state(conn, evaluated_at)
    if not history:
        payload = {
            "strategy_config_hash": strategy.config_hash,
            "status": "collecting", "reason": "No performance observations",
            "gates": {}, "abort": False,
        }
    else:
        first, last = history[0], history[-1]
        observation_days = (last.session - first.session).days + 1
        expected = set(sessions_between(first.session, last.session))
        observed = {item.session for item in history}
        missing = sorted(expected - observed)
        failed_runs = conn.execute(
            """SELECT count(*) FROM strategy_runs
               WHERE status='failed' AND effective_session BETWEEN ? AND ?""",
            [first.session, last.session],
        ).fetchone()[0]
        invalid_sources = conn.execute(
            """SELECT count(*) FROM (
                 SELECT status,row_number() OVER (PARTITION BY source,ticker ORDER BY checked_at DESC) rank
                 FROM source_coverage) WHERE rank=1 AND status='invalid'"""
        ).fetchone()[0]
        paper_dates = conn.execute(
            """SELECT min(approved_at),max(coalesce(reconciled_at,approved_at))
               FROM broker_order_intents WHERE account_id=? AND approved_at IS NOT NULL""",
            [account.id],
        ).fetchone()
        paper_days = ((paper_dates[1] - paper_dates[0]).days + 1) if paper_dates[0] and paper_dates[1] else 0
        unresolved = conn.execute(
            """SELECT count(*) FROM broker_order_intents
               WHERE account_id=? AND status='submitted'""", [account.id]
        ).fetchone()[0]
        max_drawdown = min(item.drawdown for item in history)
        gates = {
            "minimum_shadow_observation": observation_days >= strategy.evaluation.min_shadow_weeks * 7,
            "target_shadow_observation": observation_days >= strategy.evaluation.target_shadow_weeks * 7,
            "complete_session_history": not missing,
            "strategy_beats_benchmark": last.strategy_index > last.benchmark_index,
            "drawdown_within_limit": max_drawdown > -strategy.evaluation.max_drawdown_fraction,
            "no_failed_strategy_runs": failed_runs == 0,
            "source_health_valid": invalid_sources == 0,
            "minimum_paper_observation": paper_days >= strategy.evaluation.min_paper_weeks * 7,
            "paper_fill_threshold": paper["reconciled_order_count"] >= strategy.paper.auto_submit_after_reconciled_orders,
            "paper_orders_reconciled": unresolved == 0,
        }
        research_ready = all(gates[key] for key in (
            "minimum_shadow_observation", "complete_session_history", "strategy_beats_benchmark",
            "drawdown_within_limit", "no_failed_strategy_runs", "source_health_valid",
        ))
        live_review_ready = research_ready and all(gates[key] for key in (
            "minimum_paper_observation", "paper_fill_threshold", "paper_orders_reconciled",
        ))
        abort = not gates["drawdown_within_limit"]
        payload = {
            "strategy_config_hash": strategy.config_hash,
            "status": "abort" if abort else "live-review-ready" if live_review_ready else "collecting",
            "abort": abort,
            "research_ready": research_ready,
            "live_review_ready": live_review_ready,
            "observation_days": observation_days,
            "paper_observation_days": paper_days,
            "strategy_index": last.strategy_index,
            "benchmark_index": last.benchmark_index,
            "max_drawdown": max_drawdown,
            "missing_sessions": [day.isoformat() for day in missing],
            "failed_strategy_runs": failed_runs,
            "invalid_latest_sources": invalid_sources,
            "unresolved_paper_orders": unresolved,
            "reconciled_paper_fills": paper["reconciled_order_count"],
            "gates": gates,
        }
    encoded = json.dumps(payload, sort_keys=True)
    identifier = hashlib.sha256(
        f"{account.id}:{strategy.config_hash}:{evaluated_at.isoformat()}".encode()
    ).hexdigest()[:24]
    conn.execute(
        "INSERT INTO experiment_evaluations VALUES (?,?,?,?,?)",
        [identifier, account.id, strategy.config_hash, evaluated_at, encoded],
    )
    return payload
