"""Base classes for trading strategies."""
from __future__ import annotations

import abc
import logging
from typing import Iterable, Optional

from bot.models import MarketState, PortfolioState, Signal


class Strategy(abc.ABC):
    """Base interface for trading strategies."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def on_start(self, config: object | None = None, logger: Optional[logging.Logger] = None) -> None:
        """Hook executed before the engine starts processing data.

        Parameters
        ----------
        config:
            Raw strategy configuration object or mapping. The concrete
            implementation decides how to interpret it.
        logger:
            Logger instance strategies can use for structured logging. When not
            provided the strategy should fall back to ``self.logger``.
        """

    @abc.abstractmethod
    def on_bar(
        self,
        market_state: MarketState,
        portfolio_state: PortfolioState,
    ) -> Iterable[Signal] | None:
        """Process the latest market data and emit zero or more signals."""

    def on_end(self) -> None:
        """Hook executed once the engine has stopped."""
