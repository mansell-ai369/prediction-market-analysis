"""Runnable paper-trading demo for the Kalshi route (route A).

Wires together a simulated market feed, a mean-reversion strategy, a risk
manager with a kill switch, and a paper-trading client, then runs the bot loop
and prints a P&L report. No network, no real money.

Run it with::

    make trade-demo
    # or
    uv run python -m src.trading.demo --ticks 40 --seed 42
"""

from __future__ import annotations

import argparse
import logging

from src.common.trading import PaperTradingClient
from src.trading.bot import TradingBot
from src.trading.execution import ExecutionEngine
from src.trading.market_data import SimulatedMarketData
from src.trading.risk import RiskLimits, RiskManager
from src.trading.strategy import MeanReversionStrategy

STARTING_CASH = 50_000  # cents ($500.00)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


def build_bot(*, seed: int, starting_cash: int = STARTING_CASH) -> TradingBot:
    """Assemble a fully-wired paper-trading bot."""
    market_data = SimulatedMarketData(seed=seed)
    client = PaperTradingClient(starting_cash=starting_cash, price_fn=market_data.get_price)
    strategy = MeanReversionStrategy(window=8, entry_band=3.0, exit_band=2.0, size=20)
    risk = RiskManager(
        RiskLimits(
            max_contracts_per_order=50,
            max_contracts_per_market=60,
            max_total_exposure=40_000,
            max_daily_loss=15_000,
        ),
        starting_equity=starting_cash,
    )
    execution = ExecutionEngine(client, risk, market_data)
    return TradingBot(client, strategy, risk, market_data, execution)


def _format_cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def run_demo(ticks: int = 40, seed: int = 42) -> dict:
    """Run the demo end-to-end and return the final account snapshot."""
    _configure_logging()
    log = logging.getLogger("trading.demo")

    log.info("=" * 64)
    log.info("Kalshi paper-trading demo (route A) - SIMULATED, no real money")
    log.info("=" * 64)

    bot = build_bot(seed=seed)
    starting_equity = bot.client.get_balance()
    log.info("Starting cash: %s | markets: %d | ticks: %d", _format_cents(starting_equity), 5, ticks)
    log.info("-" * 64)

    bot.run(ticks)

    log.info("-" * 64)
    log.info("Flattening all open positions...")
    bot.flatten()

    snapshot = bot.snapshot()
    final_equity = snapshot["equity"]
    pnl = final_equity - starting_equity
    log.info("=" * 64)
    log.info("RESULT")
    log.info("  Starting equity : %s", _format_cents(starting_equity))
    log.info("  Final equity    : %s", _format_cents(final_equity))
    log.info("  Realized P&L    : %s (%+.2f%%)", _format_cents(pnl), 100 * pnl / starting_equity)
    log.info("  Total fills     : %d", len(bot.client.fills))
    log.info("  Open positions  : %d (after flatten)", len(snapshot["positions"]))
    log.info("  Kill switch     : %s", "TRIPPED" if bot.risk.halted else "not triggered")
    log.info("=" * 64)

    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi paper-trading demo")
    parser.add_argument("--ticks", type=int, default=40, help="number of loop iterations")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for the simulated market")
    args = parser.parse_args()
    run_demo(ticks=args.ticks, seed=args.seed)


if __name__ == "__main__":
    main()
