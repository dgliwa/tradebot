from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import duckdb

from tradebot.config import load_settings
from tradebot.db import bind_mode, init_db
from tradebot.db.connection import open_database
from tradebot.ingestion import ingest_insider, ingest_prices


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tradebot", description="Local TradeBot data pipeline (no order execution)")
    root.add_argument("--env-dir", type=Path, default=Path("."), help="directory containing .env.paper/.env.live")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="initialize or upgrade the selected database")
    ingest = commands.add_parser("ingest", help="fetch and atomically persist raw market data")
    ingest.add_argument("source", choices=("prices", "insider", "all"))
    return root


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = load_settings(env_dir=args.env_dir)
        with open_database(settings.db_path) as conn:
            init_db(conn)
            bind_mode(conn, settings.mode)
            if args.command == "init-db":
                print(json.dumps({"status": "ok", "mode": settings.mode, "database": str(settings.db_path)}))
                return 0
            operations = []
            if args.source in {"prices", "all"}:
                operations.append(ingest_prices(conn, settings))
            if args.source in {"insider", "all"}:
                operations.append(ingest_insider(conn, settings))
            print(json.dumps([asdict(summary) for summary in operations], sort_keys=True))
            return 0 if all(summary.succeeded for summary in operations) else 2
    except (duckdb.Error, OSError, RuntimeError, ValueError) as exc:
        print(f"tradebot: {exc}", file=sys.stderr)
        return 2
