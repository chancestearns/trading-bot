from __future__ import annotations

"""Run a mock backtest and display a price chart."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import sys
from pathlib import Path

import matplotlib.pyplot as plt

# Ensure project root is on sys.path (same pattern as run_backtest.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import Config, load_config
from bot.data_providers.mock import MockDataProvider
from bot.engine.logging_config import setup_logging
from bot.engine.loop import TradingEngine
from bot.risk.basic import BasicRiskConfig, BasicRiskManager
from bot.strategies.example_sma import SimpleMovingAverageStrategy
from bot.brokers.paper import PaperBroker


def _build_components(config: Config):
    """Construct components exactly like the existing scripts do."""
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


async def _run_with_chart(config: Config) -> None:
    # Force backtest mode for this script
    config.engine.mode = "backtest"

    data_provider, broker, strategy, risk_manager = _build_components(config)
    engine = TradingEngine(config, data_provider, broker, strategy, risk_manager)

    # Get some mock historical data for visualization
    symbol = config.engine.symbols[0]
    timeframe = config.engine.timeframe
    candles = data_provider.get_historical_data(
        symbol=symbol,
        start=None,
        end=None,
        timeframe=timeframe,
    )
    prices = [c.close for c in candles]

    print("[INFO] Running backtest...")
    await engine.run()
    print("[INFO] Backtest complete — generating chart...")

    # Plot price series
    plt.figure(figsize=(10, 5))
    plt.plot(prices, label=f"{symbol} mock price")
    plt.title("Mock Backtest — Simple Moving Average Strategy")
    plt.xlabel("Time step")
    plt.ylabel("Price")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()


def main() -> None:
    setup_logging()
    config_path = Path("config.example.json")
    config = load_config(config_path)
    asyncio.run(_run_with_chart(config))


if __name__ == "__main__":
    main()
