import json
import sqlite3
import time

import config

_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0,
    debt INTEGER NOT NULL DEFAULT 0,
    shield_until REAL NOT NULL DEFAULT 0,
    spouse INTEGER,
    married_at REAL,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    cd TEXT NOT NULL DEFAULT '{}',
    inv TEXT NOT NULL DEFAULT '{}',
    perks TEXT NOT NULL DEFAULT '{}',
    settings TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS market(
    key TEXT PRIMARY KEY, price REAL, prev REAL
);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
""")
_conn.commit()

_JSON = ("cd", "inv", "perks", "settings")


def get_user(uid: int) -> dict:
    row = _conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if row is None:
        _conn.execute("INSERT INTO users(id) VALUES(?)", (uid,))
        _conn.commit()
        row = _conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    u = dict(row)
    for k in _JSON:
        u[k] = json.loads(u[k])
    return u


def save(u: dict):
    d = dict(u)
    for k in _JSON:
        d[k] = json.dumps(d[k], ensure_ascii=False)
    _conn.execute(
        """UPDATE users SET balance=:balance, debt=:debt, shield_until=:shield_until,
           spouse=:spouse, married_at=:married_at, wins=:wins, losses=:losses,
           cd=:cd, inv=:inv, perks=:perks, settings=:settings WHERE id=:id""", d)
    _conn.commit()


def all_users() -> list[dict]:
    rows = _conn.execute("SELECT * FROM users").fetchall()
    out = []
    for r in rows:
        u = dict(r)
        for k in _JSON:
            u[k] = json.loads(u[k])
        out.append(u)
    return out


# -------- مساعدات
def cd_left(u: dict, key: str, seconds: float) -> float:
    return max(0.0, u["cd"].get(key, 0) + seconds - time.time())


def cd_set(u: dict, key: str):
    u["cd"][key] = time.time()


def shield_left(u: dict) -> float:
    return max(0.0, u["shield_until"] - time.time())


def perk(u: dict, key: str) -> int:
    return int(u["perks"].get(key, 0))


# -------- السوق
def market_rows() -> dict:
    return {r["key"]: (r["price"], r["prev"]) for r in _conn.execute("SELECT * FROM market")}


def market_set(key: str, price: float, prev: float):
    _conn.execute("INSERT OR REPLACE INTO market VALUES(?,?,?)", (key, price, prev))
    _conn.commit()


def meta_get(k: str, default=None):
    r = _conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(k: str, v):
    _conn.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, str(v)))
    _conn.commit()
