from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from tradebot.shadow.account import load_account
from tradebot.shadow.portfolio import portfolio
from tradebot.strategy.base import TradingStrategy
from tradebot.strategy.query import recommendation_rows
from tradebot.report.performance import performance_history


def _xirr(cash_flows: list[tuple[date, float]]) -> float | None:
    if len({day for day, _ in cash_flows}) < 2 or not any(value < 0 for _, value in cash_flows) or not any(value > 0 for _, value in cash_flows):
        return None
    origin = min(day for day, _ in cash_flows)

    def npv(rate: float) -> float:
        return sum(value / ((1 + rate) ** ((day - origin).days / 365)) for day, value in cash_flows)

    low, high = -0.999, 1000.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        middle = (low + high) / 2
        if npv(low) * npv(middle) <= 0:
            high = middle
        else:
            low = middle
    return (low + high) / 2


def _metrics(conn: duckdb.DuckDBPyConnection, account_id: str) -> dict:
    history = performance_history(conn, account_id)
    if not history:
        return {}
    first, last = history[0], history[-1]
    days = max(1, (last.session - first.session).days)
    strategy_return = last.strategy_index - 1
    benchmark_return = last.benchmark_index - 1
    fills = conn.execute(
        """SELECT f.ticker,f.side,f.quantity,f.price,f.filled_at FROM shadow_fills f
           JOIN shadow_orders o ON o.id=f.order_id WHERE o.account_id=? ORDER BY f.filled_at,f.id""",
        [account_id],
    ).fetchall()
    lots: dict[str, list[list]] = {}
    closed_pnl: list[float] = []
    holding_days: list[int] = []
    for ticker, side, quantity, price, filled_at in fills:
        if side == "buy":
            lots.setdefault(ticker, []).append([quantity, price, filled_at])
            continue
        remaining, pnl = quantity, 0.0
        while remaining > 1e-8 and lots.get(ticker):
            lot = lots[ticker][0]
            consumed = min(remaining, lot[0])
            pnl += consumed * (price - lot[1])
            holding_days.append((filled_at - lot[2]).days)
            lot[0] -= consumed
            remaining -= consumed
            if lot[0] <= 1e-8:
                lots[ticker].pop(0)
        closed_pnl.append(pnl)
    turnover = sum(quantity * price for _, _, quantity, price, _ in fills) / max(
        1, sum(item.strategy_equity for item in history) / len(history)
    )
    funding = [(row[0].date(), -float(row[1])) for row in conn.execute(
        """SELECT occurred_at,amount FROM cash_ledger
           WHERE account_id=? AND entry_type IN ('initial','contribution') ORDER BY occurred_at""",
        [account_id],
    ).fetchall()]
    money_weighted = _xirr([*funding, (last.session, last.strategy_equity)])
    return {
        "strategy_return": strategy_return,
        "benchmark_return": benchmark_return,
        "excess_return": strategy_return - benchmark_return,
        "strategy_cagr": (last.strategy_index ** (365 / days) - 1) if len(history) > 1 else None,
        "money_weighted_return": money_weighted,
        "benchmark_cagr": (last.benchmark_index ** (365 / days) - 1) if len(history) > 1 else None,
        "max_drawdown": min(item.drawdown for item in history),
        "average_gross_exposure": sum(item.gross_exposure for item in history) / len(history),
        "turnover": turnover,
        "fill_count": len(fills),
        "closed_trade_count": len(closed_pnl),
        "win_rate": (sum(pnl > 0 for pnl in closed_pnl) / len(closed_pnl)) if closed_pnl else None,
        "average_holding_days": (sum(holding_days) / len(holding_days)) if holding_days else None,
        "average_win": (sum(p for p in closed_pnl if p > 0) / sum(p > 0 for p in closed_pnl)) if any(p > 0 for p in closed_pnl) else None,
        "average_loss": (sum(p for p in closed_pnl if p < 0) / sum(p < 0 for p in closed_pnl)) if any(p < 0 for p in closed_pnl) else None,
    }


