"""Kalender ekonomi gratis (feed ForexFactory) untuk blackout news.
Gagal fetch -> fail-open (trading tetap jalan), tidak pernah menghentikan bot.
"""
import os
import time
import datetime
import xml.etree.ElementTree as ET
import config

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
CACHE = os.path.join(config.BASE_DIR, "news_cache.xml")
CACHE_TTL = 6 * 3600  # refresh tiap 6 jam
HIGH_IMPACT = {"High"}
# negara yang relevan dengan pair yang ditrade
COUNTRIES = {"USD", "EUR", "GBP", "JPY", "AUD"}


def _refresh() -> bool:
    try:
        import requests
        r = requests.get(FEED, timeout=15)
        r.raise_for_status()
        with open(CACHE, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"[news] gagal refresh kalender: {e}")
        return False


def events():
    """List (waktu_utc, judul, negara) news high-impact minggu ini."""
    if not os.path.exists(CACHE) or time.time() - os.path.getmtime(CACHE) > CACHE_TTL:
        _refresh()
    if not os.path.exists(CACHE):
        return []
    try:
        root = ET.parse(CACHE).getroot()
    except Exception:
        return []
    out = []
    for ev in root.findall("event"):
        try:
            if ev.findtext("impact") not in HIGH_IMPACT:
                continue
            if ev.findtext("country") not in COUNTRIES:
                continue
            dt = datetime.datetime.strptime(ev.findtext("date"), "%Y-%m-%dT%H:%M:%S%z")
            out.append((dt, ev.findtext("title"), ev.findtext("country")))
        except Exception:
            continue
    return out


def blackout(minutes_before: int = 30, minutes_after: int = 30):
    """(True, 'judul (negara)') jika ada news high-impact dalam jendela waktu."""
    now = datetime.datetime.now(datetime.timezone.utc)
    for dt, title, country in events():
        if dt - datetime.timedelta(minutes=minutes_before) <= now <= dt + datetime.timedelta(minutes=minutes_after):
            return True, f"{title} ({country})"
    return False, ""
