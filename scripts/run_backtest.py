"""Run a mock backtest using the built-in components."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.brokers.paper import PaperBroker
from bot.config import Config, load_config
from bot.data_providers.mock import MockDataProvider
from bot.engine.logging_config import setup_logging
from bot.engine.loop import TradingEngine
from bot.risk.basic import BasicRiskConfig, BasicRiskManager
from bot.strategies.example_sma import SimpleMovingAverageStrategy


def _build_components(config: Config):
    data_provider = MockDataProvider(**config.engine.data_provider.params)
    broker = PaperBroker(starting_cash=config.engine.broker.starting_cash)
    strategy = SimpleMovingAverageStrategy()
    risk_cfg = BasicRiskConfig(
        max_position_size=config.engine.risk.max_position_size,
        max_daily_loss=config.engine.risk.max_daily_loss,
        starting_cash=config.engine.broker.starting_cash,
    )
    risk_manager = BasicRiskManager(risk_cfg)
    return data_provider, broker, strategy, risk_manager


async def _run(config: Config) -> None:
    data_provider, broker, strategy, risk_manager = _build_components(config)
    engine = TradingEngine(config, data_provider, broker, strategy, risk_manager)
    await engine.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock backtest.")
    parser.add_argument("--config", type=Path, default=None, help="Path to config JSON file")
    args = parser.parse_args()

    setup_logging()
    config = load_config(args.config)
    config.engine.mode = "backtest"
    asyncio.run(_run(config))


if __name__ == "__main__":
    main()
