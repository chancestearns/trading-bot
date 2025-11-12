# Trading Bot - Production-Ready Framework

A modular, production-leaning trading bot built with Python 3.11+ featuring async broker integrations, comprehensive risk management, and real-time monitoring capabilities.

## 🚀 Features

### Core Architecture
- **Async-first design** - Full async/await support for real-world broker APIs
- **Interface-driven** - Clean abstractions for swappable components
- **Configuration-driven** - Runtime behavior controlled via typed config models
- **Production-ready error handling** - Retry logic, circuit breakers, and graceful degradation

### Trading Capabilities
- **Order lifecycle management** - Complete tracking of order states, fills, and reconciliation
- **Position tracking** - Real-time P&L calculations and position management
- **Risk management** - Pre-trade checks, position limits, drawdown protection
- **Multiple broker support** - Paper trading, TradingView webhooks, thinkorswim API

### Monitoring & Control
- **FastAPI dashboard** - Real-time web interface for monitoring
- **WebSocket updates** - Live position and P&L streaming
- **Prometheus metrics** - Production-grade monitoring integration
- **Emergency controls** - Circuit breakers and emergency liquidation

## 📁 Architecture Overview

```
bot/
  config.py              # Enhanced configuration with validation
  models.py              # Production-ready domain models with full lifecycle tracking
  data_providers/        # Data provider interfaces & implementations
    base.py              # BaseDataProvider abstract interface
    mock.py              # Mock data provider for testing
  brokers/               # Broker abstractions & implementations
    base.py              # Async BaseBroker interface with exception hierarchy
    paper.py             # Enhanced paper broker with realistic simulation
    tradingview.py       # TradingView webhook receiver (optional)
    thinkorswim.py       # thinkorswim API integration (optional)
  strategies/            # Strategy interfaces & implementations
    base.py              # Strategy abstract interface
    example_sma.py       # SMA crossover example strategy
  risk/                  # Risk management
    base.py              # RiskManager interface
    basic.py             # BasicRiskManager with position & drawdown limits
  engine/                # Orchestration
    loop.py              # Trading engine with async support & error handling
    logging_config.py    # Centralized logging configuration
  api/                   # Web API & Dashboard (optional)
    server.py            # FastAPI server for monitoring & control
  ui/                    # Web dashboard (optional)
    templates/           # HTML templates
    static/              # CSS, JavaScript, assets
scripts/
  run_backtest.py        # Run historical backtest
  run_paper_trading.py   # Run simulated live trading
  run_with_ui.py         # Run with web dashboard
tests/
  test_models.py         # Test enhanced models
  test_engine_loop.py    # Test engine orchestration
  test_risk_basic.py     # Test risk management
  test_broker_paper.py   # Test paper broker
config.example.json      # Example configuration file
requirements.txt         # Python dependencies
Dockerfile               # Container configuration
docker-compose.yml       # Multi-container orchestration
```

## 🔧 Getting Started

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd trading-bot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy example configuration
cp config.example.json config.json

# Edit configuration
nano config.json
```

**Environment Variables** (override config values):
```bash
export TRADING_BOT__ENGINE__MODE=paper
export TRADING_BOT__ENGINE__STRATEGY__PARAMS__TRADE_QUANTITY=5
export TRADING_BOT__BROKER__STARTING_CASH=50000
```

### Running the Bot

**Backtest Mode:**
```bash
python scripts/run_backtest.py --config config.json
```

**Paper Trading:**
```bash
python scripts/run_paper_trading.py --config config.json --iterations 50
```

**With Web Dashboard:**
```bash
python scripts/run_with_ui.py --config config.json
# Open browser to http://localhost:8080
```

## 📊 Configuration Options

### Complete Configuration Example

```json
{
  "engine": {
    "mode": "paper",
    "symbols": ["AAPL", "MSFT", "GOOGL"],
    "timeframe": "5m",
    "data_provider": {
      "name": "mock",
      "params": {
        "seed": 42,
        "base_price": 150.0
      }
    },
    "broker": {
      "name": "paper",
      "starting_cash": 100000.0,
      "commission_per_share": 0.0,
      "commission_percent": 0.001,
      "slippage_percent": 0.0005
    },
    "strategy": {
      "name": "example_sma",
      "params": {
        "short_window": 5,
        "long_window": 20,
        "trade_quantity": 10
      }
    },
    "risk": {
      "max_position_size": 1000,
      "max_daily_loss": 5000,
      "max_total_exposure": 50000,
      "max_open_positions": 5
    },
    "logging": {
      "level": "INFO",
      "format": "standard",
      "file": "logs/trading.log"
    }
  }
}
```

### Modes

- **`backtest`** - Historical data simulation
- **`paper`** - Simulated live trading with mock data
- **`live`** - Real trading with live broker integration

### Broker Options

- **`paper`** - Built-in paper trading with realistic fills
- **`tradingview`** - TradingView webhook receiver
- **`thinkorswim`** - Charles Schwab thinkorswim API

## 🔌 Broker Integrations

### Paper Trading (Built-in)

No additional setup required. Configured via `broker` section in config.

### TradingView Webhooks

1. Set webhook secret:
   ```bash
   export WEBHOOK_SECRET=your_secret_here
   ```

2. Configure TradingView alert with JSON payload:
   ```json
   {
     "timestamp": "{{time}}",
     "ticker": "{{ticker}}",
     "action": "buy",
     "quantity": 10,
     "price": {{close}},
     "strategy": "My_Strategy",
     "secret": "your_secret_here"
   }
   ```

3. Set webhook URL: `https://yourdomain.com/webhook/tradingview`

