from __future__ import annotations

import asyncio
import unittest

from bot.brokers.paper import PaperBroker
from bot.config import Config
from bot.data_providers.mock import MockDataProvider
from bot.engine.loop import TradingEngine
from bot.risk.basic import BasicRiskConfig, BasicRiskManager
from bot.strategies.example_sma import SimpleMovingAverageStrategy


class EngineLoopTest(unittest.TestCase):
    def test_backtest_runs_without_errors(self) -> None:
        config = Config()
        config.engine.symbols = ["AAPL"]
        config.engine.mode = "backtest"
        data_provider = MockDataProvider()
        broker = PaperBroker(starting_cash=config.engine.broker.starting_cash)
        strategy = SimpleMovingAverageStrategy()
        risk_cfg = BasicRiskConfig(
            max_position_size=config.engine.risk.max_position_size,
            max_daily_loss=config.engine.risk.max_daily_loss,
            starting_cash=config.engine.broker.starting_cash,
        )
        risk_manager = BasicRiskManager(risk_cfg)
        engine = TradingEngine(config, data_provider, broker, strategy, risk_manager)
        asyncio.run(engine.run())


if __name__ == "__main__":
    unittest.main()
