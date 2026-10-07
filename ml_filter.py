"""ML filter: belajar dari riwayat trade. Model hanya meloloskan sinyal
yang 'menurut pengalaman' berpotensi profit. Di-retrain tiap minggu."""
import os
import pickle
import sqlite3
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import config

FEATURES = ["f_rsi", "f_adx", "f_atr_ratio", "f_bb_pos", "f_ema_dist", "f_hour"]


def load_dataset(db_path: str = config.DB_PATH) -> pd.DataFrame:
    if not os.path.exists(db_path):
        return pd.DataFrame()
    with sqlite3.connect(db_path) as c:
        df = pd.read_sql("SELECT * FROM trades WHERE pnl IS NOT NULL", c)
    return df.dropna(subset=FEATURES)


def train(db_path: str = config.DB_PATH, model_path: str = config.MODEL_PATH) -> dict:
    from sklearn.model_selection import cross_val_score
    df = load_dataset(db_path)
    if len(df) < config.MIN_TRADES_FOR_ML:
        return {"status": "skip", "trades": len(df),
                "need": config.MIN_TRADES_FOR_ML}
    X, y = df[FEATURES], (df["pnl"] > 0).astype(int)
    if y.nunique() < 2:
        return {"status": "skip", "trades": len(df), "reason": "hanya satu kelas"}
    # hindari model bias kelas: seimbangkan bobot
    model = RandomForestClassifier(n_estimators=100, max_depth=6,
                                   class_weight="balanced", random_state=42)
    # GATE: model hanya dipakai kalau validasi silang > lempar koin.
    # Mencegah model overfit ikut live.
    cv = cross_val_score(model, X, y, cv=3, scoring="accuracy")
    cv_mean = float(cv.mean())
    if cv_mean <= 0.55:
        return {"status": "rejected", "trades": len(df),
                "cv_accuracy": round(cv_mean, 3),
                "reason": "tidak lebih baik dari acak -> model tidak dipakai"}
    model.fit(X, y)
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    imp = dict(zip(FEATURES, model.feature_importances_.round(3)))
    return {"status": "trained", "trades": len(df),
            "cv_accuracy": round(cv_mean, 3),
            "winrate_data": round(float(y.mean()), 3),
            "importance": imp}


class MLFilter:
    def __init__(self, model_path: str = config.MODEL_PATH):
        self.model = None
        if os.path.exists(model_path):
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)

    def approve(self, features: dict) -> tuple:
        """Return (boleh_entry, probabilitas)."""
        if self.model is None:
            return True, 0.5  # fase belajar: loloskan semua
        x = [[features.get(k, 0) for k in FEATURES]]
        proba = float(self.model.predict_proba(x)[0][1])
        return proba >= config.ML_THRESHOLD, round(proba, 3)

    def reload(self):
        self.__init__()
