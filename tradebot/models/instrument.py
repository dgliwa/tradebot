from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional


@dataclass
class Instrument:
    """Represents a tradable instrument — stock or option contract.

    For stocks: expiry and strike are None.
    For options: expiry and strike are required.
    """
    id: str
    ticker: str
    instrument_type: Literal["stock", "call", "put"]
    expiry: Optional[date] = None
    strike: Optional[float] = None
