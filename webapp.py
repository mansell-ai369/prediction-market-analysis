"""Web frontend for prediction-market-analysis using synthetic data."""

from __future__ import annotations

import base64
import inspect
import io
import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

# ── synthetic data (mirrors tests/conftest.py) ──────────────────────────────


def _make_kalshi_trades() -> pd.DataFrame:
    rows = []
    prices = [10, 20, 30, 50, 60, 70, 90]
    variants = [
        ("MKT-A", "yes", lambda p: p, lambda p: 100 - p, 10),
        ("MKT-B", "no", lambda p: 100 - p, lambda p: p, 5),
        ("MKT-B", "yes", lambda p: p, lambda p: 100 - p, 3),
    ]
    trade_id = 0
    base_time = pd.Timestamp("2024-06-01 12:00:00")
    for _ in range(100):
        for price in prices:
            for ticker, taker_side, yes_fn, no_fn, count in variants:
                trade_id += 1
                rows.append(
                    {
                        "trade_id": str(trade_id),
                        "ticker": ticker,
                        "count": count,
                        "yes_price": yes_fn(price),
                        "no_price": no_fn(price),
                        "taker_side": taker_side,
                        "created_time": base_time + pd.Timedelta(minutes=trade_id),
                        "_fetched_at": base_time,
                    }
                )
    return pd.DataFrame(rows)


def _make_kalshi_markets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "MKT-A", "status": "finalized", "result": "yes", "volume": 1000, "event_ticker": "INXD-24JAN01"},
            {"ticker": "MKT-B", "status": "finalized", "result": "no", "volume": 2000, "event_ticker": "NFLGAME-25FEB01"},
        ]
    )


def _make_polymarket_ctf_trades() -> pd.DataFrame:
    rows = []
    for i, price in enumerate([20, 40, 50, 60, 80]):
        rows += [
            {"block_number": 100 + i * 2, "maker_asset_id": "0", "taker_asset_id": "token_yes_a", "maker_amount": price * 10000, "taker_amount": 1000000},
            {"block_number": 100 + i * 2 + 1, "maker_asset_id": "0", "taker_asset_id": "token_yes_b", "maker_amount": price * 10000, "taker_amount": 1000000},
        ]
    return pd.DataFrame(rows)


def _make_polymarket_legacy_trades() -> pd.DataFrame:
    rows = []
    for i, price in enumerate([20, 40, 50, 60, 80]):
        rows += [
            {"block_number": 200 + i * 2, "fpmm_address": "0xfpmm_address_a", "amount": str(price * 10000), "outcome_tokens": str(1000000), "outcome_index": 0},
            {"block_number": 200 + i * 2 + 1, "fpmm_address": "0xfpmm_address_a", "amount": str(price * 10000), "outcome_tokens": str(1000000), "outcome_index": 1},
        ]
    return pd.DataFrame(rows)


def _make_polymarket_markets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": "market_a", "clob_token_ids": json.dumps(["token_yes_a", "token_no_a"]), "outcome_prices": json.dumps([1.0, 0.0]), "market_maker_address": "0xfpmm_address_a", "closed": True},
            {"id": "market_b", "clob_token_ids": json.dumps(["token_yes_b", "token_no_b"]), "outcome_prices": json.dumps([0.0, 1.0]), "market_maker_address": None, "closed": True},
        ]
    )


def _make_polymarket_blocks(ctf, legacy) -> pd.DataFrame:
    bns = sorted(set(ctf["block_number"].tolist()) | set(legacy["block_number"].tolist()))
    base = pd.Timestamp("2024-06-01 12:00:00", tz="UTC")
    return pd.DataFrame([{"block_number": bn, "timestamp": (base + pd.Timedelta(seconds=bn * 2)).isoformat()} for bn in bns])


# ── fixture dirs (written to temp parquet files once) ───────────────────────

import tempfile

_TMP = tempfile.mkdtemp(prefix="pma_fixtures_")

def _write(df: pd.DataFrame, subdir: str, filename: str) -> Path:
    d = Path(_TMP) / subdir
    d.mkdir(exist_ok=True)
    df.to_parquet(d / filename)
    return d


