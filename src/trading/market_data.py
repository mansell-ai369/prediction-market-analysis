"""Market-data sources for the trading bot.

``SimulatedMarketData`` produces a reproducible, mean-reverting price feed so the
demo can run offline. ``KalshiMarketData`` wraps the repo's existing read-only
``KalshiClient`` to pull live quotes from the public Kalshi API.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.common.trading import Side


@dataclass
class MarketQuote:
    """A snapshot of best prices for a binary market (cents)."""

    ticker: str
    yes_price: int
    no_price: int


def _clamp_price(price: int) -> int:
    return max(1, min(99, price))


class MarketDataSource(ABC):
    """Provides current quotes and, for simulated feeds, advances time."""

    @abstractmethod
    def get_quotes(self) -> list[MarketQuote]:
        """Return the current quote for every tracked market."""

    def step(self) -> None:
        """Advance the feed by one tick. No-op for live sources."""
        return None

    def get_price(self, ticker: str, side: Side) -> int | None:
        """Return the current price (cents) for one side of a market."""
        for quote in self.get_quotes():
            if quote.ticker == ticker:
                return quote.yes_price if side is Side.YES else quote.no_price
        return None


class SimulatedMarketData(MarketDataSource):
    """Reproducible mean-reverting price simulator.

    Each market has a hidden fair value; its YES price performs a noisy random
    walk that drifts back toward that fair value. A price-history-based strategy
    (see ``MeanReversionStrategy``) can therefore find genuine edge without any
    look-ahead into the hidden fair value.
    """

    _DEFAULT_MARKETS = {
        "PRES-2028-DEM": 52,
        "FED-CUT-MAR": 38,
        "BTC-100K-EOY": 64,
        "SPX-ATH-Q3": 45,
        "GDP-POSITIVE-Q4": 71,
    }

    def __init__(
        self,
        fair_values: dict | None = None,
        *,
        seed: int = 42,
        reversion: float = 0.25,
        volatility: float = 4.0,
    ):
        self._rng = random.Random(seed)
        self._reversion = reversion
        self._volatility = volatility
        fair_values = fair_values or dict(self._DEFAULT_MARKETS)
        self._fair: dict = {}
        self._price: dict = {}
        for ticker, fair in fair_values.items():
            self._fair[ticker] = fair
            # Start a little away from fair so early ticks have tradeable signal.
            self._price[ticker] = _clamp_price(fair + self._rng.randint(-8, 8))

    def step(self) -> None:
        for ticker, price in self._price.items():
            drift = self._reversion * (self._fair[ticker] - price)
            noise = self._rng.gauss(0, self._volatility)
            self._price[ticker] = _clamp_price(round(price + drift + noise))

    def get_quotes(self) -> list[MarketQuote]:
        return [MarketQuote(t, p, 100 - p) for t, p in self._price.items()]


class KalshiMarketData(MarketDataSource):
    """Live quotes from the public Kalshi API via the existing read-only client.

    Provide the tickers you want to trade; prices come from each market's
    ``yes_bid``/``yes_ask`` midpoint. Requires network access to Kalshi.
    """

    def __init__(self, tickers: list):
        # Imported lazily so the simulated demo has no hard dependency on it.
        from src.indexers.kalshi.client import KalshiClient

        self._tickers = list(tickers)
        self._client = KalshiClient()

    def get_quotes(self) -> list[MarketQuote]:
        quotes: list[MarketQuote] = []
        for ticker in self._tickers:
            market = self._client.get_market(ticker)
            yes_bid = getattr(market, "yes_bid", None)
            yes_ask = getattr(market, "yes_ask", None)
            if yes_bid is None or yes_ask is None:
                continue
            yes_price = _clamp_price(round((yes_bid + yes_ask) / 2))
            quotes.append(MarketQuote(ticker, yes_price, 100 - yes_price))
        return quotes
