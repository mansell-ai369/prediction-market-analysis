"""Flask app serving the trading-bot monitoring dashboard."""

from __future__ import annotations

import argparse

from flask import Flask, Response, jsonify

from src.trading.dashboard.page import PAGE_HTML
from src.trading.dashboard.runner import BotRunner


def create_app(runner: BotRunner | None = None, *, autostart: bool = False) -> Flask:
    """Create the dashboard Flask app.

    Args:
        runner: an existing ``BotRunner`` (injected in tests); one is created if None.
        autostart: start the background bot loop immediately.
    """
    app = Flask(__name__)
    runner = runner or BotRunner()
    if autostart:
        runner.start()

    @app.route("/")
    def index() -> Response:
        return Response(PAGE_HTML, mimetype="text/html")

    @app.route("/api/state")
    def state():
        return jsonify(runner.snapshot())

    @app.route("/api/pause", methods=["POST"])
    def pause():
        runner.pause()
        return jsonify({"ok": True, "running": False})

    @app.route("/api/resume", methods=["POST"])
    def resume():
        runner.resume()
        return jsonify({"ok": True, "running": True})

    @app.route("/api/reset", methods=["POST"])
    def reset():
        runner.reset()
        runner.start()
        return jsonify({"ok": True})

    app.config["runner"] = runner
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading bot monitoring dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between bot ticks")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    runner = BotRunner(interval=args.interval, seed=args.seed)
    app = create_app(runner, autostart=True)
    print(f"Dashboard running at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
