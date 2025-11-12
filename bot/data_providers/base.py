"""Abstract interfaces for market data providers."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import AsyncIterator, Dict, Iterable, List

from bot.models import Candle, Tick


class BaseDataProvider(abc.ABC):
    """Abstract base class for all data providers."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish any external connections (e.g. WebSocket, REST)."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close any external connections and release resources."""

    @abc.abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> List[Candle]:
        """Return historical candles for the requested period."""

    @abc.abstractmethod
    def stream_prices(self, symbols: Iterable[str]) -> AsyncIterator[Dict[str, Tick]]:
        """Yield tick data as it becomes available.

        Implementations should be async generators yielding a mapping from
        symbol to :class:`bot.models.Tick`.
        """
