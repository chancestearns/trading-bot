"""In-memory paper trading broker implementation."""
from __future__ import annotations

from typing import Dict, Iterable

from bot.brokers.base import BaseBroker
from bot.models import Order, OrderSide, Position


class PaperBroker(BaseBroker):
    """Simple fill-on-touch broker suitable for tests and dry runs."""

    def __init__(self, starting_cash: float = 100_000.0) -> None:
        self._cash = starting_cash
        self._positions: Dict[str, Position] = {}
        self._last_prices: Dict[str, float] = {}
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    def get_balance(self) -> float:
        return self._cash

    def get_open_positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def submit_order(self, order: Order) -> Order:
        if not self._connected:
            raise RuntimeError("Broker is not connected. Call connect() first.")
        fill_price = order.price or self._last_prices.get(order.symbol)
        if fill_price is None:
            raise ValueError(f"No market price available for symbol {order.symbol!r}.")

        signed_qty = order.quantity if order.side == OrderSide.BUY else -order.quantity
        position = self._positions.get(order.symbol)
        if position is None:
            position = Position(symbol=order.symbol, quantity=0.0, avg_price=fill_price)
            self._positions[order.symbol] = position

        position.update(signed_qty, fill_price)
        if position.quantity == 0:
            self._positions.pop(order.symbol, None)

        self._cash -= signed_qty * fill_price
        return order

    def cancel_order(self, order_id: str) -> None:
        # The paper broker fills immediately, so cancel is a no-op.
        del order_id

    def sync_with_market_data(self, symbols: Iterable[str]) -> None:
        # The paper broker has no pre-processing requirements.
        del symbols

    def update_market_prices(self, prices: Dict[str, float]) -> None:
        self._last_prices.update(prices)
