# Trading Bot - Production Deployment Guide

## Quick Start

### Running with Web Dashboard

The easiest way to get started is with the web dashboard:

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure
cp config.example.json config.json
# Edit config.json with your settings

# Run with dashboard
python scripts/run_with_dashboard.py --config config.json

# Dashboard available at: http://localhost:8000
```

### Docker Deployment

```bash
# Build and run with docker compose (v2)
docker compose up -d

# View logs
docker compose logs -f trading-bot

# Stop
docker compose down

# Note: If you have the older docker-compose installed, use:
# docker-compose up -d
```

## Configuration

### Environment Variables

Override configuration using environment variables with `TRADING_BOT__` prefix:

```bash
export TRADING_BOT__ENGINE__MODE=paper
export TRADING_BOT__ENGINE__BROKER__STARTING_CASH=50000
export TRADING_BOT__ENGINE__STRATEGY__PARAMS__TRADE_QUANTITY=10
export TRADING_BOT__WEBHOOK__SECRET=your_secret_key
```

### Configuration File

Create `config.json` based on `config.example.json`:

```json
{
  "engine": {
    "mode": "paper",
    "symbols": ["AAPL", "MSFT"],
    "timeframe": "1m",
    "broker": {
      "name": "paper",
      "starting_cash": 100000.0
    },
    "strategy": {
      "name": "example_sma",
      "params": {
        "short_window": 5,
        "long_window": 15,
        "trade_quantity": 10
      }
    },
    "risk": {
      "max_position_size": 50,
      "max_daily_loss": 2000,
      "max_total_exposure": 50000,
      "max_open_positions": 5
    }
  }
}
```

## TradingView Integration

### Setup Webhook Receiver

1. **Configure bot to receive webhooks:**

```python
# Use TradingViewBroker wrapper
from bot.brokers.tradingview import TradingViewBroker
from bot.brokers.paper import PaperBroker

execution_broker = PaperBroker(starting_cash=100000)
tv_broker = TradingViewBroker(
    execution_broker=execution_broker,
    webhook_secret="your_secret_key",
    order_type=OrderType.MARKET
)
```

2. **Run bot with webhook server:**

```bash
python scripts/run_with_dashboard.py --host 0.0.0.0 --port 8000
```

3. **Configure TradingView alert:**

In TradingView, create an alert with:
- **Webhook URL:** `https://your-domain.com/webhook/tradingview`
- **Message (JSON format):**

```json
{
  "timestamp": "{{timenow}}",
  "ticker": "{{ticker}}",
  "action": "buy",
  "price": {{close}},
  "quantity": 10,
  "strategy": "{{strategy.order.comment}}",
  "message": "{{strategy.order.alert_message}}",
  "secret": "your_secret_key"
}
```

### TradingView Alert Actions

- **buy** - Open long position
- **sell** - Close long position
- **short** or **sell_short** - Open short position
- **cover** or **buy_to_cover** - Close short position

### Security

For production deployment with TradingView:

1. **Use HTTPS** (required by TradingView)
2. **Set strong webhook secret**
3. **Optional: IP whitelist** TradingView IPs:
   - 52.89.214.238
   - 34.212.75.30
   - 54.218.53.128
   - 52.32.178.7

## Web Dashboard Features

### Accessing the Dashboard

Open browser to `http://localhost:8000` (or your server URL)

### Dashboard Components

- **Bot Status** - Running/Stopped with uptime
- **Control Panel** - Start/Stop/Emergency Stop buttons
- **Account Metrics** - Balance, Equity, P&L
- **Positions Table** - Real-time position tracking
- **Orders Table** - Recent order history
- **System Info** - Mode, strategy, symbols

### API Endpoints

- `GET /api/status` - Bot status
- `GET /api/positions` - Current positions
- `GET /api/orders` - Recent orders
- `GET /api/performance` - Performance metrics
- `GET /api/account` - Account information
- `POST /api/start` - Start bot
- `POST /api/stop` - Stop bot
- `POST /api/emergency_stop` - Emergency liquidation
- `POST /webhook/tradingview` - TradingView webhook receiver
- `WS /ws/updates` - WebSocket for real-time updates

## Risk Management

### Enhanced Risk Features

The `EnhancedRiskManager` provides production-grade risk controls:

#### Position Limits
- **Max position size per symbol** - Prevents overconcentration
- **Max open positions** - Limits simultaneous trades
- **Max total exposure** - Portfolio-wide limit

#### Loss Protection
- **Daily loss limit** - Stops trading after daily loss threshold
- **Max drawdown** - Percentage-based drawdown limit
- **Circuit breaker** - Auto-stops trading on large losses

