"""Tests for enhanced risk management."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from bot.models import MarketState, PortfolioState, Position, Signal, SignalAction, Candle
from bot.risk.enhanced import EnhancedRiskConfig, EnhancedRiskManager, TradeActivity


class TestTradeActivity:
    """Test trade activity tracking."""

    def test_add_order(self):
        """Test adding order timestamps."""
        activity = TradeActivity()
        now = datetime.utcnow()
        
        activity.add_order(now)
        assert len(activity.order_timestamps) == 1

    def test_get_orders_in_last_minute(self):
        """Test counting orders in last minute."""
        activity = TradeActivity()
        now = datetime.utcnow()
        
        # Add orders over time
        activity.add_order(now - timedelta(seconds=90))  # > 1 min ago
        activity.add_order(now - timedelta(seconds=30))  # < 1 min ago
        activity.add_order(now)  # now
        
        count = activity.get_orders_in_last_minute(now)
        assert count == 2  # Only the last two

    def test_add_day_trade(self):
        """Test recording day trades."""
        activity = TradeActivity()
        now = datetime.utcnow()
        
        activity.add_day_trade(now)
        activity.add_day_trade(now)
        
        assert activity.day_trades_count == 2


class TestEnhancedRiskManager:
    """Test enhanced risk manager."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return EnhancedRiskConfig(
            max_position_size=100.0,
            max_total_exposure=50000.0,  # High enough to not interfere with position size tests
            max_open_positions=3,
            max_daily_loss=1000.0,
            starting_cash=10000.0,
            enforce_pdt_rules=False,
            enable_circuit_breaker=True,
            circuit_breaker_loss_percent=10.0,
        )

    @pytest.fixture
    def risk_manager(self, config):
        """Create a risk manager."""
        return EnhancedRiskManager(config)

    @pytest.fixture
    def portfolio_state(self):
        """Create a test portfolio state."""
        return PortfolioState(cash=10000.0, positions={}, pending_orders={})

    @pytest.fixture
    def market_state(self):
        """Create a test market state."""
        now = datetime.utcnow()
        return MarketState(
            candles={
                "AAPL": [Candle("AAPL", now, 150.0, 151.0, 149.0, 150.5, 1000000)],
                "MSFT": [Candle("MSFT", now, 300.0, 301.0, 299.0, 300.5, 500000)],
            }
        )

    def test_always_allow_close_positions(self, risk_manager, portfolio_state, market_state):
        """Test that closing positions is always allowed."""
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.CLOSE_LONG,
            quantity=10,
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        assert result is not None
        assert result.symbol == "AAPL"

    def test_position_size_limit(self, risk_manager, portfolio_state, market_state):
        """Test position size limit enforcement."""
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.OPEN_LONG,
            quantity=150,  # Exceeds max of 100
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        
        # Should be capped to 100
        assert result is not None
        assert result.quantity == 100

    def test_reject_at_position_limit(self, risk_manager, portfolio_state, market_state):
        """Test rejection when already at position limit."""
        # Add existing position at limit
        portfolio_state.positions["AAPL"] = Position("AAPL", 100, 150.0)
        
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.OPEN_LONG,
            quantity=10,
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        assert result is None  # Should be rejected

    def test_max_open_positions_limit(self, risk_manager, portfolio_state, market_state):
        """Test max open positions limit."""
        # Add 3 positions (at limit)
        portfolio_state.positions["AAPL"] = Position("AAPL", 10, 150.0)
        portfolio_state.positions["MSFT"] = Position("MSFT", 10, 300.0)
        portfolio_state.positions["GOOGL"] = Position("GOOGL", 10, 100.0)
        
        # Try to open a 4th position
        signal = Signal(
            symbol="TSLA",
            action=SignalAction.OPEN_LONG,
            quantity=10,
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        assert result is None  # Should be rejected

    def test_daily_loss_limit(self, risk_manager, portfolio_state, market_state):
        """Test daily loss limit enforcement."""
        # Simulate loss
        portfolio_state.cash = 8500.0  # Lost $1500, exceeds $1000 limit
        
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.OPEN_LONG,
            quantity=10,
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        assert result is None  # Should be rejected

    def test_circuit_breaker_trips(self, risk_manager, portfolio_state, market_state):
        """Test circuit breaker tripping on large loss."""
        # Simulate large loss (>10% from peak)
        portfolio_state.cash = 8500.0  # 15% loss from $10k
        
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.OPEN_LONG,
            quantity=10,
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        assert result is None
        assert risk_manager.circuit_breaker_tripped is True

    def test_rate_limiting(self, risk_manager, portfolio_state, market_state):
        """Test rate limiting enforcement."""
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.OPEN_LONG,
            quantity=10,
        )
        
        # Submit many signals quickly
        now = datetime.utcnow()
        for i in range(risk_manager.config.max_orders_per_symbol_per_minute):
            result = risk_manager.validate_signal(signal, portfolio_state, market_state)
            if result:
                risk_manager._record_order("AAPL")
        
        # Next signal should be rate limited
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        assert result is None

    def test_total_exposure_limit(self, risk_manager, portfolio_state, market_state):
        """Test total exposure limit."""
        # Add positions near exposure limit (max is 50k)
        portfolio_state.positions["AAPL"] = Position("AAPL", 300, 150.0)  # $45,000
        
        # Try to add position that would exceed $50k limit
        signal = Signal(
            symbol="MSFT",
            action=SignalAction.OPEN_LONG,
            quantity=20,  # Would add ~$6,010 -> total ~$51k
        )
        
        result = risk_manager.validate_signal(signal, portfolio_state, market_state)
        # Should be capped to fit within exposure limit
        # Available: 50k - 45k = 5k, at $300.5 = 16 shares max
        assert result is not None
        assert result.quantity == 16  # Capped to fit within limit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
