from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

import duckdb

from tradebot.config import Settings
from tradebot.execution.paper import plan_intents
from tradebot.report.benchmark import sync_benchmark
from tradebot.report.performance import PerformanceSnapshot, record_performance
from tradebot.shadow.account import apply_weekly_contribution, create_account, load_account
from tradebot.shadow.actions import apply_corporate_actions
from tradebot.shadow.orders import generate_entry_orders, generate_exit_orders, settle_pending_orders
from tradebot.shadow.portfolio import Portfolio, portfolio, positions
from tradebot.strategy.base import TradingStrategy
from tradebot.strategy.daily import DailyResult, run_daily


@dataclass(frozen=True)
class ShadowCycleResult:
    daily: DailyResult
    account_id: str
    contribution_added: bool
    corporate_actions_applied: int
    orders_filled: int
    orders_rejected: int
    entry_orders_created: int
    exit_orders_created: int
    paper_intents_created: int
    portfolio: Portfolio
    performance: PerformanceSnapshot


def run_shadow_cycle(
    conn: duckdb.DuckDBPyConnection, settings: Settings, strategy: TradingStrategy,
    *, decision_at: datetime | None = None, account_name: str = "default",
) -> ShadowCycleResult:
    decision_at = (decision_at or datetime.now(UTC)).astimezone(UTC)
    account = create_account(conn, strategy, name=account_name, created_at=decision_at)
    owned = {position.ticker for position in positions(conn, account.id)}
    daily = run_daily(conn, settings, strategy, decision_at=decision_at, owned_tickers=owned)
    contribution = apply_weekly_contribution(conn, account, strategy, daily.session, decision_at)
    benchmark_equity = sync_benchmark(conn, account, strategy.benchmark, daily.session)
    actions = apply_corporate_actions(conn, account, daily.session, decision_at)
    filled, rejected = settle_pending_orders(conn, account, strategy, daily.session)
    exits = generate_exit_orders(conn, account, strategy, daily.run_id, daily.session, decision_at)
    entries = generate_entry_orders(conn, account, strategy, daily.run_id, daily.session, decision_at)
    paper_intents = plan_intents(conn, account)
    state = portfolio(conn, account.id, daily.session)
    performance = record_performance(
        conn, account, daily.session, state, benchmark_equity, decision_at
    )
    return ShadowCycleResult(
        daily, account.id, contribution, actions, filled, rejected, entries, exits,
        paper_intents, state, performance,
    )


def shadow_status(
    conn: duckdb.DuckDBPyConnection, account_name: str, session: date,
) -> dict:
    account = load_account(conn, account_name)
    state = portfolio(conn, account.id, session)
    orders = conn.execute(
        """SELECT id,ticker,side,quantity,status,reason,eligible_session
           FROM shadow_orders WHERE account_id=? ORDER BY submitted_at,id""", [account.id]
    ).fetchall()
    return {
        "account": asdict(account),
        "portfolio": asdict(state),
        "orders": [{
            "id": row[0], "ticker": row[1], "side": row[2], "quantity": row[3],
            "status": row[4], "reason": row[5], "eligible_session": row[6].isoformat(),
        } for row in orders],
    }
