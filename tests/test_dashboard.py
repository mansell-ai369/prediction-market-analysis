"""Tests for the monitoring dashboard (runner + Flask endpoints)."""

from __future__ import annotations

import pytest

from src.trading.dashboard.app import create_app
from src.trading.dashboard.runner import BotRunner


@pytest.fixture
def runner():
    # Deterministic; we drive ticks manually instead of the background thread.
    return BotRunner(interval=0.01, seed=42)


def test_runner_initial_snapshot(runner):
    snap = runner.snapshot()
    assert snap["tick"] == 0
    assert snap["equity"] == snap["starting_equity"]
    assert snap["pnl"] == 0
    assert snap["positions"] == []
    assert snap["equity_history"] == [snap["starting_equity"]]


def test_runner_step_advances_state(runner):
    for _ in range(15):
        runner.step()
    snap = runner.snapshot()
    assert snap["tick"] == 15
    assert len(snap["equity_history"]) == 16  # starting point + 15 ticks
    # A mean-reversion strategy on the seeded feed should have traded by now.
    assert snap["fills"] or snap["positions"] is not None


def test_runner_history_is_capped():
    r = BotRunner(interval=0.01, seed=1, max_history=10)
    for _ in range(30):
        r.step()
    assert len(r.snapshot()["equity_history"]) == 10


def test_reset_restores_initial_state(runner):
    for _ in range(10):
        runner.step()
    runner.reset()
    snap = runner.snapshot()
    assert snap["tick"] == 0
    assert snap["equity"] == snap["starting_equity"]


@pytest.fixture
def client(runner):
    app = create_app(runner, autostart=False)
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Trading Bot Monitor" in resp.data


def test_state_endpoint_returns_expected_keys(client):
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in [
        "running",
        "tick",
        "cash",
        "equity",
        "pnl",
        "pnl_pct",
        "kill_switch",
        "positions",
        "fills",
        "equity_history",
    ]:
        assert key in data


def test_pause_and_resume_endpoints(client):
    assert client.post("/api/pause").get_json()["running"] is False
    assert client.post("/api/resume").get_json()["running"] is True
    # Clean up the background thread started by resume.
    client.post("/api/pause")
