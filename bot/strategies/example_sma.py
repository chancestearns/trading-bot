"""Example simple moving average crossover strategy."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, Iterable, List

from bot.models import MarketState, PortfolioState, Signal, SignalAction
from bot.strategies.base import Strategy


@dataclass(slots=True)
class SimpleMovingAverageConfig:
    short_window: int = 5
    long_window: int = 20
    trade_quantity: float = 10.0


class SimpleMovingAverageStrategy(Strategy):
    """Minimal moving average crossover example.

    The strategy goes long when the short moving average crosses above the long
    moving average and exits the position when the inverse happens. This module
    is intentionally simple and heavily commented to act as a template for more
    sophisticated strategies.
    """

    def __init__(self, config: SimpleMovingAverageConfig | None = None) -> None:
        super().__init__()
        self.config = config or SimpleMovingAverageConfig()
        self._trend_state: Dict[str, str] = {}

    def on_start(self, config: object | None = None, logger: logging.Logger | None = None) -> None:
        # Update defaults from engine configuration if provided. Users can pass
        # arbitrary parameters in the config file which will be forwarded here.
        overrides: Dict[str, object] = {}
        if isinstance(config, dict):
            overrides = config.get("params", {}) or {}
        elif hasattr(config, "params"):
            overrides = getattr(config, "params") or {}
        strategy_logger = logger or self.logger
        self.config.short_window = int(overrides.get("short_window", self.config.short_window))
        self.config.long_window = int(overrides.get("long_window", self.config.long_window))
        self.config.trade_quantity = float(overrides.get("trade_quantity", self.config.trade_quantity))
        if self.config.short_window >= self.config.long_window:
            raise ValueError("short_window must be strictly smaller than long_window")
        strategy_logger.info(
            "Starting SMA strategy with short=%s long=%s quantity=%s",
            self.config.short_window,
            self.config.long_window,
            self.config.trade_quantity,
        )

    def on_bar(
        self,
        market_state: MarketState,
        portfolio_state: PortfolioState,
    ) -> Iterable[Signal]:
        signals: List[Signal] = []
        for symbol, candles in market_state.candles.items():
            if len(candles) < self.config.long_window:
                continue
            closes = [candle.close for candle in candles]
            short_avg = sum(closes[-self.config.short_window :]) / self.config.short_window
            long_avg = sum(closes[-self.config.long_window :]) / self.config.long_window

            current_trend = self._trend_state.get(symbol, "flat")
            position = portfolio_state.positions.get(symbol)
            if short_avg > long_avg and current_trend != "long":
                signals.append(
                    Signal(
                        symbol=symbol,
                        action=SignalAction.OPEN_LONG,
                        quantity=self.config.trade_quantity,
                        meta={"short_avg": short_avg, "long_avg": long_avg},
                    )
                )
                self._trend_state[symbol] = "long"
            elif short_avg < long_avg and (current_trend == "long" or (position and position.quantity > 0)):
                signals.append(
                    Signal(
                        symbol=symbol,
                        action=SignalAction.CLOSE_LONG,
                        quantity=self.config.trade_quantity,
                        meta={"short_avg": short_avg, "long_avg": long_avg},
                    )
                )
                self._trend_state[symbol] = "flat"
        return signals

    def on_end(self) -> None:
        self.logger.info("SMA strategy finished execution")
