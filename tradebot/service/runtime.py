from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import duckdb

from tradebot.config import Settings
from tradebot.report import generate_report
from tradebot.shadow.service import run_shadow_cycle
from tradebot.strategy.base import TradingStrategy
from tradebot.strategy.daily import effective_session
from tradebot.strategy.runs import run_id


@dataclass(frozen=True)
class ServiceResult:
    id: str
    strategy_run_id: str
    session: str
    report_json: str
    report_html: str


def acquire_lock(
    conn: duckdb.DuckDBPyConnection, owner: str, now: datetime | None = None,
    lease: timedelta = timedelta(minutes=30),
) -> bool:
    now = now or datetime.now(UTC)
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("DELETE FROM service_locks WHERE name='daily' AND expires_at<=?", [now])
        row = conn.execute(
            """INSERT INTO service_locks VALUES ('daily',?,?,?,?)
               ON CONFLICT DO NOTHING RETURNING owner""",
            [owner, now, now + lease, now],
        ).fetchone()
        conn.execute("COMMIT")
        return row is not None
    except Exception:
        conn.execute("ROLLBACK")
        raise


def heartbeat(
    conn: duckdb.DuckDBPyConnection, owner: str, now: datetime | None = None,
    lease: timedelta = timedelta(minutes=30),
) -> None:
    now = now or datetime.now(UTC)
    row = conn.execute(
        """UPDATE service_locks SET heartbeat_at=?,expires_at=?
           WHERE name='daily' AND owner=? RETURNING owner""",
        [now, now + lease, owner],
    ).fetchone()
    if row is None:
        raise RuntimeError("Service lock was lost")


def release_lock(conn: duckdb.DuckDBPyConnection, owner: str) -> None:
    conn.execute("DELETE FROM service_locks WHERE name='daily' AND owner=?", [owner])


def run_once(
    conn: duckdb.DuckDBPyConnection, settings: Settings, strategy: TradingStrategy,
    *, owner: str = "manual", output_root: Path = Path("reports"),
    decision_at: datetime | None = None,
) -> ServiceResult:
    started_at = (decision_at or datetime.now(UTC)).astimezone(UTC)
    identifier = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO service_runs (id,owner,started_at,status) VALUES (?,?,?,'running')",
        [identifier, owner, started_at],
    )
    try:
        cycle = run_shadow_cycle(conn, settings, strategy, decision_at=started_at)
        report_paths = generate_report(
            conn, strategy, cycle.daily.session, output_root=output_root
        )
        conn.execute(
            """UPDATE service_runs SET status='completed',completed_at=?,strategy_run_id=? WHERE id=?""",
            [datetime.now(UTC), cycle.daily.run_id, identifier],
        )
        return ServiceResult(
            identifier, cycle.daily.run_id, cycle.daily.session.isoformat(),
            str(report_paths[0]), str(report_paths[1]),
        )
    except Exception as exc:
        conn.execute(
            """UPDATE service_runs SET status='failed',completed_at=?,diagnostics=? WHERE id=?""",
            [datetime.now(UTC), json.dumps({"error": str(exc)}), identifier],
        )
        raise


def service_due(
    conn: duckdb.DuckDBPyConnection, strategy: TradingStrategy,
    now: datetime | None = None,
) -> bool:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    expected = run_id(strategy, effective_session(strategy, now))
    row = conn.execute(
        "SELECT 1 FROM service_runs WHERE strategy_run_id=? AND status='completed' LIMIT 1",
        [expected],
    ).fetchone()
    return row is None


def run_loop(
    conn: duckdb.DuckDBPyConnection, settings: Settings, strategy: TradingStrategy,
    *, poll_seconds: int = 60, output_root: Path = Path("reports"),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if poll_seconds < 1:
        raise ValueError("poll_seconds must be positive")
    owner = str(uuid.uuid4())
    if not acquire_lock(conn, owner):
        raise RuntimeError("Another TradeBot service owns the daily lock")
    failures = 0
    try:
        while True:
            heartbeat(conn, owner)
            try:
                if service_due(conn, strategy):
                    run_once(conn, settings, strategy, owner=owner, output_root=output_root)
                failures = 0
            except Exception:
                failures += 1
            heartbeat(conn, owner)
            sleep(min(poll_seconds * (2 ** min(failures, 6)), 3600))
    finally:
        release_lock(conn, owner)


def service_status(conn: duckdb.DuckDBPyConnection) -> dict:
    lock = conn.execute(
        "SELECT owner,heartbeat_at,expires_at FROM service_locks WHERE name='daily'"
    ).fetchone()
    latest = conn.execute(
        """SELECT id,started_at,completed_at,status,strategy_run_id,diagnostics
           FROM service_runs ORDER BY started_at DESC LIMIT 1"""
    ).fetchone()
    return {
        "lock": ({"owner": lock[0], "heartbeat_at": lock[1].isoformat(), "expires_at": lock[2].isoformat()}
                 if lock else None),
        "latest_run": ({
            "id": latest[0], "started_at": latest[1].isoformat(),
            "completed_at": latest[2].isoformat() if latest[2] else None,
            "status": latest[3], "strategy_run_id": latest[4],
            "diagnostics": json.loads(latest[5]),
        } if latest else None),
    }
