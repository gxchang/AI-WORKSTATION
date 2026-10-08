
import os
import re
import sqlite3
import threading
import time


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))




_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")

_META_PREFIX = "provider:"
_LOCK = threading.RLock()


DEFAULTS = {
    "base_url": "https://api.agnes-ai.cn/v1",
    "poll_endpoint": "https://api.agnes-ai.cn/agnesapi",

    "video_models": ["agnes-video-2.5-flash", "agnes-video-2.5"],
    "image_models": ["agnes-image-2.1-flash", "agnes-image-2.5-flash"],
    "llm_models": ["agnes-2.5-flash", "agnes-3.0-flash"],

    "agent_models": ["agnes-3.0-flash"],



    "agent_caps_tools": True,
    "agent_caps_vision": True,
    "llm_caps_tools": True,
    "llm_caps_vision": True,
    "agent_thinking": True,
    "llm_thinking": False,
    "agent_ctx_limit": 512000,
    "llm_ctx_limit": 512000,
    "llm_max_output": "",
    "agent_max_output": "",
}


WRITABLE_KEYS = ("base_url", "api_key", "poll_endpoint",
                 "video_models", "image_models", "llm_models", "agent_models",
                 "agent_caps_tools", "agent_caps_vision", "llm_caps_tools", "llm_caps_vision",
                 "agent_thinking", "llm_thinking",
                 "agent_ctx_limit", "llm_ctx_limit", "llm_max_output", "agent_max_output")

_BOOL_PROV_KEYS = ("agent_caps_tools", "agent_caps_vision", "llm_caps_tools", "llm_caps_vision",
                   "agent_thinking", "llm_thinking")
_INT_PROV_KEYS = ("agent_ctx_limit", "llm_ctx_limit", "llm_max_output", "agent_max_output")



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



def _truthy(v):
    
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _truthy(v):
    
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")



def chat_thinking(use_case):
    
    return bool(get("agent_thinking" if use_case == "assistant" else "llm_thinking"))


def chat_caps(use_case, kind):
    
    return bool(get(("agent_caps_" if use_case == "assistant" else "llm_caps_") + kind))


def chat_ctx_limit(use_case):
    
    return get("agent_ctx_limit" if use_case == "assistant" else "llm_ctx_limit")


def chat_max_output(use_case):
    
    return get("agent_max_output" if use_case == "assistant" else "llm_max_output")


def _parse_models(raw):
    
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        parts = [str(x).strip() for x in raw]
    else:
        parts = re.split(r"[,;\s]+", str(raw))
    out = []
    for p in parts:

        if p and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}", p) and p not in out:
            out.append(p)
    return out


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
        return os.environ.get("AGNES_API_KEY", "")
    if key == "base_url":
        v = _meta_get("base_url", "")
        if v:
            return _norm_url(v)
        return (os.environ.get("AGNES_BASE_URL") or DEFAULTS["base_url"]).rstrip("/")
    if key == "poll_endpoint":
        v = _meta_get("poll_endpoint", "")
        if v:
            return _norm_url(v)
        env_v = os.environ.get("POLL_ENDPOINT")
        if env_v:
            return env_v.rstrip("/")
        return DEFAULTS["poll_endpoint"]
    if key in ("video_models", "image_models", "llm_models", "agent_models"):
        v = _meta_get(key, "")
        if v:
            parsed = _parse_models(v)
            if parsed:
                return parsed
        if key == "video_models":
            env_v = os.environ.get("AGNES_VIDEO_MODELS")
            if env_v:
                parsed = _parse_models(env_v)
                if parsed:
                    return parsed
        return list(DEFAULTS[key])
    if key in _BOOL_PROV_KEYS:
        v = _meta_get(key, "")
        if v != "":
            return _truthy(v)
        return _truthy(DEFAULTS.get(key))
    if key in _INT_PROV_KEYS:
        v = _meta_get(key, "")
        try:
            if str(v).strip():
                return int(v)
        except (TypeError, ValueError):
            pass
        d = DEFAULTS.get(key)
        try:
            return int(d) if str(d or "").strip() else None
        except (TypeError, ValueError):
            return None
    return None


def config_snapshot(masked=True):
    
    snap = {
        "base_url": get("base_url"),
        "has_key": bool(get("api_key")),
        "hasKey": bool(get("api_key")),
        "api_key_masked": mask_key(get("api_key")) if masked else get("api_key"),
        "poll_endpoint": get("poll_endpoint"),
        "video_models": get("video_models"),
        "image_models": get("image_models"),
        "llm_models": get("llm_models"),
        "agent_models": get("agent_models"),

        "agent_caps_tools": get("agent_caps_tools"),
        "agent_caps_vision": get("agent_caps_vision"),
        "llm_caps_tools": get("llm_caps_tools"),
        "llm_caps_vision": get("llm_caps_vision"),
        "agent_thinking": get("agent_thinking"),
        "llm_thinking": get("llm_thinking"),
        "agent_ctx_limit": get("agent_ctx_limit"),
        "llm_ctx_limit": get("llm_ctx_limit"),
        "llm_max_output": get("llm_max_output") or "",
        "agent_max_output": get("agent_max_output") or "",
        "defaults": DEFAULTS,
        "source": _source_map(),
    }
    return snap


