"""TradingView webhook receiver broker integration."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from bot.brokers.base import BaseBroker, BrokerError, OrderRejectedError
from bot.models import (
    Account,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    SignalAction,
)


class TradingViewWebhookPayload:
    """Parsed TradingView webhook payload."""

    def __init__(self, data: dict):
        self.timestamp = data.get("timestamp", datetime.utcnow().isoformat())
        self.ticker = data.get("ticker", "")
        self.action = data.get("action", "")
        self.price = float(data.get("price", 0))
        self.quantity = float(data.get("quantity", 0))
        self.strategy = data.get("strategy", "")
        self.message = data.get("message", "")
        self.secret = data.get("secret", "")

    def to_signal(self) -> Signal:
        """Convert webhook payload to internal Signal."""
        action_map = {
            "buy": SignalAction.OPEN_LONG,
            "sell": SignalAction.CLOSE_LONG,
            "short": SignalAction.OPEN_SHORT,
            "cover": SignalAction.CLOSE_SHORT,
            "buy_to_cover": SignalAction.CLOSE_SHORT,
            "sell_short": SignalAction.OPEN_SHORT,
        }

        action = action_map.get(self.action.lower(), SignalAction.OPEN_LONG)

        return Signal(
            symbol=self.ticker,
            action=action,
            quantity=abs(self.quantity),
            confidence=1.0,
            meta={
                "source": "tradingview",
                "strategy": self.strategy,
                "message": self.message,
                "price": self.price,
            },
            timestamp=datetime.fromisoformat(self.timestamp)
            if isinstance(self.timestamp, str)
            else self.timestamp,
        )


class TradingViewBroker(BaseBroker):
    """
    Broker that receives signals from TradingView webhooks and routes them to an execution broker.
    
    This is a wrapper broker that translates TradingView alerts into orders
    and delegates actual execution to another broker (paper, thinkorswim, etc.).
    """

    def __init__(
        self,
        execution_broker: BaseBroker,
        webhook_secret: str,
        order_type: OrderType = OrderType.MARKET,
        limit_offset_percent: float = 0.1,
    ):
        """
        Initialize TradingView webhook broker.
        
        Args:
            execution_broker: The underlying broker to execute orders
            webhook_secret: Secret key for webhook validation
            order_type: Default order type (MARKET or LIMIT)
            limit_offset_percent: If using LIMIT orders, offset from market price
        """
        self.execution_broker = execution_broker
        self.webhook_secret = webhook_secret
        self.order_type = order_type
        self.limit_offset_percent = limit_offset_percent
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Track webhook signal deduplication
        self._seen_signals: Dict[str, datetime] = {}
        self._signal_ttl_seconds = 60

    async def connect(self) -> None:
        """Connect the execution broker."""
        await self.execution_broker.connect()
        self.logger.info("TradingView broker connected")

    async def close(self) -> None:
        """Close the execution broker connection."""
        await self.execution_broker.close()
        self.logger.info("TradingView broker disconnected")

    async def get_account(self) -> Account:
        """Delegate to execution broker."""
        return await self.execution_broker.get_account()

    async def get_balance(self) -> float:
        """Delegate to execution broker."""
        return await self.execution_broker.get_balance()

    async def get_positions(self) -> Dict[str, Position]:
        """Delegate to execution broker."""
        return await self.execution_broker.get_positions()

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Delegate to execution broker."""
        return await self.execution_broker.get_position(symbol)

    def validate_webhook(self, payload: dict, signature: Optional[str] = None) -> bool:
        """
        Validate incoming webhook payload.
        
        Args:
            payload: The webhook payload dict
            signature: Optional HMAC signature for verification
            
        Returns:
            True if webhook is valid
        """
        # Check required fields
        required_fields = ["ticker", "action", "quantity"]
        if not all(field in payload for field in required_fields):
            self.logger.warning("Webhook missing required fields: %s", payload)
            return False

        # Verify secret if provided in payload
        if "secret" in payload:
            if payload["secret"] != self.webhook_secret:
                self.logger.warning("Webhook secret mismatch")
                return False

        # Verify HMAC signature if provided
        if signature:
            payload_str = str(sorted(payload.items()))
            expected_sig = hmac.new(
                self.webhook_secret.encode(), payload_str.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected_sig):
                self.logger.warning("Webhook HMAC signature invalid")
                return False

        return True

    def is_duplicate_signal(self, signal: Signal) -> bool:
        """Check if this signal was recently processed (prevent duplicates)."""
        # Create unique signal fingerprint
        fingerprint = f"{signal.symbol}:{signal.action.value}:{signal.quantity}:{signal.timestamp.isoformat()}"
        signal_hash = hashlib.md5(fingerprint.encode()).hexdigest()

        # Clean up old signals
        now = datetime.utcnow()
        self._seen_signals = {
            k: v
            for k, v in self._seen_signals.items()
            if (now - v).total_seconds() < self._signal_ttl_seconds
        }

        # Check if seen
        if signal_hash in self._seen_signals:
            self.logger.info("Duplicate signal detected, skipping: %s", fingerprint)
            return True

        # Mark as seen
        self._seen_signals[signal_hash] = now
        return False

    async def process_webhook(self, payload: dict, signature: Optional[str] = None) -> Optional[Order]:
        """
        Process an incoming TradingView webhook and execute the trade.
        
        Args:
            payload: Webhook payload dict
            signature: Optional HMAC signature
            
        Returns:
            The executed order or None if rejected
        """
        # Validate webhook
        if not self.validate_webhook(payload, signature):
            raise BrokerError("Invalid webhook payload or signature")

        # Parse payload
        webhook = TradingViewWebhookPayload(payload)
        signal = webhook.to_signal()

        # Check for duplicates
        if self.is_duplicate_signal(signal):
            return None

        self.logger.info(
            "Processing TradingView signal: %s %s %.2f shares @ %.2f",
            signal.action.value,
            signal.symbol,
            signal.quantity,
            webhook.price,
        )

        # Convert signal to order
        order = await self._signal_to_order(signal, webhook.price)

        # Execute order through underlying broker
        try:
            executed_order = await self.execution_broker.submit_order(order)
            self.logger.info("TradingView signal executed: %s", executed_order.broker_order_id)
            return executed_order
        except Exception as e:
            self.logger.error("Failed to execute TradingView signal: %s", e, exc_info=True)
            raise

    async def _signal_to_order(self, signal: Signal, market_price: float) -> Order:
        """Convert a signal to an order."""
        # Determine order side
        if signal.action in {SignalAction.OPEN_LONG, SignalAction.CLOSE_SHORT}:
            side = OrderSide.BUY if signal.action == SignalAction.OPEN_LONG else OrderSide.BUY_TO_COVER
        else:
            side = OrderSide.SELL if signal.action == SignalAction.CLOSE_LONG else OrderSide.SELL_SHORT

        # Calculate limit price if needed
        price = None
        if self.order_type == OrderType.LIMIT:
            offset = market_price * (self.limit_offset_percent / 100)
            if side in {OrderSide.BUY, OrderSide.BUY_TO_COVER}:
                price = market_price + offset
            else:
                price = max(0.01, market_price - offset)

        return Order(
            id=str(uuid.uuid4()),
            symbol=signal.symbol,
            side=side,
            quantity=signal.quantity,
            order_type=self.order_type,
            price=price,
            timestamp=datetime.utcnow(),
        )

    async def submit_order(self, order: Order) -> Order:
        """Delegate to execution broker."""
        return await self.execution_broker.submit_order(order)

    async def cancel_order(self, order_id: str) -> bool:
        """Delegate to execution broker."""
        return await self.execution_broker.cancel_order(order_id)

    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Delegate to execution broker."""
        return await self.execution_broker.get_order_status(order_id)

    async def get_open_orders(self) -> List[Order]:
        """Delegate to execution broker."""
        return await self.execution_broker.get_open_orders()

    async def reconcile_positions(self, symbols: Iterable[str]) -> Dict[str, Position]:
        """Delegate to execution broker."""
        return await self.execution_broker.reconcile_positions(symbols)

    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """Delegate to execution broker."""
        self.execution_broker.update_market_prices(prices)
