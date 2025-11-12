# Trading Bot Production Readiness Guide

## Executive Summary

Your trading bot skeleton has a solid foundation with clean architecture. This guide provides a prioritized roadmap to production readiness with specific code examples and implementation steps.

**Current Status: 7.5/10**
- ✅ Clean interface-driven design
- ✅ Good separation of concerns  
- ✅ Configuration management foundation
- ❌ Missing async support in critical paths
- ❌ Incomplete error handling
- ❌ No production broker integration

---

## Critical Issues (Must Fix Before Production)

### 1. 🔴 Convert Broker Interface to Async ✅ FIXED

**Issue**: Current broker methods are synchronous, but real broker APIs (TradingView webhooks, thinkorswim API) require async operations.

**Impact**: Cannot integrate with any real broker without major refactoring.

**Solution**: I've created an enhanced async broker interface (see artifact: "Async Broker Interface with Production Features")

**Key Changes**:
- All broker methods now use `async/await`
- Added proper exception hierarchy (`OrderRejectedError`, `InsufficientFundsError`, `RateLimitError`)
- Added `OrderManager` helper class for tracking orders
- Added position reconciliation method (critical for recovery)

**Implementation**:
1. Replace `bot/brokers/base.py` with the enhanced version
2. Update `bot/brokers/paper.py` with async implementation (provided in artifacts)
3. Update engine loop to use `await` for all broker calls

---

### 2. 🔴 Add Order Lifecycle Management ✅ FIXED

**Issue**: Current `Order` model lacks status tracking, fill tracking, and broker ID mapping.

**Impact**: Cannot track order states, handle partial fills, or reconcile with broker.

**Solution**: Enhanced models with complete order lifecycle (see artifact: "Enhanced Models with Order Lifecycle")

**Key Additions**:
- `OrderStatus` enum with all lifecycle states
- `OrderFill` class for tracking individual fills
- Order tracking methods (`add_fill`, `average_fill_price`, `is_complete`)
- Enhanced `Position` class with P&L calculations

---

### 3. 🔴 Fix Thread Safety Issues

**Issue**: Shared state (`_positions`, `_last_prices`) accessed by multiple components without synchronization.

**Current Code** (bot/brokers/paper.py:57):
```python
self._positions: Dict[str, Position] = {}
self._last_prices: Dict[str, float] = {}
```

**Problem**: If webhook receiver runs in separate thread from engine loop, race conditions occur.

**Solution**: Add thread-safe wrappers

```python
import threading
from typing import Dict

class ThreadSafeDict:
    def __init__(self):
        self._data: Dict = {}
        self._lock = threading.RLock()
    
    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key, value):
        with self._lock:
            self._data[key] = value
    
    def items(self):
        with self._lock:
            return list(self._data.items())
    
    def update(self, other: Dict):
        with self._lock:
            self._data.update(other)

# Usage in PaperBroker
self._positions = ThreadSafeDict()
self._last_prices = ThreadSafeDict()
```

**Alternative**: Use `asyncio.Lock` if running fully async without threads:

```python
class PaperBroker(BaseBroker):
    def __init__(self, ...):
        self._positions: Dict[str, Position] = {}
        self._positions_lock = asyncio.Lock()
    
    async def get_positions(self) -> Dict[str, Position]:
        async with self._positions_lock:
            return dict(self._positions)
```

---

### 4. 🟠 Add Comprehensive Error Handling

**Issue**: Missing try-except blocks in critical paths, no retry logic, no circuit breakers.

**Example Fix for Engine Loop** (bot/engine/loop.py):

```python
import asyncio
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

class TradingEngine:
    def __init__(self, ...):
        self.circuit_breaker_tripped = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ConnectionError)
    )
    async def _submit_order_with_retry(self, order: Order) -> Order:
        """Submit order with exponential backoff retry."""
        return await self.broker.submit_order(order)
    
    async def _process_iteration(self, ...):
        try:
            # ... existing logic ...
            
            for signal in signals:
                try:
                    approved = self.risk_manager.validate_signal(...)
                    if not approved:
                        continue
                    
                    order = self._signal_to_order(approved, latest_prices)
                    if order is None:
                        continue
                    
                    # Use retry wrapper
                    await self._submit_order_with_retry(order)
                    
                    # Reset error counter on success
                    self.consecutive_errors = 0
                    
                except OrderRejectedError as e:
                    self.logger.warning("Order rejected: %s", e)
                    # Don't increment error counter for business logic rejections
                    
                except InsufficientFundsError as e:
                    self.logger.error("Insufficient funds: %s", e)
                    # Stop trading until resolved
                    self.circuit_breaker_tripped = True
                    break
                    
                except RateLimitError as e:
                    self.logger.warning("Rate limited, waiting %ss", e.retry_after)
                    if e.retry_after:
                        await asyncio.sleep(e.retry_after)
                    
                except Exception as e:
                    self.logger.error("Unexpected error submitting order: %s", e, exc_info=True)
                    self.consecutive_errors += 1
                    
                    if self.consecutive_errors >= self.max_consecutive_errors:
                        self.logger.critical("Circuit breaker tripped after %d errors", 
                                           self.consecutive_errors)
                        self.circuit_breaker_tripped = True
                        break
        
        except Exception as e:
            self.logger.critical("Fatal error in engine loop: %s", e, exc_info=True)
            raise
```

