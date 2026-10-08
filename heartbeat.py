"""Laporan harian (heartbeat): bukti bot hidup + ringkasan performa.
Jalankan via workflow heartbeat.yml tiap 00:00 UTC (07:00 WIB)."""
import sqlite3
import datetime
import config
from broker import PaperBroker
from notify import send


def main():
    broker = PaperBroker()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    tgl = now_utc.strftime("%d %b %Y")
    fmt = "%Y-%m-%d %H:%M:%S"

    with sqlite3.connect(broker.db_path) as c:
        total = c.execute("SELECT COALESCE(SUM(pnl),0), COUNT(*) FROM trades").fetchone()
        total_pnl, n_all = float(total[0]), total[1]
        d7 = c.execute(
            "SELECT COALESCE(SUM(pnl),0), COUNT(*), "
            "SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) FROM trades "
            "WHERE close_time >= ?",
            ((now_utc - datetime.timedelta(days=7)).strftime(fmt),)).fetchone()
        d1 = c.execute(
            "SELECT COALESCE(SUM(pnl),0), COUNT(*) FROM trades WHERE close_time >= ?",
            ((now_utc - datetime.timedelta(days=1)).strftime(fmt),)).fetchone()
        opens = c.execute(
            "SELECT symbol, direction, entry, open_time FROM open_positions").fetchall()

    balance = config.START_BALANCE + total_pnl
    peak = broker.get_meta("peak_balance")
    peak = float(peak) if peak else max(config.START_BALANCE, balance)
    dd = (peak - balance) / peak if peak else 0.0
    wr7 = (d7[2] / d7[1]) if d7[1] else 0.0

    lines = [
        f"💓 Laporan Harian Bot — {tgl}",
        "Status: HIDUP & sehat",
        "",
        f"📊 Saldo: ${balance:,.2f} ({total_pnl:+,.2f} dari awal)",
        f"📈 24 jam terakhir: {d1[1]} trade | ${d1[0]:+,.2f}",
        f"📅 7 hari terakhir: {d7[1]} trade | WR {wr7:.0%} | ${d7[0]:+,.2f}",
        f"📉 Drawdown: {dd:.1%}",
    ]
    if opens:
        lines.append(f"🔓 Posisi terbuka: {len(opens)}")
        for sym, dirc, entry, ot in opens:
            d = "LONG" if dirc == 1 else "SHORT"
            dec = 3 if "JPY" in sym else 5
            lines.append(f"  • {d} {sym} @ {entry:.{dec}f} (buka {ot[:16]})")
    else:
        lines.append("🔓 Posisi terbuka: tidak ada")
    lines += ["", "Dewan 9 peran standby. Laporan otomatis tiap ada trade."]
    msg = "\n".join(lines)
    print(msg)
    send(msg)


if __name__ == "__main__":
    main()
