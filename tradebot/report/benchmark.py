from __future__ import annotations

import hashlib
from datetime import date

import duckdb

from tradebot.fetchers.market import next_session
from tradebot.shadow.account import ShadowAccount
from tradebot.shadow.portfolio import price_on


def _key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


def sync_benchmark(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, ticker: str, session: date,
) -> float:
    pending = conn.execute(
        """SELECT id,amount,eligible_session FROM benchmark_orders
           WHERE account_id=? AND status='pending' AND eligible_session<=?""",
        [account.id, session],
    ).fetchall()
    for order_id, amount, eligible in pending:
        price = price_on(conn, ticker, eligible, "open")
        conn.execute(
            "UPDATE benchmark_orders SET status='filled',fill_price=?,quantity=? WHERE id=?",
            [price, amount / price, order_id],
        )
    cash_rows = conn.execute(
        """SELECT l.id,l.amount FROM cash_ledger l
           LEFT JOIN benchmark_orders b ON b.cash_ledger_id=l.id AND b.account_id=l.account_id
           WHERE l.account_id=? AND l.entry_type IN ('initial','contribution') AND b.id IS NULL""",
        [account.id],
    ).fetchall()
    for ledger_id, amount in cash_rows:
        conn.execute(
            "INSERT INTO benchmark_orders VALUES (?,?,?,?,?,?,'pending',NULL,NULL)",
            [_key(account.id, ledger_id), account.id, ledger_id, ticker, amount, next_session(session)],
        )
    filled_quantity = conn.execute(
        "SELECT coalesce(sum(quantity),0) FROM benchmark_orders WHERE account_id=? AND status='filled'",
        [account.id],
    ).fetchone()[0]
    uninvested = conn.execute(
        "SELECT coalesce(sum(amount),0) FROM benchmark_orders WHERE account_id=? AND status='pending'",
        [account.id],
    ).fetchone()[0]
    return float(uninvested + filled_quantity * price_on(conn, ticker, session))
