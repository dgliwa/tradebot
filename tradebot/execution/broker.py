from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tradebot.config import Settings


@dataclass(frozen=True)
class BrokerOrder:
    id: str
    client_order_id: str
    status: str
    ticker: str
    side: str
    quantity: float
    filled_quantity: float
    filled_average_price: float | None


class PaperBroker(Protocol):
    is_paper: bool

    def submit_market_order(
        self, *, ticker: str, side: str, quantity: float, client_order_id: str,
    ) -> BrokerOrder: ...

    def get_order(self, client_order_id: str) -> BrokerOrder | None: ...


class AlpacaPaperBroker:
    is_paper = True

    def __init__(self, settings: Settings):
        if settings.mode != "paper" or settings.alpaca_base_url != "https://paper-api.alpaca.markets":
            raise ValueError("Alpaca adapter is locked to paper mode and the paper endpoint")
        if not settings.alpaca_key or not settings.alpaca_secret:
            raise ValueError("ALPACA_KEY and ALPACA_SECRET are required for paper execution")
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(settings.alpaca_key, settings.alpaca_secret, paper=True)

    @staticmethod
    def _order(order) -> BrokerOrder:
        return BrokerOrder(
            id=str(order.id), client_order_id=order.client_order_id,
            status=getattr(order.status, "value", str(order.status)), ticker=order.symbol,
            side=getattr(order.side, "value", str(order.side)), quantity=float(order.qty),
            filled_quantity=float(order.filled_qty or 0),
            filled_average_price=float(order.filled_avg_price) if order.filled_avg_price else None,
        )

    def submit_market_order(
        self, *, ticker: str, side: str, quantity: float, client_order_id: str,
    ) -> BrokerOrder:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        request = MarketOrderRequest(
            symbol=ticker, qty=quantity, side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY, client_order_id=client_order_id,
        )
        return self._order(self._client.submit_order(order_data=request))

    def get_order(self, client_order_id: str) -> BrokerOrder | None:
        try:
            return self._order(self._client.get_order_by_client_id(client_order_id))
        except Exception as exc:
            if "not found" in str(exc).lower() or "404" in str(exc):
                return None
            raise
