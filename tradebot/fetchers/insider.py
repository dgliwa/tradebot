from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from numbers import Real

import httpx

from tradebot.config import normalize_universe
from tradebot.fetchers.sec_filings import Filing, load_filings
from tradebot.fetchers.sec_http import SecHTTP
from tradebot.models.raw_record import FetchResult, RawRecord, TickerFetchResult
from tradebot.models.validation import require_aware, validate_record

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
LOOKBACK_DAYS = 90


def _text(element: ET.Element, path: str) -> str | None:
    found = element.find(path)
    return found.text.strip() if found is not None and found.text and found.text.strip() else None


def _parse_positive(value: str | None, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not isinstance(number, Real) or number <= 0 or number in {float("inf"), float("-inf")} or number != number:
        raise ValueError(f"Invalid {field}")
    return number


def parse_form4(xml_text: str, filing: Filing, ticker: str, fetched_at: datetime) -> list[RawRecord]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("Malformed Form 4 XML") from exc
    # SEC ownership XML is normally unnamespaced. Strip namespaces defensively.
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    symbol = (_text(root, "issuer/issuerTradingSymbol") or "").upper()
    if symbol and symbol != ticker:
        raise ValueError(f"Filing symbol {symbol} does not match {ticker}")
    filer_name = _text(root, "reportingOwner/reportingOwnerId/rptOwnerName") or ""
    records = []
    for index, transaction in enumerate(root.findall(".//nonDerivativeTransaction")):
        code = _text(transaction, "transactionCoding/transactionCode")
        if code != "P":
            continue
        raw_date = _text(transaction, "transactionDate/value")
        try:
            transaction_date = date.fromisoformat(raw_date or "")
        except ValueError as exc:
            raise ValueError("Invalid transaction date") from exc
        record = RawRecord(
            source="edgar",
            ticker=ticker,
            fetched_at=fetched_at,
            transaction_date=transaction_date,
            filed_at=filing.filed_at,
            data={
                "accession": filing.accession,
                "transaction_index": index,
                "filer_name": filer_name,
                "transaction_code": "P",
                "shares": _parse_positive(_text(transaction, "transactionAmounts/transactionShares/value"), "shares"),
                "price_per_share": _parse_positive(
                    _text(transaction, "transactionAmounts/transactionPricePerShare/value"),
                    "price_per_share", optional=True,
                ),
                "raw_xml": xml_text,
                "document_url": filing.document_url,
            },
        )
        validate_record(record, "raw_insider")
        records.append(record)
    return records


def _load_cik_map(http: SecHTTP) -> dict[str, int]:
    payload = http.get(TICKERS_URL).json()
    if not isinstance(payload, dict):
        raise ValueError("Malformed SEC ticker registry")
    result = {}
    for entry in payload.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("ticker"), str):
            raise ValueError("Malformed SEC ticker registry entry")
        try:
            result[entry["ticker"].upper()] = int(entry["cik_str"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Malformed SEC CIK") from exc
    return result


def fetch_insider(
    universe: list[str], *, user_agent: str, now: datetime | None = None,
    client: httpx.Client | None = None, sleep=None,
) -> tuple[list[RawRecord], FetchResult]:
    """Scan SEC filing availability through today; zero purchases is a valid result."""
    now = now or datetime.now(UTC)
    require_aware(now)
    now = now.astimezone(UTC)
    end = now.date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    universe = normalize_universe(universe)
    result = FetchResult("edgar", now)
    records: list[RawRecord] = []
    owned_client = client is None
    client = client or httpx.Client(timeout=15.0)
    http = SecHTTP(client, user_agent, **({"sleep": sleep} if sleep is not None else {}))
    try:
        try:
            cik_map = _load_cik_map(http)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            result.errors.append(f"SEC ticker registry failed: {type(exc).__name__}: {exc}")
            return [], result
        for ticker in universe:
            status = TickerFetchResult(ticker)
            result.tickers.append(status)
            cik = cik_map.get(ticker)
            if cik is None:
                status.errors.append("Ticker not found in SEC registry")
                continue
            try:
                filings = load_filings(http, cik, start, end)
                amendments = [f.accession for f in filings if f.form == "4/A"]
                if amendments:
                    raise ValueError(f"Form 4 amendments require review: {', '.join(amendments)}")
                ticker_records = []
                for filing in filings:
                    response = http.get(filing.document_url)
                    ticker_records.extend(parse_form4(response.text, filing, ticker, now))
                status.row_count = len(ticker_records)
                status.freshness_date = end
                records.extend(ticker_records)
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                status.errors.append(f"SEC filing scan failed: {type(exc).__name__}: {exc}")
        return records, result
    finally:
        if owned_client:
            client.close()