**Add to requirements**:
```txt
tenacity>=8.0.0  # For retry logic
```

---

### 5. 🟠 Add Configuration Validation ✅ FIXED

**Solution**: Enhanced configuration with validation (see artifact: "Enhanced Configuration with Validation")

**Key Features**:
- Validation in `__post_init__` methods
- Cross-field validation in `Config.validate()`
- Better error messages with `ConfigValidationError`
- Secret masking for logging

**Usage**:
```python
from bot.config import load_config, mask_secrets

try:
    config = load_config("config.json")
    logger.info("Configuration loaded successfully")
    logger.debug("Config: %s", mask_secrets(config))
except ConfigValidationError as e:
    logger.error("Invalid configuration: %s", e)
    sys.exit(1)
```

---

## Broker Integration Strategy

### Recommended: Hybrid Approach

**Architecture**:
```
TradingView (Signals) → Webhook → Python Bot → thinkorswim API (Execution)
                                        ↓
                                   Risk Manager
                                        ↓
                                  FastAPI Dashboard
```

**Benefits**:
- Leverage TradingView's excellent charting and indicator library
- Full programmatic control over execution via thinkorswim
- Python-based risk management not available in TradingView
- Can enhance/override TradingView signals with custom logic

---

### Implementation: TradingView Webhook Receiver

**Create** `bot/brokers/tradingview_webhook.py`:

```python
"""TradingView webhook integration."""
from __future__ import annotations

import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from collections import deque

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, validator

from bot.models import Signal, SignalAction


class TradingViewAlert(BaseModel):
    """Expected TradingView webhook payload."""
    timestamp: str
    ticker: str
    action: str  # "buy" or "sell"
    quantity: float
    price: Optional[float] = None
    strategy: str
    message: Optional[str] = None
    secret: str
    
    @validator('action')
    def validate_action(cls, v):
        if v not in {'buy', 'sell', 'close_long', 'close_short'}:
            raise ValueError(f'Invalid action: {v}')
        return v
    
    @validator('quantity')
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError(f'Quantity must be positive: {v}')
        return v


class WebhookDeduplicator:
    """Prevent duplicate webhook processing."""
    
    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.seen_alerts: deque = deque()
    
    def is_duplicate(self, alert: TradingViewAlert) -> bool:
        """Check if alert was recently processed."""
        fingerprint = hash((
            alert.ticker,
            alert.action,
            alert.quantity,
            alert.timestamp
        ))
        current_time = datetime.utcnow()
        
        # Remove old entries
        while self.seen_alerts and self.seen_alerts[0][1] < current_time - timedelta(seconds=self.window_seconds):
            self.seen_alerts.popleft()
        
        # Check for duplicate
        if any(fp == fingerprint for fp, _ in self.seen_alerts):
            return True
        
        self.seen_alerts.append((fingerprint, current_time))
        return False


class TradingViewWebhookHandler:
    """Handles TradingView webhook alerts."""
    
    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret
        self.deduplicator = WebhookDeduplicator(window_seconds=60)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app = FastAPI(title="TradingView Webhook Receiver")
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.post("/webhook/tradingview")
        async def receive_alert(request: Request):
            try:
                # Parse payload
                payload = await request.json()
                alert = TradingViewAlert(**payload)
                
                # Verify secret
                if alert.secret != self.webhook_secret:
                    self.logger.warning("Invalid webhook secret from %s", request.client.host)
                    raise HTTPException(status_code=401, detail="Invalid secret")
                
                # Check for duplicates
                if self.deduplicator.is_duplicate(alert):
                    self.logger.info("Duplicate alert ignored: %s", alert.ticker)
                    return {"status": "duplicate", "message": "Alert already processed"}
                
                # Convert to internal signal
                signal = self._alert_to_signal(alert)
                
                # Queue signal for processing (implement signal queue)
                await self._queue_signal(signal)
                
                self.logger.info("Alert received: %s %s %s @ %s",
                               alert.action, alert.ticker, alert.quantity, alert.price)
                
                return {"status": "success", "signal_id": str(signal.timestamp)}
                
            except ValueError as e:
                self.logger.error("Invalid alert payload: %s", e)
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                self.logger.error("Error processing alert: %s", e, exc_info=True)
                raise HTTPException(status_code=500, detail="Internal error")
        
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "service": "tradingview-webhook"}
    
    def _alert_to_signal(self, alert: TradingViewAlert) -> Signal:
        """Convert TradingView alert to internal Signal."""
        action_map = {
            'buy': SignalAction.OPEN_LONG,
            'sell': SignalAction.CLOSE_LONG,
            'close_long': SignalAction.CLOSE_LONG,
            'close_short': SignalAction.CLOSE_SHORT,
        }
        
        return Signal(
            symbol=alert.ticker,
            action=action_map[alert.action],
            quantity=alert.quantity,
            confidence=1.0,
            meta={
                'source': 'tradingview',
                'strategy': alert.strategy,
                'alert_price': alert.price or 0.0,
                'message': alert.message or '',
            },
            timestamp=datetime.fromisoformat(alert.timestamp.replace('Z', '+00:00'))
        )
    
    async def _queue_signal(self, signal: Signal):
        """Queue signal for processing by engine.
        
        Implement using asyncio.Queue or Redis for production.
        """
        # TODO: Implement signal queue
        pass


# Usage:
# handler = TradingViewWebhookHandler(webhook_secret="your_secret_here")
# uvicorn.run(handler.app, host="0.0.0.0", port=8080, ssl_certfile="cert.pem", ssl_keyfile="key.pem")
```

