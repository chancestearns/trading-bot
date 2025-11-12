# Trading Bot - AI Agent Instructions

## Architecture Overview

This is a modular, **async-first** trading bot framework with pluggable components. The engine orchestrates data providers, brokers, strategies, and risk managers through well-defined interfaces.

### Core Component Flow
```
DataProvider → Strategy → RiskManager → Broker → Engine (orchestrates all)
```

**Key directories:**
- `bot/models.py` - Domain models with full order lifecycle tracking (OrderStatus, OrderFill, Position with P&L)
- `bot/brokers/` - Execution providers (all methods are async: `await broker.submit_order()`)
- `bot/strategies/` - Strategy implementations extending `Strategy` base class
- `bot/risk/` - Risk management (position limits, drawdown protection)
- `bot/engine/loop.py` - Main orchestration with circuit breakers and error handling
- `bot/data_providers/` - Market data interfaces (async connect/close, sync data retrieval)

## Critical Patterns

### 1. Async Broker Interface
ALL broker methods are async and must be awaited:
```python
# Correct:
order = await broker.submit_order(order)
positions = await broker.get_positions()
await broker.connect()

# Wrong:
order = broker.submit_order(order)  # Missing await!
```

### 2. Configuration System
Uses typed dataclasses with validation in `bot/config.py`. Override via environment variables with `TRADING_BOT__` prefix:
```bash
export TRADING_BOT__ENGINE__MODE=paper
export TRADING_BOT__ENGINE__BROKER__STARTING_CASH=50000
```

Config paths checked: `config.json`, `config.yaml`, `config.example.json`

### 3. Order Lifecycle Management
Orders track complete lifecycle with fills, status transitions, and error messages:
```python
order.status  # PENDING → SUBMITTED → ACCEPTED → FILLED
order.filled_quantity  # Track partial fills
order.fills  # List[OrderFill] with timestamps
order.average_fill_price  # Calculated property
order.is_complete  # Helper property
```

### 4. Strategy Implementation Pattern
Extend `Strategy` base class. Engine calls `on_bar()` with market and portfolio state:
```python
class MyStrategy(Strategy):
    def on_bar(self, market_state: MarketState, portfolio_state: PortfolioState) -> Iterable[Signal] | None:
        # Access historical candles: market_state.candles[symbol]
        # Current positions: portfolio_state.positions[symbol]
        # Return Signal objects with action (OPEN_LONG, CLOSE_LONG, etc.)
```

See `bot/strategies/example_sma.py` for reference implementation.

### 5. Risk Manager Integration
Risk managers validate signals before execution. Always allow closing positions:
```python
# From bot/risk/basic.py pattern:
if signal.action in {SignalAction.CLOSE_LONG, SignalAction.CLOSE_SHORT}:
    return signal  # Always allow closes

# Check limits for opens, return None to reject or adjusted Signal
```

### 6. Engine Modes
- `backtest`: Historical simulation using `get_historical_data()`
- `paper`: Live simulation with mock data streaming
- `live`: Real broker execution (requires broker implementation)

## Development Workflows

### Running Tests
```bash
pytest tests/ -v                    # All tests
pytest tests/test_engine_loop.py    # Specific test
pytest --cov=bot tests/             # With coverage
```

### Running the Bot
```bash
# Paper trading (simulated live)
python scripts/run_paper_trading.py --config config.json

# Backtest
python scripts/run_backtest.py --config config.json

# With chart visualization
python scripts/run_backtest_with_chart.py
```

### Component Registration
Build pattern in `scripts/run_*.py`:
1. Load config: `config = load_config(path)`
2. Instantiate data provider from config
3. Instantiate broker with starting_cash from config
4. Instantiate strategy (pass params from config.engine.strategy.params)
5. Build risk manager with BasicRiskConfig
6. Create TradingEngine with all components
7. `await engine.run(iterations=None)`

## Exception Hierarchy

Broker errors use typed exceptions from `bot/brokers/base.py`:
- `BrokerError` - Base class
- `ConnectionError` - Network/connection failures
- `OrderRejectedError` - Order validation failures (includes order object)
- `InsufficientFundsError` - Buying power issues
- `RateLimitError` - API throttling (includes retry_after)

Handle appropriately - engine has circuit breaker that trips after 5 consecutive errors.

## Key Conventions

1. **Slots on dataclasses**: All models use `@dataclass(slots=True)` for memory efficiency
2. **Type hints everywhere**: Use `from __future__ import annotations` for forward refs
3. **Logging**: Use class-level logger: `self.logger = logging.getLogger(self.__class__.__name__)`
4. **Enums for states**: OrderStatus, OrderSide, OrderType, SignalAction are string enums
5. **Quantity always positive**: Signal quantity is absolute; action (OPEN_LONG vs SELL) determines direction
6. **Position reconciliation**: Call `await broker.reconcile_positions(symbols)` on startup to sync state

## Testing Patterns

Tests use pytest with async support (`@pytest.mark.asyncio`). Mock components:
```python
data_provider = MockDataProvider(seed=42)
broker = PaperBroker(starting_cash=100000)
strategy = SimpleMovingAverageStrategy(SimpleMovingAverageConfig(...))
```

Engine runs with timeout to prevent hanging tests.

## When Adding New Components

- **New strategy**: Extend `Strategy`, implement `on_bar()`, add config dataclass
- **New broker**: Extend `BaseBroker`, implement all async methods, handle connection lifecycle
- **New risk manager**: Extend `RiskManager`, implement `validate_signal()`
- **New data provider**: Extend `BaseDataProvider`, implement async connect/close and data methods

All components receive config via constructor, not globals.

## Production Features

### TradingView Integration
- `bot/brokers/tradingview.py` - Webhook receiver that wraps another broker
- Validates signatures, detects duplicates, converts alerts to signals
- Use with any execution broker: `TradingViewBroker(execution_broker=PaperBroker(), ...)`

### Web Dashboard
- `bot/api/server.py` - FastAPI backend with REST API and WebSocket
- `bot/ui/templates/dashboard.html` - Real-time dashboard UI
- Run with: `python scripts/run_with_dashboard.py --config config.json`
- Access at: `http://localhost:8000`

### Enhanced Risk Management
- `bot/risk/enhanced.py` - Production risk manager with circuit breakers
- Features: PDT compliance, rate limiting, drawdown protection, multi-level limits
- Use `EnhancedRiskManager` instead of `BasicRiskManager` for production

### Deployment
- `Dockerfile` - Multi-stage build for production
- `docker-compose.yml` - Full stack with optional monitoring
- `DEPLOYMENT.md` - Complete production deployment guide
- Supports Docker, systemd, and manual deployment

