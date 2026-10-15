
import os
import re
import sqlite3
import threading
import time


try:
    from . import tts_models as _tmodels
except ImportError:
    import tts_models as _tmodels

try:
    from . import tts_adapters as _tadapters
except ImportError:
    import tts_adapters as _tadapters



_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))




_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")

_LOCK = threading.RLock()


PROVIDERS = _tmodels.TTS_PROVIDER_ORDER
BASE_PROVIDER = _tmodels.TTS_BASE_PROVIDER


_META_PREFIX_BY_PROVIDER = {"openrouter": "tts:", "mimo": "tts:mimo:"}


DEFAULTS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "fish-audio/s2.1-pro-free:free",
    },
    "mimo": {
        "base_url": "https://api.xiaomimimo.com/v1",

        "model": "mimo-v2.5-tts-voiceclone, mimo-v2.5-tts-voicedesign",
    },
}


_ENV_KEYS = {
    "openrouter": {"enabled": "OPENROUTER_TTS_ENABLED",
                   "base_url": "OPENROUTER_BASE_URL",
                   "api_key": "OPENROUTER_API_KEY",
                   "model": "OPENROUTER_TTS_MODEL"},
    "mimo": {"enabled": "MIMO_TTS_ENABLED",
             "base_url": "MIMO_BASE_URL",
             "api_key": "MIMO_API_KEY",
             "model": "MIMO_TTS_MODELS"},
}


WRITABLE_KEYS = ("enabled", "base_url", "api_key", "model")



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



def pname(provider=None):
    
    k = str(provider or "").strip().lower() or BASE_PROVIDER
    if k not in PROVIDERS:
        raise ValueError("未知的音频服务商：%r（可选：%s）" % (provider, " / ".join(PROVIDERS)))
    return k


def _meta_key(provider, key):
    return _META_PREFIX_BY_PROVIDER[provider] + key


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _split_models(raw):
    
    out = []
    for p in re.split(r"[,，、\n]+", str(raw or "")):
        p = p.strip()
        if p and p not in out:
            out.append(p)
    return out



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


def _meta_get(provider, key, default=None):
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key=?",
                               (_meta_key(provider, key),)).fetchone()
            return row["value"] if row else default
        except sqlite3.OperationalError:

            return default
        finally:
            conn.close()


def _meta_set(provider, key, value):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_meta_key(provider, key), value),
            )
            conn.commit()
        finally:
            conn.close()


def _meta_del(provider, key):
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("DELETE FROM meta WHERE key=?", (_meta_key(provider, key),))
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



def get(key, provider=BASE_PROVIDER):
    
    p = pname(provider)
    env = _ENV_KEYS[p]

    if key == "enabled":

        if p == BASE_PROVIDER:
            return False
        v = _meta_get(p, "enabled", "")
        if v != "":
            return _truthy(v)
        return _truthy(os.environ.get(env["enabled"], ""))

    if key == "api_key":

        v = _meta_get(p, "api_key", "")
        if v:
            return v
        return os.environ.get(env["api_key"], "")

    if key == "base_url":
        v = _meta_get(p, "base_url", "")
        if v:
            return _norm_url(v)
        return (os.environ.get(env["base_url"]) or DEFAULTS[p]["base_url"]).rstrip("/")

    if key == "model":
        v = _meta_get(p, "model", "")
        if v:
            return v.strip()
        return (os.environ.get(env["model"]) or DEFAULTS[p]["model"]).strip()

    raise ValueError("不支持的配置项：%s" % key)


def models(provider=BASE_PROVIDER):
    
    return _split_models(get("model", provider))


def default_model(provider=BASE_PROVIDER):
    lst = models(provider)
    return lst[0] if lst else ""


def ready(provider):
    
    p = pname(provider)
    if p == BASE_PROVIDER:
        return True
    return bool(get("enabled", p)) and bool(get("api_key", p))


def active_state(provider):
    
    p = pname(provider)
    if p == BASE_PROVIDER:
        return True, ""
    en, key = bool(get("enabled", p)), bool(get("api_key", p))
    if en and key:
        return True, ""
    if en and not key:
        return False, ("已勾选「%s」作为音频服务商，但未配置密钥 —— 音频实际仍走「%s」"
                       % (_tmodels.TTS_PROVIDER_LABELS[p],
                          _tmodels.TTS_PROVIDER_LABELS[BASE_PROVIDER]))
    return False, ""


def active(provider):
    
    return active_state(provider)[0]


