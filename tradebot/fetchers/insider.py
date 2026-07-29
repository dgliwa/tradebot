from __future__ import annotations
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from tradebot.models.raw_record import FetchResult, RawRecord


_USER_AGENT = "TradeBot/1.0 (dgliwa7bhs@gmail.com)"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik_padded}.json"
_FORM4_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/form4.xml"
_RATE_SLEEP = 0.12  # seconds between requests to stay under 10 req/s SEC limit
_LOOKBACK_DAYS = 90


def _make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": _USER_AGENT},
        timeout=15.0,
    )


def _is_retryable(exc: BaseException) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in (429, 500, 503)
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable),
)
def _get(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.get(url)
    resp.raise_for_status()
    return resp


def _load_cik_map(client: httpx.Client) -> dict[str, int]:
    resp = _get(client, _TICKERS_URL)
    payload = resp.json()
    return {
        entry["ticker"].upper(): int(entry["cik_str"])
        for entry in payload.values()
    }


def _parse_form4_xml(
    xml_text: str,
    accession: str,
    filed_at: date,
    ticker: str,
    fetched_at: datetime,
) -> list[RawRecord]:
    """Parse Form 4 XML and return code-P (open-market purchase) RawRecords only."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    filer_name = root.findtext(
        "reportingOwner/reportingOwnerId/rptOwnerName", ""
    ) or ""

    records: list[RawRecord] = []
    for i, txn in enumerate(root.findall(".//nonDerivativeTransaction")):
        code = txn.findtext("transactionCoding/transactionCode") or ""
        if code != "P":
            continue

        txn_date_str = txn.findtext("transactionDate/value")
        shares_str = txn.findtext("transactionAmounts/transactionShares/value")
        price_str = txn.findtext(
            "transactionAmounts/transactionPricePerShare/value"
        )

        txn_date: Optional[date] = None
        if txn_date_str:
            try:
                txn_date = date.fromisoformat(txn_date_str)
            except ValueError:
                pass

        shares: Optional[float] = None
        if shares_str:
            try:
                shares = float(shares_str)
            except ValueError:
                pass

        price: Optional[float] = None
        if price_str:
            try:
                price = float(price_str)
            except ValueError:
                pass

        records.append(
            RawRecord(
                source="edgar",
                ticker=ticker,
                fetched_at=fetched_at,
                transaction_date=txn_date,
                filed_at=filed_at,
                data={
                    "accession": accession,
                    "transaction_index": i,
                    "filer_name": filer_name,
                    "transaction_code": code,
                    "shares": shares,
                    "price_per_share": price,
                },
            )
        )
    return records


def fetch_insider(universe: list[str]) -> tuple[list[RawRecord], FetchResult]:
    """Fetch EDGAR Form 4 open-market purchase (code-P) filings for all tickers.

    Three-step HTTP: company_tickers.json -> submissions/{CIK}.json -> form4.xml.
    All HTTP via httpx.Client with shared User-Agent header — fully mockable by respx.
    Returns only code-P transactions; others are filtered at parse time.
    """
    fetched_at = datetime.utcnow()
    end_date = date.today()
    start_date = end_date - timedelta(days=_LOOKBACK_DAYS)

    records: list[RawRecord] = []
    freshness_date: Optional[date] = None

    with _make_client() as client:
        # Step 1: load CIK map once
        cik_map = _load_cik_map(client)
        time.sleep(_RATE_SLEEP)

        for ticker in universe:
            cik_int = cik_map.get(ticker.upper())
            if cik_int is None:
                continue  # ticker not found in SEC registry

            cik_padded = str(cik_int).zfill(10)

            # Step 2: fetch submissions list for this ticker
            subs_url = _SUBMISSIONS_URL.format(cik_padded=cik_padded)
            try:
                subs_resp = _get(client, subs_url)
            except Exception:
                time.sleep(_RATE_SLEEP)
                continue
            time.sleep(_RATE_SLEEP)

            recent = subs_resp.json().get("filings", {}).get("recent", {})
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            forms = recent.get("form", [])

            # Filter to Form 4 filings within the 90-day window
            form4_accessions: list[tuple[str, date]] = []
            for acc, filed_str, form in zip(accession_numbers, filing_dates, forms):
                if form != "4":
                    continue
                try:
                    filed = date.fromisoformat(filed_str)
                except ValueError:
                    continue
                if filed < start_date:
                    continue
                form4_accessions.append((acc, filed))

            # Step 3: fetch and parse each Form 4 XML
            for accession, filed_at in form4_accessions:
                accession_nodash = accession.replace("-", "")
                xml_url = _FORM4_URL.format(
                    cik_int=cik_int,
                    accession_nodash=accession_nodash,
                )
                try:
                    xml_resp = _get(client, xml_url)
                except Exception:
                    time.sleep(_RATE_SLEEP)
                    continue
                time.sleep(_RATE_SLEEP)

                new_records = _parse_form4_xml(
                    xml_resp.text, accession, filed_at, ticker, fetched_at
                )
                records.extend(new_records)

                for rec in new_records:
                    if rec.transaction_date is not None:
                        if freshness_date is None or rec.transaction_date > freshness_date:
                            freshness_date = rec.transaction_date

    return records, FetchResult(
        source="edgar",
        ticker="universe",
        row_count=len(records),
        freshness_date=freshness_date,
    )
