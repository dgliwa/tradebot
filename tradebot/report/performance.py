from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

import duckdb

from tradebot.shadow.account import ShadowAccount
from tradebot.shadow.portfolio import Portfolio


@dataclass(frozen=True)
class PerformanceSnapshot:
    session: date
    strategy_equity: float
    benchmark_equity: float
    net_cash_flow: float
    strategy_index: float
    benchmark_index: float
    drawdown: float
    gross_exposure: float


def record_performance(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, session: date,
    state: Portfolio, benchmark_equity: float, created_at: datetime | None = None,
) -> PerformanceSnapshot:
    created_at = created_at or datetime.now(UTC)
    existing = conn.execute(
        """SELECT session,strategy_equity,benchmark_equity,net_cash_flow,strategy_index,
                  benchmark_index,drawdown,gross_exposure
           FROM performance_snapshots WHERE account_id=? AND session=?""", [account.id, session]
    ).fetchone()
    if existing:
        return PerformanceSnapshot(*existing)
    previous = conn.execute(
        """SELECT session,strategy_equity,benchmark_equity,strategy_index,benchmark_index,created_at
           FROM performance_snapshots WHERE account_id=? AND session<? ORDER BY session DESC LIMIT 1""",
        [account.id, session],
    ).fetchone()
    if previous is None:
        cash_flow = float(conn.execute(
            "SELECT coalesce(sum(amount),0) FROM cash_ledger WHERE account_id=? AND entry_type IN ('initial','contribution')",
            [account.id],
        ).fetchone()[0])
        strategy_index = state.equity / cash_flow if cash_flow else 1.0
        benchmark_index = benchmark_equity / cash_flow if cash_flow else 1.0
    else:
        cash_flow = float(conn.execute(
            """SELECT coalesce(sum(amount),0) FROM cash_ledger
               WHERE account_id=? AND entry_type IN ('initial','contribution')
                 AND occurred_at>? AND occurred_at<=?""",
            [account.id, previous[5], created_at],
        ).fetchone()[0])
        strategy_index = previous[3] * (state.equity - cash_flow) / previous[1]
        benchmark_index = previous[4] * (benchmark_equity - cash_flow) / previous[2]
    peak = conn.execute(
        "SELECT coalesce(max(strategy_index),?) FROM performance_snapshots WHERE account_id=?",
        [strategy_index, account.id],
    ).fetchone()[0]
    drawdown = strategy_index / max(float(peak), strategy_index) - 1
    exposure = state.market_value / state.equity if state.equity else 0.0
    snapshot = PerformanceSnapshot(
        session, state.equity, benchmark_equity, cash_flow, strategy_index,
        benchmark_index, drawdown, exposure,
    )
    conn.execute(
        "INSERT INTO performance_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
        [account.id, *asdict(snapshot).values(), created_at],
    )
    return snapshot


def performance_history(conn: duckdb.DuckDBPyConnection, account_id: str) -> list[PerformanceSnapshot]:
    rows = conn.execute(
        """SELECT session,strategy_equity,benchmark_equity,net_cash_flow,strategy_index,
                  benchmark_index,drawdown,gross_exposure
           FROM performance_snapshots WHERE account_id=? ORDER BY session""", [account_id]
    ).fetchall()
    return [PerformanceSnapshot(*row) for row in rows]
