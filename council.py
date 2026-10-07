"""DEWAN 7 PERAN: tiap peran memberi suara, Ketua memutuskan entry/skip.
Manajer Risiko punya HAK VETO. Semua suara dicatat transparan."""
from dataclasses import dataclass, field


@dataclass
class Vote:
    role: str
    score: float       # -1.0 (tolak) sampai +1.0 (dukung)
    reason: str
    veto: bool = False


class TechnicalAnalyst:
    """Peran 1 — Analis Teknikal: membaca sinyal strategi + regime."""
    name = "Analis Teknikal"

    def vote(self, sig, df, ctx):
        if sig is None:
            return Vote(self.name, 0.0, "tidak ada sinyal")
        return Vote(self.name, 0.6, f"{sig.strategy} ({sig.regime})")


class SessionExpert:
    """Peran 2 — Ahli Sesi: pasar forex ramai saat London/New York."""
    name = "Ahli Sesi"

    def vote(self, sig, df, ctx):
        h = int(df.index[-1].hour)  # UTC
        if 7 <= h <= 21:
            return Vote(self.name, 0.4, f"jam {h:02d}:00 UTC sesi aktif")
        return Vote(self.name, -0.8, f"jam {h:02d}:00 UTC pasar sepi")


class VolatilityGuard:
    """Peran 3 — Penjaga Volatilitas: tolak saat gonjang-ganjing abnormal."""
    name = "Penjaga Volatilitas"

    def vote(self, sig, df, ctx):
        r = df.iloc[-1]
        ratio = float(r["atr"] / r["atr_median"]) if r["atr_median"] else 1.0
        if ratio > 2.5:
            return Vote(self.name, -1.0, f"ATR {ratio:.1f}x normal (berita?)")
        if ratio > 1.8:
            return Vote(self.name, -0.4, f"ATR {ratio:.1f}x normal")
        return Vote(self.name, 0.2, "volatilitas normal")


class ExhaustionDetector:
    """Peran 4 — Detektor Kelelahan: jangan beli di pucuk / jual di lembah."""
    name = "Detektor Kelelahan"

    def vote(self, sig, df, ctx):
        if sig is None or sig.strategy != "breakout":
            return Vote(self.name, 0.0, "-")
        closes = df["Close"].tail(6)
        moves = (closes.diff() * sig.direction).tail(5)
        climax = (moves > 0).sum() >= 4 and abs(float(df["rsi"].iloc[-1]) - 50) > 25
        if climax:
            return Vote(self.name, -0.9, "pasar kelelahan (climax)")
        return Vote(self.name, 0.1, "tidak ada climax")


class MLValidator:
    """Peran 5 — Validator ML: suara berdasarkan pengalaman trade sebelumnya."""
    name = "Validator ML"

    def vote(self, sig, df, ctx):
        if sig is None:
            return Vote(self.name, 0.0, "-")
        ml = ctx.get("ml")
        if ml is None:
            return Vote(self.name, 0.0, "belum aktif (fase belajar)")
        ok, proba = ml.approve(sig.features)
        return Vote(self.name, round((proba - 0.5) * 2, 2), f"proba {proba}")


class RiskManagerRole:
    """Peran 6 — Manajer Risiko: punya HAK VETO mutlak."""
    name = "Manajer Risiko"

    def vote(self, sig, df, ctx):
        ok, why = ctx["risk"].allow_new_trade()
        if not ok:
            return Vote(self.name, -1.0, why, veto=True)
        return Vote(self.name, 0.3, "dalam batas aman")


class Chairman:
    """Peran 7 — Ketua Dewan: agregasi semua suara."""
    name = "Ketua Dewan"
    THRESHOLD = 0.5

    def decide(self, votes: list) -> tuple:
        for v in votes:
            if v.veto and v.score < 0:
                return False, f"VETO {v.role}: {v.reason}", votes
        total = round(sum(v.score for v in votes), 2)
        if total >= self.THRESHOLD:
            return True, f"skor {total} >= {self.THRESHOLD}", votes
        return False, f"skor {total} < {self.THRESHOLD}", votes


class PatternJudge:
    """Peran 8 — Hakim Pola: VETO kombinasi strategi+regime yang di-ban Auditor
    karena terbukti berdarah (auto-ban dari learn.py, kedaluwarsa otomatis)."""
    name = "Hakim Pola"

    def vote(self, sig, df, ctx):
        if sig is None:
            return Vote(self.name, 0.0, "-")
        broker = ctx.get("broker")
        if broker is None:
            return Vote(self.name, 0.0, "-")
        reason = broker.is_banned(sig.strategy, sig.regime)
        if reason:
            return Vote(self.name, -1.0, f"di-ban Auditor: {reason}", veto=True)
        return Vote(self.name, 0.1, "pola bersih")


class NewsGuard:
    """Peran 9 — Penjaga Berita: VETO entry di sekitar news high-impact
    (NFP, CPI, suku bunga). Kalender gagal dibaca -> fail-open, tetap voting netral."""
    name = "Penjaga Berita"

    def vote(self, sig, df, ctx):
        if sig is None:
            return Vote(self.name, 0.0, "-")
        try:
            from news import blackout
            hit, title = blackout()
        except Exception:
            return Vote(self.name, 0.0, "kalender tak tersedia")
        if hit:
            return Vote(self.name, -1.0, f"blackout: {title}", veto=True)
        return Vote(self.name, 0.1, "tidak ada news besar")


class Council:
    """Dewan lengkap: 6 peran voting + 1 ketua."""
    def __init__(self):
        self.roles = [TechnicalAnalyst(), SessionExpert(), VolatilityGuard(),
                      ExhaustionDetector(), MLValidator(), RiskManagerRole(),
                      PatternJudge(), NewsGuard()]
        self.chairman = Chairman()

    def decide(self, sig, df, ctx) -> tuple:
        if sig is None:
            votes = [r.vote(None, df, ctx) for r in self.roles]
            return False, "tidak ada sinyal", votes
        votes = [r.vote(sig, df, ctx) for r in self.roles]
        return self.chairman.decide(votes)

    @staticmethod
    def format_votes(votes: list) -> str:
        lines = []
        for v in votes:
            emo = "👍" if v.score > 0 else ("👎" if v.score < 0 else "➖")
            veto = " [VETO]" if v.veto else ""
            lines.append(f"{emo} {v.role}{veto}: {v.reason} ({v.score:+})")
        return "\n".join(lines)
