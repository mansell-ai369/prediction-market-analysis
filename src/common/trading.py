"""Broker-agnostic trading primitives and a local paper-trading client.

This module defines the core value types (orders, fills, positions) and an
abstract ``TradingClient`` interface. Concrete live clients (e.g. Kalshi under
``src/trading/kalshi_client.py``) implement the same interface, so a bot can
switch between paper and live trading simply by swapping the client.

All monetary amounts are integer **cents**, matching Kalshi conventions where a
contract trades at 1-99c and settles at 100c ($1) if it resolves in your favour.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """Which side of a binary market a position is on."""

    YES = "yes"
    NO = "no"


class Action(str, Enum):
    """Whether an order opens (buy) or closes (sell) exposure."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class Order:
    """A single order to submit to a trading client."""

    ticker: str
    side: Side
    action: Action
    count: int
    type: OrderType = OrderType.MARKET
    price: int | None = None  # limit price in cents; ignored for market orders
    client_order_id: str | None = None


@dataclass
class Fill:
    """The result of an order that executed."""

    ticker: str
    side: Side
    action: Action
    count: int
    price: int  # execution price in cents
    cash_delta: int  # signed cash change in cents (negative when buying)


@dataclass
class Position:
    """A net long position on one side of a market."""

    ticker: str
    side: Side
    count: int
    avg_price: int  # average entry price in cents

    @property
    def cost_basis(self) -> int:
        """Total cash originally paid to open this position, in cents."""
        return self.count * self.avg_price

    def market_value(self, current_price: int) -> int:
        """Mark-to-market value of the position at ``current_price`` (cents)."""
        return self.count * current_price


@dataclass
class OrderResult:
    """Outcome of a ``place_order`` call."""

    accepted: bool
    order: Order
    fill: Fill | None = None
    reason: str = ""


class TradingClient(ABC):
    """Abstract trading interface shared by paper and live implementations."""

    @abstractmethod
    def get_balance(self) -> int:
        """Available cash in cents."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """All currently held (non-zero) positions."""

    @abstractmethod
    def place_order(self, order: Order) -> OrderResult:
        """Submit an order and return its outcome."""

    def get_position(self, ticker: str, side: Side) -> Position | None:
        """Convenience lookup for a single position; ``None`` if not held."""
        for pos in self.get_positions():
            if pos.ticker == ticker and pos.side == side:
                return pos
        return None

    def cancel_all(self) -> None:
        """Cancel all resting orders. No-op for market-only clients."""
        return None


# Callback returning the current market price (cents) for a (ticker, side),
# or None if the market is unknown. Used by the paper client to simulate fills.
PriceFn = Callable[[str, Side], Optional[int]]


@dataclass
class PaperTradingClient(TradingClient):
    """In-memory client that simulates fills against a live price callback.

    No network and no real money: buys/sells fill immediately at the price
    returned by ``price_fn`` (subject to limit-price marketability), while cash
    and positions are tracked locally. Ideal for validating a strategy and the
    execution/risk pipeline end-to-end before going live.
    """

    starting_cash: int
    price_fn: PriceFn
    _cash: int = field(init=False)
    _positions: dict = field(init=False, default_factory=dict)
    fills: list = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self._cash = self.starting_cash

    def get_balance(self) -> int:
        return self._cash

    def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.count > 0]

    def _fill_price(self, order: Order, market_price: int) -> int | None:
        if order.type is OrderType.MARKET or order.price is None:
            return market_price
        # Limit order: only fills if marketable at the requested price.
        if order.action is Action.BUY and market_price <= order.price:
            return market_price
        if order.action is Action.SELL and market_price >= order.price:
            return market_price
        return None

    def place_order(self, order: Order) -> OrderResult:
        if order.count <= 0:
            return OrderResult(False, order, reason="order count must be positive")

        market_price = self.price_fn(order.ticker, order.side)
        if market_price is None:
            return OrderResult(False, order, reason=f"no market price for {order.ticker}")

        fill_price = self._fill_price(order, market_price)
        if fill_price is None:
            return OrderResult(False, order, reason="limit price not marketable")

        key = (order.ticker, order.side)
        if order.action is Action.BUY:
            cost = order.count * fill_price
            if cost > self._cash:
                return OrderResult(False, order, reason="insufficient balance")
            self._cash -= cost
            existing = self._positions.get(key)
            if existing is None or existing.count == 0:
                self._positions[key] = Position(order.ticker, order.side, order.count, fill_price)
            else:
                total = existing.count + order.count
                existing.avg_price = round((existing.cost_basis + cost) / total)
                existing.count = total
            fill = Fill(order.ticker, order.side, order.action, order.count, fill_price, -cost)
        else:  # SELL
            existing = self._positions.get(key)
            held = existing.count if existing else 0
            if order.count > held:
                return OrderResult(False, order, reason="cannot sell more than held")
            proceeds = order.count * fill_price
            self._cash += proceeds
            existing.count -= order.count
            fill = Fill(order.ticker, order.side, order.action, order.count, fill_price, proceeds)

        self.fills.append(fill)
        return OrderResult(True, order, fill=fill)

    def equity(self) -> int:
        """Total account value: cash + mark-to-market value of open positions."""
        total = self._cash
        for pos in self.get_positions():
            price = self.price_fn(pos.ticker, pos.side)
            if price is not None:
                total += pos.market_value(price)
        return total
