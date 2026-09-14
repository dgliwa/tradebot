from datetime import UTC, date, datetime

from tradebot.config import Settings
from tradebot.db.writer import write_raw_records
from tradebot.fetchers.market import completed_sessions
from tradebot.fetchers.political import ManualCSVProvider, import_political_batch
from tradebot.ingestion import IngestionSummary
from tradebot.models.raw_record import RawRecord
from tradebot.strategy.config import Strategy
from tradebot.strategy.daily import effective_session, run_daily
from tradebot.strategy.pelosi import PelosiStrategy

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def setup_candidate(db, tmp_path):
    path = tmp_path / "political.csv"
    path.write_text(
        "source_id,politician,owner,ticker,transaction_type,asset_type,option_type,transaction_date,filed_at,amount_min,amount_max\n"
        "p1,Nancy Pelosi,Spouse,AAPL,purchase,stock,,2026-07-01,2026-07-08,100,200\n"
    )
    import_political_batch(db, ManualCSVProvider(path, date(2026, 7, 8)).load())
    rows = []
    for index, day in enumerate(completed_sessions(NOW)[-64:]):
        close = 100 + index
        rows.append(RawRecord("yfinance", "AAPL", NOW, {
            "open": close, "high": close, "low": close, "close": close, "volume": 100,
        }, day))
    write_raw_records(db, "raw_prices", rows)


def test_daily_run_and_replay(db, tmp_path, monkeypatch):
    setup_candidate(db, tmp_path)
    calls = []

    def healthy(*args, **kwargs):
        calls.append(kwargs["universe"])
        return IngestionSummary("mock", 0, 0, 0, "2026-07-08")

    monkeypatch.setattr("tradebot.strategy.daily.ingest_prices", healthy)
    monkeypatch.setattr("tradebot.strategy.daily.ingest_insider", healthy)
    settings = Settings(universe=["IGNORED"], sec_user_agent="TradeBot test@example.com")
    strategy = PelosiStrategy(Strategy())
    first = run_daily(db, settings, strategy, decision_at=NOW)
    replay = run_daily(db, settings, strategy, decision_at=NOW)
    assert not first.replayed and replay.replayed
    assert calls == [["AAPL", "SPY"], ["AAPL"]]
    assert first.recommendations[0].ticker == "AAPL"
    assert db.execute("SELECT count(*) FROM strategy_runs").fetchone() == (1,)


def test_daily_runner_accepts_strategy_contract_without_pelosi_logic(db, monkeypatch):
    class EmptyStrategy:
        def __init__(self):
            self.config = Strategy(name="empty-test")

        def __getattr__(self, name):
            return getattr(self.config, name)

        def build_candidates(self, conn, run_id, session, *, owned_tickers=None):
            return []

        def score(self, conn, run_id, session, decision_at, candidates):
            raise AssertionError("empty candidate strategies must not score")

    strategy = EmptyStrategy()
    monkeypatch.setattr(
        "tradebot.strategy.daily.ingest_prices",
        lambda *args, **kwargs: IngestionSummary("mock", 0, 0, 0, "2026-07-08"),
    )
    result = run_daily(db, Settings(), strategy, decision_at=NOW)
    assert result.recommendations == ()


def test_before_configured_time_uses_previous_session():
    before_evaluation = datetime(2026, 7, 8, 21, tzinfo=UTC)  # 17:00 ET
    assert effective_session(Strategy(), before_evaluation) == date(2026, 7, 7)
