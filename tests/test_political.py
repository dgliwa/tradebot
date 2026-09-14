from datetime import UTC, date, datetime

import pytest

from tradebot.fetchers.political import ManualCSVProvider, import_political_batch
from tradebot.strategy.config import Strategy
from tradebot.strategy.universe import build_universe

HEADER = "source_id,politician,owner,ticker,transaction_type,asset_type,option_type,transaction_date,filed_at,amount_min,amount_max\n"


def write_csv(tmp_path, rows):
    path = tmp_path / "disclosures.csv"
    path.write_text(HEADER + "\n".join(rows) + "\n")
    return path


def test_manual_csv_import_is_atomic_and_idempotent(db, tmp_path):
    path = write_csv(tmp_path, [
        "p1,Nancy Pelosi,Spouse,NVDA,Purchase,option,call,2026-07-01,2026-07-07,100001,250000",
    ])
    batch = ManualCSVProvider(path, date(2026, 7, 8)).load()
    assert import_political_batch(db, batch, imported_at=datetime(2026, 7, 8, tzinfo=UTC)) == (1, 0)
    assert import_political_batch(db, batch, imported_at=datetime(2026, 7, 8, tzinfo=UTC)) == (0, 1)
    assert db.execute("SELECT member_name,asset_type,option_type FROM raw_congressional").fetchone() == (
        "Nancy Pelosi", "option", "call")


def test_invalid_csv_rolls_back(db, tmp_path):
    path = write_csv(tmp_path, [
        "p1,Nancy Pelosi,Spouse,NVDA,purchase,option,call,2026-07-01,2026-07-07,1,2",
        "p2,Nancy Pelosi,Spouse,AAPL,purchase,option,bad,2026-07-01,2026-07-07,1,2",
    ])
    with pytest.raises(ValueError, match="line 3"):
        ManualCSVProvider(path, date(2026, 7, 8)).load()
    assert db.execute("SELECT count(*) FROM raw_congressional").fetchone() == (0,)


def test_politician_led_universe_handles_option_direction(db, tmp_path):
    path = write_csv(tmp_path, [
        "p1,Nancy Pelosi,Spouse,NVDA,purchase,option,call,2026-07-01,2026-07-07,100,200",
        "p2,Nancy Pelosi,Spouse,TSLA,purchase,option,put,2026-07-01,2026-07-07,100,200",
        "p3,Someone Else,Self,AAPL,purchase,stock,,2026-07-01,2026-07-07,100,200",
        "p4,Nancy Pelosi,Spouse,MSFT,purchase,stock,,2026-07-01,2026-07-07,100,200",
        "p5,Nancy Pelosi,Spouse,MSFT,sale,stock,,2026-07-02,2026-07-08,200,300",
    ])
    import_political_batch(db, ManualCSVProvider(path, date(2026, 7, 8)).load())
    candidates = build_universe(db, Strategy(), "run-1", date(2026, 7, 8), owned_tickers={"OWNED"})
    assert [candidate.ticker for candidate in candidates] == ["NVDA", "OWNED"]
    assert db.execute("SELECT ticker FROM universe_snapshots ORDER BY ticker").fetchall() == [("NVDA",), ("OWNED",)]


def test_stale_congressional_coverage_blocks_run(db):
    with pytest.raises(ValueError, match="coverage is stale"):
        build_universe(db, Strategy(), "run", date(2026, 7, 8))