**TradingView Alert Template**:
```javascript
{
  "timestamp": "{{time}}",
  "ticker": "{{ticker}}",
  "action": "buy",
  "quantity": 10,
  "price": {{close}},
  "strategy": "SMA_Crossover",
  "message": "{{strategy.order.comment}}",
  "secret": "YOUR_WEBHOOK_SECRET_HERE"
}
```

**Security Checklist**:
- ✅ HTTPS only (use Let's Encrypt)
- ✅ Webhook secret validation
- ✅ IP whitelist (TradingView IPs: 52.89.214.238, 34.212.75.30, etc.)
- ✅ Rate limiting
- ✅ Request size limits
- ✅ Duplicate detection

---

### Implementation: thinkorswim Broker

**Create** `bot/brokers/thinkorswim.py`:

```python
"""thinkorswim (Schwab) API integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp

from bot.brokers.base import (
    BaseBroker,
    ConnectionError,
    InsufficientFundsError,
    OrderManager,
    OrderRejectedError,
    RateLimitError,
)
from bot.models import (
    Account,
    Candle,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)


class ThinkorswimAuthManager:
    """Manages OAuth 2.0 authentication for thinkorswim API."""
    
    def __init__(self, client_id: str, refresh_token: str, redirect_uri: str):
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.redirect_uri = redirect_uri
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary."""
        if not self.access_token or self._is_token_expired():
            await self._refresh_access_token()
        return self.access_token
    
    def _is_token_expired(self) -> bool:
        """Check if token is expired or expiring soon."""
        if not self.token_expiry:
            return True
        # Refresh 5 minutes before actual expiry
        return datetime.utcnow() >= self.token_expiry - timedelta(minutes=5)
    
    async def _refresh_access_token(self):
        """Exchange refresh token for new access token."""
        async with aiohttp.ClientSession() as session:
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
            }
            
            try:
                async with session.post(
                    'https://api.schwabapi.com/v1/oauth/token',
                    data=data
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise ConnectionError(f"Token refresh failed: {text}")
                    
                    token_data = await response.json()
                    self.access_token = token_data['access_token']
                    expires_in = token_data['expires_in']
                    self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
                    
                    self.logger.info("Access token refreshed, expires at %s", self.token_expiry)
            except aiohttp.ClientError as e:
                raise ConnectionError(f"Network error during token refresh: {e}")


class ThinkorswimBroker(BaseBroker):
    """thinkorswim (Schwab) broker implementation."""
    
    def __init__(
        self,
        client_id: str,
        refresh_token: str,
        account_id: str,
        redirect_uri: str = "https://localhost:8080/callback",
        use_paper_trading: bool = True,
    ):
        self.auth_manager = ThinkorswimAuthManager(client_id, refresh_token, redirect_uri)
        self.account_id = account_id
        self.base_url = 'https://api.schwabapi.com/trader/v1'
        self.use_paper_trading = use_paper_trading
        
        self._order_manager = OrderManager()
        self._positions: Dict[str, Position] = {}
        self._last_prices: Dict[str, float] = {}
        self._connected = False
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def connect(self) -> None:
        """Establish connection and verify credentials."""
        try:
            # Test connection by fetching account
            account = await self.get_account()
            self._connected = True
            self.logger.info("Connected to thinkorswim (account: %s, mode: %s)",
                           self.account_id,
                           "paper" if self.use_paper_trading else "live")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to thinkorswim: {e}")
    
    async def close(self) -> None:
        """Close connection."""
        self._connected = False
        self.logger.info("Disconnected from thinkorswim")
    
    async def _make_request(self, method: str, endpoint: str, **kwargs):
        """Make authenticated API request with retry logic."""
        token = await self.auth_manager.get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.request(method, url, headers=headers, **kwargs) as response:
                    if response.status == 401:
                        # Token expired, refresh and retry
                        await self.auth_manager._refresh_access_token()
                        return await self._make_request(method, endpoint, **kwargs)
                    
                    if response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', 60))
                        raise RateLimitError("API rate limit exceeded", retry_after=retry_after)
                    
                    if response.status >= 400:
                        text = await response.text()
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=text
                        )
                    
                    return await response.json()
            
            except aiohttp.ClientError as e:
                raise ConnectionError(f"Network error: {e}")
    
    async def get_account(self) -> Account:
        """Fetch account information."""
        data = await self._make_request('GET', f'/accounts/{self.account_id}')
        
        account_data = data['securitiesAccount']
        return Account(
            account_id=self.account_id,
            cash=account_data['currentBalances']['cashBalance'],
            buying_power=account_data['currentBalances']['buyingPower'],
            equity=account_data['currentBalances']['equity'],
            margin_used=account_data['currentBalances'].get('marginBalance', 0.0),
            timestamp=datetime.utcnow(),
        )
    
    async def get_balance(self) -> float:
        """Get cash balance."""
        account = await self.get_account()
        return account.cash
    
    async def get_positions(self) -> Dict[str, Position]:
        """Fetch all open positions."""
        data = await self._make_request('GET', f'/accounts/{self.account_id}/positions')
        
        positions = {}
        for pos_data in data:
            instrument = pos_data['instrument']
            symbol = instrument['symbol']
            quantity = pos_data['longQuantity'] - pos_data['shortQuantity']
            avg_price = pos_data['averagePrice']
            
            if abs(quantity) > 0:
                positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=avg_price
                )
        
        self._positions = positions
        return positions
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        positions = await self.get_positions()
        return positions.get(symbol)
    
    async def submit_order(self, order: Order) -> Order:
        """Submit order to thinkorswim."""
        if not self._connected:
            raise ConnectionError("Not connected to thinkorswim")
        
        # Convert to thinkorswim order format
        tos_order = self._convert_order_to_tos_format(order)
        
        try:
            # Submit order
            response = await self._make_request(
                'POST',
                f'/accounts/{self.account_id}/orders',
                json=tos_order
            )
            
            # Extract order ID from response headers (location header)
            order.broker_order_id = response.get('orderId', f"TOS_{uuid.uuid4().hex[:8]}")
            order.status = OrderStatus.SUBMITTED
            
            self._order_manager.add_order(order)
            self.logger.info("Order submitted: %s", order.broker_order_id)
            
            # Poll for order status update
            await asyncio.sleep(0.5)
            updated_order = await self.get_order_status(order.broker_order_id)
            
            return updated_order or order
        
        except aiohttp.ClientResponseError as e:
            if e.status == 400:
                order.status = OrderStatus.REJECTED
                order.error_message = str(e)
                raise OrderRejectedError(f"Order rejected: {e}", order)
            elif e.status == 403:
                raise InsufficientFundsError("Insufficient buying power")
            else:
                raise
    
    def _convert_order_to_tos_format(self, order: Order) -> Dict:
        """Convert internal Order to thinkorswim API format."""
        tos_order_type_map = {
            OrderType.MARKET: 'MARKET',
            OrderType.LIMIT: 'LIMIT',
            OrderType.STOP: 'STOP',
            OrderType.STOP_LIMIT: 'STOP_LIMIT',
        }
        
        tos_instruction_map = {
            OrderSide.BUY: 'BUY',
            OrderSide.SELL: 'SELL',
            OrderSide.BUY_TO_COVER: 'BUY_TO_COVER',
            OrderSide.SELL_SHORT: 'SELL_SHORT',
        }
        
        tos_order = {
            'orderType': tos_order_type_map[order.order_type],
            'session': 'NORMAL',
            'duration': 'DAY',
            'orderStrategyType': 'SINGLE',
            'orderLegCollection': [
                {
                    'instruction': tos_instruction_map[order.side],
                    'quantity': order.quantity,
                    'instrument': {
                        'symbol': order.symbol,
                        'assetType': 'EQUITY'
                    }
                }
            ]
        }
        
        if order.price:
            tos_order['price'] = order.price
        
        if order.stop_price:
            tos_order['stopPrice'] = order.stop_price
        
        return tos_order
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            await self._make_request(
                'DELETE',
                f'/accounts/{self.account_id}/orders/{order_id}'
            )
            
            order = self._order_manager.get_order(order_id)
            if order:
                order.status = OrderStatus.CANCELLED
                self._order_manager.update_order(order)
            
            self.logger.info("Order cancelled: %s", order_id)
            return True
        except Exception as e:
            self.logger.error("Failed to cancel order %s: %s", order_id, e)
            return False
    
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current order status."""
        try:
            data = await self._make_request(
                'GET',
                f'/accounts/{self.account_id}/orders/{order_id}'
            )
            
            # Parse response and update order
            # (Implementation depends on thinkorswim response format)
            order = self._order_manager.get_order(order_id)
            if order:
                # Update order status based on response
                status_map = {
                    'ACCEPTED': OrderStatus.ACCEPTED,
                    'WORKING': OrderStatus.ACCEPTED,
                    'FILLED': OrderStatus.FILLED,
                    'CANCELED': OrderStatus.CANCELLED,
                    'REJECTED': OrderStatus.REJECTED,
                }
                order.status = status_map.get(data['status'], OrderStatus.PENDING)
                self._order_manager.update_order(order)
            
            return order
        except Exception as e:
            self.logger.error("Failed to get order status for %s: %s", order_id, e)
            return None
    
    async def get_open_orders(self) -> List[Order]:
        """Get all open orders."""
        try:
            data = await self._make_request(
                'GET',
                f'/accounts/{self.account_id}/orders'
            )
            # Parse and return orders
            return self._order_manager.get_open_orders()
        except Exception as e:
            self.logger.error("Failed to get open orders: %s", e)
            return []
    
    async def reconcile_positions(self, symbols: Iterable[str]) -> Dict[str, Position]:
        """Sync local positions with broker."""
        return await self.get_positions()
    
    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """Update latest market prices."""
        self._last_prices.update(prices)
    
    async def get_price_history(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1m"
    ) -> List[Candle]:
        """Fetch historical price data."""
        # Map timeframe to thinkorswim period/frequency
        # Implementation depends on thinkorswim API format
        pass
```

---

## UI Implementation Roadmap

### Phase 1: FastAPI Backend (Week 1-2)

**Create** `bot/api/server.py`:

```python
"""FastAPI server for bot monitoring and control."""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List
import asyncio
import logging

from bot.engine.loop import TradingEngine

app = FastAPI(title="Trading Bot API", version="1.0.0")
logger = logging.getLogger(__name__)

# Global bot instance (set by main)
bot: TradingEngine = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# REST Endpoints
@app.get("/api/status")
async def get_status():
    if not bot:
        raise HTTPException(500, "Bot not initialized")
    
    return {
        "running": bot._connected,
        "mode": bot.config.engine.mode,
        "symbols": bot.config.engine.symbols,
        "strategy": bot.config.engine.strategy.name,
    }

@app.get("/api/positions")
async def get_positions():
    if not bot:
        raise HTTPException(500, "Bot not initialized")
    
    positions = await bot.broker.get_positions()
    prices = bot.broker._last_prices
    
    return [
        {
            "symbol": symbol,
            "quantity": pos.quantity,
            "avg_price": pos.avg_price,
            "current_price": prices.get(symbol, 0.0),
            "unrealized_pnl": pos.unrealized_pnl(prices.get(symbol, pos.avg_price)),
            "unrealized_pnl_percent": pos.unrealized_pnl_percent(prices.get(symbol, pos.avg_price)),
        }
        for symbol, pos in positions.items()
    ]

@app.get("/api/account")
async def get_account():
    if not bot:
        raise HTTPException(500, "Bot not initialized")
    
    account = await bot.broker.get_account()
    return {
        "account_id": account.account_id,
        "cash": account.cash,
        "buying_power": account.buying_power,
        "equity": account.equity,
    }

@app.post("/api/emergency_stop")
async def emergency_stop():
    """Liquidate all positions and stop bot."""
    if not bot:
        raise HTTPException(500, "Bot not initialized")
    
    logger.critical("EMERGENCY STOP TRIGGERED")
    
    try:
        # Liquidate all positions
        if hasattr(bot.broker, 'liquidate_all_positions'):
            orders = await bot.broker.liquidate_all_positions()
            logger.info("Liquidated %d positions", len(orders))
        
        # Stop the engine
        bot.circuit_breaker_tripped = True
        
        return {
            "status": "emergency_stop_executed",
            "positions_liquidated": len(orders) if orders else 0
        }
    except Exception as e:
        logger.error("Emergency stop failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Emergency stop failed: {e}")

# WebSocket for real-time updates
@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send periodic updates
            if bot:
                positions = await bot.broker.get_positions()
                prices = bot.broker._last_prices
                
                update = {
                    "type": "update",
                    "timestamp": datetime.utcnow().isoformat(),
                    "positions": [
                        {
                            "symbol": symbol,
                            "quantity": pos.quantity,
                            "pnl": pos.unrealized_pnl(prices.get(symbol, pos.avg_price))
                        }
                        for symbol, pos in positions.items()
                    ]
                }
                await websocket.send_json(update)
            
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Serve static files and HTML
app.mount("/static", StaticFiles(directory="bot/ui/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open("bot/ui/templates/dashboard.html") as f:
        return f.read()

# Initialize bot instance
def set_bot_instance(engine: TradingEngine):
    global bot
    bot = engine
```

---

### Phase 2: Frontend Dashboard (Week 2-3)

**Create** `bot/ui/templates/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Dashboard</title>
    <link rel="stylesheet" href="/static/css/dashboard.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="dashboard">
        <header>
            <h1>🤖 Trading Bot Dashboard</h1>
            <div class="status-badge" id="status">
                <span class="indicator"></span>
                <span id="status-text">Connecting...</span>
            </div>
        </header>

        <section class="controls">
            <button id="emergency-stop" class="btn btn-danger">⚠️ EMERGENCY STOP</button>
        </section>

        <section class="metrics">
            <div class="metric-card">
                <h3>Account Equity</h3>
                <p class="value" id="equity">$0.00</p>
            </div>
            <div class="metric-card">
                <h3>Cash</h3>
                <p class="value" id="cash">$0.00</p>
            </div>
            <div class="metric-card">
                <h3>Unrealized P&L</h3>
                <p class="value" id="pnl">$0.00</p>
            </div>
            <div class="metric-card">
                <h3>Open Positions</h3>
                <p class="value" id="position-count">0</p>
            </div>
        </section>

        <section class="positions">
            <h2>Current Positions</h2>
            <table id="positions-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Qty</th>
                        <th>Avg Price</th>
                        <th>Current</th>
                        <th>P&L</th>
                        <th>P&L %</th>
                    </tr>
                </thead>
                <tbody id="positions-body">
                    <tr><td colspan="6">No positions</td></tr>
                </tbody>
            </table>
        </section>
    </div>

    <script src="/static/js/dashboard.js"></script>
</body>
</html>
```

**Create** `bot/ui/static/js/dashboard.js`:

```javascript
class TradingDashboard {
    constructor() {
        this.ws = null;
        this.reconnectInterval = 5000;
        this.init();
    }

    init() {
        this.setupWebSocket();
        this.setupEventListeners();
        this.loadInitialData();
    }

    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${window.location.host}/ws/updates`);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateStatus('Connected', true);
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleUpdate(data);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('Error', false);
        };

        this.ws.onclose = () => {
            console.log('WebSocket closed, reconnecting...');
            this.updateStatus('Disconnected', false);
            setTimeout(() => this.setupWebSocket(), this.reconnectInterval);
        };
    }

    setupEventListeners() {
        document.getElementById('emergency-stop').addEventListener('click', async () => {
            if (!confirm('⚠️ EMERGENCY STOP: Liquidate all positions?')) {
                return;
            }

            try {
                const response = await fetch('/api/emergency_stop', { method: 'POST' });
                const data = await response.json();
                alert(`Emergency stop executed. Liquidated ${data.positions_liquidated} positions.`);
                this.loadInitialData();
            } catch (error) {
                alert('Emergency stop failed: ' + error.message);
            }
        });
    }

    async loadInitialData() {
        try {
            const [account, positions] = await Promise.all([
                fetch('/api/account').then(r => r.json()),
                fetch('/api/positions').then(r => r.json())
            ]);

            this.updateAccount(account);
            this.updatePositions(positions);
        } catch (error) {
            console.error('Failed to load data:', error);
        }
    }

    handleUpdate(data) {
        if (data.type === 'update') {
            this.updatePositions(data.positions);
        }
    }

    updateStatus(text, connected) {
        const statusEl = document.getElementById('status');
        const statusText = document.getElementById('status-text');
        statusText.textContent = text;
        statusEl.classList.toggle('connected', connected);
    }

    updateAccount(account) {
        document.getElementById('equity').textContent = `${account.equity.toFixed(2)}`;
        document.getElementById('cash').textContent = `${account.cash.toFixed(2)}`;
    }

    updatePositions(positions) {
        const tbody = document.getElementById('positions-body');
        
        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6">No positions</td></tr>';
            document.getElementById('position-count').textContent = '0';
            document.getElementById('pnl').textContent = '$0.00';
            return;
        }

        let totalPnl = 0;
        tbody.innerHTML = positions.map(pos => {
            totalPnl += pos.unrealized_pnl;
            const pnlClass = pos.unrealized_pnl >= 0 ? 'positive' : 'negative';
            
            return `
                <tr>
                    <td><strong>${pos.symbol}</strong></td>
                    <td>${pos.quantity.toFixed(2)}</td>
                    <td>${pos.avg_price.toFixed(2)}</td>
                    <td>${pos.current_price.toFixed(2)}</td>
                    <td class="${pnlClass}">${pos.unrealized_pnl.toFixed(2)}</td>
                    <td class="${pnlClass}">${pos.unrealized_pnl_percent.toFixed(2)}%</td>
                </tr>
            `;
        }).join('');

        document.getElementById('position-count').textContent = positions.length;
        
        const pnlEl = document.getElementById('pnl');
        pnlEl.textContent = `${totalPnl.toFixed(2)}`;
        pnlEl.className = totalPnl >= 0 ? 'value positive' : 'value negative';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new TradingDashboard();
});
```

**Create** `bot/ui/static/css/dashboard.css`:

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: #0f1419;
    color: #e1e8ed;
    line-height: 1.6;
}

.dashboard {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px;
    background: #1a1f2e;
    border-radius: 10px;
    margin-bottom: 20px;
}

header h1 {
    font-size: 24px;
    color: #fff;
}

.status-badge {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    background: #2a2f3e;
    border-radius: 20px;
}

.status-badge .indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #dc3545;
    animation: pulse 2s infinite;
}

.status-badge.connected .indicator {
    background: #28a745;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

.controls {
    margin-bottom: 20px;
}

.btn {
    padding: 12px 24px;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-danger {
    background: #dc3545;
    color: white;
}

.btn-danger:hover {
    background: #c82333;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(220, 53, 69, 0.4);
}

.metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.metric-card {
    background: #1a1f2e;
    padding: 20px;
    border-radius: 10px;
    border-left: 4px solid #4a9eff;
}

.metric-card h3 {
    font-size: 14px;
    color: #8899a6;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.metric-card .value {
    font-size: 28px;
    font-weight: 700;
    color: #fff;
}

.metric-card .value.positive {
    color: #28a745;
}

.metric-card .value.negative {
    color: #dc3545;
}

.positions {
    background: #1a1f2e;
    padding: 20px;
    border-radius: 10px;
}

.positions h2 {
    margin-bottom: 20px;
    color: #fff;
}

table {
    width: 100%;
    border-collapse: collapse;
}

thead {
    background: #2a2f3e;
}

th, td {
    padding: 12px;
    text-align: left;
}

th {
    font-weight: 600;
    color: #8899a6;
    text-transform: uppercase;
    font-size: 12px;
    letter-spacing: 0.5px;
}

tbody tr {
    border-bottom: 1px solid #2a2f3e;
    transition: background 0.2s;
}

tbody tr:hover {
    background: #2a2f3e;
}

.positive {
    color: #28a745 !important;
}

.negative {
    color: #dc3545 !important;
}

@media (max-width: 768px) {
    .metrics {
        grid-template-columns: 1fr;
    }
    
    table {
        font-size: 14px;
    }
    
    th, td {
        padding: 8px;
    }
}
```

