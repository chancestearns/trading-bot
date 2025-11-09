from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from bot.models import Candle, MarketState, PortfolioState, Position, SignalAction
from bot.strategies.example_sma import SimpleMovingAverageConfig, SimpleMovingAverageStrategy


class SimpleSMATest(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = SimpleMovingAverageStrategy(
            SimpleMovingAverageConfig(short_window=2, long_window=3, trade_quantity=1)
        )
        self.strategy.on_start({"params": {}})
        self.portfolio = PortfolioState(cash=100_000.0)

    def _build_candles(self, prices):
        base_time = datetime.utcnow()
        return [
            Candle(
                symbol="AAPL",
                timestamp=base_time + timedelta(minutes=index),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1.0,
            )
            for index, price in enumerate(prices)
        ]

    def test_generates_open_long_signal(self):
        candles = self._build_candles([100, 101, 105])
        market_state = MarketState(candles={"AAPL": candles})
        signals = self.strategy.on_bar(market_state, self.portfolio)
        self.assertTrue(signals)
        self.assertEqual(SignalAction.OPEN_LONG, signals[0].action)

    def test_generates_close_long_signal(self):
        candles_open = self._build_candles([100, 105, 110])
        self.strategy.on_bar(MarketState(candles={"AAPL": candles_open}), self.portfolio)
        self.portfolio.positions["AAPL"] = Position(symbol="AAPL", quantity=1.0, avg_price=105.0)
        candles_close = self._build_candles([100, 105, 110, 90])
        market_state = MarketState(candles={"AAPL": candles_close})
        signals = self.strategy.on_bar(market_state, self.portfolio)
        self.assertTrue(signals)
        self.assertEqual(SignalAction.CLOSE_LONG, signals[0].action)


if __name__ == "__main__":
    unittest.main()
