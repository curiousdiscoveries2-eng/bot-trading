"""Notifikasi Telegram + perintah darurat (/stop, /status)."""
import threading
import requests
import config

API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def _px(symbol: str, v: float) -> str:
    """Format harga: 3 desimal untuk JPY, 5 untuk lainnya."""
    dec = 3 if "JPY" in symbol else 5
    return f"{v:.{dec}f}"


def send(msg: str):
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(f"[TG] {msg}")
        return
    try:
        requests.post(f"{API}/sendMessage",
                      json={"chat_id": config.TELEGRAM_CHAT_ID, "text": msg},
                      timeout=10)
    except Exception as e:
        print(f"[TG error] {e}")


def trade_opened(pos) -> str:
    d = "LONG" if pos.direction == 1 else "SHORT"
    return (f"🟢 OPEN {d} {pos.symbol}\n"
            f"Entry: {_px(pos.symbol, pos.entry)} | SL: {_px(pos.symbol, pos.stop)}"
            f" | TP: {_px(pos.symbol, pos.tp)}\n"
            f"Size: {pos.size:,.0f} unit | Strategi: {pos.strategy}\n"
            f"💰 Saldo saat open: ${pos.balance_before:,.2f}")


def trade_closed(pnl: float, close_reason: str, pos, balance_after: float) -> str:
    d = "LONG" if pos.direction == 1 else "SHORT"
    hasil = "✅ WIN" if pnl > 0 else "❌ LOSS"
    reason_id = {"take_profit": "take profit 🎯",
                 "stop_loss": "stop loss 🛑",
                 "emergency": "emergency stop 🛑"}.get(close_reason, close_reason)
    risk_amt = abs(pos.entry - pos.stop) * pos.size
    if pos.symbol.startswith("USD"):  # konversi risiko JPY -> USD
        risk_amt /= pos.entry
    rmult = pnl / risk_amt if risk_amt > 0 else 0.0
    votes = f"\n{pos.council_votes}" if pos.council_votes else ""
    return (f"{hasil} — CLOSE {d} {pos.symbol}\n"
            f"Alasan: {reason_id}\n\n"
            f"💰 P/L: ${pnl:+,.2f} ({rmult:+.1f}R)\n"
            f"📊 Saldo: ${pos.balance_before:,.2f} → ${balance_after:,.2f}\n\n"
            f"🎯 Kenapa posisi ini dibuka:\n"
            f"• Strategi: {pos.strategy} | Dewan: {pos.council_reason}"
            f"{votes}\n\n"
            f"Entry {_px(pos.symbol, pos.entry)} | SL {_px(pos.symbol, pos.stop)}"
            f" | TP {_px(pos.symbol, pos.tp)}\n"
            f"Dibuka: {pos.open_time}")


class CommandListener(threading.Thread):
    """Polling perintah Telegram: /stop (darurat), /status."""
    daemon = True

    def __init__(self, on_stop, on_status):
        super().__init__()
        self.on_stop = on_stop
        self.on_status = on_status
        self._offset = 0
        self._running = True

    def run(self):
        if not config.TELEGRAM_TOKEN:
            return
        while self._running:
            try:
                r = requests.get(f"{API}/getUpdates",
                                 params={"offset": self._offset, "timeout": 30},
                                 timeout=35).json()
                for u in r.get("result", []):
                    self._offset = u["update_id"] + 1
                    msg = u.get("message", {})
                    if str(msg.get("chat", {}).get("id")) != str(config.TELEGRAM_CHAT_ID):
                        continue
                    text = msg.get("text", "").strip().lower()
                    if text == "/stop":
                        send("🛑 PERINTAH DARURAT: menutup semua posisi & menghentikan bot.")
                        self.on_stop()
                    elif text == "/status":
                        send(self.on_status())
            except Exception:
                pass

    def stop(self):
        self._running = False
