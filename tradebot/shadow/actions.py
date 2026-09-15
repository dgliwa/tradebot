from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import duckdb

from tradebot.shadow.account import ShadowAccount
from tradebot.shadow.portfolio import positions_before


def _key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


def apply_corporate_actions(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, through_session: date,
    applied_at: datetime | None = None,
) -> int:
    applied_at = applied_at or datetime.now(UTC)
    rows = conn.execute(
        """SELECT a.id,a.ticker,a.action_date,a.action_type,a.value FROM corporate_actions a
           LEFT JOIN applied_corporate_actions x ON x.action_id=a.id AND x.account_id=?
           WHERE x.action_id IS NULL AND a.action_date<=?
           ORDER BY a.action_date, CASE WHEN a.action_type='split' THEN 0 ELSE 1 END, a.id""",
        [account.id, through_session],
    ).fetchall()
    count = 0
    for action_id, ticker, action_date, action_type, value in rows:
        held = {
            item.ticker: item.quantity for item in positions_before(conn, account.id, action_date)
        }.get(ticker, 0)
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute(
                "INSERT INTO applied_corporate_actions VALUES (?,?,?)",
                [account.id, action_id, applied_at],
            )
            if action_type == "dividend" and held > 0:
                conn.execute(
                    "INSERT INTO cash_ledger VALUES (?,?,?,?, 'dividend', ?)",
                    [_key(account.id, action_id), account.id, applied_at, held * value, action_id],
                )
            conn.execute("COMMIT")
            count += 1
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return count
