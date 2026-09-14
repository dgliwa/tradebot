import json
from datetime import UTC, date, datetime

import duckdb
import pytest

from tradebot.cli import run
from tradebot.models.raw_record import FetchResult, RawRecord, TickerFetchResult

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for name in ("TRADEBOT_MODE", "TRADEBOT_DB_PATH", "TRADEBOT_LOG_LEVEL", "TRADEBOT_UNIVERSE",
                 "ALPACA_KEY", "ALPACA_SECRET", "ALPACA_BASE_URL", "SEC_USER_AGENT"):
        monkeypatch.delenv(name, raising=False)
    db_path = tmp_path / "paper.duckdb"
    (tmp_path / ".env.paper").write_text(
        f"TRADEBOT_MODE=paper\nTRADEBOT_DB_PATH={db_path}\nTRADEBOT_UNIVERSE=AAPL\nSEC_USER_AGENT=TradeBot test@example.com\n"
    )
    return tmp_path, db_path


def record():
    return RawRecord("yfinance", "AAPL", NOW,
                     {"open": 100., "high": 100., "low": 100., "close": 100., "volume": 10},
                     date(2026, 7, 8))


def valid_result():
    return FetchResult("yfinance", NOW, [TickerFetchResult("AAPL", 1, date(2026, 7, 8))])


def test_strategy_show_does_not_require_environment(capsys):
    assert run(["strategy", "show"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["config"]["version"] == "0.1.0"
    assert len(payload["config_hash"]) == 64


def test_init_db_cli_is_idempotent(clean_env, capsys):
    env_dir, db_path = clean_env
    assert run(["--env-dir", str(env_dir), "init-db"]) == 0
    assert run(["--env-dir", str(env_dir), "init-db"]) == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload == {"status": "ok", "mode": "paper", "database": str(db_path)}
    with duckdb.connect(str(db_path)) as conn:
        assert conn.execute("SELECT value FROM database_metadata WHERE key='mode'").fetchone() == ("paper",)


def test_fetch_to_database_integration(clean_env, monkeypatch, capsys):
    env_dir, db_path = clean_env
    monkeypatch.setattr("tradebot.ingestion.fetch_prices", lambda universe: ([record()], valid_result()))
    assert run(["--env-dir", str(env_dir), "ingest", "prices"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["inserted"] == 1
    assert payload[0]["errors"] == []
    with duckdb.connect(str(db_path)) as conn:
        assert conn.execute("SELECT ticker, close FROM latest_prices").fetchall() == [("AAPL", 100.)]


def test_invalid_fetch_exits_nonzero_without_partial_write(clean_env, monkeypatch, capsys):
    env_dir, db_path = clean_env
    result = valid_result()
    result.tickers.append(TickerFetchResult("MSFT", errors=["missing history"]))
    monkeypatch.setattr("tradebot.ingestion.fetch_prices", lambda universe: ([record()], result))
    assert run(["--env-dir", str(env_dir), "ingest", "prices"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["inserted"] == 0
    assert payload[0]["errors"] == ["MSFT: missing history"]
    with duckdb.connect(str(db_path)) as conn:
        assert conn.execute("SELECT count(*) FROM raw_prices").fetchone() == (0,)


def test_congressional_csv_import(clean_env, tmp_path, capsys):
    env_dir, db_path = clean_env
    csv_path = tmp_path / "political.csv"
    csv_path.write_text(
        "source_id,politician,owner,ticker,transaction_type,asset_type,option_type,transaction_date,filed_at,amount_min,amount_max\n"
        "p1,Nancy Pelosi,Spouse,NVDA,purchase,option,call,2026-07-01,2026-07-07,100001,250000\n"
    )
    assert run(["--env-dir", str(env_dir), "ingest", "congressional", "--file", str(csv_path),
                "--coverage-through", "2026-07-08"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["inserted"] == 1
    with duckdb.connect(str(db_path)) as conn:
        assert conn.execute("SELECT ticker FROM raw_congressional").fetchone() == ("NVDA",)


def test_bad_configuration_exits_nonzero(clean_env, monkeypatch, capsys):
    env_dir, _ = clean_env
    monkeypatch.setenv("TRADEBOT_MODE", "danger")
    assert run(["--env-dir", str(env_dir), "init-db"]) == 2
    assert "must be paper or live" in capsys.readouterr().err
