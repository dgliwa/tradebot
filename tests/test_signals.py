from datetime import UTC, date, datetime, timedelta

import pytest

from tradebot.db.writer import write_raw_records
from tradebot.fetchers.market import completed_sessions
from tradebot.models.raw_record import RawRecord
from tradebot.signals.scorer import score_candidates
from tradebot.strategy.config import Strategy
from tradebot.strategy.universe import Candidate

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def prices(ticker, step, fetched_at=NOW):
    rows = []
    for index, day in enumerate(completed_sessions(NOW)[-64:]):
        close = 100 + index * step
        rows.append(RawRecord("yfinance", ticker, fetched_at, {
            "open": close, "high": close, "low": close, "close": close, "volume": 1000,
        }, day))
    return rows


def insider(ticker):
    return RawRecord("edgar", ticker, NOW, {
        "accession": f"{ticker}-accession", "transaction_index": 0,
        "filer_name": "Executive", "transaction_code": "P", "shares": 5000.,
        "price_per_share": 200., "raw_xml": "<xml/>", "document_url": "https://sec.test/form.xml",
    }, date(2026, 7, 6), date(2026, 7, 7))


def test_signal_ranking_is_reproducible_and_explainable(db):
    write_raw_records(db, "raw_prices", prices("AAPL", .1) + prices("NVDA", 1.0))
    write_raw_records(db, "raw_insider", [insider("AAPL")])
    candidates = [Candidate("AAPL", 10, date(2026, 7, 7), ("p1",)),
                  Candidate("NVDA", 10, date(2026, 7, 7), ("p2",))]
    results = score_candidates(db, Strategy(), "run-1", date(2026, 7, 8), NOW, candidates)
    assert [result.ticker for result in results] == ["AAPL", "NVDA"]
    assert results[0].scores["insider"] == 1
    assert results[0].scores["momentum"] == -1
    assert results[0].composite_score == pytest.approx(1 / 7)
    assert db.execute("SELECT count(*) FROM signals").fetchone() == (4,)
    assert db.execute("SELECT count(*) FROM recommendations WHERE selected").fetchone() == (2,)
    score_candidates(db, Strategy(), "run-1", date(2026, 7, 8), NOW, candidates)
    assert db.execute("SELECT count(*) FROM signals").fetchone() == (4,)


def test_future_snapshot_is_not_available_to_signal(db):
    write_raw_records(db, "raw_prices", prices("AAPL", 1, NOW + timedelta(minutes=1)))
    with pytest.raises(ValueError, match="Need 64"):
        score_candidates(
            db, Strategy(), "run", date(2026, 7, 8), NOW,
            [Candidate("AAPL", 1, date(2026, 7, 7), ("p",))],
        )


def test_insider_filed_after_session_is_excluded(db):
    write_raw_records(db, "raw_prices", prices("AAPL", 1))
    late = insider("AAPL")
    late.fetched_at = datetime(2026, 7, 10, tzinfo=UTC)
    late.filed_at = date(2026, 7, 9)
    late.transaction_date = date(2026, 7, 8)
    write_raw_records(db, "raw_insider", [late])
    result = score_candidates(
        db, Strategy(), "run", date(2026, 7, 8), NOW,
        [Candidate("AAPL", 1, date(2026, 7, 7), ("p",))],
    )[0]
    assert result.raw_values["insider"] == 0
