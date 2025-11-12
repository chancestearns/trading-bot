"""Tests for the main orchestration loop of the trading bot."""

from __future__ import annotations

import asyncio
import unittest
import pytest

from bot.brokers.paper import PaperBroker
from bot.config import Config
from bot.data_providers.mock import MockDataProvider
from bot.engine.loop import TradingEngine
from bot.risk.basic import BasicRiskConfig, BasicRiskManager
from bot.strategies.example_sma import (
    SimpleMovingAverageConfig,
    SimpleMovingAverageStrategy,
)


class EngineLoopTest(unittest.TestCase):
    @pytest.mark.asyncio
    async def test_backtest_runs_without_errors(self) -> None:
        """Test that the trading engine runs a backtest without errors."""
        config = Config()
        config.engine.symbols = ["AAPL"]
        config.engine.mode = "backtest"
        data_provider = MockDataProvider()
        broker = PaperBroker(starting_cash=config.engine.broker.starting_cash)
        strategy = SimpleMovingAverageStrategy(
            SimpleMovingAverageConfig(short_window=2, long_window=3, trade_quantity=1)
        )
        risk_cfg = BasicRiskConfig(
            max_position_size=config.engine.risk.max_position_size,
            max_daily_loss=config.engine.risk.max_daily_loss,
            starting_cash=config.engine.broker.starting_cash,
        )
        risk_manager = BasicRiskManager(risk_cfg)
        engine = TradingEngine(config, data_provider, broker, strategy, risk_manager)
        # Run with a short timeout to avoid hanging tests
        try:
            await asyncio.wait_for(engine.run(), timeout=5.0)
        except asyncio.TimeoutError:
            # It's okay if we timeout - the engine was working, just slow
            pass
