from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

import duckdb

from tradebot.models.validation import require_aware


@dataclass(frozen=True)
class PoliticalDisclosure:
    source_id: str
    politician: str
    owner: str
    ticker: str
    transaction_type: str
    asset_type: str
    transaction_date: date
    filed_at: date
    amount_min: float
    amount_max: float
    option_type: str | None = None

    def __post_init__(self) -> None:
        if not all((self.source_id.strip(), self.politician.strip(), self.ticker.strip())):
            raise ValueError("Disclosure identity fields are required")
        if self.ticker != self.ticker.strip().upper():
            raise ValueError("Disclosure ticker must be normalized")
        if self.transaction_type not in {"purchase", "sale"}:
            raise ValueError("Disclosure transaction_type must be purchase or sale")
        if self.asset_type not in {"stock", "option"}:
            raise ValueError("Disclosure asset_type must be stock or option")
        if self.asset_type == "option" and self.option_type not in {"call", "put"}:
            raise ValueError("Option disclosure requires call or put")
        if self.asset_type == "stock" and self.option_type is not None:
            raise ValueError("Stock disclosure cannot have option_type")
        if self.transaction_date > self.filed_at:
            raise ValueError("Disclosure transaction occurs after filing")
        if self.amount_min < 0 or self.amount_max < self.amount_min:
            raise ValueError("Invalid disclosure amount range")


@dataclass(frozen=True)
class PoliticalBatch:
    source: str
    coverage_through: date
    records: tuple[PoliticalDisclosure, ...]
    source_path: str | None = None


class PoliticalProvider(Protocol):
    def load(self) -> PoliticalBatch: ...


class ManualCSVProvider:
    required = {
        "source_id", "politician", "owner", "ticker", "transaction_type",
        "asset_type", "transaction_date", "filed_at", "amount_min", "amount_max",
    }

    def __init__(self, path: Path, coverage_through: date):
        self.path = path
        self.coverage_through = coverage_through

    def load(self) -> PoliticalBatch:
        try:
            handle = self.path.open(newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise ValueError(f"Cannot read congressional CSV: {self.path}") from exc
        with handle:
            reader = csv.DictReader(handle)
            missing = self.required - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Congressional CSV missing columns: {', '.join(sorted(missing))}")
            records = []
            for line, row in enumerate(reader, start=2):
                try:
                    transaction = row["transaction_type"].strip().lower()
                    transaction = {"buy": "purchase", "purchased": "purchase", "sell": "sale", "sold": "sale"}.get(transaction, transaction)
                    asset = row["asset_type"].strip().lower()
                    option_type = (row.get("option_type") or "").strip().lower() or None
                    records.append(PoliticalDisclosure(
                        source_id=row["source_id"].strip(), politician=row["politician"].strip(),
                        owner=row["owner"].strip(), ticker=row["ticker"].strip().upper(),
                        transaction_type=transaction, asset_type=asset,
                        option_type=option_type, transaction_date=date.fromisoformat(row["transaction_date"].strip()),
                        filed_at=date.fromisoformat(row["filed_at"].strip()),
                        amount_min=float(row["amount_min"]), amount_max=float(row["amount_max"]),
                    ))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid congressional CSV line {line}: {exc}") from exc
        return PoliticalBatch("manual_csv", self.coverage_through, tuple(records), str(self.path))


def disclosure_id(source: str, source_id: str) -> str:
    return hashlib.sha256(f"{source}:{source_id}".encode()).hexdigest()[:32]


def import_political_batch(
    conn: duckdb.DuckDBPyConnection, batch: PoliticalBatch, *, imported_at: datetime | None = None,
) -> tuple[int, int]:
    imported_at = imported_at or datetime.now(UTC)
    require_aware(imported_at)
    batch_id = hashlib.sha256(f"{batch.source}:{batch.coverage_through}".encode()).hexdigest()[:24]
    existing = conn.execute("SELECT row_count FROM congressional_imports WHERE id = ?", [batch_id]).fetchone()
    if existing:
        return 0, existing[0]
    if any(record.filed_at > batch.coverage_through for record in batch.records):
        raise ValueError("Disclosure filing exceeds declared coverage date")
    conn.execute("BEGIN TRANSACTION")
    try:
        inserted = 0
        for record in batch.records:
            payload = json.dumps(asdict(record), default=str, sort_keys=True)
            row = conn.execute(
                """INSERT INTO raw_congressional
                (id, ticker, member_name, transaction_date, filed_at, amount_min, amount_max,
                 transaction_type, fetched_at, owner, asset_type, option_type, source,
                 source_id, raw_payload, import_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING RETURNING id""",
                [disclosure_id(batch.source, record.source_id), record.ticker, record.politician,
                 record.transaction_date, record.filed_at, record.amount_min, record.amount_max,
                 record.transaction_type, imported_at.astimezone(UTC), record.owner,
                 record.asset_type, record.option_type, batch.source, record.source_id, payload, batch_id],
            ).fetchone()
            inserted += row is not None
        conn.execute(
            """INSERT INTO congressional_imports
            (id, source, coverage_through, source_path, row_count, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [batch_id, batch.source, batch.coverage_through, batch.source_path, len(batch.records), imported_at],
        )
        conn.execute("COMMIT")
        return inserted, len(batch.records) - inserted
    except Exception:
        conn.execute("ROLLBACK")
        raise
