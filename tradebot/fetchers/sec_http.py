from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, httpx.RequestError) or (
        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {429, 500, 502, 503, 504}
    )


class SecHTTP:
    def __init__(self, client: httpx.Client, user_agent: str, sleep: Callable[[float], None] = time.sleep):
        if not user_agent.strip() or "@" not in user_agent or "\n" in user_agent or "\r" in user_agent:
            raise ValueError("SEC_USER_AGENT must identify your application and contact email")
        self.client = client
        self.user_agent = user_agent
        self.sleep = sleep

    def get(self, url: str) -> httpx.Response:
        for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
                                retry=retry_if_exception(_retryable), sleep=self.sleep, reraise=True):
            with attempt:
                self.sleep(0.12)
                response = self.client.get(url, headers={"User-Agent": self.user_agent})
                response.raise_for_status()
                return response
        raise RuntimeError("Retry loop exhausted")
