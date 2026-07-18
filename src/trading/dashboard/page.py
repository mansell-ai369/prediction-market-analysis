"""Static HTML/CSS/JS for the dashboard (served as a single page)."""

from __future__ import annotations

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Trading Bot Monitor</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --border: #21262d; --muted: #8b949e;
    --text: #e6edf3; --green: #3fb950; --red: #f85149; --accent: #58a6ff;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--panel);
  }
  header h1 { font-size: 18px; margin: 0; font-weight: 600; }
  header .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .pill { font-size: 12px; padding: 4px 10px; border-radius: 999px; font-weight: 600; }
  .pill.live { background: rgba(63,185,80,.15); color: var(--green); }
  .pill.paused { background: rgba(139,148,158,.15); color: var(--muted); }
  .pill.halted { background: rgba(248,81,73,.15); color: var(--red); }
  main { padding: 24px; max-width: 1100px; margin: 0 auto; }
  .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
  .card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
  .card .value { font-size: 26px; font-weight: 700; margin-top: 6px; font-variant-numeric: tabular-nums; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 20px; }
  .panel h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 0 0 12px; }
  canvas { width: 100%; height: 240px; display: block; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: .04em; }
  td.num, th.num { text-align: right; }
  .green { color: var(--green); } .red { color: var(--red); }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .controls button {
    background: #21262d; color: var(--text); border: 1px solid var(--border);
    padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; margin-left: 8px;
  }
  .controls button:hover { border-color: var(--accent); }
  .empty { color: var(--muted); font-size: 13px; padding: 8px 10px; }
  @media (max-width: 820px) { .cards { grid-template-columns: repeat(2,1fr); } .grid2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div>
    <h1>Trading Bot Monitor</h1>
    <div class="sub">Kalshi route A &middot; paper trading (simulated, no real money)</div>
  </div>
  <div class="controls">
    <span id="status" class="pill paused">--</span>
    <button onclick="ctl('pause')">Pause</button>
    <button onclick="ctl('resume')">Resume</button>
    <button onclick="ctl('reset')">Reset</button>
  </div>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="label">Equity</div><div class="value" id="equity">--</div></div>
    <div class="card"><div class="label">P&amp;L</div><div class="value" id="pnl">--</div></div>
    <div class="card"><div class="label">Cash</div><div class="value" id="cash">--</div></div>
    <div class="card"><div class="label">Tick</div><div class="value" id="tick">--</div></div>
  </div>

  <div class="panel">
    <h2>Equity curve</h2>
    <canvas id="chart"></canvas>
  </div>

  <div class="grid2">
    <div class="panel">
      <h2>Open positions</h2>
      <table>
        <thead><tr><th>Market</th><th>Side</th><th class="num">Qty</th><th class="num">Avg</th><th class="num">Mark</th><th class="num">Unreal.</th></tr></thead>
        <tbody id="positions"></tbody>
      </table>
    </div>
    <div class="panel">
      <h2>Recent fills</h2>
      <table>
        <thead><tr><th class="num">#</th><th>Market</th><th>Action</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Cash</th></tr></thead>
        <tbody id="fills"></tbody>
      </table>
    </div>
  </div>
</main>

<script>
const usd = (c) => (c/100).toLocaleString("en-US", {style:"currency", currency:"USD"});

function ctl(action) {
  fetch("/api/" + action, {method: "POST"}).then(() => setTimeout(refresh, 100));
}

function drawChart(history) {
  const canvas = document.getElementById("chart");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (!history || history.length < 2) return;

  const pad = 8;
  const min = Math.min(...history), max = Math.max(...history);
  const range = (max - min) || 1;
  const x = (i) => pad + (i/(history.length-1)) * (w - 2*pad);
  const y = (v) => h - pad - ((v - min)/range) * (h - 2*pad);

  // baseline (starting equity = first point)
  const base = history[0];
  ctx.strokeStyle = "#30363d"; ctx.lineWidth = 1; ctx.setLineDash([4,4]);
  ctx.beginPath(); ctx.moveTo(pad, y(base)); ctx.lineTo(w-pad, y(base)); ctx.stroke();
  ctx.setLineDash([]);

  const up = history[history.length-1] >= base;
  const color = up ? "#3fb950" : "#f85149";
  // area fill
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, up ? "rgba(63,185,80,.25)" : "rgba(248,81,73,.25)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.beginPath(); ctx.moveTo(x(0), y(history[0]));
  history.forEach((v,i) => ctx.lineTo(x(i), y(v)));
  ctx.lineTo(x(history.length-1), h-pad); ctx.lineTo(x(0), h-pad); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  // line
  ctx.beginPath(); ctx.moveTo(x(0), y(history[0]));
  history.forEach((v,i) => ctx.lineTo(x(i), y(v)));
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
}

function refresh() {
  fetch("/api/state").then(r => r.json()).then(s => {
    const status = document.getElementById("status");
    if (s.kill_switch) { status.className = "pill halted"; status.textContent = "KILL SWITCH"; }
    else if (s.running) { status.className = "pill live"; status.textContent = "LIVE"; }
    else { status.className = "pill paused"; status.textContent = "PAUSED"; }

    document.getElementById("equity").textContent = usd(s.equity);
    document.getElementById("cash").textContent = usd(s.cash);
    document.getElementById("tick").textContent = s.tick;
    const pnlEl = document.getElementById("pnl");
    const sign = s.pnl >= 0 ? "+" : "";
    pnlEl.textContent = sign + usd(s.pnl) + " (" + sign + s.pnl_pct.toFixed(2) + "%)";
    pnlEl.className = "value " + (s.pnl >= 0 ? "green" : "red");

    const pos = document.getElementById("positions");
    if (!s.positions.length) { pos.innerHTML = '<tr><td colspan="6" class="empty">No open positions</td></tr>'; }
    else pos.innerHTML = s.positions.map(p => {
      const u = p.unrealized == null ? 0 : p.unrealized;
      const cls = u >= 0 ? "green" : "red";
      return `<tr><td>${p.ticker}</td><td>${p.side}</td><td class="num">${p.count}</td>`
        + `<td class="num">${p.avg_price}c</td><td class="num">${p.mark==null?"-":p.mark+"c"}</td>`
        + `<td class="num ${cls}">${u>=0?"+":""}${usd(u)}</td></tr>`;
    }).join("");

    const fills = document.getElementById("fills");
    if (!s.fills.length) { fills.innerHTML = '<tr><td colspan="6" class="empty">No fills yet</td></tr>'; }
    else fills.innerHTML = s.fills.map(f => {
      const cls = f.action === "buy" ? "red" : "green";
      return `<tr><td class="num">${f.tick}</td><td>${f.ticker}</td>`
        + `<td class="${cls}">${f.action} ${f.side}</td><td class="num">${f.count}</td>`
        + `<td class="num">${f.price}c</td><td class="num">${f.cash_delta>=0?"+":""}${usd(f.cash_delta)}</td></tr>`;
    }).join("");

    drawChart(s.equity_history);
  }).catch(() => {});
}

refresh();
setInterval(refresh, 1000);
</script>
</body>
</html>
"""
