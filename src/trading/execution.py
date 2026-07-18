"""Execution engine: reconcile desired targets into risk-checked orders."""

from __future__ import annotations

import logging

from src.common.trading import Action, Order, OrderType, TradingClient
from src.trading.market_data import MarketDataSource
from src.trading.risk import RiskManager

logger = logging.getLogger("trading.execution")


class ExecutionEngine:
    """Converts target positions into orders, gated by the risk manager."""

    def __init__(
        self,
        client: TradingClient,
        risk: RiskManager,
        market_data: MarketDataSource,
    ):
        self.client = client
        self.risk = risk
        self.market_data = market_data

    def reconcile(self, targets: list) -> list:
        """Place market orders to move current holdings toward ``targets``.

        Returns the list of accepted fills produced this cycle.
        """
        positions = {(p.ticker, p.side): p for p in self.client.get_positions()}
        total_exposure = sum(p.cost_basis for p in positions.values())
        fills = []

        for target in targets:
            key = (target.ticker, target.side)
            current = positions.get(key)
            current_count = current.count if current else 0
            delta = target.count - current_count
            if delta == 0:
                continue

            action = Action.BUY if delta > 0 else Action.SELL
            count = abs(delta)
            ref_price = self.market_data.get_price(target.ticker, target.side)
            if ref_price is None:
                logger.warning("skip %s: no reference price", target.ticker)
                continue

            order = Order(target.ticker, target.side, action, count, OrderType.MARKET)
            decision = self.risk.validate(
                order,
                current_count=current_count,
                total_exposure=total_exposure,
                balance=self.client.get_balance(),
                ref_price=ref_price,
            )
            if not decision.approved:
                logger.info("risk rejected %s %s x%d: %s", action.value, target.ticker, count, decision.reason)
                continue

            result = self.client.place_order(order)
            if not result.accepted:
                logger.info("broker rejected %s %s x%d: %s", action.value, target.ticker, count, result.reason)
                continue

            fill = result.fill
            fills.append(fill)
            logger.info(
                "FILLED %s %s x%d @ %dc (cash %+d)",
                action.value,
                target.ticker,
                fill.count,
                fill.price,
                fill.cash_delta,
            )
            if action is Action.BUY:
                total_exposure += count * ref_price

        return fills
