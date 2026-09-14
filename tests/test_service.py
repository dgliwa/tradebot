from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from tradebot.config import Settings
from tradebot.service.runtime import acquire_lock, release_lock, run_loop, run_once, service_status
from tradebot.strategy import PelosiConfig, PelosiStrategy

NOW = datetime(2026, 7, 8, 22, tzinfo=UTC)


def test_service_lock_has_single_owner_and_expiry(db):
    assert acquire_lock(db, "one", NOW, timedelta(minutes=1))
    assert not acquire_lock(db, "two", NOW)
    assert acquire_lock(db, "two", NOW + timedelta(minutes=2))
    release_lock(db, "two")
    assert service_status(db)["lock"] is None


def test_run_once_records_success(db, monkeypatch, tmp_path):
    strategy = PelosiStrategy(PelosiConfig())
    cycle = SimpleNamespace(daily=SimpleNamespace(run_id="strategy-run", session=date(2026, 7, 8)))
    monkeypatch.setattr("tradebot.service.runtime.run_shadow_cycle", lambda *args, **kwargs: cycle)
    monkeypatch.setattr(
        "tradebot.service.runtime.generate_report",
        lambda *args, **kwargs: (tmp_path / "report.json", tmp_path / "report.html"),
    )
    result = run_once(db, Settings(), strategy, decision_at=NOW)
    assert result.strategy_run_id == "strategy-run"
    assert service_status(db)["latest_run"]["status"] == "completed"


def test_loop_releases_lock_on_shutdown(db, monkeypatch):
    strategy = PelosiStrategy(PelosiConfig())
    monkeypatch.setattr("tradebot.service.runtime.run_once", lambda *args, **kwargs: None)

    def stop(_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_loop(db, Settings(), strategy, sleep=stop)
    assert service_status(db)["lock"] is None
