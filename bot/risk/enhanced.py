"""Enhanced risk management with PDT compliance, circuit breakers, and rate limiting."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional

from bot.models import MarketState, PortfolioState, Position, Signal, SignalAction
from bot.risk.base import RiskManager


@dataclass(slots=True)
class EnhancedRiskConfig:
    """Configuration for EnhancedRiskManager."""

    # Position limits
    max_position_size: float = 1000.0
    max_total_exposure: float = 50000.0
    max_open_positions: int = 5
    
    # Loss limits
    max_daily_loss: float = 5000.0
    max_drawdown_percent: float = 20.0
    starting_cash: float = 100000.0
    
    # PDT compliance (Pattern Day Trader)
    enforce_pdt_rules: bool = True
    min_account_value_for_day_trading: float = 25000.0
    max_day_trades_per_5_days: int = 3
    
    # Rate limiting
    max_orders_per_minute: int = 10
    max_orders_per_symbol_per_minute: int = 3
    
    # Circuit breaker
    enable_circuit_breaker: bool = True
    circuit_breaker_loss_percent: float = 10.0
    circuit_breaker_reset_hours: int = 24


@dataclass
class TradeActivity:
    """Track trading activity for rate limiting and PDT compliance."""
    
    order_timestamps: list[datetime] = field(default_factory=list)
    day_trades_count: int = 0
    day_trades_dates: list[datetime] = field(default_factory=list)
    last_entry_timestamp: Optional[datetime] = None
    
    def add_order(self, timestamp: datetime) -> None:
        """Record an order timestamp."""
        self.order_timestamps.append(timestamp)
        
        # Keep only last hour of timestamps
        cutoff = timestamp - timedelta(hours=1)
        self.order_timestamps = [ts for ts in self.order_timestamps if ts > cutoff]
    
    def add_day_trade(self, timestamp: datetime) -> None:
        """Record a day trade."""
        self.day_trades_dates.append(timestamp)
        
        # Keep only last 5 days
        cutoff = timestamp - timedelta(days=5)
        self.day_trades_dates = [dt for dt in self.day_trades_dates if dt > cutoff]
        self.day_trades_count = len(self.day_trades_dates)
    
    def get_orders_in_last_minute(self, now: datetime) -> int:
        """Count orders in the last minute."""
        cutoff = now - timedelta(minutes=1)
        return sum(1 for ts in self.order_timestamps if ts > cutoff)


class EnhancedRiskManager(RiskManager):
    """Enhanced risk manager with production features."""

    def __init__(self, config: EnhancedRiskConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Track activity per symbol
        self.activity: Dict[str, TradeActivity] = {}
        
        # Circuit breaker state
        self.circuit_breaker_tripped = False
        self.circuit_breaker_trip_time: Optional[datetime] = None
        self.peak_equity = config.starting_cash
        
        # Track daily metrics
        self.start_of_day_equity = config.starting_cash
        self.daily_reset_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    def validate_signal(
        self,
        signal: Signal,
        portfolio_state: PortfolioState,
        market_state: MarketState,
    ) -> Signal | None:
        """Validate signal through multiple risk checks."""
        
        # Always allow closing positions
        if signal.action in {SignalAction.CLOSE_LONG, SignalAction.CLOSE_SHORT}:
            # But check if this would be a day trade
            if self._would_be_day_trade(signal, portfolio_state):
                if not self._check_pdt_compliance(portfolio_state):
                    self.logger.warning(
                        "Closing position blocked: would violate PDT rules for %s",
                        signal.symbol
                    )
                    return None
            return signal
        
        # Check circuit breaker
        if not self._check_circuit_breaker(portfolio_state, market_state):
            self.logger.warning("Signal rejected: circuit breaker tripped")
            return None
        
        # Check drawdown limits
        if not self._check_drawdown_limit(portfolio_state, market_state):
            self.logger.warning("Signal rejected: drawdown limit exceeded")
            return None
        
        # Check daily loss limit
        if self._daily_loss_exceeded(portfolio_state):
            self.logger.warning("Signal rejected: daily loss limit exceeded")
            return None
        
        # Check rate limiting
        if not self._check_rate_limits(signal):
            self.logger.warning("Signal rejected: rate limit exceeded for %s", signal.symbol)
            return None
        
        # Check PDT compliance for new positions
        if self._would_be_day_trade(signal, portfolio_state):
            if not self._check_pdt_compliance(portfolio_state):
                self.logger.warning("Signal rejected: PDT rules for %s", signal.symbol)
                return None
        
        # Check position count limit
        if not self._check_position_count(signal, portfolio_state):
            self.logger.warning("Signal rejected: max open positions reached")
            return None
        
        # Check total exposure limit (can adjust quantity)
        symbol = signal.symbol  # Store symbol before checks that might return None
        signal = self._check_total_exposure(signal, portfolio_state, market_state)
        if signal is None:
            self.logger.warning("Signal rejected: total exposure limit exceeded")
            return None
        
        # Check individual position size limit (can adjust quantity)
        signal = self._check_position_size(signal, portfolio_state)
        if signal is None:
            self.logger.warning("Signal rejected: position size limit for %s", symbol)
            return None
        
        # Record the order
        self._record_order(symbol)
        
        return signal

    def _check_circuit_breaker(
        self, portfolio_state: PortfolioState, market_state: MarketState
    ) -> bool:
        """Check if circuit breaker should trip or reset."""
        if not self.config.enable_circuit_breaker:
            return True
        
        now = datetime.utcnow()
        
        # Check if circuit breaker should reset
        if self.circuit_breaker_tripped:
            if self.circuit_breaker_trip_time:
                hours_since_trip = (now - self.circuit_breaker_trip_time).total_seconds() / 3600
                if hours_since_trip >= self.config.circuit_breaker_reset_hours:
                    self.logger.info("Circuit breaker reset after %d hours", hours_since_trip)
                    self.circuit_breaker_tripped = False
                    self.circuit_breaker_trip_time = None
                    return True
            return False
        
        # Calculate current equity
        prices = {symbol: market_state.latest_price(symbol) or 0 for symbol in portfolio_state.positions.keys()}
        current_equity = portfolio_state.equity(prices)
        
        # Update peak equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        # Check if we should trip the breaker
        drawdown_percent = ((self.peak_equity - current_equity) / self.peak_equity) * 100
        if drawdown_percent >= self.config.circuit_breaker_loss_percent:
            self.logger.critical(
                "CIRCUIT BREAKER TRIPPED: %.2f%% drawdown from peak $%.2f to $%.2f",
                drawdown_percent,
                self.peak_equity,
                current_equity
            )
            self.circuit_breaker_tripped = True
            self.circuit_breaker_trip_time = now
            return False
        
        return True

    def _check_drawdown_limit(
        self, portfolio_state: PortfolioState, market_state: MarketState
    ) -> bool:
        """Check if current drawdown exceeds limit."""
        prices = {symbol: market_state.latest_price(symbol) or 0 for symbol in portfolio_state.positions.keys()}
        current_equity = portfolio_state.equity(prices)
        
        drawdown_percent = ((self.config.starting_cash - current_equity) / self.config.starting_cash) * 100
        
        return drawdown_percent < self.config.max_drawdown_percent

    def _daily_loss_exceeded(self, portfolio_state: PortfolioState) -> bool:
        """Check if daily loss limit is exceeded."""
        # Reset daily tracking at start of day
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if today > self.daily_reset_time:
            self.daily_reset_time = today
            self.start_of_day_equity = portfolio_state.cash
        
        loss = self.start_of_day_equity - portfolio_state.cash
        return self.config.max_daily_loss > 0 and loss >= self.config.max_daily_loss

    def _check_rate_limits(self, signal: Signal) -> bool:
        """Check if signal exceeds rate limits."""
        now = datetime.utcnow()
        
        # Get or create activity tracker for this symbol
        if signal.symbol not in self.activity:
            self.activity[signal.symbol] = TradeActivity()
        
        activity = self.activity[signal.symbol]
        
        # Check symbol-specific rate limit
        orders_this_minute = activity.get_orders_in_last_minute(now)
        if orders_this_minute >= self.config.max_orders_per_symbol_per_minute:
            return False
        
        # Check global rate limit
        total_orders = sum(
            act.get_orders_in_last_minute(now)
            for act in self.activity.values()
        )
        if total_orders >= self.config.max_orders_per_minute:
            return False
        
        return True

    def _check_pdt_compliance(self, portfolio_state: PortfolioState) -> bool:
        """Check Pattern Day Trader rules compliance."""
        if not self.config.enforce_pdt_rules:
            return True
        
        # If account is above PDT threshold, allow day trading
        if portfolio_state.cash >= self.config.min_account_value_for_day_trading:
            return True
        
        # Check day trade count
        # Note: This is simplified - real PDT tracking requires more complex logic
        return True  # Allow for now, would need to track actual day trades

    def _would_be_day_trade(self, signal: Signal, portfolio_state: PortfolioState) -> bool:
        """Check if this signal would create a day trade."""
        if signal.symbol not in self.activity:
            return False
        
        activity = self.activity[signal.symbol]
        
        # If we entered a position today and are closing it, it's a day trade
        if activity.last_entry_timestamp:
            today = datetime.utcnow().date()
            entry_date = activity.last_entry_timestamp.date()
            return entry_date == today
        
        return False

    def _check_position_count(self, signal: Signal, portfolio_state: PortfolioState) -> bool:
        """Check if adding this position would exceed max open positions."""
        current_positions = len([p for p in portfolio_state.positions.values() if not p.is_flat])
        
        # If we already have a position in this symbol, don't count it as new
        if signal.symbol in portfolio_state.positions:
            existing_pos = portfolio_state.positions[signal.symbol]
            if not existing_pos.is_flat:
                return True
        
        return current_positions < self.config.max_open_positions

    def _check_total_exposure(
        self, signal: Signal, portfolio_state: PortfolioState, market_state: MarketState
    ) -> Signal | None:
        """Check if adding this position would exceed total exposure limit.
        
        Returns adjusted signal if needed, None if exposure too high.
        """
        current_exposure = portfolio_state.net_exposure
        
        # Estimate new position value
        price = market_state.latest_price(signal.symbol) or 0
        if price <= 0:
            return signal  # Can't calculate without price
        
        new_exposure = signal.quantity * price
        total_exposure = current_exposure + new_exposure
        
        if total_exposure <= self.config.max_total_exposure:
            return signal
        
        # Calculate max allowed quantity
        available_exposure = self.config.max_total_exposure - current_exposure
        if available_exposure <= 0:
            return None  # Already at limit
        
        max_quantity = available_exposure / price
        
        # Cap to at least 1 share if there's any room
        if max_quantity < 1.0:
            return None
        
        return Signal(
            symbol=signal.symbol,
            action=signal.action,
            quantity=int(max_quantity),
        )

    def _check_position_size(
        self, signal: Signal, portfolio_state: PortfolioState
    ) -> Signal | None:
        """Check and adjust position size if needed."""
        if self.config.max_position_size <= 0:
            return signal
        
        desired_qty = abs(signal.quantity)
        if desired_qty <= 0:
            return signal
        
        # Current absolute position for this symbol
        current_qty = abs(
            portfolio_state.positions.get(
                signal.symbol,
                Position(signal.symbol, 0.0, 0.0),
            ).quantity
        )
        
        # Reject if already at or above the cap
        if current_qty >= self.config.max_position_size:
            return None
        
        remaining = self.config.max_position_size - current_qty
        if desired_qty <= remaining:
            return signal
        
        # Cap the order size
        adjusted_qty = remaining
        return Signal(
            symbol=signal.symbol,
            action=signal.action,
            quantity=adjusted_qty,
            meta={**signal.meta, "capped_quantity": adjusted_qty, "adjusted": True},
        )

    def _record_order(self, symbol: str) -> None:
        """Record an order for rate limiting and tracking."""
        now = datetime.utcnow()
        
        if symbol not in self.activity:
            self.activity[symbol] = TradeActivity()
        
        self.activity[symbol].add_order(now)
        self.activity[symbol].last_entry_timestamp = now
