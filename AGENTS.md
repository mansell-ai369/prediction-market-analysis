# AGENTS.md

## Cursor Cloud specific instructions

This is a **Python CLI / data-analysis toolkit** (prediction market research) managed with
[`uv`](https://github.com/astral-sh/uv). It has **no web server, backend, or database daemon** —
everything runs locally via `uv run main.py <command>` (or the `Makefile` wrappers). Storage is
local Parquet queried in-process with DuckDB.

### Environment
- Python is pinned to **3.9** (`.python-version`); `uv` manages the interpreter and the `.venv`.
- `uv` is installed at `~/.local/bin/uv` and is added to `PATH` via `~/.bashrc`. If `uv` is not
  found in a non-interactive shell, invoke it as `~/.local/bin/uv`.
- The update script runs `uv sync --group dev`, which is all that's needed to refresh dependencies.

### Standard commands (see `Makefile`)
- Lint: `uv run ruff check . && uv run ruff format --check .` (`make lint`)
- Test: `uv run pytest tests/ -v` (`make test`) — 111 tests, all self-contained (they build
  synthetic Parquet fixtures in temp dirs; **no dataset or network required**).
- Run an analysis: `uv run main.py analyze <name>` (or `make run <name>`); outputs land in `output/`.
- Interactive menus: `make analyze` / `make index` use `simple-term-menu` and need a real TTY —
  prefer the non-interactive `uv run main.py analyze <name>` form when scripting.

### Running analyses (non-obvious)
- Analyses read from `data/kalshi/{trades,markets}` and `data/polymarket/...` Parquet files. The
  full 36 GiB dataset is downloaded via `make setup` (needs `zstd` + `aria2c`/`curl`), which is
  **not** installed by the update script and is impractical in this environment.
- To exercise the analysis pipeline end-to-end without the full dataset, generate small synthetic
  Parquet files under `data/` (mirror the fixture builders in `tests/conftest.py`) and run a
  specific analysis, e.g. `uv run main.py analyze win_rate_by_price`.
- `data/` and `output/` are gitignored, so generating sample data/outputs won't dirty the repo.

### Data collection (`make index`)
- Indexers hit external third-party APIs (Kalshi, Polymarket Gamma) and, for on-chain Polymarket
  trades, a Polygon RPC endpoint configured in `.env` (`POLYGON_RPC`; see `.env.example`). These are
  optional and only needed for collecting fresh data, not for analysis or tests.
