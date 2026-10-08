
import math
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

_META_PREFIX = "ark:"
_LOCK = threading.RLock()


DEFAULTS = {
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",


    "image_models": ["doubao-seedream-4-0-250828"],


    "video_models": ["doubao-seedance-2-0-260128", "doubao-seedance-2-5-260628"],
}


WRITABLE_KEYS = ("enabled", "video_enabled", "base_url", "api_key", "image_models", "video_models")


PIXEL_TIERS = _imgen.PIXEL_TIERS











ARK_MODEL_LIMITS = _imgen.model_limits_map("ark")


_FALLBACK_LIMITS = dict(_imgen.FALLBACK_CAPS["ark"])



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
        return _truthy(os.environ.get("ARK_IMAGE_ENABLED"))
    if key == "video_enabled":

        v = _meta_get("video_enabled", "")
        if v != "":
            return _truthy(v)
        return _truthy(os.environ.get("ARK_VIDEO_ENABLED"))
    if key == "api_key":
        v = _meta_get("api_key", "")
        if v:
            return v
        return os.environ.get("ARK_API_KEY", "")
    if key == "base_url":
        v = _meta_get("base_url", "")
        if v:
            return _norm_url(v)
        return (os.environ.get("ARK_BASE_URL") or DEFAULTS["base_url"]).rstrip("/")
    if key == "image_models":
        v = _meta_get("image_models", "")
        if v:
            lst = _split_models(v)
            if lst:
                return lst
        lst = _split_models(os.environ.get("ARK_IMAGE_MODELS"))
        return lst or list(DEFAULTS["image_models"])
    if key == "video_models":
        v = _meta_get("video_models", "")
        if v:
            lst = _split_models(v)
            if lst:
                return lst
        lst = _split_models(os.environ.get("ARK_VIDEO_MODELS"))
        return lst or list(DEFAULTS["video_models"])
    return None


def image_models():
    
    return list(get("image_models") or DEFAULTS["image_models"])


def video_models():
    
    return list(get("video_models") or DEFAULTS["video_models"])


def is_video_model(model):
    
    return str(model or "").strip() in set(video_models())


def video_ready():
    
    return bool(get("video_enabled")) and bool(get("api_key"))


def active_state():
    
    en, key = bool(get("enabled")), bool(get("api_key"))
    if en and key:
        return True, ""
    if en and not key:
        return False, "已开启方舟生图，但未配置 ARK 访问密钥 —— 已回落 Agnes 生图"
    return False, ""


def active():
    
    return active_state()[0]


def config_snapshot(masked=True):
    
    act, why = active_state()
    mdl = image_models()
    return {
        "enabled": bool(get("enabled")),
        "video_enabled": bool(get("video_enabled")),
        "active": act,
        "fallback_reason": why,
        "base_url": get("base_url"),
        "has_key": bool(get("api_key")),
        "hasKey": bool(get("api_key")),
        "api_key_masked": mask_key(get("api_key")) if masked else get("api_key"),
        "image_models": mdl,
        "image_models_text": ", ".join(mdl),
        "video_models": video_models(),
        "video_models_text": ", ".join(video_models()),
        "model_limits": model_limits_map(),
        "defaults": DEFAULTS,
        "source": _source_map(),
    }


def _source_map():
    
    src = {}
    src["enabled"] = "ui" if _meta_get("enabled", "") != "" else ("env" if os.environ.get("ARK_IMAGE_ENABLED") else "default")
    for k, env in (("base_url", "ARK_BASE_URL"), ("image_models", "ARK_IMAGE_MODELS"), ("video_models", "ARK_VIDEO_MODELS")):
        src[k] = "ui" if _meta_get(k, "") else ("env" if os.environ.get(env) else "default")
    if _meta_get("api_key", ""):
        src["api_key"] = "ui"
    elif os.environ.get("ARK_API_KEY"):
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
    if "video_enabled" in patch:
        _meta_set("video_enabled", "1" if _truthy(patch["video_enabled"]) else "0")
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
    if "video_models" in patch:
        lst = _split_models(patch["video_models"])
        if lst:
            _meta_set("video_models", ", ".join(lst))
        else:
            _meta_del("video_models")
    if "api_key" in patch:
        k = (patch["api_key"] or "").strip()
        if k:
            _meta_set("api_key", k)
        else:
            _meta_del("api_key")
    return config_snapshot(masked=True)







