"""Tests for enhanced model features."""

from __future__ import annotations

import unittest
from datetime import datetime

from bot.models import Order, OrderFill, OrderSide, OrderStatus, OrderType, Position
from bot.config import BrokerConfig, ConfigValidationError, EngineConfig


class TestOrderLifecycle(unittest.TestCase):
    """Test order lifecycle management."""

    def test_order_fill_tracking(self):
        """Test tracking order fills through the lifecycle."""
        order = Order(
            id="TEST_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100.0,
            order_type=OrderType.MARKET,
        )

        # Add first fill
        fill1 = OrderFill(
            fill_id="FILL_001", timestamp=datetime.utcnow(), quantity=50.0, price=150.0
        )
        order.add_fill(fill1)

        self.assertEqual(order.filled_quantity, 50.0)
        self.assertEqual(order.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(order.remaining_quantity, 50.0)

        # Add second fill
        fill2 = OrderFill(
            fill_id="FILL_002", timestamp=datetime.utcnow(), quantity=50.0, price=151.0
        )
        order.add_fill(fill2)

        self.assertEqual(order.filled_quantity, 100.0)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.remaining_quantity, 0.0)
        self.assertAlmostEqual(order.average_fill_price, 150.5, places=2)

    def test_order_is_complete(self):
        """Test order completion status."""
        order = Order(
            id="TEST_002",
            symbol="MSFT",
            side=OrderSide.SELL,
            quantity=50.0,
            order_type=OrderType.MARKET,
        )

        self.assertFalse(order.is_complete)

        order.status = OrderStatus.FILLED
        self.assertTrue(order.is_complete)

        order.status = OrderStatus.CANCELLED
        self.assertTrue(order.is_complete)

        order.status = OrderStatus.REJECTED
        self.assertTrue(order.is_complete)


class TestPositionManagement(unittest.TestCase):
    """Test position management and P&L calculations."""

    def test_position_pnl_calculation(self):
        """Test unrealized P&L calculations."""
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)

        current_price = 155.0
        pnl = position.unrealized_pnl(current_price)
        self.assertEqual(pnl, 500.0)  # (155 - 150) * 100

        pnl_pct = position.unrealized_pnl_percent(current_price)
        self.assertAlmostEqual(pnl_pct, 3.33, places=2)

    def test_position_flags(self):
        """Test position directional flags."""
        long_position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)
        self.assertTrue(long_position.is_long)
        self.assertFalse(long_position.is_short)
        self.assertFalse(long_position.is_flat)

        short_position = Position(symbol="TSLA", quantity=-50.0, avg_price=200.0)
        self.assertFalse(short_position.is_long)
        self.assertTrue(short_position.is_short)
        self.assertFalse(short_position.is_flat)

        flat_position = Position(symbol="GOOGL", quantity=0.0, avg_price=100.0)
        self.assertFalse(flat_position.is_long)
        self.assertFalse(flat_position.is_short)
        self.assertTrue(flat_position.is_flat)

    def test_position_update_add(self):
        """Test adding to a position."""
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)

        position.update(50.0, 155.0)

        self.assertEqual(position.quantity, 150.0)
        # Weighted average: (100*150 + 50*155) / 150 = 151.67
        self.assertAlmostEqual(position.avg_price, 151.67, places=2)

    def test_position_update_reduce(self):
        """Test reducing a position."""
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)

        position.update(-50.0, 155.0)

        self.assertEqual(position.quantity, 50.0)
        self.assertEqual(position.avg_price, 150.0)  # Avg price unchanged when reducing

    def test_position_update_close(self):
        """Test closing a position."""
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)

        position.update(-100.0, 160.0)

        self.assertEqual(position.quantity, 0.0)
        self.assertEqual(position.avg_price, 0.0)
        self.assertTrue(position.is_flat)

    def test_position_reversal(self):
        """Test reversing a position (long to short)."""
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)

        # Sell more than we have
        position.update(-150.0, 160.0)

        self.assertEqual(position.quantity, -50.0)
        self.assertEqual(
            position.avg_price, 160.0
        )  # New avg price for reversed position
        self.assertTrue(position.is_short)


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation."""

    def test_invalid_starting_cash(self):
        """Test that negative starting cash is rejected."""
        with self.assertRaises(ConfigValidationError):
            BrokerConfig(starting_cash=-1000.0)

    def test_invalid_mode(self):
        """Test that invalid mode is rejected."""
        with self.assertRaises(ConfigValidationError):
            EngineConfig(mode="invalid_mode")

    def test_invalid_commission(self):
        """Test that negative commission is rejected."""
        with self.assertRaises(ConfigValidationError):
            BrokerConfig(commission_per_share=-0.01)

    def test_empty_symbols(self):
        """Test that empty symbols list is rejected."""
        with self.assertRaises(ConfigValidationError):
            EngineConfig(symbols=[])

    def test_invalid_timeframe(self):
        """Test that invalid timeframe is rejected."""
        with self.assertRaises(ConfigValidationError):
            EngineConfig(timeframe="invalid")


if __name__ == "__main__":
    unittest.main()
