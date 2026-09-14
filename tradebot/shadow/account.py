from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import duckdb

from tradebot.models.validation import require_aware
from tradebot.strategy.base import TradingStrategy


@dataclass(frozen=True)
class ShadowAccount:
    id: str
    name: str
    strategy_version: str
    strategy_config_hash: str


def _key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


def create_account(
    conn: duckdb.DuckDBPyConnection, strategy: TradingStrategy, *, name: str = "default",
    created_at: datetime | None = None,
) -> ShadowAccount:
    created_at = created_at or datetime.now(UTC)
    require_aware(created_at)
    identifier = _key("shadow-account", name)
    row = conn.execute(
        "SELECT name,strategy_version,strategy_config_hash FROM shadow_accounts WHERE id=?", [identifier]
    ).fetchone()
    if row:
        if row[1] != strategy.version or row[2] != strategy.config_hash:
            raise ValueError("Shadow account strategy configuration differs")
        return ShadowAccount(identifier, row[0], row[1], row[2])
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            "INSERT INTO shadow_accounts VALUES (?,?,?,?,?)",
            [identifier, name, strategy.version, strategy.config_hash, created_at],
        )
        conn.execute(
            "INSERT INTO cash_ledger VALUES (?,?,?,?,?,?)",
            [_key(identifier, "initial"), identifier, created_at, strategy.capital.starting_cash, "initial", "initial"],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return ShadowAccount(identifier, name, strategy.version, strategy.config_hash)


def load_account(conn: duckdb.DuckDBPyConnection, name: str = "default") -> ShadowAccount:
    row = conn.execute(
        "SELECT id,name,strategy_version,strategy_config_hash FROM shadow_accounts WHERE name=?", [name]
    ).fetchone()
    if row is None:
        raise ValueError(f"Shadow account not found: {name}")
    return ShadowAccount(*row)


def cash_balance(conn: duckdb.DuckDBPyConnection, account_id: str) -> float:
    return float(conn.execute("SELECT coalesce(sum(amount),0) FROM cash_ledger WHERE account_id=?", [account_id]).fetchone()[0])


def apply_weekly_contribution(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, strategy: TradingStrategy,
    session: date, occurred_at: datetime,
) -> bool:
    require_aware(occurred_at)
    week_start = session - timedelta(days=session.weekday())
    reference = week_start.isoformat()
    identifier = _key(account.id, "contribution", reference)
    row = conn.execute(
        """INSERT INTO cash_ledger (id,account_id,occurred_at,amount,entry_type,reference_id)
           VALUES (?,?,?,?, 'contribution', ?) ON CONFLICT DO NOTHING RETURNING id""",
        [identifier, account.id, occurred_at, strategy.capital.weekly_contribution, reference],
    ).fetchone()
    return row is not None
