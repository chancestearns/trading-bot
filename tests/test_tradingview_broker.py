"""Tests for TradingView webhook integration."""

from __future__ import annotations

import pytest
from datetime import datetime

from bot.brokers.paper import PaperBroker
from bot.brokers.tradingview import TradingViewBroker, TradingViewWebhookPayload
from bot.models import Signal, SignalAction


class TestTradingViewWebhookPayload:
    """Test TradingView webhook payload parsing."""

    def test_parse_buy_signal(self):
        """Test parsing a buy signal."""
        data = {
            "timestamp": "2025-11-11T10:30:00Z",
            "ticker": "AAPL",
            "action": "buy",
            "price": 150.25,
            "quantity": 10,
            "strategy": "SMA_Crossover",
            "message": "SMA 20 crossed above SMA 50",
            "secret": "test_secret"
        }
        
        payload = TradingViewWebhookPayload(data)
        
        assert payload.ticker == "AAPL"
        assert payload.action == "buy"
        assert payload.price == 150.25
        assert payload.quantity == 10
        assert payload.strategy == "SMA_Crossover"

    def test_to_signal_buy(self):
        """Test converting buy payload to signal."""
        data = {
            "ticker": "AAPL",
            "action": "buy",
            "price": 150.25,
            "quantity": 10,
        }
        
        payload = TradingViewWebhookPayload(data)
        signal = payload.to_signal()
        
        assert signal.symbol == "AAPL"
        assert signal.action == SignalAction.OPEN_LONG
        assert signal.quantity == 10
        assert signal.meta["price"] == 150.25

    def test_to_signal_sell(self):
        """Test converting sell payload to signal."""
        data = {
            "ticker": "TSLA",
            "action": "sell",
            "price": 200.0,
            "quantity": 5,
        }
        
        payload = TradingViewWebhookPayload(data)
        signal = payload.to_signal()
        
        assert signal.symbol == "TSLA"
        assert signal.action == SignalAction.CLOSE_LONG
        assert signal.quantity == 5

    def test_to_signal_short(self):
        """Test converting short payload to signal."""
        data = {
            "ticker": "MSFT",
            "action": "short",
            "price": 300.0,
            "quantity": 10,
        }
        
        payload = TradingViewWebhookPayload(data)
        signal = payload.to_signal()
        
        assert signal.symbol == "MSFT"
        assert signal.action == SignalAction.OPEN_SHORT
        assert signal.quantity == 10


class TestTradingViewBroker:
    """Test TradingView broker integration."""

    @pytest.fixture
    def paper_broker(self):
        """Create a paper broker for testing."""
        return PaperBroker(starting_cash=100000)

    @pytest.fixture
    def tv_broker(self, paper_broker):
        """Create a TradingView broker for testing."""
        return TradingViewBroker(
            execution_broker=paper_broker,
            webhook_secret="test_secret",
        )

    @pytest.mark.asyncio
    async def test_connect(self, tv_broker):
        """Test broker connection."""
        await tv_broker.connect()
        account = await tv_broker.get_account()
        assert account.cash == 100000
        await tv_broker.close()

    def test_validate_webhook_valid(self, tv_broker):
        """Test webhook validation with valid payload."""
        payload = {
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
            "secret": "test_secret"
        }
        
        assert tv_broker.validate_webhook(payload) is True

    def test_validate_webhook_missing_fields(self, tv_broker):
        """Test webhook validation with missing fields."""
        payload = {
            "ticker": "AAPL",
            "action": "buy",
            # Missing quantity
        }
        
        assert tv_broker.validate_webhook(payload) is False

    def test_validate_webhook_wrong_secret(self, tv_broker):
        """Test webhook validation with wrong secret."""
        payload = {
            "ticker": "AAPL",
            "action": "buy",
            "quantity": 10,
            "price": 150.0,
            "secret": "wrong_secret"
        }
        
        assert tv_broker.validate_webhook(payload) is False

    def test_is_duplicate_signal(self, tv_broker):
        """Test duplicate signal detection."""
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.OPEN_LONG,
            quantity=10,
            timestamp=datetime.utcnow(),
        )
        
        # First time should not be duplicate
        assert tv_broker.is_duplicate_signal(signal) is False
        
        # Second time should be duplicate
        assert tv_broker.is_duplicate_signal(signal) is True

    @pytest.mark.asyncio
    async def test_process_webhook(self, tv_broker):
        """Test processing a webhook."""
        await tv_broker.connect()
        
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "ticker": "AAPL",
            "action": "buy",
            "price": 150.0,
            "quantity": 10,
            "secret": "test_secret"
        }
        
        # Update market prices for the execution broker
        tv_broker.execution_broker.update_market_prices({"AAPL": 150.0})
        
        order = await tv_broker.process_webhook(payload)
        
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.quantity == 10
        
        await tv_broker.close()

    @pytest.mark.asyncio
    async def test_process_webhook_duplicate(self, tv_broker):
        """Test that duplicate webhooks are skipped."""
        await tv_broker.connect()
        
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "ticker": "AAPL",
            "action": "buy",
            "price": 150.0,
            "quantity": 10,
            "secret": "test_secret"
        }
        
        tv_broker.execution_broker.update_market_prices({"AAPL": 150.0})
        
        # First webhook should process
        order1 = await tv_broker.process_webhook(payload)
        assert order1 is not None
        
        # Duplicate should be skipped
        order2 = await tv_broker.process_webhook(payload)
        assert order2 is None
        
        await tv_broker.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
