from __future__ import annotations
import hashlib
from datetime import date

import duckdb

from tradebot.models.raw_record import RawRecord


def _price_id(ticker: str, trade_date: date) -> int:
    """Deterministic BIGINT from (ticker, date). Collision probability negligible for a 20-ticker universe.

    Uses first 16 hex chars of SHA-256, masked to positive signed 64-bit range.
    """
    key = f"{ticker}:{trade_date}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16) & 0x7FFF_FFFF_FFFF_FFFF


def write_raw_records(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    records: list[RawRecord],
) -> int:
    """Bulk-insert records into table with ON CONFLICT DO NOTHING idempotency.

    Returns the number of rows attempted (not necessarily inserted — duplicates are silently skipped).
    """
    if not records:
        return 0

    if table == "raw_prices":
        rows = [
            (
                _price_id(r.ticker, r.transaction_date),
                r.ticker,
                r.transaction_date,
                r.data.get("open"),
                r.data.get("high"),
                r.data.get("low"),
                r.data.get("close"),
                r.data.get("volume"),
                r.fetched_at,
                r.source,
            )
            for r in records
        ]
        conn.executemany(
            "INSERT INTO raw_prices VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            rows,
        )
        return len(rows)

    elif table == "raw_insider":
        rows = [
            (
                f"{r.data['accession']}:{r.data['transaction_index']}",
                r.ticker,
                r.data.get("filer_name"),
                r.transaction_date,
                r.filed_at,
                r.data.get("shares"),
                r.data.get("price_per_share"),
                "Form4",
                r.data.get("transaction_code", "P"),
                r.fetched_at,
            )
            for r in records
        ]
        conn.executemany(
            "INSERT INTO raw_insider VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            rows,
        )
        return len(rows)

    else:
        raise ValueError(f"Unsupported table: {table!r}. Expected 'raw_prices' or 'raw_insider'.")
