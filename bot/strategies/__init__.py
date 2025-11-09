"""Strategy interfaces and built-in examples."""

from .base import Strategy
from .example_sma import SimpleMovingAverageStrategy

__all__ = ["Strategy", "SimpleMovingAverageStrategy"]
