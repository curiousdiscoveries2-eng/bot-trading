# 🤖 Bot Autotrading Forex — Full Auto

Bot Python yang jalan 24/7: AI memilih strategi sesuai kondisi pasar
(regime detection), money management full-otomatis, dan **belajar dari
kesalahan** via retrain ML mingguan. Paper trading dulu — tanpa duit beneran.

## Arsitektur

| Modul | Fungsi |
|---|---|
| `data.py` | Data OHLC gratis (Dukascopy) + indikator (EMA/RSI/ATR/ADX/BB/Donchian) |
| `strategy.py` | Regime detector → pilih strategi: breakout (trending), mean-reversion (ranging) |
| `ml_filter.py` | Model RandomForest: hanya loloskan sinyal yg "menurut pengalaman" profit. Di-retrain tiap minggu; model overfit DITOLAK otomatis (CV gate) |
| `risk.py` | Position sizing dari % risiko, batas rugi harian, kill switch drawdown |
| `broker.py` | Paper broker (simulasi spread realistis) + log trade SQLite |
| `notify.py` | Notifikasi Telegram + perintah `/stop` (darurat) & `/status` |
| `dashboard.py` | Dashboard web (buka dari HP): balance, equity curve, riwayat trade |
| `learn.py` | Job mingguan: retrain ML + laporan performa |
| `run.py` | Loop utama live |
| `backtest.py` | Backtest memakai kode strategi yg SAMA persis dengan live |

## Hasil backtest (data real Dukascopy, ~1.4 tahun, H1)

> ⚠️ **Jujur:** strategi dasar belum menunjukkan edge yang konsisten
> (sistem dewan: EURUSD -9.5%, GBPUSD -5.6%; kill switch aktif dan kerugian
> terkendali). Dewan 7 peran membuat entry lebih selektif & transparan,
> tapi **winrate tinggi tidak bisa dijanjikan** — harus dibuktikan di
> paper trading forward. **Bot ini aman untuk demo** (risk management
> terbukti bekerja), tapi JANGAN pakai uang asli sebelum hasil demo
> konsisten bagus minimal 1-3 bulan.

## Dewan 7 Peran (council.py)

Setiap sinyal entry disidangkan oleh dewan sebelum dieksekusi:

| # | Peran | Tugas |
|---|---|---|
| 1 | Analis Teknikal | Menilai sinyal strategi + regime |
| 2 | Ahli Sesi | +dukung jam 07-21 UTC (London/NY), tolak pasar sepi |
| 3 | Penjaga Volatilitas | Tolak saat ATR spike abnormal (news besar) |
| 4 | Detektor Kelelahan | Tolak entry breakout saat pasar climax/kelelahan |
| 5 | Validator ML | Suara dari model yg belajar dari riwayat trade |
| 6 | Manajer Risiko | **HAK VETO** — tolak mutlak jika batas terlampaui |
| 7 | Ketua Dewan | Agregasi suara, entry jika skor >= 0.5 |

Peran ke-8, **Auditor**, bekerja tiap minggu via `learn.py`: membedah pola
kekalahan (strategi/regime/jam terburuk) dan melaporkannya ke Telegram.

## Deploy: 3 pilihan (termasuk yang GRATIS tanpa kartu kredit)

### A. GitHub Actions — 100% GRATIS, tanpa kartu (REKOMENDASI untuk mulai)

Bot jalan tiap 2 jam via scheduled workflow. Repo **public** = menit Actions
unlimited. State (trades.db + model) di-commit otomatis tiap run.

```bash
# 1. bikin repo public baru di github.com, upload semua file ini
# 2. di repo: Settings -> Secrets and variables -> Actions, tambahkan:
#      TELEGRAM_TOKEN   (dari @BotFather)
#      TELEGRAM_CHAT_ID (dari https://api.telegram.org/botTOKEN/getUpdates)
# 3. buka tab Actions -> enable workflows. Selesai!
# Monitoring: notifikasi Telegram tiap trade + /status manual via workflow_dispatch
```

### B. VPS lokal bayar QRIS/transfer — ~Rp50-100rb/bln, tanpa kartu kredit

Provider lokal (contoh: hostnic.id, IDCloudHost) terima QRIS, OVO, virtual
account, transfer bank. Ikuti langkah di bawah.

### C. VPS (Ubuntu) — langkah umum

```bash
# 1. copy folder ini ke VPS, misal /home/ubuntu/autotrading
# 2. install
cd /home/ubuntu/autotrading
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

# 3. buat bot Telegram via @BotFather -> dapatkan token
#    kirim /start ke bot, dapatkan chat id via https://api.telegram.org/botTOKEN/getUpdates

# 4. install service
sudo cp bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/bot.service   # isi TELEGRAM_TOKEN & TELEGRAM_CHAT_ID
sudo systemctl daemon-reload && sudo systemctl enable --now bot

# 5. retrain mingguan (cron)
(crontab -l; echo "0 0 * * 0 /home/ubuntu/autotrading/venv/bin/python /home/ubuntu/autotrading/learn.py") | crontab -

# 6. dashboard: http://IP-VPS:5000  (batasi akses via firewall / basic auth)
```

## Perintah Telegram

- `/status` — balance, P/L hari ini, posisi terbuka
- `/stop` — DARURAT: tutup semua posisi & hentikan bot

## Profil risiko

`BOT_RISK_PROFILE=konservatif|sedang|agresif` (lihat `config.py`).
Default: sedang (1% risiko/trade, 3% max rugi harian, 10% kill switch drawdown).
