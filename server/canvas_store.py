

import json
import os
import sqlite3
import threading
import time
import uuid

_LOCK = threading.Lock()
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")
_PREFIX = "canvas:proj_"


def _conn():
    conn = sqlite3.connect(_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    
    _write(lambda conn: conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"))


def _write(fn, retries=3):
    
    last = None
    for i in range(retries):
        try:
            result = None
            with _LOCK:
                conn = _conn()
                try:
                    result = fn(conn)
                    conn.commit()
                finally:
                    conn.close()
            return result
        except sqlite3.OperationalError as e:
            last = e
            time.sleep(0.15 * (i + 1))
    raise last


_ensure_table()


def _doc_from_row(row):
    
    try:
        doc = json.loads(row["value"])
        pid = row["key"][len(_PREFIX):]
        doc.setdefault("id", pid)
        return doc
    except Exception:
        return None


def list_projects():
    
    out = []
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT key, value FROM meta WHERE key LIKE ? ORDER BY value DESC",
                (_PREFIX + "%",),
            ).fetchall()
        finally:
            conn.close()
    for r in rows:
        doc = _doc_from_row(r)
        if not doc:
            continue
        nodes = doc.get("nodes") or []
        edges = doc.get("edges") or []
        out.append({
            "id": doc["id"],
            "name": doc.get("name") or "未命名",
            "created_at": doc.get("created_at") or 0,
            "updated_at": doc.get("updated_at") or 0,
            "node_count": len(nodes),

            "mini_nodes": [{"t": n.get("type"), "x": n.get("x"), "y": n.get("y"),
                            "w": n.get("w"), "h": n.get("h")} for n in nodes],
            "mini_edges": [{"a": e.get("from"), "b": e.get("to")} for e in edges],
        })
    out.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
    return out


def create_project(name):
    
    pid = "cv_" + uuid.uuid4().hex[:10]
    now = time.time()
    doc = {
        "id": pid, "name": (name or "").strip() or "未命名",
        "created_at": now, "updated_at": now,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "nodes": [], "edges": [],
    }
    save_project(pid, doc, create=True)
    return doc


def get_project(pid):
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT key, value FROM meta WHERE key=?", (_PREFIX + pid,)).fetchone()
        finally:
            conn.close()
    return _doc_from_row(row) if row else None


def save_project(pid, doc, create=False):
    
    doc["id"] = pid
    doc["updated_at"] = time.time()
    if create:
        doc.setdefault("created_at", doc["updated_at"])
    elif get_project(pid) is None:
        return None
    payload = json.dumps(doc, ensure_ascii=False)
    key = _PREFIX + pid

    def _do(conn):
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, payload),
        )

    _write(_do)
    return doc


def delete_projects(ids):
    
    ids = [i for i in (ids or []) if isinstance(i, str) and i.startswith("cv_")]
    if not ids:
        return 0

    def _do(conn):
        n = 0
        for pid in ids:
            cur = conn.execute("DELETE FROM meta WHERE key=?", (_PREFIX + pid,))
            n += cur.rowcount
        return n

    return _write(_do) or 0
