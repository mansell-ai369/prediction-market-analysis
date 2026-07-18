"""Background runner that drives the paper-trading bot for the dashboard.

The bot loop runs on a daemon thread, advancing one tick every ``interval``
seconds. All shared state is guarded by a lock so the Flask request handlers can
take a consistent snapshot at any time.
"""

from __future__ import annotations

import threading
import time

from src.trading.demo import build_bot


class BotRunner:
    """Runs a paper-trading bot on a timer and exposes thread-safe snapshots."""

    def __init__(self, *, interval: float = 1.0, seed: int = 42, max_history: int = 240):
        self.interval = interval
        self.max_history = max_history
        self._seed = seed
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._stop = threading.Event()
        self._build()

    def _build(self) -> None:
        self.bot = build_bot(seed=self._seed)
        self.starting_equity = self.bot.client.get_balance()
        self.tick = 0
        self.equity_history = [self.starting_equity]
        self.recent_fills = []

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def pause(self) -> None:
        with self._lock:
            self._running = False
        self._stop.set()

    def resume(self) -> None:
        self.start()

    def reset(self) -> None:
        self.pause()
        if self._thread is not None:
            self._thread.join(timeout=2 * self.interval + 1)
        with self._lock:
            self._build()

    # -- loop -----------------------------------------------------------------

    def step(self) -> None:
        """Advance the bot by exactly one tick (used by the loop and by tests)."""
        with self._lock:
            if self.bot.risk.halted:
                self._running = False
                return
            report, fills = self.bot.step_once(self.tick + 1)
            self.tick += 1
            self.equity_history.append(report.equity)
            if len(self.equity_history) > self.max_history:
                self.equity_history = self.equity_history[-self.max_history :]
            for fill in fills:
                self.recent_fills.insert(
                    0,
                    {
                        "tick": self.tick,
                        "ticker": fill.ticker,
                        "side": fill.side.value,
                        "action": fill.action.value,
                        "count": fill.count,
                        "price": fill.price,
                        "cash_delta": fill.cash_delta,
                    },
                )
            self.recent_fills = self.recent_fills[:20]

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.step()
            with self._lock:
                if not self._running:
                    break
            time.sleep(self.interval)

    # -- snapshot -------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            snap = self.bot.snapshot()
            equity = snap["equity"]
            pnl = equity - self.starting_equity
            pnl_pct = (100 * pnl / self.starting_equity) if self.starting_equity else 0.0
            return {
                "running": self._running,
                "tick": self.tick,
                "cash": snap["cash"],
                "equity": equity,
                "starting_equity": self.starting_equity,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "kill_switch": self.bot.risk.halted,
                "positions": snap["positions"],
                "fills": list(self.recent_fills),
                "equity_history": list(self.equity_history),
            }
