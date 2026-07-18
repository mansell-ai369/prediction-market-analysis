"""Tests for the paper-trading demo pipeline (route A)."""

from __future__ import annotations

import pytest

from src.common.trading import (
    Action,
    Order,
    OrderType,
    PaperTradingClient,
    Side,
)
from src.trading.demo import build_bot, run_demo
from src.trading.execution import ExecutionEngine
from src.trading.market_data import MarketQuote, SimulatedMarketData
from src.trading.risk import RiskLimits, RiskManager
from src.trading.strategy import MeanReversionStrategy, TargetPosition


@pytest.fixture
def fixed_prices():
    return {("MKT", Side.YES): 40, ("MKT", Side.NO): 60}


@pytest.fixture
def paper_client(fixed_prices):
    return PaperTradingClient(
        starting_cash=10_000,
        price_fn=lambda ticker, side: fixed_prices.get((ticker, side)),
    )


# -- PaperTradingClient -------------------------------------------------------


def test_buy_reduces_cash_and_opens_position(paper_client):
    result = paper_client.place_order(Order("MKT", Side.YES, Action.BUY, 10))
    assert result.accepted
    assert paper_client.get_balance() == 10_000 - 10 * 40
    pos = paper_client.get_position("MKT", Side.YES)
    assert pos is not None and pos.count == 10 and pos.avg_price == 40


def test_sell_increases_cash_and_reduces_position(paper_client):
    paper_client.place_order(Order("MKT", Side.YES, Action.BUY, 10))
    result = paper_client.place_order(Order("MKT", Side.YES, Action.SELL, 4))
    assert result.accepted
    assert paper_client.get_position("MKT", Side.YES).count == 6
    # spent 400, got back 160 -> balance 10000 - 400 + 160
    assert paper_client.get_balance() == 10_000 - 400 + 160


def test_insufficient_balance_rejected(fixed_prices):
    client = PaperTradingClient(starting_cash=100, price_fn=lambda t, s: fixed_prices.get((t, s)))
    result = client.place_order(Order("MKT", Side.YES, Action.BUY, 10))  # needs 400
    assert not result.accepted
    assert "insufficient" in result.reason
    assert client.get_balance() == 100


def test_cannot_sell_more_than_held(paper_client):
    paper_client.place_order(Order("MKT", Side.YES, Action.BUY, 5))
    result = paper_client.place_order(Order("MKT", Side.YES, Action.SELL, 8))
    assert not result.accepted
    assert paper_client.get_position("MKT", Side.YES).count == 5


def test_limit_buy_not_marketable(paper_client):
    # market YES price is 40; a limit buy at 30 should not fill.
    order = Order("MKT", Side.YES, Action.BUY, 5, OrderType.LIMIT, price=30)
    result = paper_client.place_order(order)
    assert not result.accepted
    assert "marketable" in result.reason


def test_equity_marks_to_market(paper_client):
    paper_client.place_order(Order("MKT", Side.YES, Action.BUY, 10))
    # cash 9600 + 10 contracts * 40c = 10000 (unchanged at entry price)
    assert paper_client.equity() == 10_000


# -- RiskManager --------------------------------------------------------------


def test_risk_rejects_oversized_order():
    risk = RiskManager(RiskLimits(max_contracts_per_order=10), starting_equity=10_000)
    decision = risk.validate(
        Order("MKT", Side.YES, Action.BUY, 50),
        current_count=0,
        total_exposure=0,
        balance=10_000,
        ref_price=40,
    )
    assert not decision.approved


def test_risk_enforces_exposure_cap():
    risk = RiskManager(RiskLimits(max_total_exposure=1_000), starting_equity=10_000)
    decision = risk.validate(
        Order("MKT", Side.YES, Action.BUY, 40),
        current_count=0,
        total_exposure=0,
        balance=10_000,
        ref_price=40,  # 40 * 40 = 1600 > 1000 cap
    )
    assert not decision.approved


def test_kill_switch_trips_and_blocks_orders():
    risk = RiskManager(RiskLimits(max_daily_loss=500), starting_equity=10_000)
    assert risk.update_kill_switch(9_400) is True  # lost 600 > 500
    decision = risk.validate(
        Order("MKT", Side.YES, Action.BUY, 1),
        current_count=0,
        total_exposure=0,
        balance=10_000,
        ref_price=40,
    )
    assert not decision.approved and "kill switch" in decision.reason


# -- Strategy -----------------------------------------------------------------


def test_strategy_holds_until_window_filled():
    strat = MeanReversionStrategy(window=3, size=10)
    quotes = [MarketQuote("MKT", 40, 60)]
    # First two ticks: not enough history -> target equals current holding (0).
    assert strat.generate_targets(quotes, [])[0].count == 0
    assert strat.generate_targets(quotes, [])[0].count == 0


def test_strategy_buys_below_mean():
    strat = MeanReversionStrategy(window=3, entry_band=2.0, exit_band=2.0, size=10)
    # Prime the window with high prices so the next low price is below mean.
    strat.generate_targets([MarketQuote("MKT", 60, 40)], [])
    strat.generate_targets([MarketQuote("MKT", 60, 40)], [])
    targets = strat.generate_targets([MarketQuote("MKT", 40, 60)], [])
    assert targets[0].count == 10  # entered long YES


# -- Execution ----------------------------------------------------------------


def test_execution_places_order_to_reach_target(paper_client):
    risk = RiskManager(RiskLimits(), starting_equity=10_000)
    market = SimulatedMarketData(fair_values={"MKT": 40}, seed=1)
    # Use paper_client's own fixed price feed via a tiny source shim.
    engine = ExecutionEngine(paper_client, risk, _StubMarket({"MKT": 40}))
    fills = engine.reconcile([TargetPosition("MKT", Side.YES, 10)])
    assert len(fills) == 1
    assert paper_client.get_position("MKT", Side.YES).count == 10
    assert market is not None  # market source constructs without error


class _StubMarket:
    def __init__(self, prices):
        self._prices = prices

    def get_quotes(self):
        return [MarketQuote(t, p, 100 - p) for t, p in self._prices.items()]

    def get_price(self, ticker, side):
        p = self._prices.get(ticker)
        if p is None:
            return None
        return p if side is Side.YES else 100 - p

    def step(self):
        return None


# -- End-to-end demo ----------------------------------------------------------


def test_demo_runs_end_to_end():
    snapshot = run_demo(ticks=20, seed=42)
    assert "equity" in snapshot and snapshot["equity"] > 0


def test_build_bot_is_deterministic():
    bot_a = build_bot(seed=7)
    bot_b = build_bot(seed=7)
    reports_a = bot_a.run(15)
    reports_b = bot_b.run(15)
    assert [r.equity for r in reports_a] == [r.equity for r in reports_b]
