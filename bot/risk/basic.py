"""Basic risk management implementation."""

from __future__ import annotations

from dataclasses import dataclass
from bot.models import MarketState, PortfolioState, Position, Signal, SignalAction
from bot.risk.base import RiskManager


@dataclass(slots=True)
class BasicRiskConfig:
    """Configuration for BasicRiskManager.

    max_position_size:
        Maximum absolute position size per symbol. If 0 or negative, no cap.
    max_daily_loss:
        Maximum allowed loss (starting_cash – current cash). If exceeded,
        new opening positions are blocked.
    starting_cash:
        Reference starting equity used to measure daily loss.
    """

    max_position_size: float
    max_daily_loss: float
    starting_cash: float


class BasicRiskManager(RiskManager):
    """Risk manager enforcing a position cap per symbol and a daily drawdown limit."""

    def __init__(self, config: BasicRiskConfig) -> None:
        self.config = config

    def validate_signal(
        self,
        signal: Signal,
        portfolio_state: PortfolioState,
        market_state: MarketState,
    ) -> Signal | None:
        """Return the approved signal (optionally size‑adjusted), or None if rejected."""

        # Always allow closing positions, regardless of limits
        if signal.action in {SignalAction.CLOSE_LONG, SignalAction.CLOSE_SHORT}:
            return signal

        # Block new opens once daily loss exceeds the configured limit
        if self._daily_loss_exceeded(portfolio_state):
            return None

        # If no position size cap is configured, accept the signal
        if self.config.max_position_size <= 0:
            return signal

        desired_qty = abs(signal.quantity)
        if desired_qty <= 0:
            return signal

        # Current absolute position for this symbol (0 if flat)
        current_qty = abs(
            portfolio_state.positions.get(
                signal.symbol,
                Position(signal.symbol, 0.0, 0.0),
            ).quantity
        )

        # Reject if already at or above the cap
        if current_qty >= self.config.max_position_size:
            return None

        remaining = self.config.max_position_size - current_qty
        if desired_qty <= remaining:
            # Within the cap, no adjustment needed
            return signal

        # Cap the order size to the remaining allowable quantity
        adjusted_qty = remaining
        return Signal(
            symbol=signal.symbol,
            action=signal.action,
            quantity=adjusted_qty,
            meta={**signal.meta, "capped_quantity": adjusted_qty, "adjusted": 1.0},
        )

    def _daily_loss_exceeded(self, portfolio_state: PortfolioState) -> bool:
        loss = self.config.starting_cash - portfolio_state.cash
        return self.config.max_daily_loss > 0 and loss >= self.config.max_daily_loss