def model_limits(model):
    
    return _imgen.caps_for(model, "ark")


def model_limits_map():
    
    return _imgen.model_limits_map("ark")


def resolve_tier(size, limits):
    
    return _imgen.resolve_tier(size, limits)









VIDEO_MODEL_LIMITS = {
    "doubao-seedance-2-5-260628": {
        "label": "豆包 Seedance 2.5",
        "sizes": ["480p", "720p", "1080p"],
        "min_seconds": 4, "max_seconds": 30,
        "max_images": 30, "max_audios": 3, "allow_video": False,
        "submit_gap_base": 10,
        "note": "时长 4~30s；参考图≤30；成片 24h 有效自动转存",
    },
    "doubao-seedance-2-0-260128": {
        "label": "豆包 Seedance 2.0",
        "sizes": ["480p", "720p", "1080p", "4k"],
        "min_seconds": 4, "max_seconds": 15,
        "max_images": 12, "max_audios": 3, "allow_video": False,
        "submit_gap_base": 10,
        "note": "时长 4~15s；支持 4K；参考图≤12；成片 24h 有效自动转存",
    },
    "doubao-seedance-2-0-fast-260128": {
        "label": "豆包 Seedance 2.0 Fast",
        "sizes": ["480p", "720p"],
        "min_seconds": 4, "max_seconds": 15,
        "max_images": 12, "max_audios": 3, "allow_video": False,
        "submit_gap_base": 10,
        "note": "时长 4~15s；不支持 1080p；参考图≤12",
    },
    "doubao-seedance-2-0-mini-260615": {
        "label": "豆包 Seedance 2.0 Mini",
        "sizes": ["480p", "720p"],
        "min_seconds": 4, "max_seconds": 15,
        "max_images": 12, "max_audios": 3, "allow_video": False,
        "submit_gap_base": 10,
        "note": "时长 4~15s；不支持 1080p；参考图≤12",
    },
}

_VIDEO_FALLBACK_LIMITS = {
    "label": "", "sizes": None,
    "min_seconds": None, "max_seconds": None,
    "max_images": 12, "max_audios": 0, "allow_video": False, "submit_gap_base": 10,
    "note": "未识别的方舟视频模型：不限时长/分辨率，由上游校验",
}


def video_limits(model):
    
    lim = VIDEO_MODEL_LIMITS.get(str(model or "").strip())
    if lim:
        return dict(lim)
    out = dict(_VIDEO_FALLBACK_LIMITS)
    out["label"] = str(model or "").strip()
    return out


