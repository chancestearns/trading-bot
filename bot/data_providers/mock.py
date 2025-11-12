"""Mock data provider generating deterministic synthetic data."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import AsyncIterator, Dict, Iterable, List

from bot.data_providers.base import BaseDataProvider
from bot.models import Candle, Tick


class MockDataProvider(BaseDataProvider):
    """Simple deterministic data source for tests and examples."""

    def __init__(self, seed: int = 42, base_price: float = 100.0) -> None:
        self._rng = random.Random(seed)
        self._base_price = base_price
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> List[Candle]:
        del timeframe  # Not used in the mock implementation
        candles: List[Candle] = []
        current = start
        price = self._base_price
        while current <= end:
            change = self._rng.uniform(-1, 1)
            open_price = price
            close_price = max(1.0, open_price + change)
            high = max(open_price, close_price) + self._rng.random()
            low = min(open_price, close_price) - self._rng.random()
            volume = abs(change) * 100 + self._rng.uniform(10, 50)
            candles.append(
                Candle(
                    symbol=symbol,
                    timestamp=current,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close_price,
                    volume=volume,
                )
            )
            price = close_price
            current += timedelta(minutes=1)
        return candles

    async def _generate_tick(self, symbol: str, last_price: float) -> Tick:
        change = self._rng.uniform(-0.5, 0.5)
        price = max(1.0, last_price + change)
        return Tick(symbol=symbol, timestamp=datetime.utcnow(), price=price)

    async def stream_prices(
        self, symbols: Iterable[str]
    ) -> AsyncIterator[Dict[str, Tick]]:
        if not self._connected:
            raise RuntimeError("Data provider is not connected. Call connect() first.")

        prices = {symbol: self._base_price for symbol in symbols}
        while self._connected:
            updates: Dict[str, Tick] = {}
            for symbol in list(prices.keys()):
                tick = await self._generate_tick(symbol, prices[symbol])
                prices[symbol] = tick.price
                updates[symbol] = tick
            yield updates
            await asyncio.sleep(0.5)
