"""Money management full-otomatis: sizing, batas harian, kill switch."""
from dataclasses import dataclass


@dataclass
class RiskState:
    balance: float
    peak_balance: float
    day_pnl: float
    open_count: int
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self, cfg: dict, start_balance: float):
        self.cfg = cfg
        self.state = RiskState(start_balance, start_balance, 0.0, 0)

    def position_size(self, entry: float, stop: float, symbol: str = "",
                      price: float = 0.0) -> float:
        """Ukuran posisi (unit) dari % risiko per trade.
        Pair USDXXX (mis. USDJPY): risiko dihitung dalam JPY -> konversi ke USD."""
        risk_amount = self.state.balance * self.cfg["risk_per_trade"]
        dist = abs(entry - stop)
        if dist <= 0:
            return 0.0
        size = risk_amount / dist
        if symbol.startswith("USD") and price > 0:
            size *= price
        return size

    def allow_new_trade(self) -> tuple:
        s, c = self.state, self.cfg
        if s.halted:
            return False, f"HALT: {s.halt_reason}"
        if s.day_pnl <= -c["max_daily_loss"] * s.balance:
            return False, "batas rugi harian tercapai"
        if s.open_count >= c["max_positions"]:
            return False, "slot posisi penuh"
        return True, "ok"

    def on_trade_close(self, pnl: float):
        s = self.state
        s.balance += pnl
        s.day_pnl += pnl
        s.open_count = max(0, s.open_count - 1)
        s.peak_balance = max(s.peak_balance, s.balance)
        dd = (s.peak_balance - s.balance) / s.peak_balance
        if dd >= self.cfg["max_drawdown"]:
            s.halted = True
            s.halt_reason = f"drawdown {dd:.1%} >= batas"

    def on_trade_open(self):
        self.state.open_count += 1

    def new_day(self):
        self.state.day_pnl = 0.0

    def restore(self, balance: float, peak_balance: float, day_pnl: float, open_count: int):
        """Pulihkan state lintas-run (mode --once / GitHub Actions)."""
        s = self.state
        s.balance = balance
        s.peak_balance = max(peak_balance, balance)
        s.day_pnl = day_pnl
        s.open_count = open_count

    def drawdown(self) -> float:
        s = self.state
        return (s.peak_balance - s.balance) / s.peak_balance if s.peak_balance else 0.0
