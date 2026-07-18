"""Risk management: the authoritative gate before any order reaches the broker.

Every order must pass ``RiskManager.validate`` before being placed. The manager
also runs a portfolio-level kill switch that halts all new trading once losses
breach ``max_daily_loss``.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.common.trading import Action, Order


@dataclass
class RiskLimits:
    """Hard limits enforced on every order and on the portfolio as a whole."""

    max_contracts_per_order: int = 50
    max_contracts_per_market: int = 100
    max_total_exposure: int = 50_000  # cap on total cost basis, in cents
    max_daily_loss: int = 10_000  # equity drawdown that trips the kill switch, in cents


@dataclass
class RiskDecision:
    approved: bool
    reason: str = ""


class RiskManager:
    """Validates individual orders and enforces a portfolio kill switch."""

    def __init__(self, limits: RiskLimits, starting_equity: int):
        self.limits = limits
        self.starting_equity = starting_equity
        self.halted = False

    def update_kill_switch(self, current_equity: int) -> bool:
        """Trip (and latch) the kill switch if drawdown exceeds the limit."""
        if self.starting_equity - current_equity >= self.limits.max_daily_loss:
            self.halted = True
        return self.halted

    def validate(
        self,
        order: Order,
        *,
        current_count: int,
        total_exposure: int,
        balance: int,
        ref_price: int,
    ) -> RiskDecision:
        """Approve or reject a single order against all configured limits."""
        if self.halted:
            return RiskDecision(False, "trading halted by kill switch")
        if order.count <= 0:
            return RiskDecision(False, "non-positive order count")
        if order.count > self.limits.max_contracts_per_order:
            return RiskDecision(
                False,
                f"order size {order.count} exceeds per-order cap {self.limits.max_contracts_per_order}",
            )

        if order.action is Action.BUY:
            projected = current_count + order.count
            if projected > self.limits.max_contracts_per_market:
                return RiskDecision(
                    False,
                    f"position {projected} would exceed per-market cap {self.limits.max_contracts_per_market}",
                )
            est_cost = order.count * ref_price
            if est_cost > balance:
                return RiskDecision(False, "insufficient balance for order")
            if total_exposure + est_cost > self.limits.max_total_exposure:
                return RiskDecision(
                    False,
                    f"total exposure would exceed cap {self.limits.max_total_exposure}",
                )

        return RiskDecision(True)
