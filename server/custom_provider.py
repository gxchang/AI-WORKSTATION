

import os
import re
import sqlite3
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")
_META_PREFIX = "custom:"

_LOCK = threading.RLock()



DEFAULTS = {
    "base_url": "",
    "chat_models_assistant": [],
    "chat_models_storyboard": [],
    "chat_models_assistant_enabled": False,
    "chat_models_storyboard_enabled": False,

    "chat_caps_assistant_tools": True,
    "chat_caps_assistant_vision": True,
    "chat_caps_storyboard_tools": True,
    "chat_caps_storyboard_vision": True,
    "chat_thinking_assistant": True,
    "chat_thinking_storyboard": False,


    "chat_budget_assistant": "auto",
    "chat_budget_storyboard": "auto",
    "chat_max_output_assistant": "",
    "chat_max_output_storyboard": "",
    "chat_ctx_assistant": "",
    "chat_ctx_storyboard": "",
}


WRITABLE_KEYS = ("base_url", "api_key",
                 "chat_models_assistant", "chat_models_storyboard",
                 "chat_models_assistant_enabled", "chat_models_storyboard_enabled",
                 "chat_caps_assistant_tools", "chat_caps_assistant_vision",
                 "chat_caps_storyboard_tools", "chat_caps_storyboard_vision",
                 "chat_thinking_assistant", "chat_thinking_storyboard",
                 "chat_budget_assistant", "chat_budget_storyboard",
                 "chat_max_output_assistant", "chat_max_output_storyboard",
                 "chat_ctx_assistant", "chat_ctx_storyboard")

_BOOL_LLM_KEYS = ("chat_caps_assistant_tools", "chat_caps_assistant_vision",
                  "chat_caps_storyboard_tools", "chat_caps_storyboard_vision",
                  "chat_thinking_assistant", "chat_thinking_storyboard",
                  "chat_models_assistant_enabled", "chat_models_storyboard_enabled")
_BUDGET_KEYS = ("chat_budget_assistant", "chat_budget_storyboard")
_BUDGET_LEVELS = {"auto": None, "low": "low", "medium": "medium", "high": "high"}
_INT_LLM_KEYS = ("chat_max_output_assistant", "chat_max_output_storyboard", "chat_ctx_assistant", "chat_ctx_storyboard")

_LOCK_OBJ = threading.RLock()


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


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _split_models(raw):
    
    parts = re.split(r"[,，、\n]+", str(raw or ""))
    out = []
    for p in parts:
        p = p.strip()
        if p and p not in out:
            out.append(p)
    return out


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



def get(key):
    
    if key == "api_key":
        v = _meta_get("api_key", "")
        return v or os.environ.get("CUSTOM_LLM_API_KEY", "")
    if key == "base_url":
        v = _meta_get("base_url", "")
        if v:
            return _norm_url(v)
        return _norm_url(os.environ.get("CUSTOM_LLM_BASE_URL", ""))
    if key in ("chat_models_assistant_enabled", "chat_models_storyboard_enabled"):
        v = _meta_get(key, "")
        if v != "":
            return _truthy(v)
        env_key = ("CUSTOM_LLM_ASSISTANT_ENABLED" if key == "chat_models_assistant_enabled"
                   else "CUSTOM_LLM_STORYBOARD_ENABLED")
        return _truthy(os.environ.get(env_key))
    if key == "chat_models_assistant":
        return _chat_models_for("chat_models_assistant", "CUSTOM_LLM_ASSISTANT_MODELS")
    if key == "chat_models_storyboard":
        return _chat_models_for("chat_models_storyboard", "CUSTOM_LLM_STORYBOARD_MODELS")
    if key in _BOOL_LLM_KEYS:
        v = _meta_get(key, "")
        if v != "":
            return _truthy(v)
        if key == "chat_models_assistant_enabled":
            return _truthy(os.environ.get("CUSTOM_LLM_ASSISTANT_ENABLED"))
        if key == "chat_models_storyboard_enabled":
            return _truthy(os.environ.get("CUSTOM_LLM_STORYBOARD_ENABLED"))
        return _truthy(DEFAULTS.get(key))
    if key in _BUDGET_KEYS:
        v = _meta_get(key, "")
        return v if v in _BUDGET_LEVELS else "auto"
    if key in _INT_LLM_KEYS:
        v = _meta_get(key, "")
        try:
            return int(v) if str(v).strip() else None
        except (TypeError, ValueError):
            return None
    return None


def chat_caps(use_case, kind):
    
    return bool(get(f"chat_caps_{use_case}_{kind}"))


def chat_thinking(use_case):
    
    return bool(get(f"chat_thinking_{use_case}"))


def chat_budget(use_case):
    
    return get(f"chat_budget_{use_case}")


def chat_budget_effort(use_case):
    
    return _BUDGET_LEVELS.get(chat_budget(use_case))


def chat_max_output(use_case):
    
    return get(f"chat_max_output_{use_case}")


def chat_ctx_limit(use_case):
    
    return get(f"chat_ctx_{use_case}")


def _chat_models_for(meta_key, env_key):
    
    v = _meta_get(meta_key, "")
    if v:
        lst = _split_models(v)
        if lst:
            return lst
    return _split_models(os.environ.get(env_key))


