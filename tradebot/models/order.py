from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Optional


@dataclass
class Order:
    """Represents intent to trade — recorded before submission to Alpaca.

    Separates order intent (this dataclass / orders table) from confirmed
    fills (Trade dataclass / trades table). Never mutate an Order after
    submission; create a Trade when the fill is confirmed.
    """
    id: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: float
    instrument_id: Optional[str] = None
    order_type: Literal["market", "limit"] = "market"
    status: str = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