def generate_report(
    conn: duckdb.DuckDBPyConnection, strategy: TradingStrategy, session: date,
    *, account_name: str = "default", output_root: Path = Path("reports"),
) -> tuple[Path, Path]:
    account = load_account(conn, account_name)
    stored = conn.execute(
        """SELECT payload FROM report_artifacts
           WHERE account_id=? AND session=? AND strategy_config_hash=?""",
        [account.id, session, strategy.config_hash],
    ).fetchone()
    state = portfolio(conn, account.id, session)
    run = conn.execute(
        """SELECT id,status,diagnostics FROM strategy_runs
           WHERE effective_session<=? ORDER BY effective_session DESC LIMIT 1""", [session]
    ).fetchone()
    orders = conn.execute(
        """SELECT ticker,side,quantity,status,reason,eligible_session,diagnostics
           FROM shadow_orders WHERE account_id=? ORDER BY submitted_at,id""", [account.id]
    ).fetchall()
    fills = conn.execute(
        """SELECT f.ticker,f.side,f.quantity,f.price,f.commission,f.filled_at,o.reason
           FROM shadow_fills f JOIN shadow_orders o ON o.id=f.order_id
           WHERE o.account_id=? ORDER BY f.filled_at,f.id""", [account.id]
    ).fetchall()
    coverage = conn.execute(
        """SELECT source,ticker,checked_through,checked_at,status,errors FROM (
             SELECT *,row_number() OVER (PARTITION BY source,ticker ORDER BY checked_at DESC) rank
             FROM source_coverage) WHERE rank=1 ORDER BY source,ticker"""
    ).fetchall()
    payload = json.loads(stored[0]) if stored else {
        "strategy": {"name": strategy.name, "version": strategy.version, "config_hash": strategy.config_hash},
        "session": session.isoformat(),
        "account": asdict(account),
        "portfolio": asdict(state),
        "metrics": _metrics(conn, account.id),
        "performance": [asdict(item) for item in performance_history(conn, account.id)],
        "run": {"id": run[0], "status": run[1], "diagnostics": json.loads(run[2])} if run else None,
        "recommendations": recommendation_rows(conn, run[0]) if run else [],
        "fills": [{
            "ticker": row[0], "side": row[1], "quantity": row[2], "price": row[3],
            "commission": row[4], "filled_at": row[5].isoformat(), "reason": row[6],
        } for row in fills],
        "data_quality": [{
            "source": row[0], "ticker": row[1],
            "checked_through": row[2].isoformat() if row[2] else None,
            "checked_at": row[3].isoformat(), "status": row[4], "errors": json.loads(row[5]),
        } for row in coverage],
        "failed_runs": [{"id": row[0], "session": row[1].isoformat(), "diagnostics": json.loads(row[2])}
                        for row in conn.execute(
                            "SELECT id,effective_session,diagnostics FROM strategy_runs WHERE status='failed' ORDER BY effective_session"
                        ).fetchall()],
        "orders": [{
            "ticker": row[0], "side": row[1], "quantity": row[2], "status": row[3],
            "reason": row[4], "eligible_session": row[5].isoformat(),
            "diagnostics": json.loads(row[6]),
        } for row in orders],
    }
    if not stored:
        conn.execute(
            "INSERT INTO report_artifacts VALUES (?,?,?,?,?)",
            [account.id, session, strategy.config_hash,
             json.dumps(payload, default=str, sort_keys=True), datetime.now(UTC)],
        )
    directory = output_root / session.isoformat() / strategy.version
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    html_path = directory / "report.html"
    rendered = json.dumps(payload, default=str, indent=2, sort_keys=True)
    json_path.write_text(rendered + "\n", encoding="utf-8")
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>TradeBot report</title>"
        "<style>body{font:14px system-ui;max-width:1100px;margin:2rem auto}pre{white-space:pre-wrap}</style>"
        f"</head><body><h1>{html.escape(strategy.name)}</h1><p>Session {session}</p>"
        f"<pre>{html.escape(rendered)}</pre></body></html>\n",
        encoding="utf-8",
    )
    return json_path, html_path