def _source_map():
    
    src = {}
    for k in ("base_url", "poll_endpoint"):
        if _meta_get(k, ""):
            src[k] = "ui"
        elif (k == "base_url" and os.environ.get("AGNES_BASE_URL")) or \
             (k == "poll_endpoint" and os.environ.get("POLL_ENDPOINT")):
            src[k] = "env"
        else:
            src[k] = "default"
    if _meta_get("api_key", ""):
        src["api_key"] = "ui"
    elif os.environ.get("AGNES_API_KEY"):
        src["api_key"] = "env"
    else:
        src["api_key"] = "default"
    for k in ("video_models", "image_models", "llm_models", "agent_models"):
        if _meta_get(k, ""):
            src[k] = "ui"
        else:
            src[k] = "default"
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
    if "poll_endpoint" in patch:
        u = _norm_url(patch["poll_endpoint"])
        if u:
            _meta_set("poll_endpoint", u)
        else:
            _meta_del("poll_endpoint")
    if "api_key" in patch:
        k = (patch["api_key"] or "").strip()
        if k:
            _meta_set("api_key", k)
        else:
            _meta_del("api_key")
    for mk in ("video_models", "image_models", "llm_models", "agent_models"):
        if mk in patch:
            parsed = _parse_models(patch[mk])
            if parsed:
                _meta_set(mk, ",".join(parsed))
            else:
                _meta_del(mk)

    for k in _BOOL_PROV_KEYS:
        if k in patch:
            _meta_set(k, "1" if _truthy(patch[k]) else "0")
    for k in _INT_PROV_KEYS:
        if k in patch:
            s = str(patch[k]).strip() if patch[k] is not None else ""
            try:
                _meta_set(k, str(int(s))) if s else _meta_del(k)
            except (TypeError, ValueError):
                _meta_del(k)
    return config_snapshot(masked=True)


def reset():
    
    for k in WRITABLE_KEYS:
        _meta_del(k)

    for k in ("assistant_llm_backend", "storyboard_llm_backend"):
        _meta_del(k)
    return config_snapshot(masked=True)



def test_connection(base_url=None, api_key=None, poll_endpoint=None):
    
    import requests as _rq

    base = _norm_url(base_url) or get("base_url")
    key = api_key or get("api_key")
    t0 = time.time()
    out = {"ok": False, "verdict": "unreachable", "detail": "", "latency_ms": 0,
           "tested_at": time.time(), "base_url": base}


    addr_ok = False
    try:
        r = _rq.get(f"{base}/models",
                     headers={"Authorization": f"Bearer {key}"} if key else {},
                     timeout=(5, 15))
        out["latency_ms"] = int((time.time() - t0) * 1000)
        if r.status_code == 404:

            addr_ok = "chat_only"
        elif r.status_code < 500:
            addr_ok = True
        else:
            addr_ok = False
    except Exception as e:
        out["latency_ms"] = int((time.time() - t0) * 1000)
        out.update(ok=False, verdict="unreachable",
                   detail=f"无法连接到 {base}：{type(e).__name__}: {e}")
        return out


    try:
        r2 = _rq.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"} if key else {},
            json={"model": (get("llm_models") or ["agnes-2.5-flash"])[0],
                  "messages": [{"role": "user", "content": "ping"}],
                  "max_tokens": 1},
            timeout=(5, 30),
        )
    except Exception as e:
        out.update(ok=False, verdict="unreachable",
                   detail=f"地址探活通过，但 chat 请求异常：{type(e).__name__}: {e}")
        return out

    if r2.status_code == 200:
        if key:
            out.update(ok=True, verdict="connected",
                       detail=f"地址可达，密钥有效（chat 鉴权面 200，延迟 {out['latency_ms']}ms）")
        else:

            out.update(ok=False, verdict="no_key",
                       detail="地址可达，但未配置密钥（该端点未拒绝匿名请求，无法验证密钥）")
    elif r2.status_code in (401, 403):
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但密钥被拒绝（HTTP {r2.status_code}）——请检查密钥是否正确/已过期")
    else:
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达（{'chat探活' if addr_ok=='chat_only' else '/models'}），"
                          f"但 chat 返回 HTTP {r2.status_code}——该端点可能不是 Agnes 契约"
                          f"（需支持 /videos + 轮询 + Bearer），请确认地址与模型名")
    return out
