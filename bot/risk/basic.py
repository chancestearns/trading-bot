"""Basic risk management implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from bot.models import MarketState, PortfolioState, Position, Signal, SignalAction
from bot.risk.base import RiskManager


@dataclass(slots=True)
class BasicRiskConfig:
    max_position_size: float
    max_daily_loss: float
    starting_cash: float


class BasicRiskManager(RiskManager):
    """Simple risk checks enforcing per-symbol position caps and drawdown limits."""

    def __init__(self, config: BasicRiskConfig) -> None:
        self.config = config

    def validate_signal(
        self,
        signal: Signal,
        portfolio_state: PortfolioState,
        market_state: MarketState,
    ) -> Signal | None:
        del market_state

        if signal.action in {SignalAction.CLOSE_LONG, SignalAction.CLOSE_SHORT}:
            return signal

        if self._daily_loss_exceeded(portfolio_state):
            return None

        if signal.action in {SignalAction.OPEN_LONG, SignalAction.OPEN_SHORT}:
            return self._validate_open_signal(signal, portfolio_state.positions)
        return signal

    def _validate_open_signal(self, signal: Signal, positions: Dict[str, Position]) -> Signal | None:
        position = positions.get(signal.symbol)
        current_qty = abs(position.quantity) if position else 0.0
        available = max(0.0, self.config.max_position_size - current_qty)
        if available <= 0.0:
            return None
        requested_qty = abs(signal.quantity)
        adjusted_qty = min(requested_qty, available)
        if adjusted_qty <= 0:
            return None
        if adjusted_qty != abs(signal.quantity):
            return Signal(
                symbol=signal.symbol,
                action=signal.action,
                quantity=adjusted_qty,
                meta=signal.meta | {"capped_quantity": adjusted_qty},
            )
        return signal

    def _daily_loss_exceeded(self, portfolio_state: PortfolioState) -> bool:
        loss = self.config.starting_cash - portfolio_state.cash
        return loss >= self.config.max_daily_loss > 0
