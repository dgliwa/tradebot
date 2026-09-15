from datetime import UTC, datetime

import pandas as pd

from tradebot.fetchers.corporate_actions import fetch_corporate_actions, write_corporate_actions
from tradebot.fetchers.market import completed_sessions

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def action_frame(tickers):
    sessions = completed_sessions(NOW)[-5:]
    fields = ["Close", "Dividends", "Stock Splits"]
    columns = pd.MultiIndex.from_product([tickers, fields], names=["Ticker", "Price"])
    values = {}
    for ticker in tickers:
        values[(ticker, "Close")] = [100.] * len(sessions)
        values[(ticker, "Dividends")] = [0.] * len(sessions)
        values[(ticker, "Stock Splits")] = [0.] * len(sessions)
    return pd.DataFrame(values, index=pd.to_datetime(sessions), columns=columns)


def test_fetches_dividends_and_splits_with_zero_event_coverage(monkeypatch):
    frame = action_frame(["AAPL", "MSFT"])
    frame.loc[frame.index[-2], ("AAPL", "Dividends")] = 0.25
    frame.loc[frame.index[-1], ("AAPL", "Stock Splits")] = 2
    monkeypatch.setattr("tradebot.fetchers.corporate_actions.yf.download", lambda **_: frame)
    actions, result = fetch_corporate_actions(["AAPL", "MSFT"], now=NOW)
    assert result.is_valid
    assert result.row_count == 2
    assert [(action.action_type, action.value) for action in actions] == [
        ("dividend", 0.25), ("split", 2.0),
    ]
    assert result.tickers[1].row_count == 0


def test_stale_action_history_fails_coverage(monkeypatch):
    frame = action_frame(["AAPL"]).iloc[:-1]
    monkeypatch.setattr("tradebot.fetchers.corporate_actions.yf.download", lambda **_: frame)
    actions, result = fetch_corporate_actions(["AAPL"], now=NOW)
    assert actions == []
    assert not result.is_valid
    assert "does not cover latest" in result.tickers[0].errors[0]


def test_action_writes_are_idempotent_and_source_revisions_fail(db, monkeypatch):
    frame = action_frame(["AAPL"])
    frame.loc[frame.index[-1], ("AAPL", "Dividends")] = 0.25
    monkeypatch.setattr("tradebot.fetchers.corporate_actions.yf.download", lambda **_: frame)
    actions, _ = fetch_corporate_actions(["AAPL"], now=NOW)
    assert write_corporate_actions(db, actions) == (1, 0)
    assert write_corporate_actions(db, actions) == (0, 1)
    revised = [type(actions[0])(**{**actions[0].__dict__, "value": 0.30})]
    try:
        write_corporate_actions(db, revised)
    except ValueError as exc:
        assert "changed at source" in str(exc)
    else:
        raise AssertionError("source revision should fail closed")
