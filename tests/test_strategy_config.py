from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from tradebot.strategy.config import Capital, Execution, Signals, Strategy, load_strategy
from tradebot.strategy.runs import finish_run, start_run


def test_repository_strategy_contract_loads():
    strategy = load_strategy()
    assert strategy.version == "0.1.0"
    assert strategy.universe.tracked_politicians == ("Nancy Pelosi",)
    assert strategy.capital.starting_cash == 10_000
    assert len(strategy.config_hash) == 64
    assert strategy.config_hash == load_strategy().config_hash


def test_hash_changes_when_contract_changes():
    original = Strategy()
    changed = replace(original, capital=replace(original.capital, weekly_contribution=500))
    assert original.config_hash != changed.config_hash


@pytest.mark.parametrize("strategy", [
    Strategy(signals=Signals()),
    Strategy(capital=Capital()),
])
def test_valid_defaults(strategy):
    assert strategy.config_hash


@pytest.mark.parametrize("kwargs,match", [
    ({"signals": Signals(insider_weight=0.8)}, "sum to one"),
    ({"capital": Capital(position_fraction=0)}, "position fraction"),
    ({"execution": Execution(allow_margin=True)}, "forbids margin"),
])
def test_invalid_contract_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        Strategy(**kwargs)


def test_unknown_toml_key_rejected(tmp_path):
    path = tmp_path / "strategy.toml"
    path.write_text('version="1"\nunknown=true\n')
    with pytest.raises(ValueError, match="Unknown strategy keys"):
        load_strategy(path)


def test_strategy_run_is_idempotent_and_immutable(db):
    strategy = Strategy()
    session = date(2026, 7, 8)
    decision = datetime(2026, 7, 8, 22, tzinfo=UTC)
    created = start_run(db, strategy, session, decision)
    replay = start_run(db, strategy, session, decision)
    assert created.created and not replay.created
    assert created.id == replay.id
    changed = replace(strategy, capital=replace(strategy.capital, weekly_contribution=500))
    with pytest.raises(ValueError, match="version changed"):
        start_run(db, changed, session, decision)
    finish_run(db, created.id)
    assert db.execute("SELECT status FROM strategy_runs").fetchone() == ("completed",)
    with pytest.raises(ValueError, match="started"):
        finish_run(db, created.id)


def test_failed_run_records_diagnostic(db):
    run = start_run(db, Strategy(), date(2026, 7, 8))
    finish_run(db, run.id, error="missing prices")
    assert db.execute("SELECT status, diagnostics->>'error' FROM strategy_runs").fetchone() == (
        "failed", "missing prices")
