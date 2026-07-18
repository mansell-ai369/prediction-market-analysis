"""Automated trading demo (Kalshi / "route A").

A minimal, broker-agnostic trading pipeline built on top of the analysis repo:

    market data -> strategy (signals) -> risk checks -> execution -> portfolio

The demo runs entirely in **paper-trading** mode against a simulated market feed
(no real money, no network). A real ``KalshiTradingClient`` adapter is provided
so the same bot can be pointed at a live Kalshi account once credentials and
risk limits have been verified.
"""
