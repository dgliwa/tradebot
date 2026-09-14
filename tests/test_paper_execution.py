from datetime import UTC, date, datetime

import pytest

from tradebot.config import Settings
from tradebot.execution.broker import AlpacaPaperBroker, BrokerOrder
from tradebot.execution.paper import (
    approve_intent, enable_automatic_submission, ensure_paper_state, pending_intents,
    plan_intents, reconcile_orders, reject_intent, set_kill_switch,
)
from tradebot.shadow.account import create_account
from tradebot.strategy import PelosiConfig, PelosiStrategy

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


class FakePaperBroker:
    is_paper = True

    def __init__(self):
        self.orders = {}
        self.submissions = 0

    def get_order(self, client_order_id):
        return self.orders.get(client_order_id)

    def submit_market_order(self, *, ticker, side, quantity, client_order_id):
        self.submissions += 1
        order = BrokerOrder("broker-1", client_order_id, "accepted", ticker, side, quantity, 0, None)
        self.orders[client_order_id] = order
        return order


def setup_intent(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    db.execute(
        """INSERT INTO shadow_orders
           (id,account_id,ticker,side,quantity,status,reason,submitted_at,eligible_session)
           VALUES ('shadow-1',?,'AAPL','buy',3.25,'pending','new_disclosure',?,'2026-07-09')""",
        [account.id, NOW],
    )
    assert plan_intents(db, account) == 1
    return strategy, account, pending_intents(db, account)[0]


def test_manual_approval_is_exact_and_idempotent(db):
    strategy, account, intent = setup_intent(db)
    broker = FakePaperBroker()
    approved = approve_intent(db, account, strategy, intent.id, broker, NOW)
    assert approved.status == "submitted"
    assert broker.orders[intent.client_order_id].quantity == 3.25
    approve_intent(db, account, strategy, intent.id, broker, NOW)
    assert broker.submissions == 1


def test_reconciliation_unlocks_automation_only_after_ten_fills(db):
    strategy, account, intent = setup_intent(db)
    broker = FakePaperBroker()
    approve_intent(db, account, strategy, intent.id, broker, NOW)
    broker.orders[intent.client_order_id] = BrokerOrder(
        "broker-1", intent.client_order_id, "filled", "AAPL", "buy", 3.25, 3.25, 101.0
    )
    assert reconcile_orders(db, account, broker, NOW) == 1
    assert ensure_paper_state(db)["reconciled_order_count"] == 1
    assert db.execute("SELECT count(*) FROM broker_order_events WHERE broker_status='filled'").fetchone() == (1,)
    reconcile_orders(db, account, broker, NOW)
    assert ensure_paper_state(db)["reconciled_order_count"] == 1
    with pytest.raises(ValueError, match="10 reconciled"):
        enable_automatic_submission(db, strategy)
    db.execute("UPDATE paper_execution_state SET reconciled_order_count=10 WHERE id")
    enable_automatic_submission(db, strategy)
    assert ensure_paper_state(db)["auto_enabled"]


def test_stale_intent_is_rejected_after_eligible_open(db):
    strategy, account, intent = setup_intent(db)
    broker = FakePaperBroker()
    with pytest.raises(ValueError, match="stale"):
        approve_intent(
            db, account, strategy, intent.id, broker,
            datetime(2026, 7, 9, 15, tzinfo=UTC),
        )


def test_operator_can_reject_pending_intent(db):
    _, account, intent = setup_intent(db)
    reject_intent(db, account, intent.id, NOW)
    assert pending_intents(db, account)[0].status == "canceled"


def test_broker_divergence_blocks_reconciliation(db):
    strategy, account, intent = setup_intent(db)
    broker = FakePaperBroker()
    broker.orders[intent.client_order_id] = BrokerOrder(
        "wrong", intent.client_order_id, "accepted", "MSFT", "buy", 3.25, 0, None
    )
    with pytest.raises(ValueError, match="diverged"):
        approve_intent(db, account, strategy, intent.id, broker, NOW)


def test_kill_switch_blocks_submission(db):
    strategy, account, intent = setup_intent(db)
    broker = FakePaperBroker()
    set_kill_switch(db, True)
    with pytest.raises(ValueError, match="kill switch"):
        approve_intent(db, account, strategy, intent.id, broker, NOW)
    assert broker.submissions == 0


def test_alpaca_adapter_rejects_live_mode_before_connecting():
    settings = Settings(
        mode="live", alpaca_base_url="https://api.alpaca.markets",
        alpaca_key="key", alpaca_secret="secret",
    )
    with pytest.raises(ValueError, match="locked to paper"):
        AlpacaPaperBroker(settings)


def test_non_paper_broker_is_rejected(db):
    strategy, account, intent = setup_intent(db)
    broker = FakePaperBroker()
    broker.is_paper = False
    with pytest.raises(ValueError, match="not locked"):
        approve_intent(db, account, strategy, intent.id, broker, NOW)
