from datetime import UTC, date, datetime

import httpx
import pytest

from tradebot.fetchers.insider import fetch_insider, parse_form4
from tradebot.fetchers.sec_filings import Filing

NOW = datetime(2026, 7, 8, 12, tzinfo=UTC)
UA = "TradeBot test@example.com"
TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
ACCESSION = "0001140361-26-025622"
DOCUMENT = "xslF345X06/form4.xml"
XML_URL = "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"


def submissions(*, form="4", document=DOCUMENT, filing_date="2026-05-16", files=None):
    return {"filings": {"recent": {
        "accessionNumber": [ACCESSION], "filingDate": [filing_date],
        "form": [form], "primaryDocument": [document],
    }, "files": files or []}}


XML = """<ownershipDocument><issuer><issuerTradingSymbol>AAPL</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerName>Test Buyer</rptOwnerName></reportingOwnerId></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction>
<transactionDate><value>2026-05-15</value></transactionDate>
<transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>{shares}</value></transactionShares>
<transactionPricePerShare>{price}</transactionPricePerShare></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""


def client_for(routes, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        response = routes.get(str(request.url))
        if response is None:
            return httpx.Response(404, request=request)
        if callable(response):
            response = response(request)
        return response
    return httpx.Client(transport=httpx.MockTransport(handler))


def routes(submission=None, xml=None):
    return {
        "https://www.sec.gov/files/company_tickers.json": httpx.Response(200, json=TICKERS),
        "https://data.sec.gov/submissions/CIK0000320193.json": httpx.Response(200, json=submission or submissions()),
        XML_URL: httpx.Response(200, text=xml or XML.format(code="P", shares="1000", price="<value>175.50</value>")),
    }


def fetch(route_map, universe=None, seen=None):
    with client_for(route_map, seen) as client:
        return fetch_insider(universe or ["AAPL"], user_agent=UA, now=NOW, client=client, sleep=lambda _: None)


def test_primary_document_purchase_and_provenance():
    records, result = fetch(routes())
    assert result.is_valid and result.row_count == 1
    record = records[0]
    assert record.transaction_date == date(2026, 5, 15)
    assert record.filed_at == date(2026, 5, 16)
    assert record.data["filer_name"] == "Test Buyer"
    assert record.data["shares"] == 1000
    assert record.data["price_per_share"] == 175.5
    assert record.data["document_url"] == XML_URL
    assert record.data["raw_xml"].startswith("<ownershipDocument>")


def test_zero_purchases_is_valid_coverage():
    xml = XML.format(code="M", shares="1000", price="<value>0</value>")
    records, result = fetch(routes(xml=xml))
    assert records == []
    assert result.is_valid
    assert result.row_count == 0
    assert result.freshness_date == NOW.date()


def test_missing_price_remains_valid():
    records, result = fetch(routes(xml=XML.format(code="P", shares="500", price='<footnoteId id="F1"/>')))
    assert result.is_valid
    assert records[0].data["price_per_share"] is None


def test_user_agent_on_every_request():
    seen = []
    fetch(routes(), seen=seen)
    assert len(seen) == 3
    assert {request.headers["user-agent"] for request in seen} == {UA}


def test_unknown_ticker_is_not_successful_zero():
    records, result = fetch(routes(), universe=["NOPE"])
    assert records == [] and not result.is_valid
    assert "not found" in result.tickers[0].errors[0]


def test_malformed_xml_is_failure_not_empty_success():
    records, result = fetch(routes(xml="<broken>"))
    assert records == [] and not result.is_valid
    assert "Malformed Form 4 XML" in result.tickers[0].errors[0]


def test_invalid_purchase_fields_fail_filing():
    records, result = fetch(routes(xml=XML.format(code="P", shares="bad", price="<value>1</value>")))
    assert records == [] and not result.is_valid
    assert "Invalid shares" in result.tickers[0].errors[0]


def test_amendment_is_flagged_for_review_without_double_counting():
    route_map = routes(submission=submissions(form="4/A"))
    route_map.pop(XML_URL)
    records, result = fetch(route_map)
    assert records == [] and not result.is_valid
    assert "amendments require review" in result.tickers[0].errors[0]


def test_historical_submission_file_is_loaded():
    recent = submissions(filing_date="2025-01-01", files=[{
        "name": "CIK0000320193-submissions-001.json", "filingFrom": "2026-04-01", "filingTo": "2026-06-01"
    }])
    history_url = "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    route_map = routes(submission=recent)
    route_map[history_url] = httpx.Response(200, json=submissions()["filings"]["recent"])
    records, result = fetch(route_map)
    assert result.is_valid and len(records) == 1


def test_mismatched_submission_arrays_fail_ticker():
    malformed = submissions()
    malformed["filings"]["recent"]["primaryDocument"] = []
    records, result = fetch(routes(submission=malformed))
    assert records == [] and not result.is_valid
    assert "Mismatched" in result.tickers[0].errors[0]


def test_registry_failure_is_global_error():
    route_map = {"https://www.sec.gov/files/company_tickers.json": httpx.Response(503)}
    records, result = fetch(route_map)
    assert records == [] and not result.is_valid
    assert "ticker registry failed" in result.errors[0]


def test_namespaced_xml_supported():
    filing = Filing(ACCESSION, date(2026, 5, 16), XML_URL, "4")
    xml = XML.format(code="P", shares="1", price="<value>2</value>").replace(
        "<ownershipDocument>", '<ownershipDocument xmlns="urn:sec">')
    records = parse_form4(xml, filing, "AAPL", NOW)
    assert len(records) == 1


@pytest.mark.parametrize("user_agent", ["", "TradeBot", "bad\nheader@example.com"])
def test_contact_user_agent_required(user_agent):
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        fetch_insider(["AAPL"], user_agent=user_agent, now=NOW, sleep=lambda _: None)
