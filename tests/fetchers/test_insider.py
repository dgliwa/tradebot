from __future__ import annotations
from datetime import date

import httpx
import pytest

from tradebot.fetchers.insider import fetch_insider


_XML_WITH_P = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Test Buyer</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>175.50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_XML_WITH_NON_P = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Option Exerciser</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-10</value></transactionDate>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>0.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_XML_NO_PRICE = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Footnote Buyer</rptOwnerName>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-20</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><footnoteId id="F1"/></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_TICKERS_JSON = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
}

_SUBMISSIONS_JSON = {
    "filings": {
        "recent": {
            "accessionNumber": ["0001140361-26-025622"],
            "filingDate": ["2026-05-16"],
            "form": ["4"],
        }
    }
}


def test_fetch_insider_returns_code_p(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_WITH_P))

    records, result = fetch_insider(["AAPL"])

    assert len(records) == 1
    assert records[0].ticker == "AAPL"
    assert records[0].source == "edgar"
    assert records[0].data["transaction_code"] == "P"
    assert records[0].data["shares"] == 1000.0
    assert records[0].data["price_per_share"] == 175.50
    assert records[0].data["filer_name"] == "Test Buyer"
    assert result.is_valid is True
    assert result.row_count == 1


def test_fetch_insider_filters_non_p(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_WITH_NON_P))

    records, result = fetch_insider(["AAPL"])

    assert records == []
    assert result.row_count == 0
    assert result.is_valid is False


def test_fetch_insider_user_agent_header(respx_mock):
    seen_headers: list[str] = []

    def capture_header(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("user-agent", ""))
        if "company_tickers" in str(request.url):
            return httpx.Response(200, json=_TICKERS_JSON)
        if "submissions" in str(request.url):
            return httpx.Response(200, json=_SUBMISSIONS_JSON)
        return httpx.Response(200, text=_XML_WITH_P)

    respx_mock.route(method="GET").mock(side_effect=capture_header)

    fetch_insider(["AAPL"])

    assert len(seen_headers) >= 3  # tickers.json + submissions + xml
    for ua in seen_headers:
        assert ua == "TradeBot/1.0 (dgliwa7bhs@gmail.com)", f"Bad User-Agent: {ua!r}"


def test_fetch_insider_filed_at_vs_transaction_date(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_WITH_P))

    records, _ = fetch_insider(["AAPL"])

    assert len(records) == 1
    rec = records[0]
    # filed_at is from submissions filingDate ("2026-05-16")
    assert rec.filed_at == date(2026, 5, 16)
    # transaction_date is from XML transactionDate/value ("2026-05-15")
    assert rec.transaction_date == date(2026, 5, 15)
    assert rec.filed_at != rec.transaction_date


def test_fetch_insider_null_price_per_share(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    respx_mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS_JSON)
    )
    respx_mock.get(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126025622/form4.xml"
    ).mock(return_value=httpx.Response(200, text=_XML_NO_PRICE))

    records, result = fetch_insider(["AAPL"])

    assert len(records) == 1
    assert records[0].data["price_per_share"] is None
    assert records[0].data["shares"] == 500.0
    assert result.is_valid is True


def test_fetch_insider_unknown_ticker(respx_mock):
    respx_mock.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=_TICKERS_JSON)
    )
    # No submissions or XML calls expected for an unknown ticker

    records, result = fetch_insider(["ZZZNOTREAL"])

    assert records == []
    assert result.is_valid is False
