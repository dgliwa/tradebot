"""TradeBot cross-layer dataclasses.

Public exports mirror the pipeline stages:
  Instrument — what is traded
  RawRecord / FetchResult — ingestion layer outputs
  Recommendation — signal layer output
  Order / Trade — execution layer I/O
"""
from tradebot.models.instrument import Instrument
from tradebot.models.raw_record import FetchResult, RawRecord
from tradebot.models.signal import Recommendation
from tradebot.models.order import Order
from tradebot.models.trade import Trade

__all__ = [
    "Instrument",
    "RawRecord",
    "FetchResult",
    "Recommendation",
    "Order",
    "Trade",
]
