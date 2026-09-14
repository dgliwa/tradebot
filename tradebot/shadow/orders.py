from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta

import duckdb

from tradebot.fetchers.market import next_session, session_open
from tradebot.shadow.account import ShadowAccount, cash_balance
from tradebot.shadow.portfolio import portfolio, positions, price_on
from tradebot.strategy.base import TradingStrategy


def _key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


def _insert_order(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, run_id: str, ticker: str,
    side: str, quantity: float, reason: str, submitted_at: datetime, eligible: date,
    recommendation_id: int | None = None, stop_price: float | None = None,
) -> bool:
    identifier = _key(account.id, run_id, ticker, side, reason)
    row = conn.execute(
        """INSERT INTO shadow_orders
        (id,account_id,run_id,recommendation_id,ticker,side,quantity,status,reason,
         submitted_at,eligible_session,stop_price)
        VALUES (?,?,?,?,?,?,?,'pending',?,?,?,?) ON CONFLICT DO NOTHING RETURNING id""",
        [identifier, account.id, run_id, recommendation_id, ticker, side, quantity,
         reason, submitted_at, eligible, stop_price],
    ).fetchone()
    return row is not None


def generate_entry_orders(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, strategy: TradingStrategy,
    run_id: str, session: date, submitted_at: datetime,
) -> int:
    current = {position.ticker for position in positions(conn, account.id)}
    pending = {row[0] for row in conn.execute(
        "SELECT ticker FROM shadow_orders WHERE account_id=? AND status='pending' AND side='buy'", [account.id]
    ).fetchall()}
    slots = strategy.capital.max_positions - len(current | pending)
    if slots <= 0:
        return 0
    account_equity = portfolio(conn, account.id, session).equity
    rows = conn.execute(
        """SELECT id,ticker,rank,entry_reason FROM recommendations
           WHERE run_id=? AND selected AND entry_signal ORDER BY rank""", [run_id]
    ).fetchall()
    created = 0
    for recommendation_id, ticker, rank, entry_reason in rows:
        if created >= min(slots, strategy.capital.max_new_positions) or ticker in current | pending:
            continue
        cooldown = conn.execute(
            "SELECT until_session FROM reentry_cooldowns WHERE account_id=? AND ticker=?", [account.id, ticker]
        ).fetchone()
        if cooldown and cooldown[0] >= session:
            continue
        reference_price = price_on(conn, ticker, session)
        quantity = round(account_equity * strategy.capital.position_fraction / reference_price, 6)
        if quantity <= 0:
            continue
        created += _insert_order(
            conn, account, run_id, ticker, "buy", quantity, entry_reason, submitted_at,
            next_session(session), recommendation_id,
        )
    return created


def generate_exit_orders(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, strategy: TradingStrategy,
    run_id: str, session: date, submitted_at: datetime,
) -> int:
    pending_sells = {row[0] for row in conn.execute(
        "SELECT ticker FROM shadow_orders WHERE account_id=? AND status='pending' AND side='sell'", [account.id]
    ).fetchall()}
    created = 0
    for position in positions(conn, account.id):
        if position.ticker in pending_sells:
            continue
        close = price_on(conn, position.ticker, session)
        stop_price = position.average_cost * (1 - strategy.risk.stop_loss_fraction)
        reason = None
        if close <= stop_price:
            reason = "stop_loss"
        elif session - position.opened_at.date() >= timedelta(days=strategy.risk.max_holding_days):
            reason = "max_holding_period"
        else:
            recent = conn.execute(
                """SELECT r.composite_score FROM recommendations r JOIN strategy_runs sr ON sr.id=r.run_id
                   WHERE r.ticker=? AND sr.status='completed' AND sr.effective_session<=?
                   ORDER BY sr.effective_session DESC LIMIT ?""",
                [position.ticker, session, strategy.risk.negative_score_runs],
            ).fetchall()
            if len(recent) == strategy.risk.negative_score_runs and all(row[0] < 0 for row in recent):
                reason = "negative_scores"
        if reason:
            created += _insert_order(
                conn, account, run_id, position.ticker, "sell", position.quantity,
                reason, submitted_at, next_session(session), stop_price=stop_price,
            )
    return created


def settle_pending_orders(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, strategy: TradingStrategy,
    through_session: date,
) -> tuple[int, int]:
    rows = conn.execute(
        """SELECT id,ticker,side,quantity,eligible_session,reason FROM shadow_orders
           WHERE account_id=? AND status='pending' AND eligible_session<=?
           ORDER BY eligible_session,submitted_at,id""", [account.id, through_session]
    ).fetchall()
    filled = rejected = 0
    for order_id, ticker, side, quantity, eligible, reason in rows:
        raw_price = price_on(conn, ticker, eligible, "open")
        slippage = strategy.execution.slippage_bps / 10_000
        fill_price = raw_price * (1 + slippage if side == "buy" else 1 - slippage)
        commission = strategy.execution.commission
        amount = quantity * fill_price
        if side == "buy" and cash_balance(conn, account.id) + 1e-8 < amount + commission:
            conn.execute(
                "UPDATE shadow_orders SET status='rejected',diagnostics=? WHERE id=?",
                [json.dumps({"error": "insufficient cash"}), order_id],
            )
            rejected += 1
            continue
        if side == "sell":
            owned = {item.ticker: item.quantity for item in positions(conn, account.id)}.get(ticker, 0)
            if owned + 1e-8 < quantity:
                conn.execute(
                    "UPDATE shadow_orders SET status='rejected',diagnostics=? WHERE id=?",
                    [json.dumps({"error": "insufficient position"}), order_id],
                )
                rejected += 1
                continue
        conn.execute("BEGIN TRANSACTION")
        try:
            fill_id = _key(order_id, "fill")
            fill_time = session_open(eligible)
            conn.execute(
                "INSERT INTO shadow_fills VALUES (?,?,?,?,?,?,?,?)",
                [fill_id, order_id, ticker, side, quantity, fill_price, commission, fill_time],
            )
            cash_amount = amount if side == "sell" else -amount
            conn.execute(
                "INSERT INTO cash_ledger VALUES (?,?,?,?, 'trade', ?)",
                [_key(order_id, "cash"), account.id, fill_time, cash_amount, order_id],
            )
            if commission:
                conn.execute(
                    "INSERT INTO cash_ledger VALUES (?,?,?,?, 'commission', ?)",
                    [_key(order_id, "commission"), account.id, fill_time, -commission, order_id],
                )
            conn.execute("UPDATE shadow_orders SET status='filled' WHERE id=?", [order_id])
            if side == "sell" and reason == "stop_loss":
                conn.execute(
                    """INSERT INTO reentry_cooldowns VALUES (?,?,?,'stop_loss')
                       ON CONFLICT (account_id,ticker) DO UPDATE SET until_session=excluded.until_session,reason=excluded.reason""",
                    [account.id, ticker, eligible + timedelta(days=strategy.risk.stop_reentry_days)],
                )
            conn.execute("COMMIT")
            filled += 1
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return filled, rejected
