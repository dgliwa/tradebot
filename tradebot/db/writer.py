from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC

import duckdb

from tradebot.models.raw_record import RawRecord
from tradebot.models.validation import validate_record


@dataclass(frozen=True)
class WriteResult:
    inserted: int = 0
    skipped: int = 0


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _write_prices(conn: duckdb.DuckDBPyConnection, records: list[RawRecord]) -> int:
    groups = defaultdict(list)
    for record in records:
        groups[(record.ticker, record.source, record.fetched_at.astimezone(UTC))].append(record)
    inserted = 0
    for (ticker, source, fetched_at), group in groups.items():
        bars = {}
        for record in group:
            values = [float(record.data[k]) for k in ("open", "high", "low", "close")]
            values.append(int(record.data["volume"]))
            key = record.transaction_date.isoformat()
            if key in bars and bars[key] != values:
                raise ValueError(f"Conflicting bars for {ticker} on {key}")
            bars[key] = values
        content_hash = _hash(bars)
        snapshot_id = _hash([ticker, source, fetched_at.isoformat()])
        existing = conn.execute("SELECT content_hash FROM price_snapshots WHERE id = ?", [snapshot_id]).fetchone()
        if existing:
            if existing[0] != content_hash:
                raise ValueError("A snapshot timestamp cannot be reused for different content")
            continue
        conn.execute(
            "INSERT INTO price_snapshots (id, ticker, source, fetched_at, content_hash, row_count) VALUES (?,?,?,?,?,?)",
            [snapshot_id, ticker, source, fetched_at, content_hash, len(bars)],
        )
        conn.executemany(
            "INSERT INTO raw_prices (snapshot_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            [(snapshot_id, day, *values) for day, values in sorted(bars.items())],
        )
        inserted += len(bars)
    return inserted


def _write_insider(conn: duckdb.DuckDBPyConnection, records: list[RawRecord]) -> int:
    inserted = 0
    for r in records:
        data = r.data
        result = conn.execute(
            """INSERT INTO raw_insider
            (id, ticker, filer_name, transaction_date, filed_at, shares, price_per_share,
             form_type, transaction_code, fetched_at, raw_xml, document_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING id""",
            [f"{data['accession']}:{data['transaction_index']}", r.ticker,
             data.get("filer_name"), r.transaction_date, r.filed_at, data["shares"],
             data.get("price_per_share"), "Form4", "P", r.fetched_at,
             data.get("raw_xml"), data.get("document_url")],
        ).fetchone()
        inserted += result is not None
    return inserted


def write_raw_records(conn: duckdb.DuckDBPyConnection, table: str, records: list[RawRecord]) -> WriteResult:
    """Validate the entire batch, then commit atomically. Invalid batches raise.

    Price records must be a complete validated history for each ticker/fetch.
    Replaying a snapshot is idempotent; refetching creates a new immutable version.
    """
    if table not in {"raw_prices", "raw_insider"}:
        raise ValueError(f"Unsupported table: {table!r}")
    for record in records:
        validate_record(record, table)
    if not records:
        return WriteResult()
    conn.execute("BEGIN TRANSACTION")
    try:
        inserted = _write_prices(conn, records) if table == "raw_prices" else _write_insider(conn, records)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return WriteResult(inserted=inserted, skipped=len(records) - inserted)
