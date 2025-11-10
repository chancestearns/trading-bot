# Trading Bot Skeleton

This repository contains a production-leaning skeleton for a modular trading bot. It
focuses on clean abstractions so real-world components—live market data feeds,
broker integrations, and sophisticated strategies—can be dropped in without
restructuring the codebase.

## Architecture Overview

```
bot/
  config.py              # Configuration management
  models.py              # Core domain models (candles, ticks, orders, signals, ...)
  data_providers/        # Data provider interfaces & mock implementation
  brokers/               # Broker abstractions & paper trading broker
  strategies/            # Strategy interfaces & sample SMA strategy
  risk/                  # Risk manager interfaces & basic implementation
  engine/                # Orchestration loop and logging config
scripts/
  run_backtest.py        # Run a mock backtest end-to-end
  run_paper_trading.py   # Run a simulated live session
config.example.json      # Example configuration file
```

Key principles:

* **Modularity** – Data providers, brokers, strategies, and risk managers use
  clear interfaces so they can be swapped independently.
* **Configuration Driven** – Runtime choices (mode, symbols, providers,
  strategy parameters) are resolved via typed configuration models.
* **Logging & Risk Hooks** – Central logging configuration and a basic risk
  manager make it easier to extend the skeleton into production workflows.

## Getting Started

### Installation

The project targets Python 3.11+. Install dependencies (only standard library
is required for the mock setup):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .  # optional if you add packaging metadata
```

### Configuration

Copy the example configuration and adapt it to your environment:

```bash
cp config.example.json config.json
```

Environment variables prefixed with `TRADING_BOT__` override nested config
values. For example:

```bash
export TRADING_BOT__ENGINE__MODE=paper
export TRADING_BOT__ENGINE__STRATEGY__PARAMS__TRADE_QUANTITY=5
```

### Running a Mock Backtest

```bash
python scripts/run_backtest.py --config config.json
```

The script wires the mock data provider, paper broker, SMA strategy, and basic
risk manager into the engine. Replace components with your own implementations
by extending the factories in `scripts/`.

### Running Simulated Paper Trading

```bash
python scripts/run_paper_trading.py --config config.json --iterations 50
```

This mode consumes streaming ticks from the mock provider. Replace the data
provider with a real-time implementation to connect to live feeds.

## Extending the Skeleton

1. **New Strategy** – Subclass `bot.strategies.base.Strategy`, implement
   `on_bar`, and update the scripts or your orchestration layer to instantiate
   it when `config.engine.strategy.name` matches your strategy key.
2. **Real Data Provider** – Implement `bot.data_providers.base.BaseDataProvider`
   to pull historical data and stream real-time ticks from an exchange or data
   vendor. Inject it using the configuration or via custom factories.
3. **Real Broker** – Subclass `bot.brokers.base.BaseBroker` and wire real order
   routing APIs. The engine already routes risk-approved signals into the broker.
4. **Advanced Risk Controls** – Implement `bot.risk.base.RiskManager` to enforce
   portfolio-specific rules (exposure, leverage, compliance) before orders are
   submitted.

## Testing

Run the included unit tests:

```bash
python -m unittest discover tests
```

The tests cover the example strategy and ensure the engine can execute a short
mock backtest end-to-end.

## Next Steps

* Add packaging metadata (e.g., `pyproject.toml`) and dependency management.
* Integrate persistent storage for trades and performance metrics.
* Enhance error handling and resilience for production deployments.
* Replace mock components with real market data, brokers, and bespoke strategies.
