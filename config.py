"""Konfigurasi bot autotrading. Ubah sesuai profil risiko."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Profil risiko: 'konservatif' | 'sedang' | 'agresif' ----
RISK_PROFILE = os.environ.get("BOT_RISK_PROFILE", "sedang")

PROFILES = {
    "konservatif": {"risk_per_trade": 0.005, "max_daily_loss": 0.015, "max_drawdown": 0.06, "max_positions": 2},
    "sedang":      {"risk_per_trade": 0.01,  "max_daily_loss": 0.03,  "max_drawdown": 0.10, "max_positions": 3},
    "agresif":     {"risk_per_trade": 0.02,  "max_daily_loss": 0.05,  "max_drawdown": 0.15, "max_positions": 5},
}
RISK = PROFILES[RISK_PROFILE]

# ---- Trading ----
SYMBOLS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"]
TIMEFRAME = "1h"
START_BALANCE = 10000.0
SPREAD = {"EURUSD=X": 0.00020, "GBPUSD=X": 0.00025,
          "USDJPY=X": 0.020, "AUDUSD=X": 0.00018}  # simulasi spread realistis
SL_ATR_MULT = 1.5
TP_RR = 2.0            # take profit = 2x risiko (risk:reward 1:2)
LOOP_MINUTES = 15      # cek sinyal tiap 15 menit

# ---- ML filter ----
MIN_TRADES_FOR_ML = 50      # sebelum 50 trade, semua sinyal lolos (fase belajar)
ML_THRESHOLD = 0.55

# ---- File ----
DB_PATH = os.path.join(BASE_DIR, "trades.db")
MODEL_PATH = os.path.join(BASE_DIR, "ml_model.pkl")
EQUITY_PATH = os.path.join(BASE_DIR, "equity.png")

# ---- Telegram (isi via environment saat deploy) ----
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---- Dashboard ----
DASHBOARD_PORT = 5000
