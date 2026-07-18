"""The trading bot loop that ties every layer together."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.common.trading import Side, TradingClient
from src.trading.execution import ExecutionEngine
from src.trading.market_data import MarketDataSource
from src.trading.risk import RiskManager
from src.trading.strategy import Strategy

logger = logging.getLogger("trading.bot")


@dataclass
class TickReport:
    tick: int
    equity: int
    cash: int
    open_positions: int
    fills: int
    halted: bool


class TradingBot:
    """Runs the market-data -> strategy -> risk -> execution loop."""

    def __init__(
        self,
        client: TradingClient,
        strategy: Strategy,
        risk: RiskManager,
        market_data: MarketDataSource,
        execution: ExecutionEngine,
    ):
        self.client = client
        self.strategy = strategy
        self.risk = risk
        self.market_data = market_data
        self.execution = execution

    def _equity(self) -> int:
        cash = self.client.get_balance()
        mark = 0
        for pos in self.client.get_positions():
            price = self.market_data.get_price(pos.ticker, pos.side)
            if price is not None:
                mark += pos.market_value(price)
        return cash + mark

    def step_once(self, tick: int) -> tuple:
        """Run exactly one loop iteration.

        Returns ``(report, fills)``. When the kill switch trips, no orders are
        placed and ``report.halted`` is True.
        """
        self.market_data.step()

        equity = self._equity()
        if self.risk.update_kill_switch(equity):
            logger.warning("kill switch active at tick %d (equity %dc) - halting", tick, equity)
            report = TickReport(tick, equity, self.client.get_balance(), len(self.client.get_positions()), 0, True)
            return report, []

        quotes = self.market_data.get_quotes()
        targets = self.strategy.generate_targets(quotes, self.client.get_positions())
        fills = self.execution.reconcile(targets)

        equity = self._equity()
        report = TickReport(
            tick=tick,
            equity=equity,
            cash=self.client.get_balance(),
            open_positions=len(self.client.get_positions()),
            fills=len(fills),
            halted=False,
        )
        return report, fills

    def run(self, ticks: int) -> list:
        """Run ``ticks`` iterations of the loop; returns a report per tick."""
        reports: list = []

        for tick in range(1, ticks + 1):
            report, _ = self.step_once(tick)
            reports.append(report)
            if report.halted:
                break
            logger.info(
                "tick %02d | equity %6dc | cash %6dc | positions %d | fills %d",
                report.tick,
                report.equity,
                report.cash,
                report.open_positions,
                report.fills,
            )

        return reports

    def flatten(self) -> None:
        """Close every open position at the current market price."""
        from src.common.trading import Action, Order, OrderType

        for pos in self.client.get_positions():
            self.client.place_order(Order(pos.ticker, pos.side, Action.SELL, pos.count, OrderType.MARKET))

    def snapshot(self) -> dict:
        """Human-readable summary of the current account state."""
        positions = []
        for pos in self.client.get_positions():
            price = self.market_data.get_price(pos.ticker, pos.side)
            positions.append(
                {
                    "ticker": pos.ticker,
                    "side": pos.side.value if isinstance(pos.side, Side) else pos.side,
                    "count": pos.count,
                    "avg_price": pos.avg_price,
                    "mark": price,
                    "unrealized": (price - pos.avg_price) * pos.count if price is not None else None,
                }
            )
        return {
            "cash": self.client.get_balance(),
            "equity": self._equity(),
            "positions": positions,
        }
