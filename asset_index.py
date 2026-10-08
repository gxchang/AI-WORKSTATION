

import os
import sqlite3
import hashlib
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_ROOT, "data")


_DB_PATH = os.path.join(_DATA_DIR, "app.db")

_CHUNK = 1 << 20


def _conn():
    
    os.makedirs(_DATA_DIR, exist_ok=True)
    con = sqlite3.connect(_DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute(
        """CREATE TABLE IF NOT EXISTS asset_content(
               hash       TEXT PRIMARY KEY,
               name       TEXT NOT NULL,
               url        TEXT NOT NULL,
               size       INTEGER,
               ext        TEXT,
               created_at REAL
           )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_asset_content_ext ON asset_content(ext)")
    return con


def content_hash(fs):
    
    h = hashlib.sha256()
    stream = fs.stream
    try:
        stream.seek(0)
    except Exception:
        pass
    for chunk in iter(lambda: stream.read(_CHUNK), b""):
        h.update(chunk)
    try:
        stream.seek(0)
    except Exception:
        pass
    return h.hexdigest()


def find_by_hash(h):
    
    if not h:
        return None
    con = _conn()
    try:
        row = con.execute(
            "SELECT name, url, size FROM asset_content WHERE hash=?", (h,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def remember(h, name, url, size, ext):
    
    if not h or not name:
        return
    con = _conn()
    try:
        con.execute(
            "INSERT OR IGNORE INTO asset_content(hash,name,url,size,ext,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (h, name, url, size, (ext or "").lower(), time.time()),
        )
        con.commit()
    finally:
        con.close()


def forget(name=None, url=None, hash_=None):
    
    conds, args = [], []
    if hash_:
        conds.append("hash=?")
        args.append(hash_)
    if name:
        conds.append("name=?")
        args.append(os.path.basename(str(name)))
    if url:
        conds.append("url=?")
        args.append(url)
    if not conds:
        return 0
    con = _conn()
    try:
        cur = con.execute("DELETE FROM asset_content WHERE " + " OR ".join(conds), args)
        con.commit()
        return int(cur.rowcount or 0)
    finally:
        con.close()


def forget_many(names):
    
    names = [os.path.basename(str(n)) for n in (names or []) if n]
    if not names:
        return 0
    con = _conn()
    try:
        total = 0
        for i in range(0, len(names), 200):
            chunk = names[i:i + 200]
            cur = con.execute(
                "DELETE FROM asset_content WHERE name IN (%s)" % ",".join("?" * len(chunk)),
                chunk,
            )
            total += int(cur.rowcount or 0)
        con.commit()
        return total
    finally:
        con.close()


def stats():
    
    con = _conn()
    try:
        row = con.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM asset_content"
        ).fetchone()
        return int(row["c"]), int(row["s"])
    finally:
        con.close()
