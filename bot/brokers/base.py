"""Enhanced async broker interfaces for production use."""

from __future__ import annotations

import abc
from typing import Dict, Iterable, List, Optional

from bot.models import Account, Order, Position


class BrokerError(Exception):
    """Base exception for broker-related errors."""

    pass


class ConnectionError(BrokerError):
    """Raised when broker connection fails."""

    pass


class OrderRejectedError(BrokerError):
    """Raised when an order is rejected by the broker."""

    def __init__(self, message: str, order: Order):
        super().__init__(message)
        self.order = order


class InsufficientFundsError(BrokerError):
    """Raised when insufficient buying power for order."""

    pass


class RateLimitError(BrokerError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class BaseBroker(abc.ABC):
    """Abstract interface implemented by execution providers."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish external connections (REST/WebSocket/etc.)."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down connections and release resources."""

    @abc.abstractmethod
    async def get_account(self) -> Account:
        """Retrieve current account information."""

    @abc.abstractmethod
    async def get_balance(self) -> float:
        """Return current cash balance."""

    @abc.abstractmethod
    async def get_positions(self) -> Dict[str, Position]:
        """Return a snapshot of all open positions."""

    @abc.abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""

    @abc.abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """Submit an order and return updated order with broker ID."""

    @abc.abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""

    @abc.abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Query current status of an order."""

    @abc.abstractmethod
    async def get_open_orders(self) -> List[Order]:
        """Get all open (not filled/cancelled) orders."""

    @abc.abstractmethod
    async def reconcile_positions(self, symbols: Iterable[str]) -> Dict[str, Position]:
        """Sync local position state with broker state."""

    @abc.abstractmethod
    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """Provide the broker with latest prices for position valuation."""

    async def health_check(self) -> bool:
        """Check if broker connection is healthy."""
        try:
            await self.get_account()
            return True
        except Exception:
            return False

    async def modify_order(
        self, order_id: str, new_quantity: Optional[float] = None, new_price: Optional[float] = None
    ) -> bool:
        """Modify an existing order (default: not supported)."""
        return False

    async def get_buying_power(self) -> float:
        """Get available buying power."""
        account = await self.get_account()
        return account.buying_power

    async def get_day_trades_remaining(self) -> Optional[int]:
        """Get remaining day trades (for PDT compliance)."""
        account = await self.get_account()
        return account.day_trades_remaining


class OrderManager:
    """Helper class for tracking order lifecycle."""

    def __init__(self):
        self._orders: Dict[str, Order] = {}
        self._broker_id_map: Dict[str, str] = {}

    def add_order(self, order: Order) -> None:
        """Register a new order."""
        self._orders[order.id] = order
        if order.broker_order_id:
            self._broker_id_map[order.broker_order_id] = order.id

    def update_order(self, order: Order) -> None:
        """Update existing order state."""
        if order.id in self._orders:
            self._orders[order.id] = order
            if order.broker_order_id:
                self._broker_id_map[order.broker_order_id] = order.id

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by internal ID or broker ID."""
        if order_id in self._orders:
            return self._orders[order_id]
        internal_id = self._broker_id_map.get(order_id)
        return self._orders.get(internal_id) if internal_id else None

    def get_open_orders(self) -> List[Order]:
        """Get all non-terminal orders."""
        return [order for order in self._orders.values() if not order.is_complete]

    def get_pending_orders_for_symbol(self, symbol: str) -> List[Order]:
        """Get all pending orders for a specific symbol."""
        return [
            order
            for order in self._orders.values()
            if order.symbol == symbol and not order.is_complete
        ]

    def remove_order(self, order_id: str) -> None:
        """Remove an order from tracking."""
        order = self.get_order(order_id)
        if order:
            self._orders.pop(order.id, None)
            if order.broker_order_id:
                self._broker_id_map.pop(order.broker_order_id, None)
