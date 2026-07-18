"""Live Kalshi trading client (route A).

Adapts the ``TradingClient`` interface onto the official ``kalshi-python`` SDK,
which handles RSA-PSS request signing for API-key auth. This is what you swap in
for ``PaperTradingClient`` once you are ready to trade real money.

Credentials (never commit these) are read from the environment:

    KALSHI_API_KEY_ID        - your API key id from the Kalshi dashboard
    KALSHI_PRIVATE_KEY_PATH  - path to the RSA private key .pem file
    KALSHI_API_HOST          - optional host override (defaults to production)

NOTE: the paper demo does NOT exercise this class. Verify against Kalshi's demo
environment with tiny size before pointing it at production.
"""

from __future__ import annotations

import os

from src.common.trading import (
    Order,
    OrderResult,
    OrderType,
    Position,
    Side,
    TradingClient,
)

_DEFAULT_HOST = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiTradingClient(TradingClient):
    """Authenticated Kalshi client backed by ``kalshi-python``'s ``PortfolioApi``."""

    def __init__(
        self,
        key_id: str | None = None,
        private_key_path: str | None = None,
        host: str | None = None,
        *,
        portfolio_api=None,
    ):
        # Allow dependency injection of a pre-built PortfolioApi (used in tests).
        if portfolio_api is not None:
            self._portfolio = portfolio_api
            return

        key_id = key_id or os.environ.get("KALSHI_API_KEY_ID")
        private_key_path = private_key_path or os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        host = host or os.environ.get("KALSHI_API_HOST", _DEFAULT_HOST)
        if not key_id or not private_key_path:
            raise ValueError(
                "Kalshi credentials missing: set KALSHI_API_KEY_ID and "
                "KALSHI_PRIVATE_KEY_PATH (see src/trading/kalshi_client.py)."
            )

        from kalshi_python.api.portfolio_api import PortfolioApi
        from kalshi_python.api_client import ApiClient
        from kalshi_python.configuration import Configuration

        api_client = ApiClient(Configuration(host=host))
        api_client.set_kalshi_auth(key_id, private_key_path)
        self._portfolio = PortfolioApi(api_client)

    def get_balance(self) -> int:
        return int(self._portfolio.get_balance().balance)

    def get_positions(self) -> list[Position]:
        response = self._portfolio.get_positions()
        positions: list[Position] = []
        for raw in response.positions or []:
            net = int(getattr(raw, "position", 0) or 0)
            if net == 0:
                continue
            side = Side.YES if net > 0 else Side.NO
            count = abs(net)
            total_cost = abs(int(getattr(raw, "total_cost", 0) or 0))
            avg_price = round(total_cost / count) if count else 0
            positions.append(Position(raw.ticker, side, count, avg_price))
        return positions

    def place_order(self, order: Order) -> OrderResult:
        kwargs = {
            "ticker": order.ticker,
            "side": order.side.value,
            "action": order.action.value,
            "count": order.count,
            "type": order.type.value,
        }
        if order.client_order_id:
            kwargs["client_order_id"] = order.client_order_id
        if order.type is OrderType.LIMIT and order.price is not None:
            if order.side is Side.YES:
                kwargs["yes_price"] = order.price
            else:
                kwargs["no_price"] = order.price

        try:
            response = self._portfolio.create_order(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any broker/API error as a rejection
            return OrderResult(False, order, reason=f"kalshi error: {exc}")

        raw_order = getattr(response, "order", None)
        status = getattr(raw_order, "status", "") if raw_order else ""
        return OrderResult(True, order, reason=f"submitted (status={status})")

    def cancel_all(self) -> None:
        response = self._portfolio.get_orders()
        for raw in getattr(response, "orders", []) or []:
            order_id = getattr(raw, "order_id", None)
            if order_id:
                self._portfolio.cancel_order(order_id)
