from datetime import UTC, date, datetime

import pytest

from tradebot.db.writer import write_raw_records
from tradebot.models.raw_record import RawRecord
from tradebot.shadow.account import apply_weekly_contribution, cash_balance, create_account
from tradebot.shadow.actions import apply_corporate_actions
from tradebot.shadow.orders import generate_entry_orders, generate_exit_orders, settle_pending_orders
from tradebot.shadow.portfolio import portfolio, positions
from tradebot.strategy import PelosiConfig, PelosiStrategy
from tradebot.strategy.runs import start_run

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def add_prices(db, ticker, fetched_at, values):
    records = [RawRecord("yfinance", ticker, fetched_at, {
        "open": value, "high": value, "low": value, "close": value, "volume": 1000,
    }, day) for day, value in values]
    write_raw_records(db, "raw_prices", records)


def add_recommendation(db, strategy, session=date(2026, 7, 8)):
    run = start_run(db, strategy, session, NOW)
    db.execute(
        """INSERT INTO universe_snapshots
           (id,run_date,week_start,ticker,run_id,reason,source_filed_at,created_at)
           VALUES (1,?,?, 'AAPL',?,'{}',?,?)""",
        [session, session, run.id, session, NOW],
    )
    db.execute(
        """INSERT INTO recommendations
           (id,ticker,run_date,composite_score,rank,run_id,selected,explanation,entry_signal,entry_reason)
           VALUES (1,'AAPL',?,1,1,?,true,'{}',true,'new_disclosure')""", [session, run.id]
    )
    return run


def test_account_and_weekly_contribution_are_idempotent(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    assert create_account(db, strategy, created_at=NOW) == account
    assert apply_weekly_contribution(db, account, strategy, date(2026, 7, 8), NOW)
    assert not apply_weekly_contribution(db, account, strategy, date(2026, 7, 9), NOW)
    assert cash_balance(db, account.id) == 10_250


def test_entry_order_fills_at_next_open_with_slippage(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    apply_weekly_contribution(db, account, strategy, date(2026, 7, 8), NOW)
    add_prices(db, "AAPL", datetime(2026, 7, 9, 22, tzinfo=UTC), [
        (date(2026, 7, 8), 100), (date(2026, 7, 9), 110),
    ])
    run = add_recommendation(db, strategy)
    assert generate_entry_orders(db, account, strategy, run.id, date(2026, 7, 8), NOW) == 1
    assert generate_entry_orders(db, account, strategy, run.id, date(2026, 7, 8), NOW) == 0
    assert settle_pending_orders(db, account, strategy, date(2026, 7, 9)) == (1, 0)
    position = positions(db, account.id)[0]
    assert position.quantity == pytest.approx(3.075)
    assert position.average_cost == pytest.approx(110.11)
    state = portfolio(db, account.id, date(2026, 7, 9))
    assert state.equity < 10_250  # unfavorable simulated slippage


def test_order_rejected_instead_of_using_margin(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    add_prices(db, "AAPL", datetime(2026, 7, 9, 22, tzinfo=UTC), [(date(2026, 7, 9), 100)])
    db.execute(
        """INSERT INTO shadow_orders
           (id,account_id,ticker,side,quantity,status,reason,submitted_at,eligible_session)
           VALUES ('too-large',?,'AAPL','buy',1000,'pending','test',?,'2026-07-09')""",
        [account.id, NOW],
    )
    assert settle_pending_orders(db, account, strategy, date(2026, 7, 9)) == (0, 1)
    assert cash_balance(db, account.id) == 10_000
    assert positions(db, account.id) == ()


def test_recorded_splits_and_dividends_are_applied_once(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    add_prices(db, "AAPL", datetime(2026, 7, 9, 22, tzinfo=UTC), [
        (date(2026, 7, 8), 100), (date(2026, 7, 9), 100),
    ])
    run = add_recommendation(db, strategy)
    generate_entry_orders(db, account, strategy, run.id, date(2026, 7, 8), NOW)
    settle_pending_orders(db, account, strategy, date(2026, 7, 9))
    original = positions(db, account.id)[0]
    db.execute(
        "INSERT INTO corporate_actions VALUES ('split','AAPL','2026-07-10','split',2,'test',?)", [NOW]
    )
    assert apply_corporate_actions(db, account, date(2026, 7, 10), NOW) == 1
    split = positions(db, account.id)[0]
    assert split.quantity == pytest.approx(original.quantity * 2)
    assert split.average_cost == pytest.approx(original.average_cost / 2)
    db.execute(
        "INSERT INTO corporate_actions VALUES ('div','AAPL','2026-07-13','dividend',1,'test',?)", [NOW]
    )
    cash_before = cash_balance(db, account.id)
    assert apply_corporate_actions(db, account, date(2026, 7, 13), NOW) == 1
    assert apply_corporate_actions(db, account, date(2026, 7, 13), NOW) == 0
    assert cash_balance(db, account.id) == pytest.approx(cash_before + split.quantity)


def test_stop_exit_creates_cooldown_after_fill(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    add_prices(db, "AAPL", datetime(2026, 7, 9, 22, tzinfo=UTC), [
        (date(2026, 7, 8), 100), (date(2026, 7, 9), 100),
    ])
    run = add_recommendation(db, strategy)
    generate_entry_orders(db, account, strategy, run.id, date(2026, 7, 8), NOW)
    settle_pending_orders(db, account, strategy, date(2026, 7, 9))
    add_prices(db, "AAPL", datetime(2026, 7, 13, 22, tzinfo=UTC), [
        (date(2026, 7, 10), 80), (date(2026, 7, 13), 79),
    ])
    assert generate_exit_orders(db, account, strategy, "exit-run", date(2026, 7, 10), NOW) == 1
    assert settle_pending_orders(db, account, strategy, date(2026, 7, 13)) == (1, 0)
    assert positions(db, account.id) == ()
    assert db.execute("SELECT reason FROM reentry_cooldowns").fetchone() == ("stop_loss",)