_ctf = _make_polymarket_ctf_trades()
_leg = _make_polymarket_legacy_trades()

FIXTURE_DIRS: dict[str, Path] = {
    "kalshi_trades_dir": _write(_make_kalshi_trades(), "kalshi_trades", "trades.parquet"),
    "kalshi_markets_dir": _write(_make_kalshi_markets(), "kalshi_markets", "markets.parquet"),
    "polymarket_trades_dir": _write(_ctf, "poly_trades", "trades.parquet"),
    "polymarket_legacy_trades_dir": _write(_leg, "poly_legacy", "legacy_trades.parquet"),
    "polymarket_markets_dir": _write(_make_polymarket_markets(), "poly_markets", "markets.parquet"),
    "polymarket_blocks_dir": _write(_make_polymarket_blocks(_ctf, _leg), "poly_blocks", "blocks.parquet"),
}

_collateral_dir = Path(_TMP) / "collateral"
_collateral_dir.mkdir(exist_ok=True)
(_collateral_dir / "fpmm_collateral_lookup.json").write_text(
    json.dumps({"0xfpmm_address_a": {"collateral_symbol": "USDC", "collateral_decimals": 6}})
)
FIXTURE_DIRS["collateral_lookup_path"] = _collateral_dir / "fpmm_collateral_lookup.json"

# ── analysis loader ──────────────────────────────────────────────────────────

from src.common.analysis import Analysis

def _build_kwargs(cls) -> dict:
    sig = inspect.signature(cls.__init__)
    params = [p for p in sig.parameters if p != "self"]
    module = cls.__module__
    is_kalshi = ".kalshi." in module
    is_polymarket = ".polymarket." in module
    kwargs = {}
    for param in params:
        if param in FIXTURE_DIRS:
            kwargs[param] = FIXTURE_DIRS[param]
        elif is_kalshi and param == "trades_dir":
            kwargs[param] = FIXTURE_DIRS["kalshi_trades_dir"]
        elif is_kalshi and param == "markets_dir":
            kwargs[param] = FIXTURE_DIRS["kalshi_markets_dir"]
        elif is_polymarket and param == "trades_dir":
            kwargs[param] = FIXTURE_DIRS["polymarket_trades_dir"]
        elif is_polymarket and param == "legacy_trades_dir":
            kwargs[param] = FIXTURE_DIRS["polymarket_legacy_trades_dir"]
        elif is_polymarket and param == "markets_dir":
            kwargs[param] = FIXTURE_DIRS["polymarket_markets_dir"]
        elif is_polymarket and param == "blocks_dir":
            kwargs[param] = FIXTURE_DIRS["polymarket_blocks_dir"]
    return kwargs


ALL_ANALYSES = [c for c in Analysis.load() if "Animated" not in c.__name__]


def run_analysis(cls) -> dict:
    kwargs = _build_kwargs(cls)
    instance = cls(**kwargs)
    output = instance.run()

    result = {"name": instance.name, "description": instance.description, "image": None, "data": None, "metadata": None}

    if output.figure is not None:
        buf = io.BytesIO()
        output.figure.savefig(buf, format="png", bbox_inches="tight", dpi=120)
        plt.close(output.figure)
        result["image"] = base64.b64encode(buf.getvalue()).decode()

    if output.data is not None:
        result["data"] = output.data.head(20).to_dict(orient="records")

    if output.metadata is not None:
        result["metadata"] = output.metadata

    return result


