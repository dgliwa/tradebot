from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

from tradebot.execution.broker import BrokerOrder, PaperBroker
from tradebot.fetchers.market import session_open
from tradebot.shadow.account import ShadowAccount
from tradebot.shadow.portfolio import positions
from tradebot.strategy.base import TradingStrategy

PAPER_ENDPOINT = "https://paper-api.alpaca.markets"


@dataclass(frozen=True)
class PaperIntent:
    id: str
    shadow_order_id: str
    client_order_id: str
    status: str
    ticker: str
    side: str
    quantity: float


def _key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


def ensure_paper_state(conn: duckdb.DuckDBPyConnection, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    conn.execute(
        """INSERT INTO paper_execution_state (id,endpoint,updated_at)
           VALUES (true,?,?) ON CONFLICT DO NOTHING""", [PAPER_ENDPOINT, now]
    )
    row = conn.execute(
        "SELECT endpoint,auto_enabled,kill_switch,reconciled_order_count FROM paper_execution_state WHERE id"
    ).fetchone()
    if row[0] != PAPER_ENDPOINT:
        raise ValueError("Paper execution endpoint lock does not match Alpaca paper")
    return {"endpoint": row[0], "auto_enabled": row[1], "kill_switch": row[2], "reconciled_order_count": row[3]}


def plan_intents(conn: duckdb.DuckDBPyConnection, account: ShadowAccount) -> int:
    rows = conn.execute(
        """SELECT o.id,o.ticker,o.side,o.quantity FROM shadow_orders o
           LEFT JOIN broker_order_intents i ON i.shadow_order_id=o.id
           WHERE o.account_id=? AND o.status='pending' AND i.id IS NULL
           ORDER BY o.submitted_at,o.id""", [account.id]
    ).fetchall()
    created = 0
    for shadow_order_id, ticker, side, quantity in rows:
        identifier = _key("paper-intent", shadow_order_id)
        client_order_id = f"tradebot-{identifier}"
        created += conn.execute(
            """INSERT INTO broker_order_intents
               (id,account_id,shadow_order_id,client_order_id,status)
               VALUES (?,?,?,?,'awaiting_approval') ON CONFLICT DO NOTHING RETURNING id""",
            [identifier, account.id, shadow_order_id, client_order_id],
        ).fetchone() is not None
    return created


def pending_intents(conn: duckdb.DuckDBPyConnection, account: ShadowAccount) -> list[PaperIntent]:
    rows = conn.execute(
        """SELECT i.id,i.shadow_order_id,i.client_order_id,i.status,o.ticker,o.side,o.quantity
           FROM broker_order_intents i JOIN shadow_orders o ON o.id=i.shadow_order_id
           WHERE i.account_id=? ORDER BY o.submitted_at,i.id""", [account.id]
    ).fetchall()
    return [PaperIntent(*row) for row in rows]


def _store_broker_order(
    conn: duckdb.DuckDBPyConnection, intent_id: str, order: BrokerOrder, now: datetime,
) -> None:
    status = order.status.lower()
    local_status = "canceled" if status in {"canceled", "expired"} else status
    if local_status not in {"submitted", "filled", "rejected", "canceled"}:
        local_status = "submitted"
    row = conn.execute(
        """SELECT i.reconciliation_counted,i.client_order_id,o.ticker,o.side,o.quantity
           FROM broker_order_intents i JOIN shadow_orders o ON o.id=i.shadow_order_id
           WHERE i.id=?""", [intent_id]
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown paper intent: {intent_id}")
    if (order.client_order_id != row[1] or order.ticker != row[2] or order.side != row[3]
            or abs(order.quantity - row[4]) > 1e-8):
        raise ValueError(f"Broker order diverged from approved intent: {intent_id}")
    if order.filled_quantity < 0 or order.filled_quantity - order.quantity > 1e-8:
        raise ValueError(f"Broker reported invalid filled quantity: {intent_id}")
    if local_status == "filled" and (
        abs(order.filled_quantity - order.quantity) > 1e-8 or not order.filled_average_price
    ):
        raise ValueError(f"Broker fill is incomplete or missing its price: {intent_id}")
    counted = bool(row[0])
    count_now = local_status == "filled" and not counted
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            """INSERT INTO broker_order_events VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
            [_key(intent_id, order.status, str(order.filled_quantity), str(order.filled_average_price)),
             intent_id, order.status, order.filled_quantity, order.filled_average_price, now],
        )
        conn.execute(
            """UPDATE broker_order_intents SET status=?,broker_order_id=?,reconciled_at=?,
                      reconciliation_counted=?,diagnostics=? WHERE id=?""",
            [local_status, order.id, now, counted or count_now, json.dumps({
                "broker_status": order.status, "filled_quantity": order.filled_quantity,
                "filled_average_price": order.filled_average_price,
            }), intent_id],
        )
        if count_now:
            conn.execute(
                """UPDATE paper_execution_state SET reconciled_order_count=reconciled_order_count+1,
                          updated_at=? WHERE id""", [now]
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def reconcile_orders(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, broker: PaperBroker,
    now: datetime | None = None,
) -> int:
    if not broker.is_paper:
        raise ValueError("Broker is not locked to paper trading")
    ensure_paper_state(conn, now)
    now = now or datetime.now(UTC)
    rows = conn.execute(
        """SELECT id,client_order_id FROM broker_order_intents
           WHERE account_id=? AND status='submitted'""", [account.id]
    ).fetchall()
    updated = 0
    for intent_id, client_order_id in rows:
        order = broker.get_order(client_order_id)
        if order is None:
            raise ValueError(f"Submitted paper order is missing at broker: {client_order_id}")
        _store_broker_order(conn, intent_id, order, now)
        updated += 1
    return updated


def approve_intent(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, strategy: TradingStrategy,
    intent_id: str, broker: PaperBroker, now: datetime | None = None,
) -> PaperIntent:
    now = now or datetime.now(UTC)
    if not broker.is_paper:
        raise ValueError("Broker is not locked to paper trading")
    state = ensure_paper_state(conn, now)
    if state["kill_switch"]:
        raise ValueError("Paper execution kill switch is active")
    reconcile_orders(conn, account, broker, now)
    row = conn.execute(
        """SELECT i.id,i.shadow_order_id,i.client_order_id,i.status,o.ticker,o.side,o.quantity,o.status,
                  o.eligible_session
           FROM broker_order_intents i JOIN shadow_orders o ON o.id=i.shadow_order_id
           WHERE i.id=? AND i.account_id=?""", [intent_id, account.id]
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown paper intent: {intent_id}")
    if row[3] != "awaiting_approval":
        return PaperIntent(*row[:7])
    if row[7] != "pending":
        raise ValueError("Linked shadow order is no longer pending")
    if now >= session_open(row[8]):
        raise ValueError("Paper intent is stale because its eligible market session has opened")
    if row[6] <= 0:
        raise ValueError("Paper quantity must be positive")
    if row[5] == "buy":
        held = {position.ticker for position in positions(conn, account.id)}
        active_buys = {item[0] for item in conn.execute(
            """SELECT DISTINCT o.ticker FROM broker_order_intents i
               JOIN shadow_orders o ON o.id=i.shadow_order_id
               WHERE i.account_id=? AND o.side='buy' AND i.status IN ('awaiting_approval','submitted')""",
            [account.id],
        ).fetchall()}
        if len(held | active_buys) > strategy.capital.max_positions:
            raise ValueError("Paper order would exceed the strategy position limit")
    existing = broker.get_order(row[2])
    order = existing or broker.submit_market_order(
        ticker=row[4], side=row[5], quantity=row[6], client_order_id=row[2]
    )
    conn.execute(
        "UPDATE broker_order_intents SET approved_at=? WHERE id=?", [now, intent_id]
    )
    _store_broker_order(conn, intent_id, order, now)
    return next(item for item in pending_intents(conn, account) if item.id == intent_id)


def reject_intent(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, intent_id: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    row = conn.execute(
        """UPDATE broker_order_intents SET status='canceled',reconciled_at=?,diagnostics=?
           WHERE id=? AND account_id=? AND status='awaiting_approval' RETURNING id""",
        [now, json.dumps({"reason": "rejected by operator"}), intent_id, account.id],
    ).fetchone()
    if row is None:
        raise ValueError("Paper intent is unknown or no longer awaiting approval")


def set_kill_switch(conn: duckdb.DuckDBPyConnection, active: bool) -> None:
    ensure_paper_state(conn)
    conn.execute(
        "UPDATE paper_execution_state SET kill_switch=?,updated_at=? WHERE id",
        [active, datetime.now(UTC)],
    )


def enable_automatic_submission(
    conn: duckdb.DuckDBPyConnection, strategy: TradingStrategy,
) -> None:
    state = ensure_paper_state(conn)
    required = strategy.paper.auto_submit_after_reconciled_orders
    if state["reconciled_order_count"] < required:
        raise ValueError(f"{required} reconciled paper fills are required before automation")
    if state["kill_switch"]:
        raise ValueError("Disable the kill switch before enabling automation")
    conn.execute(
        "UPDATE paper_execution_state SET auto_enabled=true,updated_at=? WHERE id",
        [datetime.now(UTC)],
    )


def expire_stale_intents(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    rows = conn.execute(
        """SELECT i.id,o.status,o.eligible_session FROM broker_order_intents i
           JOIN shadow_orders o ON o.id=i.shadow_order_id
           WHERE i.account_id=? AND i.status='awaiting_approval'""", [account.id]
    ).fetchall()
    expired = 0
    for intent_id, shadow_status, eligible in rows:
        if shadow_status != "pending" or now >= session_open(eligible):
            expired += conn.execute(
                """UPDATE broker_order_intents SET status='canceled',reconciled_at=?,diagnostics=?
                   WHERE id=? AND status='awaiting_approval' RETURNING id""",
                [now, json.dumps({"reason": "stale paper intent"}), intent_id],
            ).fetchone() is not None
    return expired


def submit_automatic_intents(
    conn: duckdb.DuckDBPyConnection, account: ShadowAccount, strategy: TradingStrategy,
    broker: PaperBroker,
) -> int:
    state = ensure_paper_state(conn)
    if not state["auto_enabled"] or state["kill_switch"]:
        return 0
    expire_stale_intents(conn, account)
    count = 0
    for intent in pending_intents(conn, account):
        if intent.status == "awaiting_approval":
            approve_intent(conn, account, strategy, intent.id, broker)
            count += 1
    return count
