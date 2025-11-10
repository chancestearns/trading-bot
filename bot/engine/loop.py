"""Main orchestration loop for the trading bot."""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bot.brokers.base import BaseBroker
from bot.config import Config
from bot.data_providers.base import BaseDataProvider
from bot.models import Candle, MarketState, Order, OrderSide, OrderType, PortfolioState, Signal, SignalAction, Tick
from bot.risk.base import RiskManager
from bot.strategies.base import Strategy


class TradingEngine:
    """Coordinates data ingestion, strategy execution, and order routing."""

    def __init__(
        self,
        config: Config,
        data_provider: BaseDataProvider,
        broker: BaseBroker,
        strategy: Strategy,
        risk_manager: RiskManager,
    ) -> None:
        self.config = config
        self.data_provider = data_provider
        self.broker = broker
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.portfolio_state = PortfolioState(cash=config.engine.broker.starting_cash)

    async def run(self, iterations: Optional[int] = None) -> None:
        mode = self.config.engine.mode
        self.logger.info("Starting trading engine in %s mode", mode)
        await self.data_provider.connect()
        await self.broker.connect()
        self.broker.sync_with_market_data(self.config.engine.symbols)
        self.strategy.on_start(self.config.engine.strategy, self.strategy.logger)
        try:
            if mode == "backtest":
                await self._run_backtest()
            else:
                await self._run_streaming(iterations)
        finally:
            await self.data_provider.close()
            await self.broker.close()
            self.strategy.on_end()
            self.logger.info("Engine finished execution")

    async def _run_backtest(self) -> None:
        symbols = self.config.engine.symbols
        timeframe = self.config.engine.timeframe
        end = datetime.utcnow()
        start = end - timedelta(minutes=200)
        history: Dict[str, List[Candle]] = {}
        for symbol in symbols:
            history[symbol] = self.data_provider.get_historical_data(symbol, start, end, timeframe)
        candles_history: Dict[str, List[Candle]] = defaultdict(list)
        max_length = max(len(series) for series in history.values()) if history else 0
        for index in range(max_length):
            latest_prices: Dict[str, float] = {}
            for symbol, series in history.items():
                if index >= len(series):
                    continue
                candle = series[index]
                candles_history[symbol].append(candle)
                latest_prices[symbol] = candle.close
            if not latest_prices:
                continue
            self._process_iteration(candles_history, latest_prices)

    async def _run_streaming(self, iterations: Optional[int]) -> None:
        symbols = self.config.engine.symbols
        candles_history: Dict[str, List[Candle]] = defaultdict(list)
        iteration_count = 0
        async for ticks in self.data_provider.stream_prices(symbols):
            latest_prices = {symbol: tick.price for symbol, tick in ticks.items()}
            timestamp = datetime.utcnow()
            for symbol, price in latest_prices.items():
                candles_history[symbol].append(self._tick_to_candle(symbol, price, timestamp))
                candles_history[symbol] = candles_history[symbol][-500:]
            self._process_iteration(candles_history, latest_prices, ticks=ticks)
            iteration_count += 1
            if iterations is not None and iteration_count >= iterations:
                break
        await asyncio.sleep(0)

    def _process_iteration(
        self,
        candles_history: Dict[str, List[Candle]],
        latest_prices: Dict[str, float],
        ticks: Optional[Dict[str, Tick]] = None,
    ) -> None:
        self.broker.update_market_prices(latest_prices)
        market_state = MarketState(
            candles={symbol: list(series) for symbol, series in candles_history.items()},
            ticks=ticks or {},
        )
        raw_signals = self.strategy.on_bar(market_state, self.portfolio_state)
        signals = list(raw_signals) if raw_signals else []
        for signal in signals:
            approved = self.risk_manager.validate_signal(signal, self.portfolio_state, market_state)
            if not approved:
                self.logger.debug("Signal rejected by risk manager: %s", signal)
                continue
            order = self._signal_to_order(approved, latest_prices)
            if order is None:
                continue
            self.broker.submit_order(order)
            self.logger.info("Submitted order %s", order)
        self.portfolio_state.cash = self.broker.get_balance()
        self.portfolio_state.positions = self.broker.get_open_positions()

    def _signal_to_order(self, signal: Signal, latest_prices: Dict[str, float]) -> Optional[Order]:
        price = latest_prices.get(signal.symbol)
        if price is None:
            self.logger.warning("No price available for symbol %s", signal.symbol)
            return None
        side = self._signal_to_side(signal.action)
        if side is None:
            self.logger.warning("Unsupported signal action %s", signal.action)
            return None
        order = Order(
            id=str(uuid.uuid4()),
            symbol=signal.symbol,
            side=side,
            quantity=signal.quantity,
            order_type=OrderType.MARKET,
            price=price,
        )
        return order

    @staticmethod
    def _signal_to_side(action: SignalAction) -> Optional[OrderSide]:
        mapping = {
            SignalAction.OPEN_LONG: OrderSide.BUY,
            SignalAction.CLOSE_SHORT: OrderSide.BUY,
            SignalAction.CLOSE_LONG: OrderSide.SELL,
            SignalAction.OPEN_SHORT: OrderSide.SELL,
        }
        return mapping.get(action)

    @staticmethod
    def _tick_to_candle(symbol: str, price: float, timestamp: datetime) -> Candle:
        return Candle(
            symbol=symbol,
            timestamp=timestamp,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0.0,
        )


def build_engine(
    config: Config,
    data_provider: BaseDataProvider,
    broker: BaseBroker,
    strategy: Strategy,
    risk_manager: RiskManager,
) -> TradingEngine:
    """Factory helper returning a configured :class:`TradingEngine`."""

    return TradingEngine(
        config=config,
        data_provider=data_provider,
        broker=broker,
        strategy=strategy,
        risk_manager=risk_manager,
    )
