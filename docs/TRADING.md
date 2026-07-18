# Automated Trading Demo (Kalshi / Route A)

A minimal, broker-agnostic automated-trading pipeline built on top of the
analysis repo. It demonstrates the full flow end-to-end **in paper-trading mode**
(simulated market, no network, no real money), and ships a real Kalshi adapter so
the same bot can later be pointed at a live account.

> ⚠️ **Real-money trading carries real risk.** The demo is 100% simulated. Before
> trading live, verify against Kalshi's demo environment with tiny size, and keep
> the risk limits conservative. Also confirm trading is legal in your jurisdiction.

## Run the demo

```bash
make trade-demo
# or with options:
uv run python -m src.trading.demo --ticks 40 --seed 42
```

Sample result:

```
RESULT
  Starting equity : $500.00
  Final equity    : $511.60
  Realized P&L    : $11.60 (+2.32%)
  Total fills     : 26
  Open positions  : 0 (after flatten)
  Kill switch     : not triggered
```

## Monitoring dashboard

A live web dashboard lets you watch the bot in real time (equity curve, P&L,
cash, current tick, open positions, recent fills, kill-switch status) with
Pause / Resume / Reset controls.

```bash
make dashboard
# or:
uv run python -m src.trading.dashboard.app --host 127.0.0.1 --port 8000 --interval 0.8
```

Then open <http://127.0.0.1:8000/>. The bot runs on a background thread and the
page polls `/api/state` once per second. Endpoints: `GET /api/state`,
`POST /api/pause`, `POST /api/resume`, `POST /api/reset`.

Dashboard files live under `src/trading/dashboard/` (`runner.py` drives the bot
on a timer; `app.py` is the Flask server; `page.py` is the self-contained UI).

## Architecture

```
market data  ->  strategy (signals)  ->  risk checks  ->  execution  ->  portfolio
```

| Layer | File | Responsibility |
|---|---|---|
| Primitives + paper client | `src/common/trading.py` | Orders/fills/positions, `TradingClient` interface, `PaperTradingClient` (simulated fills) |
| Market data | `src/trading/market_data.py` | `SimulatedMarketData` (offline, mean-reverting) and `KalshiMarketData` (live quotes) |
| Strategy | `src/trading/strategy.py` | `MeanReversionStrategy` -> desired `TargetPosition`s (no order placement) |
| Risk | `src/trading/risk.py` | Per-order + portfolio limits and a latching kill switch |
| Execution | `src/trading/execution.py` | Reconciles targets into risk-checked orders |
| Bot loop | `src/trading/bot.py` | Ties layers together, marks equity, flatten/snapshot |
| Live adapter | `src/trading/kalshi_client.py` | Real Kalshi trading via `kalshi-python` (RSA-signed API key) |
| Demo runner | `src/trading/demo.py` | Wires everything up and prints a P&L report |

The strategy only ever expresses *what it wants to hold*; the risk manager is the
authoritative gate before any order reaches the broker.

## Going live on Kalshi

1. Create an API key in the Kalshi dashboard and download the RSA private key.
2. Set credentials (never commit them):
   - `KALSHI_API_KEY_ID`
   - `KALSHI_PRIVATE_KEY_PATH` (path to the `.pem`)
   - `KALSHI_API_HOST` (optional; defaults to production)
3. Swap the client in `build_bot` from `PaperTradingClient` to
   `KalshiTradingClient` and feed the bot `KalshiMarketData` for live quotes.
4. Start with the smallest possible size and conservative `RiskLimits`.

`KalshiTradingClient` maps the shared `TradingClient` interface onto
`kalshi-python`'s `PortfolioApi` (`create_order`, `get_balance`, `get_positions`,
`cancel_order`). The SDK handles RSA-PSS request signing. This adapter has not
been exercised against the live API in this repo — verify it yourself first.
