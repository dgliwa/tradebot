from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

import pandas_market_calendars as mcal

from tradebot.models.validation import require_aware


@lru_cache(maxsize=1)
def _calendar():
    return mcal.get_calendar("NYSE")


def completed_sessions(now: datetime) -> list[date]:
    """Allow 20 minutes after the close for the free daily feed to settle."""
    require_aware(now)
    now = now.astimezone(UTC)
    schedule = _calendar().schedule(start_date=now.date() - timedelta(days=180), end_date=now.date())
    closed = schedule[schedule["market_close"] <= now - timedelta(minutes=20)]
    return [ts.date() for ts in closed.index]
