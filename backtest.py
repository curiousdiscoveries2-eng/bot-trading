"""Backtest event-driven: memakai strategy.py, risk.py, broker.py yang SAMA
dengan yang dipakai live. Tidak ada lookahead (indikator kausal)."""
import sys
import pandas as pd
import config
from data import fetch, add_indicators
from strategy import generate_signal
from risk import RiskManager
from broker import PaperBroker
from ml_filter import MLFilter
from council import Council


def run_backtest(symbol: str, period: str = "2y", use_ml: bool = False,
                 db_path: str = None, df=None) -> dict:
    import os
    if db_path is None:
        db_path = f"/tmp/bt_{symbol.replace('=','')}.db"
        if os.path.exists(db_path):
            os.remove(db_path)
    if df is None:
        df = add_indicators(fetch(symbol, period=period, interval=config.TIMEFRAME))
    risk = RiskManager(config.RISK, config.START_BALANCE)
    broker = PaperBroker(db_path=db_path)
    ml = MLFilter() if use_ml else None
    council = Council()
    # tanpa ML: validator abstain (skor 0) -> keputusan dari 5 peran lain
    equity = []
    last_day = None

    # butuh 100 bar untuk median ATR/BB (warmup), mulai setelahnya
    for i in range(100, len(df)):
        ts = df.index[i]
        if last_day != ts.date():
            risk.new_day()
            last_day = ts.date()
        window = df.iloc[:i + 1]
        bar = {"Open": df["Open"].iloc[i], "High": df["High"].iloc[i],
               "Low": df["Low"].iloc[i], "Close": df["Close"].iloc[i]}

        # 1) update posisi terbuka (cek SL/TP)
        for pnl, reason, pos in broker.update(symbol, bar, str(ts)):
            risk.on_trade_close(pnl)

        # 2) sidang dewan untuk sinyal baru
        if not any(p.symbol == symbol for p in broker.positions):
            sig = generate_signal(window, symbol, config.SL_ATR_MULT, config.TP_RR)
            ctx = {"risk": risk, "ml": ml}
            approved, reason, votes = council.decide(sig, window, ctx)
            if approved and sig is not None:
                size = risk.position_size(sig.entry, sig.stop)
                if size > 0:
                    pos = broker.open(sig, size, config.SPREAD[symbol], str(ts))
                    pos.features = sig.features
                    risk.on_trade_open()
        equity.append(risk.state.balance)

    # tutup sisa posisi di harga terakhir
    if broker.positions:
        px = {symbol: df["Close"].iloc[-1]}
        pnl = broker.close_all(px, str(df.index[-1]), "backtest_end")
        risk.state.balance += pnl

    stats = broker.trade_stats()
    eq = pd.Series(equity)
    peak = eq.cummax()
    max_dd = ((peak - eq) / peak).max()
    stats.update({
        "symbol": symbol,
        "bars": len(df),
        "final_balance": round(risk.state.balance, 2),
        "return_pct": round((risk.state.balance / config.START_BALANCE - 1) * 100, 2),
        "max_drawdown": round(float(max_dd) * 100, 2),
    })
    return stats


if __name__ == "__main__":
    import os
    from data import fetch, add_indicators
    from ml_filter import train as ml_train

    if "--walkforward" in sys.argv:
        # Uji "belajar dari kesalahan": latih ML di 60% awal,
        # evaluasi di 40% akhir (data yang belum pernah dilihat model)
        for sym in config.SYMBOLS:
            print(f"Walk-forward {sym}...")
            df = add_indicators(fetch(sym, period="2y", interval=config.TIMEFRAME))
            split = int(len(df) * 0.6)
            train_db = f"/tmp/wf_train_{sym.replace('=','')}.db"
            if os.path.exists(train_db):
                os.remove(train_db)
            run_backtest(sym, df=df.iloc[:split], db_path=train_db)
            res = ml_train(train_db)
            print(f"  ML train: {res}")
            if os.path.exists(config.MODEL_PATH):
                os.remove(config.MODEL_PATH)
            # model dilatih ulang dari train_db agar pasti pakai data fase 1
            from ml_filter import load_dataset
            import pickle
            from sklearn.ensemble import RandomForestClassifier
            d = load_dataset(train_db)
            if len(d) >= config.MIN_TRADES_FOR_ML:
                X, y = d[["f_rsi","f_adx","f_atr_ratio","f_bb_pos","f_ema_dist","f_hour"]], (d["pnl"] > 0).astype(int)
                m = RandomForestClassifier(n_estimators=100, max_depth=6, class_weight="balanced", random_state=42)
                m.fit(X, y)
                with open(config.MODEL_PATH, "wb") as f:
                    pickle.dump(m, f)
            test_db_ml = f"/tmp/wf_test_ml_{sym.replace('=','')}.db"
            test_db_no = f"/tmp/wf_test_no_{sym.replace('=','')}.db"
            for p in (test_db_ml, test_db_no):
                if os.path.exists(p):
                    os.remove(p)
            s_ml = run_backtest(sym, df=df.iloc[split:], use_ml=True, db_path=test_db_ml)
            if os.path.exists(config.MODEL_PATH):
                os.remove(config.MODEL_PATH)
            s_no = run_backtest(sym, df=df.iloc[split:], use_ml=False, db_path=test_db_no)
            print(f"  40% akhir TANPA ML: return={s_no['return_pct']}% trades={s_no['trades']} wr={s_no['winrate']:.0%}")
            print(f"  40% akhir DENGAN ML: return={s_ml['return_pct']}% trades={s_ml['trades']} wr={s_ml['winrate']:.0%}")
            print()
    else:
        use_ml = "--ml" in sys.argv
        for sym in config.SYMBOLS:
            print(f"Backtest {sym} (ML filter: {use_ml})...")
            s = run_backtest(sym, use_ml=use_ml)
            for k, v in s.items():
                print(f"  {k}: {v}")
            print()
