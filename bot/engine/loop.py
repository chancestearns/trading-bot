"""Main orchestration loop for the trading bot with async support."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bot.brokers.base import (
    BaseBroker,
    ConnectionError,
    InsufficientFundsError,
    OrderRejectedError,
    RateLimitError,
)
from bot.config import Config
from bot.data_providers.base import BaseDataProvider
from bot.models import (
    Candle,
    MarketState,
    Order,
    OrderSide,
    OrderType,
    PortfolioState,
    Signal,
    SignalAction,
    Tick,
)
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

        # Circuit breaker for error handling
        self.circuit_breaker_tripped = False
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5

    async def run(self, iterations: Optional[int] = None) -> None:
        mode = self.config.engine.mode
        self.logger.info("Starting trading engine in %s mode", mode)

        try:
            await self.data_provider.connect()
            await self.broker.connect()

            # Reconcile positions on startup
            await self.broker.reconcile_positions(self.config.engine.symbols)

            self.strategy.on_start(self.config.engine.strategy, self.strategy.logger)

            if mode == "backtest":
                await self._run_backtest()
            else:
                await self._run_streaming(iterations)

        except Exception as e:
            self.logger.critical("Fatal error in trading engine: %s", e, exc_info=True)
            raise
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
            history[symbol] = self.data_provider.get_historical_data(
                symbol, start, end, timeframe
            )

        candles_history: Dict[str, List[Candle]] = defaultdict(list)
        max_length = max(len(series) for series in history.values()) if history else 0

        for index in range(max_length):
            if self.circuit_breaker_tripped:
                self.logger.warning("Circuit breaker tripped, stopping backtest")
                break

            latest_prices: Dict[str, float] = {}
            for symbol, series in history.items():
                if index >= len(series):
                    continue
                candle = series[index]
                candles_history[symbol].append(candle)
                latest_prices[symbol] = candle.close

            if not latest_prices:
                continue

            await self._process_iteration(candles_history, latest_prices)

    async def _run_streaming(self, iterations: Optional[int]) -> None:
        symbols = self.config.engine.symbols
        candles_history: Dict[str, List[Candle]] = defaultdict(list)
        iteration_count = 0

        async for ticks in self.data_provider.stream_prices(symbols):
            if self.circuit_breaker_tripped:
                self.logger.warning("Circuit breaker tripped, stopping trading")
                break

            latest_prices = {symbol: tick.price for symbol, tick in ticks.items()}
            timestamp = datetime.utcnow()

            for symbol, price in latest_prices.items():
                candles_history[symbol].append(
                    self._tick_to_candle(symbol, price, timestamp)
                )
                candles_history[symbol] = candles_history[symbol][-500:]

            await self._process_iteration(candles_history, latest_prices, ticks=ticks)

            iteration_count += 1
            if iterations is not None and iteration_count >= iterations:
                break

        await asyncio.sleep(0)

    async def _process_iteration(
        self,
        candles_history: Dict[str, List[Candle]],
        latest_prices: Dict[str, float],
        ticks: Optional[Dict[str, Tick]] = None,
    ) -> None:
        """Process a single iteration with comprehensive error handling."""
        try:
            self.broker.update_market_prices(latest_prices)

            market_state = MarketState(
                candles={
                    symbol: list(series) for symbol, series in candles_history.items()
                },
                ticks=ticks or {},
            )

            raw_signals = self.strategy.on_bar(market_state, self.portfolio_state)
            signals = list(raw_signals) if raw_signals else []

            for signal in signals:
                await self._process_signal(signal, market_state, latest_prices)

            # Update portfolio state
            self.portfolio_state.cash = await self.broker.get_balance()
            self.portfolio_state.positions = await self.broker.get_positions()

        except Exception as e:
            self.logger.error("Error in engine iteration: %s", e, exc_info=True)
            self.consecutive_errors += 1

            if self.consecutive_errors >= self.max_consecutive_errors:
                self.logger.critical(
                    "Circuit breaker tripped after %d consecutive errors",
                    self.consecutive_errors,
                )
                self.circuit_breaker_tripped = True

    async def _process_signal(
        self, signal: Signal, market_state: MarketState, latest_prices: Dict[str, float]
    ) -> None:
        """Process a single signal with error handling and retry logic."""
        try:
            # Risk check
            approved = self.risk_manager.validate_signal(
                signal, self.portfolio_state, market_state
            )

            if not approved:
                self.logger.debug("Signal rejected by risk manager: %s", signal)
                return

            # Convert to order
            order = self._signal_to_order(approved, latest_prices)
            if order is None:
                return

            # Submit with retry logic
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

        except RateLimitError as e:
            self.logger.warning("Rate limited, waiting %ss", e.retry_after)
            if e.retry_after:
                await asyncio.sleep(e.retry_after)

        except ConnectionError as e:
            self.logger.error("Connection error: %s", e)
            self.consecutive_errors += 1

        except Exception as e:
            self.logger.error(
                "Unexpected error processing signal: %s", e, exc_info=True
            )
            self.consecutive_errors += 1

    async def _submit_order_with_retry(
        self, order: Order, max_retries: int = 3
    ) -> Order:
        """Submit order with exponential backoff retry."""
        for attempt in range(max_retries):
            try:
                result = await self.broker.submit_order(order)
                self.logger.info("Submitted order %s", order)
                return result

            except ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    self.logger.warning(
                        "Connection error on attempt %d, retrying in %ds: %s",
                        attempt + 1,
                        wait_time,
                        e,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

    def _signal_to_order(
        self, signal: Signal, latest_prices: Dict[str, float]
    ) -> Optional[Order]:
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
            SignalAction.CLOSE_SHORT: OrderSide.BUY_TO_COVER,
            SignalAction.CLOSE_LONG: OrderSide.SELL,
            SignalAction.OPEN_SHORT: OrderSide.SELL_SHORT,
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
    """Factory helper returning a configured TradingEngine."""
    return TradingEngine(
        config=config,
        data_provider=data_provider,
        broker=broker,
        strategy=strategy,
        risk_manager=risk_manager,
    )
