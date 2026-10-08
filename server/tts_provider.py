
import os
import re
import sqlite3
import threading
import time


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))




_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")

_META_PREFIX = "tts:"
_LOCK = threading.RLock()


DEFAULTS = {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "fish-audio/s2.1-pro-free:free",
}


WRITABLE_KEYS = ("base_url", "api_key", "model")



def _load_env_once():
    
    p = os.path.join(_ROOT, ".env")
    if not os.path.exists(p):
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'", "`"):
                    v = v[1:-1]
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_env_once()



def _conn():
    conn = sqlite3.connect(_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_meta_table():
    
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()
        finally:
            conn.close()


def _meta_get(key, default=None):
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (_META_PREFIX + key,)).fetchone()
            return row["value"] if row else default
        except sqlite3.OperationalError:

            return default
        finally:
            conn.close()


def _meta_set(key, value):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_META_PREFIX + key, value),
            )
            conn.commit()
        finally:
            conn.close()


def _meta_del(key):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("DELETE FROM meta WHERE key=?", (_META_PREFIX + key,))
            conn.commit()
        finally:
            conn.close()



def _norm_url(u):
    
    if not u:
        return ""
    u = str(u).strip().rstrip("/")
    if u and not re.match(r"^https?://", u):
        u = "https://" + u
    return u


def mask_key(k):
    
    if not k:
        return ""
    k = str(k)
    if len(k) <= 8:
        return "****"
    return f"{k[:3]}…{k[-4:]}"



def get(key):
    
    if key == "api_key":

        v = _meta_get("api_key", "")
        if v:
            return v
        return os.environ.get("OPENROUTER_API_KEY", "")
    if key == "base_url":
        v = _meta_get("base_url", "")
        if v:
            return _norm_url(v)
        return (os.environ.get("OPENROUTER_BASE_URL") or DEFAULTS["base_url"]).rstrip("/")
    if key == "model":
        v = _meta_get("model", "")
        if v:
            return v.strip()
        return os.environ.get("OPENROUTER_TTS_MODEL") or DEFAULTS["model"]
    return None


def config_snapshot(masked=True):
    
    snap = {
        "base_url": get("base_url"),
        "has_key": bool(get("api_key")),
        "hasKey": bool(get("api_key")),
        "api_key_masked": mask_key(get("api_key")) if masked else get("api_key"),
        "model": get("model"),
        "defaults": DEFAULTS,
        "source": _source_map(),
    }
    return snap


def _source_map():
    
    src = {}
    for k in ("base_url", "model"):
        if _meta_get(k, ""):
            src[k] = "ui"
        elif (k == "base_url" and os.environ.get("OPENROUTER_BASE_URL")) or \
             (k == "model" and os.environ.get("OPENROUTER_TTS_MODEL")):
            src[k] = "env"
        else:
            src[k] = "default"
    if _meta_get("api_key", ""):
        src["api_key"] = "ui"
    elif os.environ.get("OPENROUTER_API_KEY"):
        src["api_key"] = "env"
    else:
        src["api_key"] = "default"
    return src


def save(patch, keep_old_key=True):
    
    _ensure_meta_table()
    if not isinstance(patch, dict):
        raise ValueError("patch 必须是对象")
    for k in patch:
        if k not in WRITABLE_KEYS:
            raise ValueError(f"不支持的配置项：{k}")
    if "base_url" in patch:
        u = _norm_url(patch["base_url"])
        if u:
            _meta_set("base_url", u)
        else:
            _meta_del("base_url")
    if "model" in patch:
        m = (patch["model"] or "").strip()
        if m:
            _meta_set("model", m)
        else:
            _meta_del("model")
    if "api_key" in patch:
        k = (patch["api_key"] or "").strip()
        if k:
            _meta_set("api_key", k)
        else:
            _meta_del("api_key")
    return config_snapshot(masked=True)



def test_connection(base_url=None, api_key=None, model=None):
    
    import requests as _rq

    base = _norm_url(base_url) or get("base_url")
    key = api_key or get("api_key")
    mdl = model or get("model")
    t0 = time.time()
    out = {"ok": False, "verdict": "unreachable", "detail": "", "latency_ms": 0,
           "tested_at": time.time(), "base_url": base}

    if not key:
        out.update(ok=False, verdict="no_key",
                   detail="地址可达性无法验证：未配置密钥。请先在「音频生成」标签页填入 OpenRouter Key")
        return out

    try:
        r = _rq.post(
            f"{base}/audio/speech",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": mdl, "input": "啊", "response_format": "mp3", "speed": 1.0},
            timeout=(8, 30),
        )
        out["latency_ms"] = int((time.time() - t0) * 1000)
    except Exception as e:
        out["latency_ms"] = int((time.time() - t0) * 1000)
        out.update(ok=False, verdict="unreachable",
                   detail=f"无法连接到 {base}：{type(e).__name__}: {e}")
        return out

    ctype = (r.headers.get("Content-Type") or "").lower()
    if r.status_code == 200 and ("audio" in ctype or len(r.content) > 100):
        out.update(ok=True, verdict="connected",
                   detail=f"音频接口可用，密钥有效（生成最小片段 200，延迟 {out['latency_ms']}ms）")
    elif r.status_code in (401, 403):
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但密钥被拒绝（HTTP {r.status_code}）——请检查 OpenRouter Key 是否正确/已过期")
    elif r.status_code == 400:

        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但请求被拒（HTTP 400）——请确认模型名「{mdl}」正确、请求格式符合 OpenRouter TTS 契约")
    else:
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但返回 HTTP {r.status_code}（{r.text[:160]}）")
    return out
