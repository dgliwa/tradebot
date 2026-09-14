import json
from datetime import UTC, date, datetime

from tradebot.db.writer import write_raw_records
from tradebot.models.raw_record import RawRecord
from tradebot.report.benchmark import sync_benchmark
from tradebot.report.generator import generate_report
from tradebot.report.performance import record_performance
from tradebot.shadow.account import create_account
from tradebot.shadow.portfolio import portfolio
from tradebot.strategy import PelosiConfig, PelosiStrategy

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def test_contribution_matched_benchmark_and_report_files(db, tmp_path):
    strategy = PelosiStrategy(PelosiConfig())
    account = create_account(db, strategy, created_at=NOW)
    write_raw_records(db, "raw_prices", [
        RawRecord("yfinance", "SPY", datetime(2026, 7, 9, 22, tzinfo=UTC),
                  {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
                  date(2026, 7, 8)),
        RawRecord("yfinance", "SPY", datetime(2026, 7, 9, 22, tzinfo=UTC),
                  {"open": 100, "high": 110, "low": 100, "close": 110, "volume": 1},
                  date(2026, 7, 9)),
    ])
    first_benchmark = sync_benchmark(db, account, "SPY", date(2026, 7, 8))
    first = record_performance(
        db, account, date(2026, 7, 8), portfolio(db, account.id, date(2026, 7, 8)),
        first_benchmark, NOW,
    )
    assert first.strategy_index == 1
    second_benchmark = sync_benchmark(db, account, "SPY", date(2026, 7, 9))
    second = record_performance(
        db, account, date(2026, 7, 9), portfolio(db, account.id, date(2026, 7, 9)),
        second_benchmark, datetime(2026, 7, 9, 22, tzinfo=UTC),
    )
    assert second.benchmark_index == 1.1
    assert second.strategy_index == 1
    json_path, html_path = generate_report(
        db, strategy, date(2026, 7, 9), output_root=tmp_path
    )
    payload = json.loads(json_path.read_text())
    assert payload["metrics"]["excess_return"] < 0
    assert payload["strategy"]["config_hash"] == strategy.config_hash
    assert "TradeBot report" in html_path.read_text()
