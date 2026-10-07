"""Ambil data OHLC + hitung indikator teknikal (pandas murni, tanpa TA-Lib)."""
import datetime
import numpy as np
import pandas as pd

try:
    from dukascopy_python import fetch as duka_fetch, INTERVAL_HOUR_1, OFFER_SIDE_BID
    _HAS_DUKA = True
except ImportError:
    _HAS_DUKA = False

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False

_DUKA_SYMBOL = {"EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD"}


def _parse_period(period: str) -> datetime.timedelta:
    n = int(period[:-1])
    unit = period[-1].lower()
    if unit == "y":
        return datetime.timedelta(days=365 * n)
    if unit == "d":
        return datetime.timedelta(days=n)
    if unit == "h":
        return datetime.timedelta(hours=n)
    raise ValueError(f"period tidak dikenal: {period}")


def fetch(symbol: str, period: str = "2y", interval: str = "1h") -> pd.DataFrame:
    """Sumber utama: Dukascopy (gratis, tanpa key). Fallback: yfinance."""
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - _parse_period(period)
    if _HAS_DUKA and symbol in _DUKA_SYMBOL:
        df = duka_fetch(_DUKA_SYMBOL[symbol], INTERVAL_HOUR_1, OFFER_SIDE_BID, start, end)
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                 "close": "Close", "volume": "Volume"})
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if _HAS_YF:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    raise RuntimeError("tidak ada sumber data (install dukascopy-python / yfinance)")


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_s = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_s
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["Close"]
    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["rsi"] = rsi(c)
    df["atr"] = atr(df)
    df["adx"] = adx(df)
    bb_mid = c.rolling(20).mean()
    bb_sd = c.rolling(20).std()
    df["bb_up"] = bb_mid + 2 * bb_sd
    df["bb_lo"] = bb_mid - 2 * bb_sd
    df["bb_bw"] = (df["bb_up"] - df["bb_lo"]) / bb_mid  # bandwidth
    df["don_hi"] = df["High"].rolling(20).max()
    df["don_lo"] = df["Low"].rolling(20).min()
    df["atr_median"] = df["atr"].rolling(100).median()
    return df.dropna()
