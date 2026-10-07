"""Notifikasi Telegram + perintah darurat (/stop, /status)."""
import threading
import requests
import config

API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


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
            f"Entry: {pos.entry:.5f} | SL: {pos.stop:.5f} | TP: {pos.tp:.5f}\n"
            f"Size: {pos.size:,.0f} unit | Strategi: {pos.strategy}")


def trade_closed(pnl: float, reason: str, pos) -> str:
    emo = "✅" if pnl > 0 else "❌"
    return (f"{emo} CLOSE {pos.symbol} ({reason})\n"
            f"P/L: ${pnl:,.2f}")


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
