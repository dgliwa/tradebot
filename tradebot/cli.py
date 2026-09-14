from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from tradebot.config import load_settings
from tradebot.db import bind_mode, init_db
from tradebot.db.connection import open_database
from tradebot.execution.broker import AlpacaPaperBroker
from tradebot.execution.paper import (
    approve_intent, enable_automatic_submission, ensure_paper_state, pending_intents,
    reconcile_orders, reject_intent, set_kill_switch,
)
from tradebot.ingestion import ingest_insider, ingest_political_csv, ingest_prices
from tradebot.report import generate_report
from tradebot.service import run_loop, run_once, service_status
from tradebot.shadow.account import create_account, load_account
from tradebot.shadow.service import run_shadow_cycle, shadow_status
from tradebot.strategy import load_strategy
from tradebot.strategy.daily import effective_session, run_daily
from tradebot.strategy.query import recommendation_rows


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tradebot", description="Local TradeBot data pipeline (no order execution)")
    root.add_argument("--env-dir", type=Path, default=Path("."), help="directory containing .env.paper/.env.live")
    root.add_argument("--strategy", type=Path, default=Path("strategy.toml"), help="versioned strategy TOML file")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="initialize or upgrade the selected database")
    strategy = commands.add_parser("strategy", help="inspect the effective strategy contract")
    strategy.add_argument("action", choices=("show",))
    daily = commands.add_parser("run-daily", help="ingest and calculate a completed session")
    daily_mode = daily.add_mutually_exclusive_group(required=True)
    daily_mode.add_argument("--dry-run", action="store_true", help="create recommendations but no orders")
    daily_mode.add_argument("--shadow", action="store_true", help="create and fill local simulated orders")
    daily.add_argument("--account", default="default")
    shadow = commands.add_parser("shadow", help="manage the local simulated account")
    shadow.add_argument("action", choices=("init", "status"))
    shadow.add_argument("--account", default="default")
    shadow.add_argument("--session", type=date.fromisoformat)
    paper = commands.add_parser("paper", help="manage guarded Alpaca paper-order intents")
    paper.add_argument("action", choices=("status", "pending", "approve", "reject", "reconcile", "kill", "unkill", "auto-enable"))
    paper.add_argument("intent_id", nargs="?")
    paper.add_argument("--account", default="default")
    service = commands.add_parser("service", help="run or inspect the platform-neutral scheduler")
    service.add_argument("action", choices=("run-once", "run", "status", "health"))
    service.add_argument("--poll-seconds", type=int, default=60)
    service.add_argument("--output", type=Path, default=Path("reports"))
    report = commands.add_parser("report", help="generate local JSON and HTML performance reports")
    report.add_argument("action", choices=("generate",))
    report.add_argument("--account", default="default")
    report.add_argument("--session", type=date.fromisoformat)
    report.add_argument("--output", type=Path, default=Path("reports"))
    recommendations = commands.add_parser("recommendations", help="inspect stored recommendations")
    recommendations.add_argument("action", choices=("show",))
    recommendations.add_argument("--run-id")
    ingest = commands.add_parser("ingest", help="fetch and atomically persist raw market data")
    ingest.add_argument("source", choices=("prices", "insider", "congressional", "all"))
    ingest.add_argument("--file", type=Path, help="manual congressional disclosure CSV")
    ingest.add_argument("--coverage-through", type=date.fromisoformat, help="latest filing date checked (YYYY-MM-DD)")
    return root


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "strategy":
            strategy = load_strategy(args.strategy)
            print(json.dumps({"config": json.loads(strategy.canonical_json), "config_hash": strategy.config_hash}, sort_keys=True))
            return 0
        settings = load_settings(env_dir=args.env_dir)
        with open_database(settings.db_path) as conn:
            init_db(conn)
            bind_mode(conn, settings.mode)
            if args.command == "init-db":
                print(json.dumps({"status": "ok", "mode": settings.mode, "database": str(settings.db_path)}))
                return 0
            if args.command == "recommendations":
                print(json.dumps(recommendation_rows(conn, args.run_id), sort_keys=True))
                return 0
            if args.command == "paper":
                state = ensure_paper_state(conn)
                if args.action == "status":
                    print(json.dumps(state, sort_keys=True))
                    return 0
                if args.action in {"kill", "unkill"}:
                    set_kill_switch(conn, args.action == "kill")
                    print(json.dumps(ensure_paper_state(conn), sort_keys=True))
                    return 0
                if args.action == "auto-enable":
                    enable_automatic_submission(conn)
                    print(json.dumps(ensure_paper_state(conn), sort_keys=True))
                    return 0
                account = load_account(conn, args.account)
                if args.action == "pending":
                    print(json.dumps([asdict(item) for item in pending_intents(conn, account)], sort_keys=True))
                    return 0
                if args.action == "reject":
                    if not args.intent_id:
                        raise ValueError("paper reject requires an intent_id")
                    reject_intent(conn, account, args.intent_id)
                    print(json.dumps({"status": "rejected", "intent_id": args.intent_id}))
                    return 0
                broker = AlpacaPaperBroker(settings)
                if args.action == "reconcile":
                    print(json.dumps({"reconciled": reconcile_orders(conn, account, broker)}))
                    return 0
                if not args.intent_id:
                    raise ValueError("paper approve requires an intent_id")
                strategy = load_strategy(args.strategy)
                print(json.dumps(asdict(approve_intent(
                    conn, account, strategy, args.intent_id, broker
                )), sort_keys=True))
                return 0
            if args.command == "service":
                if args.action in {"status", "health"}:
                    status = service_status(conn)
                    print(json.dumps(status, sort_keys=True))
                    if args.action == "health":
                        lock = status["lock"]
                        return 0 if lock and datetime.fromisoformat(lock["expires_at"]) > datetime.now(UTC) else 2
                    return 0
                strategy = load_strategy(args.strategy)
                if args.action == "run-once":
                    print(json.dumps(asdict(run_once(
                        conn, settings, strategy, output_root=args.output
                    )), sort_keys=True))
                    return 0
                run_loop(conn, settings, strategy, poll_seconds=args.poll_seconds, output_root=args.output)
                return 0
            if args.command == "report":
                strategy = load_strategy(args.strategy)
                session = args.session or effective_session(strategy, datetime.now(UTC))
                paths = generate_report(
                    conn, strategy, session, account_name=args.account, output_root=args.output
                )
                print(json.dumps({"json": str(paths[0]), "html": str(paths[1])}, sort_keys=True))
                return 0
            if args.command == "shadow":
                strategy = load_strategy(args.strategy)
                account = create_account(conn, strategy, name=args.account)
                if args.action == "init":
                    print(json.dumps(asdict(account), sort_keys=True))
                else:
                    session = args.session or effective_session(strategy, datetime.now(UTC))
                    print(json.dumps(shadow_status(conn, args.account, session), default=str, sort_keys=True))
                return 0
            if args.command == "run-daily":
                strategy = load_strategy(args.strategy)
                result = (run_shadow_cycle(conn, settings, strategy, account_name=args.account)
                          if args.shadow else run_daily(conn, settings, strategy))
                print(json.dumps(asdict(result), default=str, sort_keys=True))
                return 0
            operations = []
            if args.source == "congressional":
                if args.file is None or args.coverage_through is None:
                    raise ValueError("Congressional import requires --file and --coverage-through")
                operations.append(ingest_political_csv(conn, args.file, args.coverage_through))
            if args.source in {"prices", "all"}:
                operations.append(ingest_prices(conn, settings))
            if args.source in {"insider", "all"}:
                operations.append(ingest_insider(conn, settings))
            print(json.dumps([asdict(summary) for summary in operations], sort_keys=True))
            return 0 if all(summary.succeeded for summary in operations) else 2
    except KeyboardInterrupt:
        print("tradebot: service stopped", file=sys.stderr)
        return 130
    except (duckdb.Error, OSError, RuntimeError, ValueError) as exc:
        print(f"tradebot: {exc}", file=sys.stderr)
        return 2
