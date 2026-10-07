"""Paper broker: simulasi eksekusi realistis (spread) + log trade ke SQLite."""
import sqlite3
from dataclasses import dataclass
import config


@dataclass
class Position:
    id: int
    symbol: str
    direction: int
    entry: float
    stop: float
    tp: float
    size: float
    strategy: str
    open_time: str


class PaperBroker:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.positions: list[Position] = []
        self._next_id = 1
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS trades(
                id INTEGER PRIMARY KEY, symbol TEXT, direction INTEGER,
                entry REAL, exit REAL, stop REAL, tp REAL, size REAL,
                strategy TEXT, regime TEXT, open_time TEXT, close_time TEXT,
                pnl REAL, reason TEXT,
                f_rsi REAL, f_adx REAL, f_atr_ratio REAL, f_bb_pos REAL,
                f_ema_dist REAL, f_hour INTEGER)""")

    def open(self, sig, size: float, spread: float, open_time: str) -> Position:
        # bayar spread saat entry (simulasi realistis)
        entry = sig.entry + sig.direction * spread / 2
        pos = Position(self._next_id, sig.symbol, sig.direction, entry,
                       sig.stop, sig.take_profit, size, sig.strategy, open_time)
        self._next_id += 1
        self.positions.append(pos)
        return pos

    def _close(self, pos: Position, exit_price: float, close_time: str, reason: str) -> float:
        # pair XXXUSD: P/L = selisih harga x unit, langsung USD
        pnl = (exit_price - pos.entry) * pos.direction * pos.size
        f = getattr(pos, "features", {}) or {}
        with sqlite3.connect(self.db_path) as c:
            c.execute("""INSERT INTO trades(symbol,direction,entry,exit,stop,tp,size,
                strategy,regime,open_time,close_time,pnl,reason,
                f_rsi,f_adx,f_atr_ratio,f_bb_pos,f_ema_dist,f_hour)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pos.symbol, pos.direction, pos.entry, exit_price, pos.stop, pos.tp,
                 pos.size, pos.strategy, f.get("regime", ""), pos.open_time,
                 close_time, pnl, reason,
                 f.get("rsi"), f.get("adx"), f.get("atr_ratio"), f.get("bb_pos"),
                 f.get("ema_dist"), f.get("hour")))
        self.positions = [p for p in self.positions if p.id != pos.id]
        return pnl

    def update(self, symbol: str, bar: dict, time: str) -> list:
        """Cek SL/TP tiap bar. Kembalikan list (pnl, reason)."""
        closed = []
        for pos in [p for p in self.positions if p.symbol == symbol]:
            exit_px, reason = None, ""
            if pos.direction == 1:
                if bar["Low"] <= pos.stop:
                    exit_px, reason = pos.stop, "stop_loss"
                elif bar["High"] >= pos.tp:
                    exit_px, reason = pos.tp, "take_profit"
            else:
                if bar["High"] >= pos.stop:
                    exit_px, reason = pos.stop, "stop_loss"
                elif bar["Low"] <= pos.tp:
                    exit_px, reason = pos.tp, "take_profit"
            if exit_px is not None:
                pnl = self._close(pos, exit_px, time, reason)
                closed.append((pnl, reason, pos))
        return closed

    def close_all(self, prices: dict, time: str, reason: str = "manual"):
        total = 0.0
        for pos in list(self.positions):
            total += self._close(pos, prices.get(pos.symbol, pos.entry), time, reason)
        return total

    def trade_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute("SELECT pnl FROM trades").fetchall()
        pnls = [r[0] for r in rows]
        wins = [p for p in pnls if p > 0]
        return {
            "trades": len(pnls),
            "winrate": len(wins) / len(pnls) if pnls else 0,
            "total_pnl": sum(pnls),
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(p for p in pnls if p <= 0) / max(1, len(pnls) - len(wins)),
        }
