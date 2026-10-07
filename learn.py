"""Job mingguan: retrain ML + AUDIT pola kesalahan + laporan.
Jalankan via cron (VPS) atau workflow learn.yml (GitHub Actions).
"""
import sqlite3
import config
from ml_filter import train
from broker import PaperBroker
from notify import send


def audit(db_path: str = config.DB_PATH) -> str:
    """Peran Auditor: bedah trade yang kalah, cari pola kesalahan."""
    try:
        with sqlite3.connect(db_path) as c:
            rows = c.execute(
                "SELECT strategy, regime, f_hour, pnl FROM trades WHERE pnl IS NOT NULL"
            ).fetchall()
    except Exception:
        return "belum ada data trade"
    if not rows:
        return "belum ada data trade"
    losses = [r for r in rows if r[3] <= 0]
    if not losses:
        return f"{len(rows)} trade, semuanya profit 🎉"

    def worst(key_idx, label):
        from collections import defaultdict
        d = defaultdict(lambda: [0, 0.0])
        for r in losses:
            d[r[key_idx]][0] += 1
            d[r[key_idx]][1] += r[3]
        if not d:
            return ""
        k = min(d, key=lambda x: d[x][1])
        return f"{label} terburuk: {k} ({d[k][0]} kalah, ${d[k][1]:,.0f})"

    lines = [
        f"Total: {len(rows)} trade, {len(losses)} kalah",
        worst(0, "Strategi"),
        worst(1, "Regime"),
    ]
    # jam paling berdarah
    from collections import defaultdict
    by_hour = defaultdict(lambda: [0, 0.0])
    for r in losses:
        by_hour[r[2]][0] += 1
        by_hour[r[2]][1] += r[3]
    if by_hour:
        h = min(by_hour, key=lambda x: by_hour[x][1])
        lines.append(f"Jam terburuk: {h:02d}:00 UTC ({by_hour[h][0]} kalah)")
    return "\n".join(l for l in lines if l)


def auto_ban(db_path: str = config.DB_PATH) -> str:
    """Auditor BERTINDAK: ban 14 hari kombinasi (strategi, regime) yang
    berdarah — minimal 3 kalah dan total P/L negatif."""
    from collections import defaultdict
    try:
        with sqlite3.connect(db_path) as c:
            rows = c.execute(
                "SELECT strategy, regime, pnl FROM trades WHERE pnl IS NOT NULL"
            ).fetchall()
    except Exception:
        return "belum ada data trade"
    if not rows:
        return "belum ada data trade"
    d = defaultdict(lambda: [0, 0.0])  # (strategi, regime) -> [kalah, total_pnl]
    for s, rg, p in rows:
        if p <= 0:
            d[(s, rg)][0] += 1
        d[(s, rg)][1] += p
    broker = PaperBroker(db_path)
    banned = []
    for (s, rg), (n_loss, tot) in d.items():
        if n_loss >= 3 and tot < 0 and not broker.is_banned(s, rg):
            why = f"{n_loss}x kalah, ${tot:,.0f}"
            broker.add_ban(s, rg, 14, why)
            banned.append(f"{s}/{rg} ({why})")
    if not banned:
        return "tidak ada pola baru yang di-ban"
    return "di-ban 14 hari: " + "; ".join(banned)


def main():
    broker = PaperBroker()
    stats = broker.trade_stats()
    result = train()
    bans = auto_ban()
    msg = (f"📚 Laporan mingguan Dewan\n"
           f"Trade: {stats['trades']} | Winrate: {stats['winrate']:.0%}\n"
           f"Total P/L: ${stats['total_pnl']:,.2f}\n\n"
           f"🔍 Audit kesalahan:\n{audit()}\n\n"
           f"🚫 Auto-ban: {bans}\n\n"
           f"🧠 ML: {result.get('status')} "
           f"(cv={result.get('cv_accuracy', '-')})")
    print(msg)
    send(msg)


if __name__ == "__main__":
    main()