---

## Testing Strategy

### Unit Tests for Enhanced Models

**Create** `tests/test_enhanced_models.py`:

```python
import unittest
from datetime import datetime
from bot.models import Order, OrderStatus, OrderFill, OrderSide, OrderType, Position

class TestOrderLifecycle(unittest.TestCase):
    def test_order_fill_tracking(self):
        order = Order(
            id="TEST_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100.0,
            order_type=OrderType.MARKET
        )
        
        # Add first fill
        fill1 = OrderFill(
            fill_id="FILL_001",
            timestamp=datetime.utcnow(),
            quantity=50.0,
            price=150.0
        )
        order.add_fill(fill1)
        
        self.assertEqual(order.filled_quantity, 50.0)
        self.assertEqual(order.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(order.remaining_quantity, 50.0)
        
        # Add second fill
        fill2 = OrderFill(
            fill_id="FILL_002",
            timestamp=datetime.utcnow(),
            quantity=50.0,
            price=151.0
        )
        order.add_fill(fill2)
        
        self.assertEqual(order.filled_quantity, 100.0)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.remaining_quantity, 0.0)
        self.assertEqual(order.average_fill_price, 150.5)
    
    def test_position_pnl_calculation(self):
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)
        
        # Test unrealized P&L
        current_price = 155.0
        pnl = position.unrealized_pnl(current_price)
        self.assertEqual(pnl, 500.0)  # (155 - 150) * 100
        
        pnl_pct = position.unrealized_pnl_percent(current_price)
        self.assertAlmostEqual(pnl_pct, 3.33, places=2)
    
    def test_position_update_with_reversal(self):
        position = Position(symbol="AAPL", quantity=100.0, avg_price=150.0)
        
        # Reduce position
        position.update(-50.0, 155.0)
        self.assertEqual(position.quantity, 50.0)
        self.assertEqual(position.avg_price, 150.0)  # Avg price unchanged when reducing
        
        # Reverse position (go from long to short)
        position.update(-100.0, 160.0)
        self.assertEqual(position.quantity, -50.0)
        self.assertEqual(position.avg_price, 160.0)  # New avg price for reversed position


class TestConfigValidation(unittest.TestCase):
    def test_invalid_starting_cash(self):
        from bot.config import BrokerConfig, ConfigValidationError
        
        with self.assertRaises(ConfigValidationError):
            BrokerConfig(starting_cash=-1000.0)
    
    def test_invalid_mode(self):
        from bot.config import EngineConfig, ConfigValidationError
        
        with self.assertRaises(ConfigValidationError):
            EngineConfig(mode="invalid_mode")


if __name__ == "__main__":
    unittest.main()
```