#### PDT Compliance
- **Pattern Day Trader rules** - Enforces SEC PDT regulations
- **Day trade tracking** - Counts day trades in rolling 5-day period
- **Account value check** - Requires $25k for day trading

#### Rate Limiting
- **Orders per minute** - Global rate limit
- **Orders per symbol** - Symbol-specific limit
- **Prevents webhook spam** - Duplicate detection

### Configuration Example

```python
from bot.risk.enhanced import EnhancedRiskConfig, EnhancedRiskManager

risk_config = EnhancedRiskConfig(
    max_position_size=100.0,
    max_total_exposure=50000.0,
    max_open_positions=5,
    max_daily_loss=2000.0,
    max_drawdown_percent=15.0,
    starting_cash=100000.0,
    enforce_pdt_rules=True,
    enable_circuit_breaker=True,
    circuit_breaker_loss_percent=10.0,
    max_orders_per_minute=10,
)

risk_manager = EnhancedRiskManager(risk_config)
```

## Production Deployment

### Prerequisites

- Python 3.11+
- SSL certificate (Let's Encrypt for free)
- Reverse proxy (nginx recommended)
- Process supervisor (systemd or Docker)

### Using Docker (Recommended)

1. **Build image:**

```bash
docker build -t trading-bot .
```

2. **Run with compose:**

```bash
docker compose up -d
```

3. **View logs:**

```bash
docker compose logs -f trading-bot
```

### Using systemd

Create `/etc/systemd/system/trading-bot.service`:

```ini
[Unit]
Description=Trading Bot
After=network.target

[Service]
Type=simple
User=tradingbot
WorkingDirectory=/opt/trading-bot
Environment="PATH=/opt/trading-bot/.venv/bin"
ExecStart=/opt/trading-bot/.venv/bin/python scripts/run_with_dashboard.py --config config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

### Nginx Reverse Proxy

For HTTPS and TradingView webhooks:

```nginx
server {
    listen 443 ssl;
    server_name trading.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/trading.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/trading.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket support
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

## Security Best Practices

1. **Never commit secrets** - Use environment variables or secret managers
2. **Use HTTPS** - Required for TradingView webhooks
3. **Webhook authentication** - Always set and verify webhook secrets
4. **Firewall rules** - Limit access to dashboard
5. **Strong passwords** - If adding authentication to dashboard
6. **Regular updates** - Keep dependencies updated
7. **Monitor logs** - Watch for suspicious activity
8. **Backup configuration** - Version control your config (without secrets)

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

### Logs

Logs are written to stdout/stderr. Configure log level in config:

```json
{
  "engine": {
    "logging": {
      "level": "INFO",
      "format": "standard"
    }
  }
}
```

### Metrics (Future)

The bot is designed to support Prometheus metrics. Enable in `docker-compose.yml`.

## Troubleshooting

### Bot won't start

1. Check configuration file syntax
2. Verify all required fields are present
3. Check logs for error messages
4. Ensure ports are not in use

### Webhooks not received

1. Verify bot is accessible from internet
2. Check HTTPS is configured
3. Verify webhook secret matches
4. Check firewall rules
5. Test with curl:

```bash
curl -X POST https://your-domain.com/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","action":"buy","quantity":10,"price":150.0,"secret":"your_secret"}'
```

### Dashboard not loading

1. Check bot is running: `curl http://localhost:8000/health`
2. Verify static files are present in `bot/ui/`
3. Check browser console for errors
4. Try accessing API directly: `curl http://localhost:8000/api/status`

### Orders not executing

1. Check risk manager logs for rejections
2. Verify sufficient buying power
3. Check position/exposure limits
4. Verify market prices are being updated
5. Check circuit breaker status

### High memory usage

1. Reduce history length in strategy
2. Limit candle buffer size
3. Clear old order/trade history periodically
4. Use `slots=True` on dataclasses (already implemented)

## Support

For issues and questions:
- Check the logs first
- Review configuration against examples
- Test components individually
- Check GitHub issues

## Next Steps

1. **Paper trading** - Test strategies with simulated data
2. **Strategy development** - Create custom strategies
3. **Backtesting** - Validate strategies on historical data
4. **Risk tuning** - Adjust limits for your risk tolerance
5. **Live trading** - When ready, switch to live mode with real broker

## Important Disclaimers

- **This is for educational purposes**
- **Past performance ≠ future results**
- **Trading involves risk of loss**
- **Test thoroughly in paper mode first**
- **Understand all risks before live trading**
- **Not financial advice**
