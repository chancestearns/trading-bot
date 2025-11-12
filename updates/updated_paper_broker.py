"""Enhanced paper trading broker with realistic simulation."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from bot.brokers.base import (
    BaseBroker,
    ConnectionError,
    InsufficientFundsError,
    OrderManager,
    OrderRejectedError,
)
from bot.models import (
    Account,
    Order,
    OrderFill,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)


class PaperBroker(BaseBroker):
    """Enhanced paper trading broker with realistic simulation."""

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        commission_per_share: float = 0.0,
        commission_percent: float = 0.0,
        slippage_percent: float = 0.0,
        simulate_partial_fills: bool = False,
    ) -> None:
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._commission_per_share = commission_per_share
        self._commission_percent = commission_percent
        self._slippage_percent = slippage_percent
        self._simulate_partial_fills = simulate_partial_fills

        self._positions: Dict[str, Position] = {}
        self._last_prices: Dict[str, float] = {}
        self._connected = False
        self._order_manager = OrderManager()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._account_id = f"paper_{uuid.uuid4().hex[:8]}"

    async def connect(self) -> None:
        """Establish connection (instant for paper broker)."""
        await asyncio.sleep(0.1)
        self._connected = True
        self._logger.info("Paper broker connected (account: %s)", self._account_id)

    async def close(self) -> None:
        """Close connection."""
        self._connected = False
        self._logger.info("Paper broker disconnected")

    async def get_account(self) -> Account:
        """Get account information."""
        if not self._connected:
            raise ConnectionError("Broker not connected")

        equity = self._cash
        for symbol, position in self._positions.items():
            if symbol in self._last_prices:
                equity += position.quantity * self._last_prices[symbol]

        return Account(
            account_id=self._account_id,
            cash=self._cash,
            buying_power=self._cash,
            equity=equity,
            margin_used=0.0,
            timestamp=datetime.utcnow(),
        )

    async def get_balance(self) -> float:
        """Return current cash balance."""
        return self._cash

    async def get_positions(self) -> Dict[str, Position]:
        """Return all open positions."""
        return {symbol: pos for symbol, pos in self._positions.items()
                if not pos.is_flat}

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        position = self._positions.get(symbol)
        return position if position and not position.is_flat else None

    async def submit_order(self, order: Order) -> Order:
        """Submit and immediately fill order (paper trading)."""
        if not self._connected:
            raise ConnectionError("Broker is not connected")

        order.broker_order_id = f"PAPER_{uuid.uuid4().hex[:12].upper()}"
        order.status = OrderStatus.SUBMITTED
        self._order_manager.add_order(order)

        fill_price = self._calculate_fill_price(order)
        if fill_price is None:
            order.status = OrderStatus.REJECTED
            order.error_message = f"No market price available for {order.symbol}"
            self._logger.warning("Order rejected: %s", order.error_message)
            raise OrderRejectedError(order.error_message, order)

        cost = self._calculate_order_cost(order, fill_price)
        if self._cash < cost:
            order.status = OrderStatus.REJECTED
            order.error_message = f"Insufficient funds: need ${cost:.2f}, have ${self._cash:.2f}"
            self._logger.warning("Order rejected: %s", order.error_message)
            raise InsufficientFundsError(order.error_message)

        order.status = OrderStatus.ACCEPTED

        await asyncio.sleep(0.05)

        if self._simulate_partial_fills and order.quantity > 100:
            await self._execute_partial_fills(order, fill_price)
        else:
            await self._execute_full_fill(order, fill_price)

        self._logger.info(
            "Order %s filled: %s %s %.2f @ %.2f",
            order.broker_order_id,
            order.side.value,
            order.symbol,
            order.quantity,
            fill_price,
        )

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order (instant in paper trading)."""
        order = self._order_manager.get_order(order_id)
        if not order:
            return False

        if order.is_complete:
            return False

        order.status = OrderStatus.CANCELLED
        self._order_manager.update_order(order)
        self._logger.info("Order %s cancelled", order_id)
        return True

    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current order status."""
        return self._order_manager.get_order(order_id)

    async def get_open_orders(self) -> List[Order]:
        """Get all open orders."""
        return self._order_manager.get_open_orders()

    async def reconcile_positions(self, symbols: Iterable[str]) -> Dict[str, Position]:
        """Reconcile positions (for paper trading, just return current state)."""
        return await self.get_positions()

    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """Update latest market prices."""
        self._last_prices.update(prices)

    def _calculate_fill_price(self, order: Order) -> Optional[float]:
        """Calculate fill price with slippage."""
        if order.order_type == OrderType.LIMIT and order.price:
            base_price = order.price
        else:
            base_price = self._last_prices.get(order.symbol)

        if base_price is None:
            return None

        slippage = base_price * self._slippage_percent
        if order.side in {OrderSide.BUY, OrderSide.BUY_TO_COVER}:
            return base_price + slippage
        else:
            return max(0.01, base_price - slippage)

    def _calculate_order_cost(self, order: Order, fill_price: float) -> float:
        """Calculate total cost including commissions."""
        notional = order.quantity * fill_price
        commission = (
            self._commission_per_share * order.quantity +
            notional * self._commission_percent
        )

        if order.side in {OrderSide.BUY, OrderSide.BUY_TO_COVER}:
            return notional + commission
        else:
            return commission

    async def _execute_full_fill(self, order: Order, fill_price: float) -> None:
        """Execute a complete fill of the order."""
        commission = (
            self._commission_per_share * order.quantity +
            fill_price * order.quantity * self._commission_percent
        )

        fill = OrderFill(
            fill_id=f"FILL_{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.utcnow(),
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
        )

        order.add_fill(fill)
        self._update_position(order, fill)
        self._order_manager.update_order(order)

    async def _execute_partial_fills(self, order: Order, fill_price: float) -> None:
        """Simulate partial fills (multiple executions)."""
        remaining = order.quantity
        num_fills = min(3, int(order.quantity / 50) + 1)

        for i in range(num_fills):
            fill_qty = remaining / (num_fills - i)

            price_variation = fill_price * 0.0005 * (i - num_fills / 2)
            actual_price = fill_price + price_variation

            commission = (
                self._commission_per_share * fill_qty +
                actual_price * fill_qty * self._commission_percent
            )

            fill = OrderFill(
                fill_id=f"FILL_{uuid.uuid4().hex[:8].upper()}",
                timestamp=datetime.utcnow(),
                quantity=fill_qty,
                price=actual_price,
                commission=commission,
            )

            order.add_fill(fill)
            self._update_position(order, fill)
            remaining -= fill_qty

            await asyncio.sleep(0.02)

        self._order_manager.update_order(order)

    def _update_position(self, order: Order, fill: OrderFill) -> None:
        """Update position and cash based on fill."""
        symbol = order.symbol
        signed_qty = fill.quantity if order.side in {OrderSide.BUY, OrderSide.BUY_TO_COVER} else -fill.quantity

        position = self._positions.get(symbol)
        if position is None:
            position = Position(symbol=symbol, quantity=0.0, avg_price=fill.price)
            self._positions[symbol] = position

        position.update(signed_qty, fill.price)

        cost = signed_qty * fill.price + fill.commission
        self._cash -= cost

        if position.is_flat:
            self._positions.pop(symbol, None)

    async def liquidate_all_positions(self) -> List[Order]:
        """Emergency liquidation of all positions."""
        orders = []
        for symbol, position in list(self._positions.items()):
            if position.is_flat:
                continue

            side = OrderSide.SELL if position.is_long else OrderSide.BUY_TO_COVER
            order = Order(
                id=str(uuid.uuid4()),
                symbol=symbol,
                side=side,
                quantity=abs(position.quantity),
                order_type=OrderType.MARKET,
            )

            try:
                filled_order = await self.submit_order(order)
                orders.append(filled_order)
            except Exception as e:
                self._logger.error("Failed to liquidate %s: %s", symbol, e)

        return orders

    def get_trade_history(self) -> List[Order]:
        """Get all filled orders."""
        return [order for order in self._order_manager._orders.values()
                if order.status == OrderStatus.FILLED]
