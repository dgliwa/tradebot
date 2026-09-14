from datetime import UTC, date, datetime

from tradebot.evaluation import evaluate_experiment
from tradebot.fetchers.market import sessions_between
from tradebot.shadow.account import create_account
from tradebot.strategy import PelosiConfig, PelosiStrategy

NOW = datetime(2026, 4, 1, 22, tzinfo=UTC)


def insert_performance(db, account_id, sessions, final_strategy=1.2, final_benchmark=1.1, drawdown=0):
    for index, session in enumerate(sessions):
        progress = index / max(1, len(sessions) - 1)
        strategy_index = 1 + (final_strategy - 1) * progress
        benchmark_index = 1 + (final_benchmark - 1) * progress
        db.execute(
            """INSERT INTO performance_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [account_id, session, strategy_index * 10_000, benchmark_index * 10_000,
             10_000 if index == 0 else 0, strategy_index, benchmark_index,
             drawdown if index == len(sessions) - 1 else 0, 0.5, NOW],
        )


def test_evaluation_reports_research_ready_but_paper_not_ready(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    sessions = sessions_between(date(2026, 1, 2), date(2026, 3, 30))
    insert_performance(db, account.id, sessions)
    result = evaluate_experiment(db, strategy, evaluated_at=NOW)
    assert result["research_ready"]
    assert not result["live_review_ready"]
    assert result["gates"]["complete_session_history"]
    assert result["status"] == "collecting"


def test_drawdown_limit_emits_abort_status(db):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    sessions = sessions_between(date(2026, 1, 2), date(2026, 3, 30))
    insert_performance(db, account.id, sessions, drawdown=-0.16)
    result = evaluate_experiment(db, strategy, evaluated_at=NOW)
    assert result["abort"]
    assert result["status"] == "abort"
    assert not result["gates"]["drawdown_within_limit"]


def test_empty_experiment_remains_collecting(db):
    strategy = PelosiStrategy(PelosiConfig())
    create_account(db, strategy, created_at=NOW)
    result = evaluate_experiment(db, strategy, evaluated_at=NOW)
    assert result["status"] == "collecting"
    assert not result["abort"]
