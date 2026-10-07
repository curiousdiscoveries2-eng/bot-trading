"""Loop utama bot live (paper trading). Jalan 24/7 di VPS, NOL kuota AI."""
import time
import threading
import pandas as pd
import config
from data import fetch, add_indicators
from strategy import generate_signal
from risk import RiskManager
from broker import PaperBroker
from ml_filter import MLFilter
from council import Council
from notify import send, trade_opened, trade_closed, CommandListener
import dashboard

risk = RiskManager(config.RISK, config.START_BALANCE)
broker = PaperBroker()
# pulihkan state lintas-run (wajib untuk mode --once / GitHub Actions)
_bal = config.START_BALANCE + broker.closed_pnl_total()
_peak = broker.get_meta("peak_balance")
risk.restore(_bal,
             float(_peak) if _peak else max(config.START_BALANCE, _bal),
             broker.day_pnl_today(), len(broker.positions))
ml = MLFilter()
council = Council()
equity = [config.START_BALANCE]
running = True
last_day = None


def status_text():
    s = broker.trade_stats()
    return (f"📊 Balance: ${risk.state.balance:,.2f}\n"
            f"Hari ini: ${risk.state.day_pnl:+,.2f} | DD: {risk.drawdown():.1%}\n"
            f"Trade: {s['trades']} | WR: {s['winrate']:.0%} | "
            f"Posisi: {len(broker.positions)} | Halt: {risk.state.halted}")


def emergency_stop():
    global running
    prices = {}
    for sym in config.SYMBOLS:
        try:
            prices[sym] = fetch(sym, period="5d").iloc[-1]["Close"]
        except Exception:
            pass
    pnl = broker.close_all(prices, "emergency", "emergency_stop")
    risk.state.balance += pnl
    risk.state.halted = True
    risk.state.halt_reason = "emergency stop via Telegram"
    running = False
    send(f"🛑 Bot dihentikan. P/L penutupan: ${pnl:+,.2f}")


def cycle():
    global last_day
    today = pd.Timestamp.now().date()
    if last_day != today:
        risk.new_day()
        last_day = today
    for sym in config.SYMBOLS:
        try:
            df = add_indicators(fetch(sym, period="60d"))
        except Exception as e:
            print(f"[data] {sym}: {e}")
            continue
        bar = df.iloc[-1]
        ts = str(df.index[-1])
        # 1) kelola posisi terbuka
        for pnl, reason, pos in broker.update(sym, bar.to_dict(), ts):
            risk.on_trade_close(pnl)
            broker.set_meta("peak_balance", risk.state.peak_balance)
            send(trade_closed(pnl, reason, pos, risk.state.balance))
        # 2) sidang dewan: 7 peran voting untuk entry baru
        if any(p.symbol == sym for p in broker.positions):
            continue
        sig = generate_signal(df, sym, config.SL_ATR_MULT, config.TP_RR)
        ctx = {"risk": risk, "ml": ml}
        approved, reason, votes = council.decide(sig, df, ctx)
        if not approved:
            continue
        size = risk.position_size(sig.entry, sig.stop)
        if size <= 0:
            continue
        pos = broker.open(sig, size, config.SPREAD[sym], ts,
                          balance_before=risk.state.balance,
                          council_reason=reason,
                          council_votes=Council.format_votes(votes))
        pos.features = sig.features
        risk.on_trade_open()
        send(trade_opened(pos) + f"\n\n🗳️ Keputusan dewan: {reason}\n"
             + Council.format_votes(votes))
    equity.append(risk.state.balance)


def main():
    import sys
    global running
    once = "--once" in sys.argv
    if not once:
        send(f"🤖 Bot mulai jalan (profil: {config.RISK_PROFILE}, balance ${config.START_BALANCE:,.0f})")
        ctx = {"risk": risk, "broker": broker, "equity": equity, "running": True}
        threading.Thread(target=dashboard.start, args=(ctx,), daemon=True).start()
        listener = CommandListener(emergency_stop, status_text)
        listener.start()
    else:
        listener = None
        ctx = {"risk": risk, "broker": broker, "equity": equity, "running": True}
    try:
        if once:
            cycle()  # satu siklus saja (untuk GitHub Actions / cron)
            print(status_text())
        else:
            while running and not risk.state.halted:
                cycle()
                ctx["running"] = running and not risk.state.halted
                time.sleep(config.LOOP_MINUTES * 60)
    finally:
        ctx["running"] = False
        if listener:
            listener.stop()
        if not once:
            send("Bot berhenti. " + status_text())


if __name__ == "__main__":
    main()
