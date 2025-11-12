"""Core data models used across the trading bot."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class OrderSide(str, Enum):
    """Enumeration of supported order sides."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Enumeration of supported order types."""

    MARKET = "market"
    LIMIT = "limit"


class SignalAction(str, Enum):
    """Actions that a trading signal can represent."""

    OPEN_LONG = "open_long"
    CLOSE_LONG = "close_long"
    OPEN_SHORT = "open_short"
    CLOSE_SHORT = "close_short"


@dataclass(slots=True)
class Candle:
    """Represents OHLCV data for a fixed interval."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Tick:
    """Represents a real-time tick price update."""

    symbol: str
    timestamp: datetime
    price: float
    volume: float = 0.0


@dataclass(slots=True)
class Order:
    """Represents an order that can be submitted to a broker."""

    id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Signal:
    """Represents a trading signal emitted by a strategy."""

    symbol: str
    action: SignalAction
    quantity: float
    meta: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Position:
    """Tracks the state of an open position."""

    symbol: str
    quantity: float
    avg_price: float

    def update(self, fill_quantity: float, fill_price: float) -> None:
        """Update the position using a new fill."""

        if self.quantity + fill_quantity == 0:
            self.quantity = 0.0
            self.avg_price = 0.0
            return
        new_total = self.quantity + fill_quantity
        self.avg_price = (
            (self.avg_price * self.quantity) + (fill_price * fill_quantity)
        ) / new_total
        self.quantity = new_total


@dataclass(slots=True)
class PortfolioState:
    """Represents the portfolio as seen by the risk manager and strategies."""

    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)

    @property
    def net_exposure(self) -> float:
        """Aggregate absolute exposure across all open positions."""

        return sum(abs(position.quantity) for position in self.positions.values())


@dataclass(slots=True)
class MarketState:
    """Container with market information provided to strategies."""

    candles: Dict[str, List[Candle]]
    ticks: Dict[str, Tick] = field(default_factory=dict)

    def latest_price(self, symbol: str) -> Optional[float]:
        """Return the last traded price for a symbol if available."""

        if symbol in self.ticks:
            return self.ticks[symbol].price
        series = self.candles.get(symbol)
        if series:
            return series[-1].close
        return None
