
import json
import os
import sqlite3
import threading
import time
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")
_LOCK = threading.RLock()


TERMINAL = ("done", "error", "interrupted")


def _conn():
    conn = sqlite3.connect(_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS agent_runs(
                id TEXT PRIMARY KEY,
                session_id TEXT,
                status TEXT NOT NULL DEFAULT 'streaming',  -- streaming|tooling|done|error|interrupted
                tool_name TEXT,
                args_json TEXT,
                state_json TEXT,
                result_json TEXT,
                error TEXT,
                claimed_at REAL,
                created_at REAL,
                updated_at REAL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status)")
            conn.commit()
        finally:
            conn.close()


_ensure_table()


def create(session_id=None):
    
    rid = uuid.uuid4().hex[:12]
    now = time.time()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO agent_runs(id,session_id,status,created_at,updated_at) VALUES(?,?,?,?,?)",
                (rid, session_id, "streaming", now, now))
            conn.commit()
        finally:
            conn.close()
    return rid


_MARKABLE = ("status", "tool_name", "args_json", "state_json", "result_json", "error", "claimed_at")


def mark(run_id, status=None, tool_name=None, args=None, state=None, result=None, error=None,
         claimed_at=None):
    
    sets, vals = ["updated_at=?"], [time.time()]
    for col, val in (("status", status), ("tool_name", tool_name), ("args_json", args),
                     ("state_json", state), ("result_json", result), ("error", error),
                     ("claimed_at", claimed_at)):
        if val is None:
            continue
        if col in ("args_json", "state_json", "result_json") and not isinstance(val, (str, bytes)):
            val = json.dumps(val, ensure_ascii=False)
        sets.append(f"{col}=?")
        vals.append(val)
    vals.append(run_id)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(f"UPDATE agent_runs SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
        finally:
            conn.close()
    return True


def get(run_id):
    
    with _LOCK:
        conn = _conn()
        try:
            r = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        finally:
            conn.close()
    if not r:
        return None
    d = dict(r)
    for col in ("args", "state", "result"):
        raw = d.pop(col + "_json", None)
        if raw:
            try:
                d[col] = json.loads(raw)
            except Exception:
                d[col] = None
        else:
            d[col] = None
    return d


def merge_state(run_id, **kv):
    
    with _LOCK:
        row = get(run_id)
        if not row:
            return False
        st = dict(row.get("state") or {})
        st.update(kv)
        mark(run_id, state=st)
    return True


def merge_state_sub(run_id, key, sub, value):
    
    with _LOCK:
        row = get(run_id)
        if not row:
            return False
        st = dict(row.get("state") or {})
        d = dict(st.get(key) or {})
        d[sub] = value
        st[key] = d
        mark(run_id, state=st)
    return True


def active_by_session(session_id):
    
    if not session_id:
        return None
    with _LOCK:
        conn = _conn()
        try:
            r = conn.execute(
                "SELECT * FROM agent_runs WHERE session_id=? AND status IN ('streaming','tooling') "
                "ORDER BY created_at DESC LIMIT 1", (session_id,)).fetchone()
        finally:
            conn.close()
    return dict(r) if r else None


def claim_resumable(window=15.0):
    
    now = time.time()
    out = []
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT id FROM agent_runs WHERE status='tooling' "
                "AND (claimed_at IS NULL OR claimed_at < ?) ORDER BY created_at",
                (now - window,)).fetchall()
            for r in rows:
                cur = conn.execute(
                    "UPDATE agent_runs SET claimed_at=?, updated_at=? "
                    "WHERE id=? AND status='tooling' AND (claimed_at IS NULL OR claimed_at < ?)",
                    (now, now, r["id"], now - window))
                if cur.rowcount:
                    out.append(r["id"])
            conn.commit()
        finally:
            conn.close()
    return out


def interrupt_streaming():
    
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE agent_runs SET status='interrupted', error=?, updated_at=? "
                "WHERE status='streaming'",
                ("服务重启导致任务中断（思考阶段无法续跑），请重新发送。", time.time()))
            conn.commit()
        finally:
            conn.close()
    return cur.rowcount


def prune(days=7):
    
    cut = time.time() - days * 86400
    with _LOCK:
        conn = _conn()
        try:
            cur = conn.execute(
                "DELETE FROM agent_runs WHERE status IN ('done','error','interrupted') "
                "AND created_at < ?", (cut,))
            conn.commit()
        finally:
            conn.close()
    return cur.rowcount
