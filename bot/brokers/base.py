"""Broker/execution interfaces."""
from __future__ import annotations

import abc
from typing import Dict, Iterable

from bot.models import Order, Position


class BaseBroker(abc.ABC):
    """Abstract interface implemented by execution providers."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish external connections (REST/WebSocket/etc.)."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down connections and release resources."""

    @abc.abstractmethod
    def get_balance(self) -> float:
        """Return current cash balance."""

    @abc.abstractmethod
    def get_open_positions(self) -> Dict[str, Position]:
        """Return a snapshot of open positions."""

    @abc.abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order and return the resulting order information."""

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> None:
        """Cancel an existing order."""

    @abc.abstractmethod
    def sync_with_market_data(self, symbols: Iterable[str]) -> None:
        """Optional hook allowing the broker to prepare for new data."""

    @abc.abstractmethod
    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """Provide the broker with the latest traded prices for fills."""
