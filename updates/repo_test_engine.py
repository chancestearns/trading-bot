from __future__ import annotations

import pytest

from bot.brokers.paper import PaperBroker
from bot.config import Config
from bot.data_providers.mock import MockDataProvider
from bot.engine.loop import TradingEngine
from bot.risk.basic import BasicRiskConfig, BasicRiskManager
from bot.strategies.example_sma import SimpleMovingAverageStrategy


class TestEngineLoop:
    @pytest.mark.asyncio
    async def test_backtest_runs_without_errors(self) -> None:
        """Test that a basic backtest completes successfully."""
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
        await engine.run()
    
    @pytest.mark.asyncio
    async def test_paper_trading_runs_with_iterations(self) -> None:
        """Test that paper trading mode works with limited iterations."""
        config = Config()
        config.engine.symbols = ["AAPL", "MSFT"]
        config.engine.mode = "paper"
        
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
        await engine.run(iterations=10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
