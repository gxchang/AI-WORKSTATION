
import os
import re
import sqlite3
import threading
import time


try:
    from . import imgen as _imgen
except ImportError:
    import imgen as _imgen



_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))




_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")

_META_PREFIX = "ms:"
_LOCK = threading.RLock()



DEFAULTS = {
    "base_url": "https://api-inference.modelscope.cn/v1",




    "image_models": ["Qwen/Qwen-Image-2.1", "Qwen/Qwen-Image-Edit-2511"],








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
    "chat_max_output_storyboard": 32768,

    "chat_ctx_assistant": "",
    "chat_ctx_storyboard": "",
}


WRITABLE_KEYS = ("enabled", "base_url", "api_key", "image_models",
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
_BUDGET_LEVELS = {"auto": None, "low": 1024, "medium": 4096, "high": 16384}
_INT_LLM_KEYS = ("chat_max_output_assistant", "chat_max_output_storyboard", "chat_ctx_assistant", "chat_ctx_storyboard")



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



def get(key):
    
    if key == "enabled":
        v = _meta_get("enabled", "")
        if v != "":
            return _truthy(v)
        return _truthy(os.environ.get("MS_IMAGE_ENABLED"))
    if key in ("chat_models_assistant_enabled", "chat_models_storyboard_enabled"):
        v = _meta_get(key, "")
        if v != "":
            return _truthy(v)
        env_key = "MS_CHAT_MODELS_ASSISTANT_ENABLED" if key == "chat_models_assistant_enabled" else "MS_CHAT_MODELS_STORYBOARD_ENABLED"
        return _truthy(os.environ.get(env_key))
    if key == "api_key":
        v = _meta_get("api_key", "")
        if v:
            return v
        return os.environ.get("MS_API_KEY", "")
    if key == "base_url":
        v = _meta_get("base_url", "")
        if v:
            return _norm_url(v)
        return (os.environ.get("MS_BASE_URL") or DEFAULTS["base_url"]).rstrip("/")
    if key == "image_models":
        v = _meta_get("image_models", "")
        if v:
            lst = _split_models(v)
            if lst:
                return lst
        lst = _split_models(os.environ.get("MS_IMAGE_MODELS"))
        return lst or list(DEFAULTS["image_models"])
    if key == "chat_models_assistant":
        return _chat_models_for("chat_models_assistant", "MS_CHAT_MODELS_ASSISTANT")
    if key == "chat_models_storyboard":
        return _chat_models_for("chat_models_storyboard", "MS_CHAT_MODELS_STORYBOARD")
    if key in _BOOL_LLM_KEYS:
        v = _meta_get(key, "")
        if v != "":
            return _truthy(v)
        if key == "chat_models_assistant_enabled":
            return _truthy(os.environ.get("MS_CHAT_MODELS_ASSISTANT_ENABLED"))
        if key == "chat_models_storyboard_enabled":
            return _truthy(os.environ.get("MS_CHAT_MODELS_STORYBOARD_ENABLED"))
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


def chat_budget_tokens(use_case):
    
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
    lst = _split_models(os.environ.get(env_key))
    return lst or []


def image_models():
    
    return list(get("image_models") or DEFAULTS["image_models"])


def chat_model(use_case):
    
    if use_case == "storyboard":
        return list(get("chat_models_storyboard") or [])
    return list(get("chat_models_assistant") or [])


def chat_model_enabled(use_case):
    
    if use_case == "storyboard":
        return bool(get("chat_models_storyboard_enabled"))
    return bool(get("chat_models_assistant_enabled"))


def active_state():
    
    en, key = bool(get("enabled")), bool(get("api_key"))
    if en and key:
        return True, ""
    if en and not key:
        return False, "已开启魔搭生图，但未配置 ModelScope 访问令牌 —— 已回落 Agnes 生图"
    return False, ""


def active():
    
    return active_state()[0]


def config_snapshot(masked=True):
    
    act, why = active_state()
    mdl = image_models()
    return {
        "enabled": bool(get("enabled")),
        "active": act,
        "fallback_reason": why,
        "base_url": get("base_url"),
        "has_key": bool(get("api_key")),
        "hasKey": bool(get("api_key")),
        "api_key_masked": mask_key(get("api_key")) if masked else get("api_key"),
        "image_models": mdl,
        "image_models_text": ", ".join(mdl),


        "chat_models_assistant": chat_model("assistant"),
        "chat_models_assistant_text": ", ".join(chat_model("assistant")),
        "chat_models_assistant_enabled": chat_model_enabled("assistant"),
        "chat_models_storyboard": chat_model("storyboard"),
        "chat_models_storyboard_text": ", ".join(chat_model("storyboard")),
        "chat_models_storyboard_enabled": chat_model_enabled("storyboard"),

        "chat_caps_assistant_tools": chat_caps("assistant", "tools"),
        "chat_caps_assistant_vision": chat_caps("assistant", "vision"),
        "chat_caps_storyboard_tools": chat_caps("storyboard", "tools"),
        "chat_caps_storyboard_vision": chat_caps("storyboard", "vision"),
        "chat_thinking_assistant": chat_thinking("assistant"),
        "chat_thinking_storyboard": chat_thinking("storyboard"),
        "chat_budget_assistant": chat_budget("assistant"),
        "chat_budget_storyboard": chat_budget("storyboard"),
        "chat_max_output_assistant": chat_max_output("assistant") or "",
        "chat_max_output_storyboard": chat_max_output("storyboard"),
        "chat_ctx_assistant": chat_ctx_limit("assistant") or "",
        "chat_ctx_storyboard": chat_ctx_limit("storyboard") or "",
        "model_limits": model_limits_map(),
        "defaults": DEFAULTS,
        "source": _source_map(),
    }


def _source_map():
    
    src = {}
    src["enabled"] = "ui" if _meta_get("enabled", "") != "" else ("env" if os.environ.get("MS_IMAGE_ENABLED") else "default")
    for k, env in (("base_url", "MS_BASE_URL"), ("image_models", "MS_IMAGE_MODELS"),
                   ("chat_models_assistant", "MS_CHAT_MODELS_ASSISTANT"),
                   ("chat_models_storyboard", "MS_CHAT_MODELS_STORYBOARD"),
                   ("chat_models_assistant_enabled", "MS_CHAT_MODELS_ASSISTANT_ENABLED"),
                   ("chat_models_storyboard_enabled", "MS_CHAT_MODELS_STORYBOARD_ENABLED")):
        src[k] = "ui" if _meta_get(k, "") else ("env" if os.environ.get(env) else "default")
    if _meta_get("api_key", ""):
        src["api_key"] = "ui"
    elif os.environ.get("MS_API_KEY"):
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
    if "enabled" in patch:
        _meta_set("enabled", "1" if _truthy(patch["enabled"]) else "0")
    if "base_url" in patch:
        u = _norm_url(patch["base_url"])
        if u:
            _meta_set("base_url", u)
        else:
            _meta_del("base_url")
    if "image_models" in patch:
        lst = _split_models(patch["image_models"])
        if lst:
            _meta_set("image_models", ", ".join(lst))
        else:
            _meta_del("image_models")
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
    if "chat_models_assistant_enabled" in patch:
        _meta_set("chat_models_assistant_enabled", "1" if _truthy(patch["chat_models_assistant_enabled"]) else "0")
    if "chat_models_storyboard_enabled" in patch:
        _meta_set("chat_models_storyboard_enabled", "1" if _truthy(patch["chat_models_storyboard_enabled"]) else "0")

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

    _meta_del("chat_models")
    if "api_key" in patch:
        k = (patch["api_key"] or "").strip()
        if k:
            _meta_set("api_key", k)
        else:
            _meta_del("api_key")
    return config_snapshot(masked=True)



def model_limits(model):
    
    return _imgen.caps_for(model, "ms")


def model_limits_map():
    
    return _imgen.model_limits_map("ms")


def registered(model):
    
    return _imgen.registered(model)



def to_ms_payload(p):
    
    first = (image_models() or DEFAULTS["image_models"])[0]
    return _imgen.build_payload("ms", p, first_model=first)



def test_connection(base_url=None, api_key=None, model=None):
    
    import requests as _rq

    base = _norm_url(base_url) or get("base_url")
    key = api_key or get("api_key")
    mdl = model or image_models()[0]
    t0 = time.time()
    out = {"ok": False, "verdict": "unreachable", "detail": "", "latency_ms": 0,
           "tested_at": time.time(), "base_url": base}

    if not key:
        out.update(ok=False, verdict="no_key",
                   detail="地址可达性无法验证：未配置令牌。请先在「魔搭生图」标签页填入 ModelScope 访问令牌")
        return out

    def _lat():
        return int((time.time() - t0) * 1000)

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


    try:
        r = _rq.get(f"{base}/models", headers=headers, timeout=(8, 20))
        out["latency_ms"] = _lat()
        if r.status_code == 200:
            out.update(ok=True, verdict="connected",
                       detail=f"魔搭接口可用，令牌有效（GET /models 200，延迟 {out['latency_ms']}ms）")
            return out
        if r.status_code in (401, 403):
            out.update(ok=False, verdict="reachable",
                       detail=f"地址可达，但令牌被拒绝（HTTP {r.status_code}）—— 请检查 ModelScope 访问令牌是否正确/已失效")
            return out
        first = f"（GET /models 返回 HTTP {r.status_code}，改用鉴权探针）"
    except Exception as e:
        out["latency_ms"] = _lat()
        out.update(ok=False, verdict="unreachable",
                   detail=f"无法连接到 {base}：{type(e).__name__}: {e}")
        return out


    try:
        r2 = _rq.post(f"{base}/images/generations", headers=dict(headers, **{"X-ModelScope-Async-Mode": "true"}),
                      json={"model": "__auth_probe_not_a_real_model__", "prompt": "ping"},
                      timeout=(8, 30))
        out["latency_ms"] = _lat()
    except Exception as e:
        out["latency_ms"] = _lat()
        out.update(ok=False, verdict="unreachable",
                   detail=f"无法连接到 {base}/images/generations：{type(e).__name__}: {e}")
        return out

    if r2.status_code in (401, 403):
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但令牌被拒绝（HTTP {r2.status_code}）—— 请检查 ModelScope 访问令牌是否正确/已失效")
    elif r2.status_code in (400, 404):

        out.update(ok=True, verdict="connected",
                   detail=f"魔搭接口可用，令牌有效（鉴权探针 HTTP {r2.status_code}：模型名不存在属预期）{first}")
    elif r2.status_code == 200:
        out.update(ok=True, verdict="connected",
                   detail=f"魔搭接口可用，令牌有效（提交返回 200；注意本接口为异步，真实结果需轮询）{first}")
    else:
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但返回 HTTP {r2.status_code}（{(r2.text or '')[:160]}）")
    return out
