"""Enhanced core data models with production-ready features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class OrderSide(str, Enum):
    """Enumeration of supported order sides."""

    BUY = "buy"
    SELL = "sell"
    BUY_TO_COVER = "buy_to_cover"
    SELL_SHORT = "sell_short"


class OrderType(str, Enum):
    """Enumeration of supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderDuration(str, Enum):
    """Order time-in-force duration."""

    DAY = "day"
    GTC = "gtc"  # Good-til-cancelled
    IOC = "ioc"  # Immediate-or-cancel
    FOK = "fok"  # Fill-or-kill


class OrderStrategyType(str, Enum):
    """Complex order strategy types."""

    SINGLE = "single"
    OCO = "oco"  # One-cancels-other
    BRACKET = "bracket"  # Entry + stop-loss + take-profit
    TRIGGER = "trigger"  # Conditional order


class OrderStatus(str, Enum):
    """Order lifecycle states."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


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

    def __post_init__(self):
        """Validate candle data integrity."""
        if self.high < max(self.open, self.close):
            raise ValueError(f"High {self.high} cannot be less than open/close")
        if self.low > min(self.open, self.close):
            raise ValueError(f"Low {self.low} cannot be greater than open/close")
        if self.volume < 0:
            raise ValueError(f"Volume {self.volume} cannot be negative")


@dataclass(slots=True)
class Tick:
    """Represents a real-time tick price update."""

    symbol: str
    timestamp: datetime
    price: float
    volume: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None

    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread if available."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None


@dataclass(slots=True)
class OrderFill:
    """Represents a single fill of an order (for partial fills)."""

    fill_id: str
    timestamp: datetime
    quantity: float
    price: float
    commission: float = 0.0
    fees: float = 0.0


@dataclass(slots=True)
class Order:
    """Represents an order with full lifecycle tracking."""

    id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    fills: List[OrderFill] = field(default_factory=list)
    broker_order_id: Optional[str] = None
    error_message: Optional[str] = None
    meta: Dict[str, any] = field(default_factory=dict)
    
    # Additional order attributes for production
    duration: OrderDuration = OrderDuration.DAY
    strategy_type: OrderStrategyType = OrderStrategyType.SINGLE
    parent_order_id: Optional[str] = None  # For bracket/OCO orders
    child_order_ids: List[str] = field(default_factory=list)  # For bracket/OCO orders
    trail_percent: Optional[float] = None  # For trailing stop orders
    trail_amount: Optional[float] = None  # For trailing stop orders

    @property
    def is_complete(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        }

    @property
    def remaining_quantity(self) -> float:
        """Calculate unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def average_fill_price(self) -> Optional[float]:
        """Calculate weighted average fill price."""
        if not self.fills:
            return None
        total_value = sum(fill.quantity * fill.price for fill in self.fills)
        total_quantity = sum(fill.quantity for fill in self.fills)
        return total_value / total_quantity if total_quantity > 0 else None

    def add_fill(self, fill: OrderFill) -> None:
        """Add a fill and update order state."""
        self.fills.append(fill)
        self.filled_quantity += fill.quantity

        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED


@dataclass(slots=True)
class Signal:
    """Represents a trading signal emitted by a strategy."""

    symbol: str
    action: SignalAction
    quantity: float
    confidence: float = 1.0
    meta: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Position:
    """Tracks the state of an open position."""

    symbol: str
    quantity: float
    avg_price: float

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-6

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L at current market price."""
        if self.is_flat:
            return 0.0
        return (current_price - self.avg_price) * self.quantity

    def unrealized_pnl_percent(self, current_price: float) -> float:
        """Calculate unrealized P&L as percentage."""
        if self.is_flat or self.avg_price == 0:
            return 0.0
        return ((current_price - self.avg_price) / self.avg_price) * 100

    def update(self, fill_quantity: float, fill_price: float) -> None:
        """Update the position using a new fill."""
        if self.quantity == 0:
            # Starting fresh
            self.quantity = fill_quantity
            self.avg_price = fill_price
            return

        new_quantity = self.quantity + fill_quantity

        if abs(new_quantity) < 1e-6:
            # Position closed
            self.quantity = 0.0
            self.avg_price = 0.0
        elif (self.quantity > 0 and fill_quantity > 0) or (self.quantity < 0 and fill_quantity < 0):
            # Adding to position (same direction)
            total_cost = (self.avg_price * abs(self.quantity)) + (
                fill_price * abs(fill_quantity)
            )
            self.avg_price = total_cost / abs(new_quantity)
            self.quantity = new_quantity
        elif (self.quantity > 0 and fill_quantity < 0) or (self.quantity < 0 and fill_quantity > 0):
            # Reducing or reversing position (opposite direction)
            if abs(fill_quantity) >= abs(self.quantity):
                # Position reversal - new position in opposite direction
                self.quantity = new_quantity
                self.avg_price = fill_price
            else:
                # Partial reduction - avg_price stays the same
                self.quantity = new_quantity
                # avg_price unchanged


@dataclass(slots=True)
class Trade:
    """Represents a completed trade (entry + exit)."""

    trade_id: str
    symbol: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: float
    exit_price: float
    quantity: float
    side: str
    pnl: float
    pnl_percent: float
    commission: float = 0.0
    meta: Dict[str, any] = field(default_factory=dict)


@dataclass(slots=True)
class Account:
    """Represents broker account information."""

    account_id: str
    cash: float
    buying_power: float
    equity: float
    margin_used: float = 0.0
    day_trades_remaining: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class PortfolioState:
    """Represents the portfolio as seen by the risk manager and strategies."""

    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    pending_orders: Dict[str, Order] = field(default_factory=dict)

    @property
    def net_exposure(self) -> float:
        """Aggregate absolute exposure across all open positions."""
        return sum(
            abs(position.quantity * position.avg_price)
            for position in self.positions.values()
        )

    @property
    def long_exposure(self) -> float:
        """Total long position value."""
        return sum(
            position.quantity * position.avg_price
            for position in self.positions.values()
            if position.is_long
        )

    @property
    def short_exposure(self) -> float:
        """Total short position value (absolute)."""
        return sum(
            abs(position.quantity * position.avg_price)
            for position in self.positions.values()
            if position.is_short
        )

    def total_unrealized_pnl(self, prices: Dict[str, float]) -> float:
        """Calculate total unrealized P&L across all positions."""
        total = 0.0
        for symbol, position in self.positions.items():
            if symbol in prices:
                total += position.unrealized_pnl(prices[symbol])
        return total

    def equity(self, prices: Dict[str, float]) -> float:
        """Calculate total equity (cash + position values)."""
        return self.cash + self.total_unrealized_pnl(prices)


@dataclass(slots=True)
class MarketState:
    """Container with market information provided to strategies."""

    candles: Dict[str, List[Candle]]
    ticks: Dict[str, Tick] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def latest_price(self, symbol: str) -> Optional[float]:
        """Return the last traded price for a symbol if available."""
        if symbol in self.ticks:
            return self.ticks[symbol].price
        series = self.candles.get(symbol)
        if series:
            return series[-1].close
        return None

    def get_latest_candle(self, symbol: str) -> Optional[Candle]:
        """Get most recent candle for a symbol."""
        series = self.candles.get(symbol)
        return series[-1] if series else None
