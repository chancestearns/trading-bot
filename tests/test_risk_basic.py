"""Tests for the basic risk manager implementation."""

from __future__ import annotations

import unittest

from bot.models import MarketState, PortfolioState, Position, Signal, SignalAction
from bot.risk.basic import BasicRiskConfig, BasicRiskManager


class BasicRiskManagerTestCase(unittest.TestCase):
    """Unit tests covering the position cap and drawdown checks."""

    def setUp(self) -> None:
        self.config = BasicRiskConfig(
            max_position_size=50.0,
            max_daily_loss=1_000.0,
            starting_cash=100_000.0,
        )
        self.risk_manager = BasicRiskManager(self.config)
        self.market_state = MarketState(candles={})

    def test_rejects_signal_when_symbol_limit_reached(self) -> None:
        """Opening a position beyond the per-symbol limit should be blocked."""

        portfolio_state = PortfolioState(
            cash=self.config.starting_cash,
            positions={"AAPL": Position(symbol="AAPL", quantity=50.0, avg_price=100.0)},
        )
        signal = Signal(symbol="AAPL", action=SignalAction.OPEN_LONG, quantity=5.0)

        result = self.risk_manager.validate_signal(
            signal, portfolio_state, self.market_state
        )

        self.assertIsNone(result)

    def test_caps_signal_to_remaining_capacity(self) -> None:
        """Signals should be resized down to the remaining allowed quantity."""

        portfolio_state = PortfolioState(
            cash=self.config.starting_cash,
            positions={"AAPL": Position(symbol="AAPL", quantity=30.0, avg_price=100.0)},
        )
        signal = Signal(symbol="AAPL", action=SignalAction.OPEN_LONG, quantity=40.0)

        result = self.risk_manager.validate_signal(
            signal, portfolio_state, self.market_state
        )

        self.assertIsNotNone(result)
        assert result is not None  # for mypy/static type checkers
        self.assertEqual(result.quantity, 20.0)
        self.assertIn("capped_quantity", result.meta)
        self.assertEqual(result.meta["capped_quantity"], 20.0)

    def test_allows_closing_signals_even_with_limit(self) -> None:
        """Exit orders should flow even if exposure limits are already met."""

        portfolio_state = PortfolioState(
            cash=self.config.starting_cash,
            positions={"AAPL": Position(symbol="AAPL", quantity=50.0, avg_price=100.0)},
        )
        signal = Signal(symbol="AAPL", action=SignalAction.CLOSE_LONG, quantity=50.0)

        result = self.risk_manager.validate_signal(
            signal, portfolio_state, self.market_state
        )

        self.assertIs(result, signal)

    def test_blocks_signals_once_daily_loss_threshold_hit(self) -> None:
        """Signals should be rejected after the configured drawdown is reached."""

        portfolio_state = PortfolioState(
            cash=self.config.starting_cash - self.config.max_daily_loss,
            positions={},
        )
        signal = Signal(symbol="AAPL", action=SignalAction.OPEN_LONG, quantity=1.0)

        result = self.risk_manager.validate_signal(
            signal, portfolio_state, self.market_state
        )

        self.assertIsNone(result)

    def test_allows_closing_signals_after_drawdown(self) -> None:
        """Exit signals should still flow even when the drawdown limit is met."""

        portfolio_state = PortfolioState(
            cash=self.config.starting_cash - self.config.max_daily_loss,
            positions={"AAPL": Position(symbol="AAPL", quantity=50.0, avg_price=100.0)},
        )
        signal = Signal(symbol="AAPL", action=SignalAction.CLOSE_LONG, quantity=50.0)

        result = self.risk_manager.validate_signal(
            signal, portfolio_state, self.market_state
        )

        self.assertIs(result, signal)


if __name__ == "__main__":
    unittest.main()
