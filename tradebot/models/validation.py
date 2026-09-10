from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from numbers import Integral, Real

from tradebot.models.raw_record import RawRecord


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")


def _number(value: object, name: str, *, positive: bool = True) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} is out of range")


def validate_record(record: RawRecord, table: str) -> None:
    require_aware(record.fetched_at)
    if not record.ticker or record.ticker != record.ticker.strip().upper():
        raise ValueError("Ticker must be normalized")
    if type(record.transaction_date) is not date:
        raise ValueError("transaction_date is required")
    data = record.data
    if table == "raw_prices":
        if record.source != "yfinance":
            raise ValueError("Expected yfinance price record")
        for key in ("open", "high", "low", "close"):
            _number(data.get(key), key)
        if not data["low"] <= min(data["open"], data["close"]) <= max(data["open"], data["close"]) <= data["high"]:
            raise ValueError("Inconsistent OHLC range")
        volume = data.get("volume")
        if isinstance(volume, bool) or not isinstance(volume, Integral) or volume < 0:
            raise ValueError("volume must be a nonnegative integer")
    elif table == "raw_insider":
        if record.source != "edgar" or type(record.filed_at) is not date:
            raise ValueError("Expected edgar record with filed_at")
        if record.transaction_date > record.filed_at:
            raise ValueError("Transaction occurs after filing")
        if not isinstance(data.get("accession"), str) or not data["accession"]:
            raise ValueError("accession is required")
        index = data.get("transaction_index")
        if type(index) is not int or index < 0:
            raise ValueError("transaction_index must be a nonnegative integer")
        if data.get("transaction_code") != "P":
            raise ValueError("Only code-P transactions are supported")
        _number(data.get("shares"), "shares")
        if data.get("price_per_share") is not None:
            _number(data["price_per_share"], "price_per_share")
    else:
        raise ValueError(f"Unsupported table: {table!r}")
