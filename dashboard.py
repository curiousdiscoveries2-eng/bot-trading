"""Dashboard web ringan: status, ekuitas, riwayat trade. Dibuka dari HP."""
import io
import base64
import sqlite3
from flask import Flask, render_template_string
import config

app = Flask(__name__)
_ctx = {}  # diisi run.py: {"risk":..., "broker":..., "equity":[...], "running":bool}

TPL = """
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bot Trading</title><style>
body{font-family:system-ui;background:#0f172a;color:#e2e8f0;margin:0;padding:16px}
.card{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:12px}
.big{font-size:28px;font-weight:700}.green{color:#4ade80}.red{color:#f87171}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px;border-bottom:1px solid #334155;text-align:left}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px}
.on{background:#14532d}.off{background:#7f1d1d}
img{width:100%;border-radius:8px}
</style></head><body>
<h2>🤖 Bot Autotrading</h2>
<div class="card"><span class="badge {{'on' if running else 'off'}}">{{'JALAN' if running else 'BERHENTI'}}</span>
<span class="badge {{'off' if halted else 'on'}}">{{'HALT' if halted else 'AKTIF'}}</span></div>
<div class="card"><div>Balance</div><div class="big">${{balance}}</div>
<div>P/L hari ini: <b class="{{'green' if day>=0 else 'red'}}">${{day}}</b> |
Drawdown: {{dd}}%</div></div>
<div class="card"><div>Winrate: {{wr}}% | Trades: {{n}}</div>
<div>Posisi terbuka: {{open_n}}</div></div>
<div class="card"><img src="data:image/png;base64,{{chart}}"></div>
<div class="card"><table><tr><th>Waktu</th><th>Pair</th><th>Dir</th><th>P/L</th></tr>
{{rows}}</table></div>
</body></html>"""


@app.route("/")
def index():
    risk, broker = _ctx.get("risk"), _ctx.get("broker")
    if risk is None:
        return "bot belum jalan"
    eq = _ctx.get("equity", [config.START_BALANCE])
    chart = _equity_chart(eq)
    stats = broker.trade_stats()
    rows = ""
    with sqlite3.connect(config.DB_PATH) as c:
        for t, s, d, p in c.execute(
                "SELECT close_time,symbol,direction,pnl FROM trades ORDER BY id DESC LIMIT 20"):
            cls = "green" if p > 0 else "red"
            rows += f"<tr><td>{t[:16]}</td><td>{s}</td><td>{'L' if d==1 else 'S'}</td><td class='{cls}'>${p:,.2f}</td></tr>"
    return render_template_string(TPL, running=_ctx.get("running", False),
        halted=risk.state.halted, balance=f"{risk.state.balance:,.2f}",
        day=f"{risk.state.day_pnl:+, .2f}".replace(" ", ""),
        dd=f"{risk.drawdown()*100:.1f}", wr=f"{stats['winrate']*100:.0f}",
        n=stats["trades"], open_n=len(broker.positions),
        chart=chart, rows=rows)


def _equity_chart(eq):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3), facecolor="#1e293b")
    ax.set_facecolor("#1e293b")
    ax.plot(eq, color="#4ade80", linewidth=1.5)
    ax.tick_params(colors="#94a3b8", labelsize=8)
    for s in ax.spines.values():
        s.set_visible(False)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="#1e293b")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def start(ctx):
    _ctx.update(ctx)
    app.run(host="0.0.0.0", port=config.DASHBOARD_PORT, threaded=True)
