"""أسعار المعادن: حركة عشوائية تميل للرجوع للمتوسط."""
import math
import random
import time

import config
import db

# الاسم: (نوع الأيقونة، أدنى سعر، أعلى سعر، لون الإطار)
METALS = {
    "الماس":  ("diamond",  9_860,  63_000,  (70, 140, 255)),
    "ذهب":    ("gold",     2_210,  30_500,  (235, 170, 40)),
    "فضة":    ("silver",   103,    4_520,   (170, 170, 185)),
    "ياقوت":  ("ruby",     3_630,  108_000, (225, 50, 60)),
    "زمرد":   ("emerald",  3_040,  149_000, (50, 200, 90)),
    "بلاتين": ("platinum", 3_550,  64_600,  (190, 195, 210)),
    "نفط":    ("oil",      68,     2_090,   (130, 110, 170)),
    "نحاس":   ("copper",   42,     5_150,   (225, 120, 50)),
    "لؤلؤ":   ("pearl",    443,    9_300,   (240, 225, 235)),
}


def avg(name: str) -> float:
    _, lo, hi, _ = METALS[name]
    return math.sqrt(lo * hi)


def ensure():
    rows = db.market_rows()
    for name, (_, lo, hi, _) in METALS.items():
        if name not in rows:
            p = random.uniform(lo, hi) if random.random() < 0.3 else avg(name) * random.uniform(0.7, 1.4)
            p = min(hi, max(lo, p))
            db.market_set(name, p, p)
    if not db.meta_get("market_next"):
        db.meta_set("market_next", time.time() + config.MARKET_INTERVAL)


def tick():
    rows = db.market_rows()
    for name, (_, lo, hi, _) in METALS.items():
        p = rows[name][0]
        drift = 0.12 * (math.log(avg(name)) - math.log(p))
        new = p * math.exp(random.gauss(drift, 0.06))
        new = min(hi, max(lo, new))
        db.market_set(name, new, p)
    db.meta_set("market_next", time.time() + config.MARKET_INTERVAL)


def maybe_tick():
    nxt = float(db.meta_get("market_next", 0))
    if time.time() >= nxt:
        tick()


def seconds_left() -> int:
    return max(0, int(float(db.meta_get("market_next", 0)) - time.time()))


def snapshot() -> list[dict]:
    """قائمة جاهزة للرسم."""
    rows = db.market_rows()
    out = []
    for name, (kind, lo, hi, color) in METALS.items():
        price, prev = rows[name]
        pct = (price - prev) / prev * 100 if prev else 0
        out.append(dict(name=name, kind=kind, price=price, pct=pct,
                        high=hi, avg=avg(name), low=lo, color=color))
    return out


def price(name: str) -> int:
    return int(db.market_rows()[name][0])


def assets_value(u: dict) -> int:
    """قيمة المعادن + الممتلكات."""
    total = 0
    rows = db.market_rows()
    for k, q in u["inv"].items():
        if k in rows:
            total += int(rows[k][0]) * q
        elif k in config.STORE_ITEMS:
            total += config.STORE_ITEMS[k]["price"] * q
    return total