def to_ark_video_payload(data, b64_fn=None):
    
    model = str(data.get("model") or "").strip()
    mode = data.get("mode", "text")
    prompt = str(data.get("prompt") or "")

    content = [{"type": "text", "text": prompt}]
    if mode == "keyframe":
        ff, lf = data.get("first_frame"), data.get("last_frame")
        if not ff and not lf:
            return None, "首尾帧模式至少需要提供首帧或尾帧图片。"
        for role, u in (("first_frame", ff), ("last_frame", lf)):
            if u:
                content.append({"type": "image_url",
                                "image_url": {"url": b64_fn(u) if b64_fn else u},
                                "role": role})
    elif mode == "reference":
        imgs = [u for u in (data.get("images") or []) if u]
        audios = [u for u in (data.get("audios") or []) if u]
        vids = [u for u in (data.get("videos") or []) if u]
        if not imgs and not audios and not vids:
            return None, "全能参考模式至少需要提供一份参考素材。"
        lim = video_limits(model)
        total = len(imgs) + len(audios) + len(vids)
        cap = int(lim.get("max_images") or 12)
        if total > cap:
            return None, f"当前方舟视频模型参考素材最多 {cap} 份（图+音频+视频合计），你传了 {total} 份。"
        for u in imgs:
            content.append({"type": "image_url",
                            "image_url": {"url": b64_fn(u) if b64_fn else u},
                            "role": "reference_image"})
        for u in vids:
            content.append({"type": "video_url",
                            "video_url": {"url": b64_fn(u) if b64_fn else u},
                            "role": "reference_video"})
        for u in audios:
            content.append({"type": "audio_url",
                            "audio_url": {"url": b64_fn(u) if b64_fn else u},
                            "role": "reference_audio"})

    payload = {"model": model, "content": content}


    try:
        dur = int(float(data.get("seconds") or 5))
    except (TypeError, ValueError):
        dur = 5
    lim = video_limits(model)
    lo, hi = lim.get("min_seconds"), lim.get("max_seconds")
    payload["duration"] = max(int(lo), min(int(hi), dur)) if (lo and hi) else dur

    res = str(data.get("size") or "").lower()
    if res in ("480p", "720p", "1080p", "4k"):
        payload["resolution"] = res

    ratio = (data.get("aspect_ratio") or "").strip()
    if ratio in ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9"):
        payload["ratio"] = ratio

    if data.get("seed") not in (None, "", -1):
        try:
            s = int(data["seed"])
            if s != -1:
                payload["seed"] = s
        except (TypeError, ValueError):
            pass
    return payload, None


def wxh_for(size, ratio, limits=None):
    
    return _imgen.solve_size(size, ratio, "pixel_range", limits or _FALLBACK_LIMITS)


def to_ark_payload(p):
    
    first = (image_models() or DEFAULTS["image_models"])[0]
    return _imgen.build_payload("ark", p, first_model=first)


def seed_supported(model):
    
    return bool(model_limits(model).get("seed"))



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
                   detail="地址可达性无法验证：未配置密钥。请先在「豆包生图」标签页填入方舟 API Key")
        return out

    def _lat():
        return int((time.time() - t0) * 1000)

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        r = _rq.get(f"{base}/models", headers=headers, timeout=(8, 20))
        out["latency_ms"] = _lat()
        if r.status_code == 200:
            out.update(ok=True, verdict="connected",
                       detail=f"方舟接口可用，密钥有效（GET /models 200，延迟 {out['latency_ms']}ms）")
            return out
        if r.status_code in (401, 403):
            out.update(ok=False, verdict="reachable",
                       detail=f"地址可达，但密钥被拒绝（HTTP {r.status_code}）—— 请检查方舟 API Key 是否正确/已过期")
            return out
        first = f"（GET /models 返回 HTTP {r.status_code}，改用鉴权探针）"
    except Exception as e:
        out["latency_ms"] = _lat()
        out.update(ok=False, verdict="unreachable",
                   detail=f"无法连接到 {base}：{type(e).__name__}: {e}")
        return out


    try:
        r2 = _rq.post(f"{base}/images/generations", headers=headers,
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
                   detail=f"地址可达，但密钥被拒绝（HTTP {r2.status_code}）—— 请检查方舟 API Key 是否正确/已过期")
    elif r2.status_code in (400, 404):

        out.update(ok=True, verdict="connected",
                   detail=f"方舟接口可用，密钥有效（鉴权探针 HTTP {r2.status_code}：模型名不存在属预期）{first}")
    elif r2.status_code == 200:
        out.update(ok=True, verdict="connected", detail=f"方舟接口可用（HTTP 200）{first}")
    else:
        out.update(ok=False, verdict="reachable",
                   detail=f"地址可达，但返回 HTTP {r2.status_code}（{(r2.text or '')[:160]}）")
    return out