# ── Flask app ────────────────────────────────────────────────────────────────

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Prediction Market Analysis</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }

    header { background: linear-gradient(135deg, #1a1f2e 0%, #16213e 100%); border-bottom: 1px solid #2d3748; padding: 1.5rem 2rem; display: flex; align-items: center; gap: 1rem; }
    header h1 { font-size: 1.5rem; font-weight: 700; color: #63b3ed; }
    header span { font-size: 0.8rem; background: #2d3748; color: #a0aec0; padding: 0.2rem 0.6rem; border-radius: 9999px; }

    .layout { display: flex; height: calc(100vh - 72px); }

    .sidebar { width: 280px; min-width: 280px; background: #141824; border-right: 1px solid #2d3748; overflow-y: auto; padding: 1rem 0; }
    .sidebar-section { padding: 0.5rem 1rem 0.25rem; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: #4a5568; font-weight: 600; }
    .analysis-btn { width: 100%; text-align: left; background: none; border: none; color: #a0aec0; padding: 0.6rem 1rem; cursor: pointer; font-size: 0.82rem; transition: all 0.15s; border-left: 2px solid transparent; }
    .analysis-btn:hover { background: #1a202c; color: #e2e8f0; }
    .analysis-btn.active { background: #1e2a3a; color: #63b3ed; border-left-color: #63b3ed; }
    .analysis-btn .badge { display: inline-block; font-size: 0.65rem; padding: 0.1rem 0.4rem; border-radius: 9999px; margin-left: 0.4rem; vertical-align: middle; }
    .badge-kalshi { background: #1a365d; color: #63b3ed; }
    .badge-poly { background: #1a3a2a; color: #48bb78; }
    .badge-comp { background: #3d1a5d; color: #b794f4; }

    .main { flex: 1; overflow-y: auto; padding: 2rem; }

    .placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 1rem; color: #4a5568; }
    .placeholder svg { width: 64px; height: 64px; opacity: 0.3; }
    .placeholder p { font-size: 1rem; }

    .card { background: #1a1f2e; border: 1px solid #2d3748; border-radius: 12px; overflow: hidden; margin-bottom: 1.5rem; }
    .card-header { padding: 1rem 1.5rem; border-bottom: 1px solid #2d3748; display: flex; align-items: center; justify-content: space-between; }
    .card-title { font-size: 1rem; font-weight: 600; color: #e2e8f0; }
    .card-desc { font-size: 0.8rem; color: #718096; margin-top: 0.2rem; }
    .card-body { padding: 1.5rem; }

    .chart-img { max-width: 100%; border-radius: 8px; display: block; margin: 0 auto; }

    .run-btn { background: #2b6cb0; color: white; border: none; padding: 0.5rem 1.2rem; border-radius: 8px; cursor: pointer; font-size: 0.85rem; font-weight: 600; transition: background 0.15s; }
    .run-btn:hover { background: #2c5282; }
    .run-btn:disabled { background: #2d3748; color: #4a5568; cursor: not-allowed; }

    .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #4a5568; border-top-color: #63b3ed; border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle; margin-right: 0.4rem; }
    @keyframes spin { to { transform: rotate(360deg); } }

    table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
    th { background: #0f1117; color: #718096; padding: 0.5rem 0.75rem; text-align: left; font-weight: 600; border-bottom: 1px solid #2d3748; }
    td { padding: 0.45rem 0.75rem; border-bottom: 1px solid #1a202c; color: #cbd5e0; white-space: nowrap; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #0f1117; }

    .meta-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }
    .meta-item { background: #0f1117; border-radius: 8px; padding: 0.75rem 1rem; }
    .meta-label { font-size: 0.7rem; color: #4a5568; text-transform: uppercase; letter-spacing: 0.05em; }
    .meta-value { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-top: 0.2rem; }

    .tag { display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 9999px; margin-right: 0.3rem; }
    .tag-demo { background: #2d3748; color: #a0aec0; }
  </style>
</head>
<body>
  <header>
    <h1>📊 Prediction Market Analysis</h1>
    <span class="tag tag-demo">合成資料 Demo</span>
  </header>
  <div class="layout">
    <aside class="sidebar" id="sidebar">
      <div class="sidebar-section">Kalshi</div>
      {% for a in analyses %}
        {% if 'kalshi' in a.module %}
          <button class="analysis-btn" data-cls="{{ a.cls }}" onclick="loadAnalysis(this)">
            {{ a.title }}<span class="badge badge-kalshi">K</span>
          </button>
        {% endif %}
      {% endfor %}
      <div class="sidebar-section" style="margin-top:0.75rem">Polymarket</div>
      {% for a in analyses %}
        {% if 'polymarket' in a.module %}
          <button class="analysis-btn" data-cls="{{ a.cls }}" onclick="loadAnalysis(this)">
            {{ a.title }}<span class="badge badge-poly">P</span>
          </button>
        {% endif %}
      {% endfor %}
      <div class="sidebar-section" style="margin-top:0.75rem">Comparison</div>
      {% for a in analyses %}
        {% if 'comparison' in a.module %}
          <button class="analysis-btn" data-cls="{{ a.cls }}" onclick="loadAnalysis(this)">
            {{ a.title }}<span class="badge badge-comp">C</span>
          </button>
        {% endif %}
      {% endfor %}
    </aside>
    <main class="main" id="main">
      <div class="placeholder">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/>
        </svg>
        <p>從左側選擇一個分析來執行</p>
      </div>
    </main>
  </div>

  <script>
    async function loadAnalysis(btn) {
      document.querySelectorAll('.analysis-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cls = btn.dataset.cls;
      const main = document.getElementById('main');

      main.innerHTML = '<div class="placeholder"><div class="spinner"></div><p>執行分析中...</p></div>';

      try {
        const res = await fetch('/api/run/' + cls);
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        let html = `
          <div class="card">
            <div class="card-header">
              <div>
                <div class="card-title">${data.name.replace(/_/g,' ')}</div>
                <div class="card-desc">${data.description || ''}</div>
              </div>
            </div>`;

        if (data.image) {
          html += `<div class="card-body"><img class="chart-img" src="data:image/png;base64,${data.image}" alt="chart"></div>`;
        }
        html += '</div>';

        if (data.metadata && Object.keys(data.metadata).length > 0) {
          html += '<div class="card"><div class="card-header"><div class="card-title">統計摘要</div></div><div class="card-body"><div class="meta-grid">';
          for (const [k, v] of Object.entries(data.metadata)) {
            html += `<div class="meta-item"><div class="meta-label">${k}</div><div class="meta-value">${typeof v === 'number' ? v.toLocaleString() : v}</div></div>`;
          }
          html += '</div></div></div>';
        }

        if (data.data && data.data.length > 0) {
          const cols = Object.keys(data.data[0]);
          html += '<div class="card"><div class="card-header"><div class="card-title">資料預覽</div><div class="card-desc">顯示前 20 筆</div></div><div class="card-body" style="overflow-x:auto"><table><thead><tr>';
          cols.forEach(c => { html += `<th>${c}</th>`; });
          html += '</tr></thead><tbody>';
          data.data.forEach(row => {
            html += '<tr>';
            cols.forEach(c => { html += `<td>${row[c] ?? ''}</td>`; });
            html += '</tr>';
          });
          html += '</tbody></table></div></div>';
        }

        if (!data.image && !data.data) {
          html += '<div class="card"><div class="card-body" style="color:#718096">此分析沒有產生圖表或資料輸出</div></div>';
        }

        main.innerHTML = html;
      } catch (e) {
        main.innerHTML = `<div class="card"><div class="card-body" style="color:#fc8181">錯誤：${e.message}</div></div>`;
      }
    }
  </script>
</body>
</html>"""


@app.route("/")
def index():
    analyses = []
    for cls in ALL_ANALYSES:
        instance_tmp = cls.__new__(cls)
        try:
            instance_tmp.__init__(**{k: v for k, v in _build_kwargs(cls).items()})
        except Exception:
            pass
        name = getattr(instance_tmp, "name", cls.__name__)
        desc = getattr(instance_tmp, "description", "")
        module = cls.__module__
        title = " ".join(w.capitalize() for w in name.split("_"))
        analyses.append({"cls": cls.__name__, "title": title, "description": desc, "module": module})
    return render_template_string(HTML, analyses=analyses)


_cls_map = {cls.__name__: cls for cls in ALL_ANALYSES}


@app.route("/api/run/<cls_name>")
def api_run(cls_name):
    cls = _cls_map.get(cls_name)
    if not cls:
        return jsonify({"error": f"Analysis '{cls_name}' not found"}), 404
    try:
        result = run_analysis(cls)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"Starting server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
