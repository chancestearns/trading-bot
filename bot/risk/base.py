"""Risk management interface definitions."""
from __future__ import annotations

import abc
from typing import Optional

from bot.models import MarketState, PortfolioState, Signal


class RiskManager(abc.ABC):
    """Base interface for risk management modules."""

    @abc.abstractmethod
    def validate_signal(
        self,
        signal: Signal,
        portfolio_state: PortfolioState,
        market_state: MarketState,
    ) -> Optional[Signal]:
        """Return the signal if approved, otherwise ``None``."""
