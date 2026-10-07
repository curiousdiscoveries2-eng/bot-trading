"""Deteksi regime pasar + 3 modul strategi. AI memilih strategi sesuai regime."""
from dataclasses import dataclass
import pandas as pd


@dataclass
class Signal:
    symbol: str
    direction: int          # +1 long, -1 short
    strategy: str
    regime: str
    entry: float
    stop: float
    take_profit: float
    features: dict


def detect_regime(row: pd.Series, bw_median: float) -> str:
    """trending | ranging | volatile | calm"""
    if row["atr"] > 2.0 * row["atr_median"]:
        return "volatile"
    if row["adx"] > 25:
        return "trending"
    if row["bb_bw"] < bw_median:
        return "ranging"
    return "calm"


def _levels(entry: float, direction: int, atr_val: float, sl_mult: float, tp_rr: float):
    sl_dist = sl_mult * atr_val
    stop = entry - direction * sl_dist
    tp = entry + direction * sl_dist * tp_rr
    return stop, tp


def trend_signal(df: pd.DataFrame, symbol: str, sl_mult: float, tp_rr: float):
    r = df.iloc[-1]
    prev = df.iloc[-2]
    if r["adx"] < 25:
        return None
    direction = 0
    # 1) EMA cross (momentum baru)
    if r["ema20"] > r["ema50"] and prev["ema20"] <= prev["ema50"]:
        direction = 1
    elif r["ema20"] < r["ema50"] and prev["ema20"] >= prev["ema50"]:
        direction = -1
    # 2) Pullback entry: di uptrend, harga memantul dari EMA20
    elif r["ema20"] > r["ema50"]:
        if prev["Close"] < prev["ema20"] and r["Close"] > r["ema20"]:
            direction = 1
    elif r["ema20"] < r["ema50"]:
        if prev["Close"] > prev["ema20"] and r["Close"] < r["ema20"]:
            direction = -1
    if not direction:
        return None
    entry = r["Close"]
    stop, tp = _levels(entry, direction, r["atr"], sl_mult, tp_rr)
    return Signal(symbol, direction, "trend", "trending", entry, stop, tp, _features(df, r))


def meanrev_signal(df: pd.DataFrame, symbol: str, sl_mult: float, tp_rr: float):
    r = df.iloc[-1]
    direction = 0
    if r["Close"] < r["bb_lo"] and r["rsi"] < 30:
        direction = 1
    elif r["Close"] > r["bb_up"] and r["rsi"] > 70:
        direction = -1
    if not direction:
        return None
    entry = r["Close"]
    stop, tp = _levels(entry, direction, r["atr"], sl_mult, tp_rr)
    return Signal(symbol, direction, "meanrev", "ranging", entry, stop, tp, _features(df, r))


def breakout_signal(df: pd.DataFrame, symbol: str, sl_mult: float, tp_rr: float):
    r = df.iloc[-1]
    prev = df.iloc[-2]
    # filter fakeout: ADX harus > 25 DAN sedang naik (momentum terkonfirmasi)
    if r["adx"] < 25 or r["adx"] <= prev["adx"]:
        return None
    buf = 0.25 * r["atr"]  # penetrasi minimum, saring false breakout
    direction = 0
    if r["Close"] > prev["don_hi"] + buf:
        direction = 1
    elif r["Close"] < prev["don_lo"] - buf:
        direction = -1
    if not direction:
        return None
    entry = r["Close"]
    stop, tp = _levels(entry, direction, r["atr"], sl_mult, tp_rr)
    return Signal(symbol, direction, "breakout", "trending", entry, stop, tp, _features(df, r))


def _features(df: pd.DataFrame, r: pd.Series) -> dict:
    return {
        "rsi": float(r["rsi"]),
        "adx": float(r["adx"]),
        "atr_ratio": float(r["atr"] / r["atr_median"]) if r["atr_median"] else 1.0,
        "bb_pos": float((r["Close"] - r["bb_lo"]) / (r["bb_up"] - r["bb_lo"])) if r["bb_up"] != r["bb_lo"] else 0.5,
        "ema_dist": float((r["ema20"] - r["ema50"]) / r["Close"]),
        "hour": int(df.index[-1].hour),
        "strategy_trend": 0, "strategy_meanrev": 0, "strategy_breakout": 0,
    }


def generate_signal(df: pd.DataFrame, symbol: str, sl_mult: float, tp_rr: float):
    """Otak pemilih strategi: regime -> strategi yang cocok -> sinyal."""
    bw_median = df["bb_bw"].rolling(100).median().iloc[-1]
    regime = detect_regime(df.iloc[-1], bw_median)

    sig = None
    if regime == "trending":
        # catatan backtest: trend-following (EMA cross/pullback) konsisten
        # merugi di H1 -> dinonaktifkan, hanya breakout yang dipakai
        sig = breakout_signal(df, symbol, sl_mult, tp_rr)
    elif regime == "ranging":
        sig = meanrev_signal(df, symbol, sl_mult, tp_rr)
    # volatile & calm -> tidak entry (disiplin: tidak maksa)
    if sig:
        sig.features[f"strategy_{sig.strategy}"] = 1
        sig.features["regime"] = regime
    return sig