def chat_model(use_case):
    
    if use_case == "storyboard":
        return list(get("chat_models_storyboard") or [])
    return list(get("chat_models_assistant") or [])


def chat_model_enabled(use_case):
    
    if use_case == "storyboard":
        return bool(get("chat_models_storyboard_enabled"))
    return bool(get("chat_models_assistant_enabled"))


def ready_state(use_case):
    
    base, key = get("base_url"), get("api_key")
    if not base:
        return False, "尚未填写接口地址（Base URL）"
    if not key:
        return False, "尚未填写访问令牌（API Key）"
    if not chat_model(use_case):
        return False, "尚未填写该用例的模型"
    return True, ""


def config_snapshot(masked=True):
    
    ra_a, why_a = ready_state("assistant")
    ra_s, why_s = ready_state("storyboard")
    return {
        "base_url": get("base_url"),
        "has_key": bool(get("api_key")),
        "hasKey": bool(get("api_key")),
        "api_key_masked": mask_key(get("api_key")) if masked else get("api_key"),
        "chat_models_assistant": chat_model("assistant"),
        "chat_models_assistant_text": ", ".join(chat_model("assistant")),
        "chat_models_assistant_enabled": chat_model_enabled("assistant"),
        "chat_models_assistant_ready": ra_a,
        "chat_models_assistant_reason": why_a,
        "chat_models_storyboard": chat_model("storyboard"),
        "chat_models_storyboard_text": ", ".join(chat_model("storyboard")),
        "chat_models_storyboard_enabled": chat_model_enabled("storyboard"),
        "chat_models_storyboard_ready": ra_s,
        "chat_models_storyboard_reason": why_s,

        "chat_caps_assistant_tools": chat_caps("assistant", "tools"),
        "chat_caps_assistant_vision": chat_caps("assistant", "vision"),
        "chat_caps_storyboard_tools": chat_caps("storyboard", "tools"),
        "chat_caps_storyboard_vision": chat_caps("storyboard", "vision"),
        "chat_thinking_assistant": chat_thinking("assistant"),
        "chat_thinking_storyboard": chat_thinking("storyboard"),
        "chat_budget_assistant": chat_budget("assistant"),
        "chat_budget_storyboard": chat_budget("storyboard"),
        "chat_max_output_assistant": chat_max_output("assistant") or "",
        "chat_max_output_storyboard": chat_max_output("storyboard") or "",
        "chat_ctx_assistant": chat_ctx_limit("assistant") or "",
        "chat_ctx_storyboard": chat_ctx_limit("storyboard") or "",
        "defaults": DEFAULTS,
    }


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
    if "api_key" in patch:
        k = str(patch["api_key"] or "").strip()
        if "…" in k:
            pass
        elif k:
            _meta_set("api_key", k)
        else:
            _meta_del("api_key")
    if "chat_models_assistant" in patch:
        lst = _split_models(patch["chat_models_assistant"])
        if lst:
            _meta_set("chat_models_assistant", ", ".join(lst))
        else:
            _meta_del("chat_models_assistant")
    if "chat_models_storyboard" in patch:
        lst = _split_models(patch["chat_models_storyboard"])
        if lst:
            _meta_set("chat_models_storyboard", ", ".join(lst))
        else:
            _meta_del("chat_models_storyboard")
    for k in ("chat_models_assistant_enabled", "chat_models_storyboard_enabled"):
        if k in patch:
            _meta_set(k, "1" if _truthy(patch[k]) else "0")

    for k in _BOOL_LLM_KEYS:
        if k in patch and not k.endswith("_enabled"):
            _meta_set(k, "1" if _truthy(patch[k]) else "0")
    for k in _BUDGET_KEYS:
        if k in patch:
            v = str(patch[k] or "auto").strip()
            _meta_set(k, v if v in _BUDGET_LEVELS else "auto")
    for k in _INT_LLM_KEYS:
        if k in patch:
            s = str(patch[k]).strip() if patch[k] is not None else ""
            try:
                _meta_set(k, str(int(s))) if s else _meta_del(k)
            except (TypeError, ValueError):
                _meta_del(k)
    return config_snapshot(masked=True)


def test_connection(base_url=None, api_key=None, model=None):
    
    import requests as _rq
    base = _norm_url(base_url) or get("base_url")
    key = api_key or get("api_key")
    t0 = __import__("time").time()
    out = {"ok": False, "verdict": "unreachable", "detail": "", "latency_ms": 0,
           "tested_at": __import__("time").time(), "base_url": base}
    if not base or not key:
        out["detail"] = "请先填写接口地址与访问令牌"
        return out

    def _lat():
        return int((__import__("time").time() - t0) * 1000)

    try:
        r = _rq.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"},
                    timeout=(8, 20))
        out["latency_ms"] = _lat()
        if r.status_code == 200:
            out.update(ok=True, verdict="connected",
                       detail=f"接口可用，令牌有效（GET /models 200，延迟 {out['latency_ms']}ms）")
            return out
        if r.status_code in (401, 403):
            out.update(verdict="rejected",
                       detail=f"令牌被拒绝（HTTP {r.status_code}）：请核对 Access Token")
            return out
        out["detail"] = f"HTTP {r.status_code}：{r.text[:120]}"
        return out
    except Exception as e:
        out["latency_ms"] = _lat()
        out["detail"] = f"地址不可达：{type(e).__name__}: {e}"
        return out
