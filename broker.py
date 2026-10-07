"""Paper broker: simulasi eksekusi realistis (spread) + log trade ke SQLite."""
import sqlite3
from dataclasses import dataclass
import config


def _pnl_usd(symbol: str, entry: float, exit_price: float, direction: int, size: float) -> float:
    """P/L dalam USD. Pair XXXUSD: langsung. Pair USDXXX (mis. USDJPY):
    P/L dalam mata uang quote -> konversi ke USD pakai harga exit."""
    pnl = (exit_price - entry) * direction * size
    if symbol.startswith("USD") and exit_price:
        pnl /= exit_price
    return pnl


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
    balance_before: float = 0.0   # saldo saat posisi dibuka
    council_reason: str = ""       # ringkasan keputusan dewan
    council_votes: str = ""        # rincian voting (teks)


class PaperBroker:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.positions: list[Position] = []
        self._next_id = 1
        self._init_db()
        self._load_open()   # pulihkan posisi lintas-run (mode --once)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS trades(
                id INTEGER PRIMARY KEY, symbol TEXT, direction INTEGER,
                entry REAL, exit REAL, stop REAL, tp REAL, size REAL,
                strategy TEXT, regime TEXT, open_time TEXT, close_time TEXT,
                pnl REAL, reason TEXT,
                f_rsi REAL, f_adx REAL, f_atr_ratio REAL, f_bb_pos REAL,
                f_ema_dist REAL, f_hour INTEGER)""")
            # posisi yang masih terbuka — bertahan antar-run
            c.execute("""CREATE TABLE IF NOT EXISTS open_positions(
                id INTEGER PRIMARY KEY, symbol TEXT, direction INTEGER,
                entry REAL, stop REAL, tp REAL, size REAL,
                strategy TEXT, open_time TEXT,
                balance_before REAL, council_reason TEXT, council_votes TEXT)""")
            # state kecil bot (peak balance utk drawdown lintas-run)
            c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
            # daftar hitam Auditor: (strategi, regime) yang terbukti berdarah
            c.execute("""CREATE TABLE IF NOT EXISTS bans(
                strategy TEXT, regime TEXT, banned_until TEXT, reason TEXT,
                PRIMARY KEY(strategy, regime))""")

    def _load_open(self):
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute("""SELECT id,symbol,direction,entry,stop,tp,size,
                strategy,open_time,balance_before,council_reason,council_votes
                FROM open_positions""").fetchall()
        for r in rows:
            self.positions.append(Position(*r))
            self._next_id = max(self._next_id, r[0] + 1)

    def open(self, sig, size: float, spread: float, open_time: str,
             balance_before: float = 0.0, council_reason: str = "",
             council_votes: str = "") -> Position:
        # bayar spread saat entry (simulasi realistis)
        entry = sig.entry + sig.direction * spread / 2
        pos = Position(self._next_id, sig.symbol, sig.direction, entry,
                       sig.stop, sig.take_profit, size, sig.strategy, open_time,
                       balance_before, council_reason, council_votes)
        self._next_id += 1
        self.positions.append(pos)
        with sqlite3.connect(self.db_path) as c:
            c.execute("""INSERT INTO open_positions(id,symbol,direction,entry,stop,tp,
                size,strategy,open_time,balance_before,council_reason,council_votes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pos.id, pos.symbol, pos.direction, pos.entry, pos.stop, pos.tp,
                 pos.size, pos.strategy, pos.open_time, balance_before,
                 council_reason, council_votes))
        return pos

    def _close(self, pos: Position, exit_price: float, close_time: str, reason: str) -> float:
        pnl = _pnl_usd(pos.symbol, pos.entry, exit_price, pos.direction, pos.size)
        f = getattr(pos, "features", {}) or {}
        with sqlite3.connect(self.db_path) as c:
            c.execute("DELETE FROM open_positions WHERE id=?", (pos.id,))
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

    # ---- helper lintas-run ----
    def closed_pnl_total(self) -> float:
        with sqlite3.connect(self.db_path) as c:
            row = c.execute("SELECT COALESCE(SUM(pnl),0) FROM trades").fetchone()
        return float(row[0])

    def day_pnl_today(self) -> float:
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        with sqlite3.connect(self.db_path) as c:
            row = c.execute(
                "SELECT COALESCE(SUM(pnl),0) FROM trades WHERE substr(close_time,1,10)=?",
                (today,)).fetchone()
        return float(row[0])

    def get_meta(self, key: str, default=None):
        with sqlite3.connect(self.db_path) as c:
            row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value):
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, str(value)))

    # ---- daftar hitam Auditor ----
    def add_ban(self, strategy: str, regime: str, days: int, reason: str):
        import datetime
        until = (datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as c:
            c.execute("INSERT INTO bans VALUES(?,?,?,?) "
                      "ON CONFLICT(strategy,regime) DO UPDATE SET "
                      "banned_until=excluded.banned_until, reason=excluded.reason",
                      (strategy, regime, until, reason))

    def is_banned(self, strategy: str, regime: str):
        """Kembalikan alasan ban jika (strategi, regime) masih di-ban, else None."""
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as c:
            row = c.execute("SELECT reason, banned_until FROM bans "
                            "WHERE strategy=? AND regime=? AND banned_until>?",
                            (strategy, regime, now)).fetchone()
        return f"{row[0]} (s/d {row[1][:10]})" if row else None
