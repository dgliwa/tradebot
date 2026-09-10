from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class Trade:
    """Confirmed fill from Alpaca — recorded after polling confirms execution.

    fill_price is the actual fill price, never assumed or estimated.
    recorded_at is when TradeBot wrote the record; filled_at is when
    Alpaca reports the fill occurred.
    """
    id: str
    order_id: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: float
    fill_price: float
    filled_at: datetime
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