def provider_state():
    
    return _tmodels.resolve_tts_provider(
        [k for k in _tmodels.TTS_PROVIDER_HOSTS if bool(get("enabled", k))],
        {k: ready(k) for k in PROVIDERS},
    )


def config_snapshot(provider=BASE_PROVIDER, masked=True):
    
    p = pname(provider)
    act, why = active_state(p)
    lst = models(p)
    return {
        "provider": p,
        "providerLabel": _tmodels.TTS_PROVIDER_LABELS[p],
        "enabled": bool(get("enabled", p)),
        "active": act,
        "fallback_reason": why,
        "base_url": get("base_url", p),
        "has_key": bool(get("api_key", p)),
        "hasKey": bool(get("api_key", p)),
        "api_key_masked": mask_key(get("api_key", p)) if masked else get("api_key", p),
        "model": get("model", p),
        "models": lst,
        "models_text": ", ".join(lst),
        "default_model": lst[0] if lst else "",
        "defaults": DEFAULTS[p],
        "source": _source_map(p),
    }


def _source_map(provider):
    
    p = pname(provider)
    env = _ENV_KEYS[p]
    src = {}
    for k in ("base_url", "model"):
        if _meta_get(p, k, ""):
            src[k] = "ui"
        elif os.environ.get(env[k]):
            src[k] = "env"
        else:
            src[k] = "default"
    if _meta_get(p, "api_key", ""):
        src["api_key"] = "ui"
    elif os.environ.get(env["api_key"]):
        src["api_key"] = "env"
    else:
        src["api_key"] = "default"
    return src


def save(patch, provider=BASE_PROVIDER, keep_old_key=True):
    
    _ensure_meta_table()
    p = pname(provider)
    if not isinstance(patch, dict):
        raise ValueError("patch 必须是对象")
    for k in patch:
        if k not in WRITABLE_KEYS:
            raise ValueError(f"不支持的配置项：{k}")
    if "enabled" in patch:
        if p == BASE_PROVIDER:
            raise ValueError("基座服务商没有开关（它恒可用，切换到别家即让它让位）")
        _meta_set(p, "enabled", "1" if _truthy(patch["enabled"]) else "0")
    if "base_url" in patch:
        u = _norm_url(patch["base_url"])
        if u:
            _meta_set(p, "base_url", u)
        else:
            _meta_del(p, "base_url")
    if "model" in patch:
        lst = _split_models(patch["model"])
        if lst:
            _meta_set(p, "model", ", ".join(lst))
        else:
            _meta_del(p, "model")
    if "api_key" in patch:
        k = (patch["api_key"] or "").strip()
        if k:
            _meta_set(p, "api_key", k)
        else:
            _meta_del(p, "api_key")
    return config_snapshot(p, masked=True)





def test_connection(provider=BASE_PROVIDER, base_url=None, api_key=None, model=None):
    
    p = pname(provider)
    base = _norm_url(base_url) or get("base_url", p)
    key = api_key or get("api_key", p)
    mdl = _split_models(model)
    mdl = mdl[0] if mdl else default_model(p)

    t0 = time.time()
    out = {"ok": False, "verdict": "unreachable", "detail": "", "latency_ms": 0,
           "tested_at": time.time(), "base_url": base,
           "provider": p, "model": mdl}

    if not key:
        out.update(ok=False, verdict="no_key",
                   detail="地址可达性无法验证：未配置密钥。请在「服务商设置 → %s」填入密钥"
                          % _tmodels.TTS_PROVIDER_LABELS[p])
        return out

    res = _tadapters.probe(p, base, key, mdl, caps=_tmodels.caps_for(mdl, p))
    out["latency_ms"] = int((time.time() - t0) * 1000)
    out["model"] = res.get("model_used") or mdl

    if res.get("ok"):
        out.update(ok=True, verdict="connected",
                   detail="%s（延迟 %dms）" % (res.get("detail") or "连接成功", out["latency_ms"]))
    elif res.get("status") == 0:
        out.update(ok=False, verdict="unreachable", detail=res.get("detail") or "无法连接")
    elif res.get("status") in (401, 403):
        out.update(ok=False, verdict="reachable",
                   detail="地址可达，但密钥被拒绝（HTTP %s）—— 请检查密钥是否正确/已过期"
                          % res.get("status"))
    else:
        out.update(ok=False, verdict="reachable",
                   detail=res.get("detail") or ("地址可达，但返回 HTTP %s" % res.get("status")))
    return out
