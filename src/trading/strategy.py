"""Trading strategies: turn market quotes into desired target positions.

A strategy never places orders directly. It only expresses *what it wants to
hold* (``TargetPosition``); the execution engine and risk manager decide whether
and how to get there. This separation keeps risk controls authoritative.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque

from src.common.trading import Side


class TargetPosition:
    """Desired total contracts to hold on one side of a market."""

    def __init__(self, ticker: str, side: Side, count: int):
        self.ticker = ticker
        self.side = side
        self.count = count

    def __repr__(self) -> str:
        return f"TargetPosition({self.ticker}, {self.side.value}, {self.count})"


class Strategy(ABC):
    """Base class for signal generation."""

    @abstractmethod
    def generate_targets(
        self,
        quotes: list,
        positions: list,
    ) -> list:
        """Return desired target positions given current quotes and holdings."""


class MeanReversionStrategy(Strategy):
    """Long-only YES mean reversion around each market's own moving average.

    For every market we track a rolling window of YES prices. When the price
    dips ``entry_band`` cents below its moving average we target a full long
    position (betting on reversion up); when it rises ``exit_band`` cents above
    the average we flatten. Otherwise we hold. No look-ahead, no shorting.
    """

    def __init__(
        self,
        *,
        window: int = 8,
        entry_band: float = 3.0,
        exit_band: float = 2.0,
        size: int = 20,
    ):
        self.window = window
        self.entry_band = entry_band
        self.exit_band = exit_band
        self.size = size
        self._history: dict = defaultdict(lambda: deque(maxlen=window))

    def generate_targets(self, quotes: list, positions: list) -> list:
        held = {(p.ticker, p.side): p.count for p in positions}
        targets: list = []

        for quote in quotes:
            history = self._history[quote.ticker]
            history.append(quote.yes_price)
            current_held = held.get((quote.ticker, Side.YES), 0)

            # Not enough history yet: hold whatever we have.
            if len(history) < self.window:
                targets.append(TargetPosition(quote.ticker, Side.YES, current_held))
                continue

            mean = sum(history) / len(history)
            if quote.yes_price <= mean - self.entry_band:
                targets.append(TargetPosition(quote.ticker, Side.YES, self.size))
            elif quote.yes_price >= mean + self.exit_band:
                targets.append(TargetPosition(quote.ticker, Side.YES, 0))
            else:
                targets.append(TargetPosition(quote.ticker, Side.YES, current_held))

        return targets
