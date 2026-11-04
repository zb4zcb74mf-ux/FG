import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫،", "0123456789.,")
_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})

_MULT = {None: 1, "k": 1e3, "ك": 1e3, "الف": 1e3, "ألف": 1e3,
         "m": 1e6, "م": 1e6, "مليون": 1e6, "b": 1e9, "مليار": 1e9}


def norm(s: str) -> str:
    """توحيد الحروف: حماية/حمايه، إعدادات/اعدادات ..."""
    return s.strip().lower().translate(_NORM)


def to_ascii_digits(s: str) -> str:
    return s.translate(_DIGITS)


def parse_amount(s: str, balance: int = 0):
    """يفهم: 100 / 5k / 126K / 1.5m / نص / كامل / ٥٠٠٠ → int أو None"""
    s = to_ascii_digits(s).strip().lower().replace(",", "")
    if s in ("نص", "نصف", "half"):
        return balance // 2
    if s in ("كامل", "كل", "الكل", "all", "max"):
        return balance
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(k|m|b|ك|م|الف|ألف|مليون|مليار)?", s)
    if not m:
        return None
    return int(float(m.group(1)) * _MULT[m.group(2)])


def short(n: float) -> str:
    """$126k / $16.8m / $950"""
    n = abs(n)
    for div, suf in ((1e9, "b"), (1e6, "m"), (1e3, "k")):
        if n >= div:
            v = n / div
            s = f"{v:.0f}" if v >= 100 else f"{v:.1f}".rstrip("0").rstrip(".")
            return f"${s}{suf}"
    return f"${int(n)}"


def full(n: float) -> str:
    return f"${abs(int(n)):,}"


def dur(sec: float) -> str:
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} ساعة")
    if m:
        parts.append(f"{m} دقيقة")
    if not h and not m:
        parts.append(f"{s} ثانية")
    return " ".join(parts)
