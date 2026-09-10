import httpx
import pytest

from tradebot.fetchers.sec_http import SecHTTP


def test_retries_transient_status_with_rate_delay_each_attempt():
    attempts = 0
    sleeps = []

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts < 3 else 200, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = SecHTTP(client, "TradeBot test@example.com", sleep=sleeps.append).get("https://www.sec.gov/test")
    assert response.status_code == 200
    assert attempts == 3
    assert sleeps == [0.12, 1.0, 0.12, 2.0, 0.12]


def test_does_not_retry_permanent_status():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            SecHTTP(client, "TradeBot test@example.com", sleep=lambda _: None).get("https://www.sec.gov/test")
    assert attempts == 1
