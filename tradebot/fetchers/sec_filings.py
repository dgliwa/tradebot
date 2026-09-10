from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from tradebot.fetchers.sec_http import SecHTTP


@dataclass(frozen=True)
class Filing:
    accession: str
    filed_at: date
    document_url: str
    form: str


def _filings(payload: dict, cik: int, start: date, end: date) -> list[Filing]:
    keys = ("accessionNumber", "filingDate", "form", "primaryDocument")
    if not isinstance(payload, dict) or any(not isinstance(payload.get(k), list) for k in keys):
        raise ValueError("Malformed SEC submissions arrays")
    if len({len(payload[k]) for k in keys}) != 1:
        raise ValueError("Mismatched SEC submissions array lengths")
    filings = []
    for accession, day, form, document in zip(*(payload[k] for k in keys)):
        if form not in {"4", "4/A"}:
            continue
        filed_at = date.fromisoformat(day)
        if not start <= filed_at <= end:
            continue
        if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("Invalid SEC accession number")
        # Presentation paths return transformed HTML; fetch the underlying XML.
        match = re.fullmatch(r"(?:xsl[^/]+/)?([A-Za-z0-9_.-]+\.xml)", document or "", flags=re.IGNORECASE)
        if not match:
            raise ValueError(f"Unsupported filing document: {document!r}")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{match[1]}"
        filings.append(Filing(accession, filed_at, url, form))
    return filings


def load_filings(http: SecHTTP, cik: int, start: date, end: date) -> list[Filing]:
    payload = http.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    container = payload["filings"]
    filings = _filings(container["recent"], cik, start, end)
    archives = container.get("files", [])
    if not isinstance(archives, list):
        raise ValueError("Malformed SEC historical submissions list")
    for archive in archives:
        first, last = date.fromisoformat(archive["filingFrom"]), date.fromisoformat(archive["filingTo"])
        if first > last:
            raise ValueError("Invalid SEC archive date range")
        if last < start or first > end:
            continue
        name = archive["name"]
        if not re.fullmatch(rf"CIK{cik:010d}-submissions-\d+\.json", name):
            raise ValueError("Invalid SEC archive filename")
        history = http.get(f"https://data.sec.gov/submissions/{name}").json()
        filings.extend(_filings(history, cik, start, end))
    by_accession = {}
    for filing in filings:
        previous = by_accession.get(filing.accession)
        if previous is not None and previous != filing:
            raise ValueError(f"Conflicting metadata for {filing.accession}")
        by_accession[filing.accession] = filing
    return list(by_accession.values())
