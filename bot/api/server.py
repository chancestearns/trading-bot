"""FastAPI server for trading bot dashboard and webhook receiver."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Will be set by the bot on startup
_bot_instance = None


def set_bot_instance(bot):
    """Set the bot instance for API access."""
    global _bot_instance
    _bot_instance = bot


def get_bot():
    """Dependency to get bot instance."""
    if _bot_instance is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    return _bot_instance


# Pydantic models for API
class BotStatus(BaseModel):
    running: bool
    mode: str
    uptime_seconds: float
    strategy: str
    symbols: List[str]


class PositionResponse(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


class OrderResponse(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    price: Optional[float]
    status: str
    filled_quantity: float
    timestamp: str
    broker_order_id: Optional[str]


class PerformanceMetrics(BaseModel):
    total_pnl: float
    daily_pnl: float
    win_rate: float
    sharpe_ratio: Optional[float]
    max_drawdown: float
    total_trades: int
    equity: float


class WebhookPayload(BaseModel):
    """TradingView webhook payload."""
    
    timestamp: Optional[str] = None
    ticker: str
    action: str
    price: float
    quantity: float
    strategy: Optional[str] = None
    message: Optional[str] = None
    secret: Optional[str] = None


# Create FastAPI app
app = FastAPI(
    title="Trading Bot API",
    description="Real-time trading bot monitoring and control",
    version="1.0.0",
)

logger = logging.getLogger(__name__)

# Mount static files
import os
from pathlib import Path

ui_dir = Path(__file__).parent.parent / "ui"
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=str(ui_dir / "static")), name="static")


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected (total: %d)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(self.active_connections))

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("Error broadcasting to websocket: %s", e)
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# REST API Endpoints

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the dashboard."""
    template_path = Path(__file__).parent.parent / "ui" / "templates" / "dashboard.html"
    if template_path.exists():
        with open(template_path, 'r') as f:
            return f.read()
    return HTMLResponse("<h1>Trading Bot API</h1><p>Dashboard template not found</p>")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard."""
    return await root()


@app.get("/api/status", response_model=BotStatus)
async def get_status(bot=Depends(get_bot)):
    """Get bot status."""
    try:
        uptime = (datetime.utcnow() - bot.start_time).total_seconds() if hasattr(bot, 'start_time') else 0
        return BotStatus(
            running=getattr(bot, 'is_running', False),
            mode=bot.config.engine.mode,
            uptime_seconds=uptime,
            strategy=bot.config.engine.strategy.name,
            symbols=bot.config.engine.symbols,
        )
    except Exception as e:
        logger.error("Error getting status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions", response_model=List[PositionResponse])
async def get_positions(bot=Depends(get_bot)):
    """Get current positions."""
    try:
        positions = await bot.broker.get_positions()
        result = []
        
        for symbol, pos in positions.items():
            current_price = bot.data_provider._last_prices.get(symbol, pos.avg_price) if hasattr(bot.data_provider, '_last_prices') else pos.avg_price
            
            result.append(PositionResponse(
                symbol=symbol,
                quantity=pos.quantity,
                avg_price=pos.avg_price,
                current_price=current_price,
                unrealized_pnl=pos.unrealized_pnl(current_price),
                unrealized_pnl_percent=pos.unrealized_pnl_percent(current_price),
            ))
        
        return result
    except Exception as e:
        logger.error("Error getting positions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders", response_model=List[OrderResponse])
async def get_orders(
    status: Optional[str] = None,
    limit: int = 100,
    bot=Depends(get_bot)
):
    """Get recent orders."""
    try:
        orders = await bot.broker.get_open_orders()
        
        # Filter by status if provided
        if status:
            orders = [o for o in orders if o.status.value == status]
        
        # Limit results
        orders = orders[-limit:]
        
        return [
            OrderResponse(
                id=order.id,
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                order_type=order.order_type.value,
                price=order.price,
                status=order.status.value,
                filled_quantity=order.filled_quantity,
                timestamp=order.timestamp.isoformat(),
                broker_order_id=order.broker_order_id,
            )
            for order in orders
        ]
    except Exception as e:
        logger.error("Error getting orders: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/performance", response_model=PerformanceMetrics)
async def get_performance(bot=Depends(get_bot)):
    """Get performance metrics."""
    try:
        account = await bot.broker.get_account()
        
        # Calculate metrics
        starting_cash = bot.config.engine.broker.starting_cash
        total_pnl = account.equity - starting_cash
        daily_pnl = total_pnl  # Simplified - could track daily separately
        
        return PerformanceMetrics(
            total_pnl=total_pnl,
            daily_pnl=daily_pnl,
            win_rate=0.0,  # Would calculate from trade history
            sharpe_ratio=None,
            max_drawdown=0.0,  # Would calculate from equity curve
            total_trades=0,  # Would track in trade history
            equity=account.equity,
        )
    except Exception as e:
        logger.error("Error getting performance: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/account")
async def get_account(bot=Depends(get_bot)):
    """Get account information."""
    try:
        account = await bot.broker.get_account()
        return {
            "account_id": account.account_id,
            "cash": account.cash,
            "buying_power": account.buying_power,
            "equity": account.equity,
            "margin_used": account.margin_used,
            "day_trades_remaining": account.day_trades_remaining,
        }
    except Exception as e:
        logger.error("Error getting account: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Control endpoints

@app.post("/api/start")
async def start_bot(bot=Depends(get_bot)):
    """Start the trading bot."""
    try:
        if getattr(bot, 'is_running', False):
            raise HTTPException(status_code=400, detail="Bot is already running")
        
        # Start bot in background task
        asyncio.create_task(bot.run())
        bot.is_running = True
        
        await manager.broadcast({"type": "status", "data": {"running": True}})
        return {"status": "started"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error starting bot: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stop")
async def stop_bot(bot=Depends(get_bot)):
    """Stop the trading bot."""
    try:
        if not getattr(bot, 'is_running', False):
            raise HTTPException(status_code=400, detail="Bot is not running")
        
        bot.is_running = False
        # Bot should check is_running flag in its loop
        
        await manager.broadcast({"type": "status", "data": {"running": False}})
        return {"status": "stopped"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error stopping bot: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/emergency_stop")
async def emergency_stop(bot=Depends(get_bot)):
    """Emergency stop - stop bot and liquidate all positions."""
    try:
        logger.warning("EMERGENCY STOP INITIATED")
        
        # Stop the bot
        bot.is_running = False
        
        # Liquidate all positions
        positions = await bot.broker.get_positions()
        liquidation_orders = []
        
        for symbol, position in positions.items():
            if position.is_flat:
                continue
            
            # Create closing order
            from bot.models import Order, OrderSide, OrderType
            import uuid
            
            side = OrderSide.SELL if position.is_long else OrderSide.BUY_TO_COVER
            order = Order(
                id=str(uuid.uuid4()),
                symbol=symbol,
                side=side,
                quantity=abs(position.quantity),
                order_type=OrderType.MARKET,
            )
            
            executed = await bot.broker.submit_order(order)
            liquidation_orders.append(executed.broker_order_id)
        
        await manager.broadcast({
            "type": "emergency_stop",
            "data": {"liquidated_orders": liquidation_orders}
        })
        
        return {
            "status": "emergency_stop_executed",
            "liquidated_positions": len(liquidation_orders),
            "order_ids": liquidation_orders,
        }
    except Exception as e:
        logger.error("Error in emergency stop: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# TradingView Webhook endpoint

@app.post("/webhook/tradingview")
async def tradingview_webhook(
    payload: WebhookPayload,
    x_signature: Optional[str] = Header(None),
    bot=Depends(get_bot)
):
    """Receive TradingView webhook alerts."""
    try:
        # Check if bot has TradingView broker
        from bot.brokers.tradingview import TradingViewBroker
        
        if not isinstance(bot.broker, TradingViewBroker):
            raise HTTPException(
                status_code=400,
                detail="Bot is not configured with TradingView broker"
            )
        
        # Process webhook
        order = await bot.broker.process_webhook(payload.dict(), x_signature)
        
        if order is None:
            return {"status": "skipped", "reason": "duplicate_signal"}
        
        # Broadcast to WebSocket clients
        await manager.broadcast({
            "type": "webhook_received",
            "data": {
                "symbol": payload.ticker,
                "action": payload.action,
                "quantity": payload.quantity,
                "order_id": order.broker_order_id,
            }
        })
        
        return {
            "status": "success",
            "order_id": order.broker_order_id,
            "symbol": order.symbol,
        }
        
    except Exception as e:
        logger.error("Error processing TradingView webhook: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint for real-time updates

@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time bot updates."""
    await manager.connect(websocket)
    
    try:
        bot = get_bot()
        
        # Send initial state
        await websocket.send_json({
            "type": "connected",
            "data": {"message": "Connected to trading bot"}
        })
        
        # Keep connection alive and send periodic updates
        while True:
            try:
                # Send position updates every 2 seconds
                await asyncio.sleep(2)
                
                positions = await bot.broker.get_positions()
                position_data = []
                
                for symbol, pos in positions.items():
                    current_price = bot.data_provider._last_prices.get(symbol, pos.avg_price) if hasattr(bot.data_provider, '_last_prices') else pos.avg_price
                    position_data.append({
                        "symbol": symbol,
                        "quantity": pos.quantity,
                        "pnl": pos.unrealized_pnl(current_price),
                    })
                
                await websocket.send_json({
                    "type": "position_update",
                    "data": position_data,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in websocket update loop: %s", e)
                await asyncio.sleep(5)
                
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# Health check endpoint

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server."""
    uvicorn.run(app, host=host, port=port, log_level="info")