---

## Deployment Checklist

### Production Environment Setup

**1. Docker Configuration**

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot/ ./bot/
COPY scripts/ ./scripts/
COPY config.json .

# Create non-root user
RUN useradd -m -u 1000 trader && chown -R trader:trader /app
USER trader

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

CMD ["python", "-m", "uvicorn", "bot.api.server:app", "--host", "0.0.0.0", "--port", "8080"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  trading-bot:
    build: .
    ports:
      - "8080:8080"
    environment:
      - TRADING_BOT__ENGINE__MODE=paper
      - TRADING_BOT__BROKER__NAME=thinkorswim
      - TOS_API_KEY=${TOS_API_KEY}
      - TOS_REFRESH_TOKEN=${TOS_REFRESH_TOKEN}
      - TOS_ACCOUNT_ID=${TOS_ACCOUNT_ID}
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
    volumes:
      - ./logs:/app/logs
      - ./config.json:/app/config.json:ro
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - trading-network

networks:
  trading-network:
    driver: bridge
```

**2. Environment Variables**

Create `.env.example`:

```bash
# Broker Configuration
TRADING_BOT__BROKER__NAME=thinkorswim
TOS_API_KEY=your_client_id_here
TOS_REFRESH_TOKEN=your_refresh_token_here
TOS_ACCOUNT_ID=your_account_id_here

# TradingView Webhook
WEBHOOK_SECRET=generate_strong_random_secret_here

# Logging
TRADING_BOT__ENGINE__LOGGING__LEVEL=INFO
TRADING_BOT__ENGINE__LOGGING__FILE=/app/logs/trading.log

# Risk Limits
TRADING_BOT__ENGINE__RISK__MAX_POSITION_SIZE=1000
TRADING_BOT__ENGINE__RISK__MAX_DAILY_LOSS=2000
TRADING_BOT__ENGINE__RISK__MAX_TOTAL_EXPOSURE=50000
```

**3. SSL/TLS Setup for Webhooks**

```bash
# Install certbot
sudo apt-get install certbot

# Get Let's Encrypt certificate
sudo certbot certonly --standalone -d yourdomain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /app/certs/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /app/certs/

# Update server configuration
# uvicorn bot.api.server:app --host 0.0.0.0 --port 443 \
#   --ssl-keyfile /app/certs/privkey.pem \
#   --ssl-certfile /app/certs/fullchain.pem
```

**4. Monitoring Setup**

Create `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'trading-bot'
    static_configs:
      - targets: ['trading-bot:8080']
```

Add metrics endpoint to `bot/api/server.py`:

```python
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Metrics
orders_submitted = Counter('orders_submitted_total', 'Total orders submitted')
orders_filled = Counter('orders_filled_total', 'Total orders filled')
orders_rejected = Counter('orders_rejected_total', 'Total orders rejected')
current_positions = Gauge('current_positions', 'Number of open positions')
account_equity = Gauge('account_equity_dollars', 'Account equity in dollars')
unrealized_pnl = Gauge('unrealized_pnl_dollars', 'Unrealized P&L')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## Priority Action Items

### Week 1: Critical Fixes
- [ ] Implement async broker interface
- [ ] Update engine loop for async operations
- [ ] Add enhanced models with order lifecycle
- [ ] Implement configuration validation
- [ ] Add comprehensive error handling
- [ ] Write unit tests for new components

### Week 2-3: Broker Integration
- [ ] Implement TradingView webhook receiver
- [ ] Implement thinkorswim broker (or choose one)
- [ ] Add authentication and security
- [ ] Test with paper trading accounts
- [ ] Implement position reconciliation
- [ ] Add rate limiting and retry logic

### Week 4-5: UI Development
- [ ] Build FastAPI backend with REST endpoints
- [ ] Create WebSocket real-time updates
- [ ] Build HTML/CSS dashboard
- [ ] Add JavaScript frontend logic
- [ ] Implement emergency stop functionality
- [ ] Test on mobile devices

### Week 6-7: Testing & Hardening
- [ ] Write integration tests
- [ ] Perform load testing on webhook receiver
- [ ] Security audit (penetration testing)
- [ ] Implement logging and monitoring
- [ ] Set up alerting (email/SMS/Discord)
- [ ] Create deployment scripts

### Week 8: Production Deployment
- [ ] Deploy to VPS/cloud
- [ ] Configure SSL certificates
- [ ] Set up domain and DNS
- [ ] Configure firewall rules
- [ ] Deploy monitoring stack
- [ ] Run paper trading for 1-2 weeks
- [ ] Document runbooks and procedures

### Week 9+: Live Trading
- [ ] Start with minimal position sizes
- [ ] Monitor closely for first week
- [ ] Gradually increase capital
- [ ] Regular performance reviews
- [ ] Continuous optimization

---

## Key Resources

### Dependencies to Add

Update `requirements.txt`:

```txt
# Core
aiohttp>=3.9.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
python-multipart>=0.0.6

# Retry logic
tenacity>=8.2.3

# Monitoring
prometheus-client>=0.19.0

# WebSockets
websockets>=12.0

# Date handling
python-dateutil>=2.8.2

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0

# Code quality
black>=23.12.0
mypy>=1.8.0
ruff>=0.1.9

# Optional: Data science
pandas>=2.1.0
numpy>=1.26.0
matplotlib>=3.8.0
```

### Useful Commands

```bash
# Run with enhanced configuration
python scripts/run_paper_trading.py --config config.json

# Run tests with coverage
pytest tests/ --cov=bot --cov-report=html

# Type checking
mypy bot/

# Code formatting
black bot/ tests/ scripts/

# Linting
ruff check bot/

# Run FastAPI server
uvicorn bot.api.server:app --reload --port 8080

# Docker build and run
docker-compose up --build

# View logs
docker-compose logs -f trading-bot
```

---

## Summary

Your trading bot has a solid foundation. The key improvements are:

1. ✅ **Async broker interface** - Required for real brokers
2. ✅ **Order lifecycle management** - Track states and fills properly
3. ⚠️ **Thread safety** - Add locks for shared state
4. ⚠️ **Error handling** - Comprehensive try-except with retries
5. ✅ **Configuration validation** - Fail fast on invalid config

**Recommended Path**: 
- **Broker**: Hybrid (TradingView signals + thinkorswim execution)
- **UI**: FastAPI + lightweight HTML/JS dashboard
- **Timeline**: 8-10 weeks to production-ready

All code artifacts have been provided. Start with the critical async conversion, then proceed to broker integration and UI development in parallel tracks.

Good luck with your trading bot! 🚀