### thinkorswim API

1. Get API credentials from Charles Schwab developer portal

2. Configure environment variables:
   ```bash
   export TOS_CLIENT_ID=your_client_id
   export TOS_REFRESH_TOKEN=your_refresh_token
   export TOS_ACCOUNT_ID=your_account_id
   ```

3. Update config:
   ```json
   {
     "broker": {
       "name": "thinkorswim",
       "use_paper_trading": true
     }
   }
   ```

## 🎯 Creating Custom Strategies

```python
from bot.strategies.base import Strategy
from bot.models import MarketState, PortfolioState, Signal, SignalAction

class MyStrategy(Strategy):
    def on_start(self, config, logger):
        self.param = config.params.get('my_param', 10)
        logger.info(f"Strategy started with param={self.param}")
    
    def on_bar(self, market_state: MarketState, portfolio_state: PortfolioState):
        signals = []
        
        for symbol, candles in market_state.candles.items():
            if len(candles) < 20:
                continue
            
            # Your strategy logic here
            if self._should_buy(candles):
                signals.append(Signal(
                    symbol=symbol,
                    action=SignalAction.OPEN_LONG,
                    quantity=10.0,
                    confidence=0.8
                ))
        
        return signals
    
    def _should_buy(self, candles):
        # Implement your logic
        return False
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=bot --cov-report=html

# Run specific test file
pytest tests/test_engine_loop.py -v

# Run with async support
pytest tests/ -v --asyncio-mode=auto
```

## 🐳 Docker Deployment

```bash
# Build image
docker-compose build

# Run container
docker-compose up -d

# View logs
docker-compose logs -f trading-bot

# Stop container
docker-compose down
```

## 📈 Monitoring & Metrics

### Web Dashboard

Access at `http://localhost:8080` when running with UI.

Features:
- Real-time position monitoring
- P&L tracking
- Order history
- Emergency stop button
- Live logs

### Prometheus Metrics

Exposed at `http://localhost:8080/metrics`

Available metrics:
- `orders_submitted_total` - Counter of orders submitted
- `orders_filled_total` - Counter of successfully filled orders
- `orders_rejected_total` - Counter of rejected orders
- `current_positions` - Gauge of open positions
- `account_equity_dollars` - Current account equity
- `unrealized_pnl_dollars` - Unrealized P&L

## 🔒 Security Best Practices

- ✅ Never commit secrets to version control
- ✅ Use environment variables for sensitive data
- ✅ Enable HTTPS for webhook endpoints
- ✅ Validate webhook signatures
- ✅ Implement rate limiting
- ✅ Use strong secrets for webhooks
- ✅ Enable IP whitelisting where possible
- ✅ Run with least-privilege user in containers

## 🛠️ Development

### Code Quality

```bash
# Format code
black bot/ tests/ scripts/

# Sort imports
isort bot/ tests/ scripts/

# Type checking
mypy bot/

# Linting
ruff check bot/
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## 📚 Documentation

- [Production Readiness Guide](docs/production_readiness.md)
- [Migration Guide](docs/migration_guide.md)
- [Broker Integration Guide](docs/broker_integration.md)
- [API Documentation](docs/api_documentation.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This software is for educational purposes only. Trading involves substantial risk of loss. The authors are not responsible for any financial losses incurred through the use of this software. Always test thoroughly with paper trading before risking real capital.

## 🆘 Support

- **Issues**: Open an issue on GitHub
- **Discussions**: Use GitHub Discussions
- **Documentation**: Check the `docs/` directory

## 🗺️ Roadmap

- [ ] Additional broker integrations (Interactive Brokers, Alpaca)
- [ ] Advanced order types (bracket orders, OCO)
- [ ] Options trading support
- [ ] Multi-strategy portfolio management
- [ ] Machine learning strategy framework
- [ ] Mobile app for monitoring
- [ ] Cloud deployment templates (AWS, GCP, Azure)

## 🙏 Acknowledgments

Built with:
- Python 3.11+
- FastAPI
- aiohttp
- pytest

---

**Version**: 1.0.0  
**Last Updated**: November 2025
