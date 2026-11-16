
import base64
import os
import re
import sqlite3
import threading
import time

try:
    from . import ark_provider as _ark
except ImportError:
    import ark_provider as _ark



_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")

_META_PREFIX = "wan:"
_LOCK = threading.RLock()


DEFAULTS = {
    "workspace_id": "",
    "region": "cn-beijing",
    "base_url": "",
    "uploads_url": "",
    "video_models": ["wan3.0-video", "wan3.0-video-prime"],

    "image_models": ["qwen-image-3.0-pro", "qwen-image-3.0",
                     "qwen-image-2.1-pro", "qwen-image-2.1-turbo"],



    "chat_models": ["qwen3.8-max", "qwen3.8-flash"],
    "chat_models_enabled": False,
    "chat_caps_tools": True,
    "chat_caps_vision": True,
    "chat_thinking": True,


    "chat_budget": "auto",
    "chat_max_output": "",
    "chat_ctx": "",
}




WRITABLE_KEYS = ("video_enabled", "enabled", "api_key", "workspace_id", "region",
                 "base_url", "uploads_url", "video_models", "image_models",
                 "chat_models", "chat_models_enabled",
                 "chat_caps_tools", "chat_caps_vision", "chat_thinking", "chat_budget",
                 "chat_max_output", "chat_ctx")


_BOOL_LLM_KEYS = ("chat_caps_tools", "chat_caps_vision", "chat_thinking", "chat_models_enabled")
_BUDGET_KEYS = ("chat_budget",)

_BUDGET_LEVELS = {"auto": None, "low": "low", "medium": "medium", "high": "high"}
_INT_LLM_KEYS = ("chat_max_output", "chat_ctx")
_INT_LABELS = {"chat_max_output": "输出上限", "chat_ctx": "上下文上限"}




VIDEO_MODEL_LIMITS = {
    "wan3.0-video": {
        "label": "万相 3.0",
        "sizes": ["480p", "720p", "1080p"],
        "min_seconds": 2, "max_seconds": 30,
        "max_images": 10, "max_audios": 5, "max_videos": 5, "allow_video": True,
        "submit_gap_base": 15,
        "note": "时长 2~30s；参考图≤10 / 参考视频≤5 / 参考音频≤5；成片 24h 有效自动转存",
    },
    "wan3.0-video-prime": {
        "label": "万相 3.0 高速版",
        "sizes": ["480p", "720p", "1080p"],
        "min_seconds": 2, "max_seconds": 30,
        "max_images": 10, "max_audios": 5, "max_videos": 5, "allow_video": True,
        "submit_gap_base": 15,
        "note": "高速版：官方标注「能力对齐标准版，端到端速度显著提升」；价格/速度差异待核",
    },
}

_VIDEO_FALLBACK_LIMITS = {
    "label": "", "sizes": None,
    "min_seconds": None, "max_seconds": None,
    "max_images": 10, "max_audios": 5, "max_videos": 5,
    "allow_video": True, "submit_gap_base": 15,
    "note": "未识别的万相视频模型：不限时长/分辨率；参考素材按官方登记的逐类上限",
}


_RESOLUTIONS = ("480P", "720P", "1080P")
_RATIOS = ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
_TASK_STATUS = {"PENDING": "processing", "RUNNING": "processing",
                "SUCCEEDED": "completed", "FAILED": "failed",
                "CANCELED": "failed", "UNKNOWN": "failed"}



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


def _split_models(raw):
    parts = re.split(r"[,，、\n]+", str(raw or ""))
    out = []
    for p in parts:
        p = p.strip()
        if p and p not in out:
            out.append(p)
    return out











_URL_TAIL_PATHS = (
    "/compatible-mode/v1/chat/completions",
    "/compatible-mode/v1/images/generations",
    "/compatible-mode/v1",
    "/api/v1/services/aigc/video-generation/video-synthesis",
    "/api/v1/tasks",
    "/api/v1/uploads",
    "/api/v1",
)


def _norm_url(u):
    
    if not u:
        return ""
    u = str(u).strip()
    if u and not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    changed = True
    while changed:
        changed = False
        u = u.rstrip("/")
        low = u.lower()
        for tail in _URL_TAIL_PATHS:
            if low.endswith(tail):
                u = u[: -len(tail)]
                changed = True
                break
    return u.rstrip("/")


def mask_key(k):
    if not k:
        return ""
    k = str(k)
    if len(k) <= 8:
        return "****"
    return f"{k[:3]}…{k[-4:]}"




_INT_SEPS = ",，_ \t\u00a0"


def _norm_int_token(v):
    
    if v is None:
        return ""
    s = "".join(ch for ch in str(v).strip() if ch not in _INT_SEPS)
    if not s:
        return ""
    try:
        n = int(s)
    except (TypeError, ValueError):
        return None
    return str(n) if n > 0 else None



def get(key):
    
    env_map = {
        "video_enabled": "WAN_VIDEO_ENABLED",
        "enabled": "WAN_IMAGE_ENABLED",
        "api_key": "WAN_API_KEY",
        "workspace_id": "WAN_WORKSPACE_ID",
        "region": "WAN_REGION",
        "base_url": "WAN_BASE_URL",
        "uploads_url": "WAN_UPLOADS_URL",
        "video_models": "WAN_VIDEO_MODELS",
        "image_models": "WAN_IMAGE_MODELS",
        "chat_models": "WAN_CHAT_MODELS",
        "chat_models_enabled": "WAN_CHAT_MODELS_ENABLED",
    }
    if key in ("video_enabled", "enabled") or key in _BOOL_LLM_KEYS:
        v = _meta_get(key, "")
        if v != "":
            return _truthy(v)
        ev = os.environ.get(env_map.get(key, ""))
        if ev:
            return _truthy(ev)

        return _truthy(DEFAULTS.get(key, False))
    if key in ("video_models", "image_models", "chat_models"):
        v = _meta_get(key, "")
        if v:
            lst = _split_models(v)
            if lst:
                return lst
        lst = _split_models(os.environ.get(env_map[key]))
        return lst or list(DEFAULTS[key])
    if key in ("base_url", "uploads_url"):
        v = _meta_get(key, "")
        if v:
            return _norm_url(v)
        return _norm_url(os.environ.get(env_map[key]) or "")
    if key == "region":
        v = _meta_get(key, "")
        if v:
            return v.strip()
        return (os.environ.get(env_map[key]) or DEFAULTS["region"]).strip()
    if key in _BUDGET_KEYS:
        v = _meta_get(key, "")
        return v if v in _BUDGET_LEVELS else "auto"
    if key in _INT_LLM_KEYS:
        v = _meta_get(key, "")
        try:
            return int(v) if str(v).strip() else None
        except (TypeError, ValueError):
            return None
    if key in env_map:
        v = _meta_get(key, "")
        if v:
            return v.strip()
        return (os.environ.get(env_map[key]) or "").strip()
    return None


def api_key():
    return str(get("api_key") or "")


def video_enabled():
    return bool(get("video_enabled"))


def video_ready():
    return video_enabled() and bool(api_key())


def video_models():
    return list(get("video_models") or DEFAULTS["video_models"])


def is_video_model(model):
    return str(model or "").strip() in set(video_models())


def video_limits(model):
    
    lim = VIDEO_MODEL_LIMITS.get(str(model or "").strip())
    if lim:
        return dict(lim)
    out = dict(_VIDEO_FALLBACK_LIMITS)
    out["label"] = str(model or "").strip()
    return out


def limits(model):
    
    return video_limits(model)



def image_enabled():
    
    return bool(get("enabled"))


def image_ready():
    
    return image_enabled() and bool(api_key())


def image_models():
    return list(get("image_models") or DEFAULTS["image_models"])


def is_image_model(model):
    return str(model or "").strip() in set(image_models())


def image_model_limits(model):
    
    try:
        from server import imgen as _imgen
    except ImportError:
        import imgen as _imgen
    return _imgen.caps_for(str(model or "").strip(), "wan")


def image_model_limits_map():
    
    try:
        from server import imgen as _imgen
    except ImportError:
        import imgen as _imgen
    return _imgen.model_limits_map("wan")


def image_active_state():
    
    if not image_enabled():
        return False, ""
    if not api_key():
        return False, "尚未配置百炼 API Key，请点击左侧「服务商设置」填入密钥。"
    if not endpoint():
        return False, _NO_ENDPOINT_HINT
    return True, ""





def chat_model(use_case=None):
    
    return list(get("chat_models") or DEFAULTS["chat_models"])


def chat_model_enabled(use_case=None):
    
    return bool(get("chat_models_enabled"))


def chat_caps(kind, use_case=None):
    
    return bool(get("chat_caps_" + kind))


def chat_thinking(use_case=None):
    
    return bool(get("chat_thinking"))


def chat_budget(use_case=None):
    
    return get("chat_budget")


def chat_budget_effort(use_case=None):
    
    return _BUDGET_LEVELS.get(chat_budget())


def chat_max_output(use_case=None):
    
    return get("chat_max_output")


def chat_ctx_limit(use_case=None):
    
    return get("chat_ctx")


def chat_ready():
    
    if not api_key():
        return False, "尚未配置百炼 API Key，请点击左侧「服务商设置」填入密钥。"
    if not endpoint():
        return False, _NO_ENDPOINT_HINT
    return True, ""


def ready_state(use_case=None):
    
    return chat_ready()










OFFICIAL_REGIONS = ("cn-beijing", "ap-southeast-1", "cn-hongkong",
                    "us-east-1", "eu-central-1", "ap-northeast-1")



_LEGACY_HOSTS = {
    "cn-beijing": "dashscope.aliyuncs.com",
    "ap-southeast-1": "dashscope-intl.aliyuncs.com",
    "cn-hongkong": "cn-hongkong.dashscope.aliyuncs.com",
    "us-east-1": "dashscope-us.aliyuncs.com",
}
_LEGACY_HOST_SET = frozenset(_LEGACY_HOSTS.values())


_MAAS_HOST_RE = re.compile(
    r"^[a-z0-9-]+\.(" + "|".join(re.escape(r) for r in OFFICIAL_REGIONS) +
    r")\.maas\.aliyuncs\.com$", re.I)



_NO_ENDPOINT_HINT = (
    "尚未配置接入地址：填业务空间 ID，或在「接口地址」粘域名"
    "（如 https://dashscope.aliyuncs.com，免业务空间 / 地域）。")


def endpoint():
    
    b = _norm_url(get("base_url"))
    if b:
        return b
    ws, region = get("workspace_id"), get("region")
    if not ws:
        return ""
    return f"https://{ws}.{region}.maas.aliyuncs.com"


def uploads_host(base_url, region, workspace_id):
    
    b = _norm_url(base_url)
    if b:
        host = b.split("://", 1)[-1].split("/", 1)[0].strip().lower()
        if host in _LEGACY_HOST_SET:
            return host
        m = _MAAS_HOST_RE.match(host)
        if m:
            return _LEGACY_HOSTS.get(m.group(1).lower()) or host
        return host
    rg = str(region or "").strip().lower() or DEFAULTS["region"]
    lg = _LEGACY_HOSTS.get(rg)
    if lg:
        return lg
    ws = str(workspace_id or "").strip()
    if ws:
        return f"{ws}.{rg}.maas.aliyuncs.com"
    return _LEGACY_HOSTS[DEFAULTS["region"]]


def uploads_endpoint():
    
    u = _norm_url(get("uploads_url"))
    if u:
        return u
    return "https://" + uploads_host(get("base_url"), get("region"), get("workspace_id")) + "/api/v1/uploads"


def create_url():
    return endpoint() + "/api/v1/services/aigc/video-generation/video-synthesis"


def task_url(task_id):
    return endpoint() + "/api/v1/tasks/" + str(task_id)


def compatible_base_url():
    
    return endpoint() + "/compatible-mode/v1"


def image_base_url():
    
    return compatible_base_url()


def image_generate_url():
    
    return image_base_url() + "/images/generations"


def active_state():
    
    if not video_enabled():
        return False, ""
    if not api_key():
        return False, "尚未配置百炼 API Key，请点击左侧「服务商设置」填入密钥。"
    if not endpoint():
        return False, _NO_ENDPOINT_HINT
    return True, ""


def config_snapshot(masked=True):
    act, why = active_state()
    iact, iwhy = image_active_state()
    mdl = video_models()
    imdl = image_models()
    return {


        "enabled": image_enabled(),
        "video_enabled": video_enabled(),
        "image_enabled": image_enabled(),
        "active": act,
        "fallback_reason": why,
        "image_active": iact,
        "image_fallback_reason": iwhy,
        "base_url": endpoint(),



        "base_url_override": get("base_url"),
        "workspace_id": get("workspace_id"),
        "region": get("region"),
        "uploads_url": uploads_endpoint(),
        "image_url": image_generate_url(),
        "has_key": bool(api_key()),
        "hasKey": bool(api_key()),
        "api_key_masked": mask_key(api_key()) if masked else api_key(),
        "video_models": mdl,
        "video_models_text": ", ".join(mdl),
        "image_models": imdl,
        "image_models_text": ", ".join(imdl),

        "chat_models": chat_model(),
        "chat_models_text": ", ".join(chat_model()),
        "chat_models_enabled": chat_model_enabled(),
        "chat_caps_tools": chat_caps("tools"),
        "chat_caps_vision": chat_caps("vision"),
        "chat_thinking": chat_thinking(),
        "chat_budget": chat_budget(),
        "chat_max_output": chat_max_output() or "",
        "chat_ctx": chat_ctx_limit() or "",
        "chat_url": compatible_base_url() + "/chat/completions",
        "chat_ready": chat_ready()[0],
        "chat_fallback_reason": chat_ready()[1],
        "model_limits": {m: video_limits(m) for m in mdl},
        "image_model_limits": {m: image_model_limits(m) for m in imdl},
        "defaults": DEFAULTS,
        "source": _source_map(),
    }


def _source_map():
    src = {}
    for k, env in (("video_enabled", "WAN_VIDEO_ENABLED"), ("enabled", "WAN_IMAGE_ENABLED"),
                   ("api_key", "WAN_API_KEY"), ("workspace_id", "WAN_WORKSPACE_ID"),
                   ("region", "WAN_REGION"), ("base_url", "WAN_BASE_URL"),
                   ("uploads_url", "WAN_UPLOADS_URL"), ("video_models", "WAN_VIDEO_MODELS"),
                   ("image_models", "WAN_IMAGE_MODELS"),
                   ("chat_models", "WAN_CHAT_MODELS"),
                   ("chat_models_enabled", "WAN_CHAT_MODELS_ENABLED")):
        src[k] = "ui" if _meta_get(k, "") != "" else ("env" if os.environ.get(env) else "default")
    return src


def save(patch, keep_old_key=True):
    
    _ensure_meta_table()
    if not isinstance(patch, dict):
        raise ValueError("patch 必须是对象")
    for k in patch:
        if k not in WRITABLE_KEYS:
            raise ValueError(f"不支持的配置项：{k}")

    _int_patch = {}
    for k in _INT_LLM_KEYS:
        if k in patch:
            s = _norm_int_token(patch[k])
            if s is None:
                raise ValueError(
                    f"{_INT_LABELS.get(k, k)} 只能填正整数（如 8192），不要带单位或字母：{patch[k]!r}")
            _int_patch[k] = s



    for k in ("video_enabled", "enabled"):
        if k in patch:
            _meta_set(k, "1" if _truthy(patch[k]) else "0")
    for k in _BOOL_LLM_KEYS:
        if k in patch:
            _meta_set(k, "1" if _truthy(patch[k]) else "0")
    for k in ("api_key", "workspace_id", "region", "base_url", "uploads_url"):
        if k in patch:
            v = str(patch[k] or "").strip()
            if k in ("base_url", "uploads_url"):
                v = _norm_url(v)
            if v:
                _meta_set(k, v)
            else:
                _meta_del(k)
    for k in ("video_models", "image_models", "chat_models"):
        if k in patch:
            lst = _split_models(patch[k])
            if lst:
                _meta_set(k, ", ".join(lst))
            else:
                _meta_del(k)
    for k in _BUDGET_KEYS:
        if k in patch:
            v = str(patch[k] or "auto").strip()
            _meta_set(k, v if v in _BUDGET_LEVELS else "auto")
    for k, s2 in _int_patch.items():
        _meta_set(k, s2) if s2 else _meta_del(k)
    return config_snapshot(masked=True)



def to_wan_image_payload(p):
    
    try:
        from server import imgen as _imgen
    except ImportError:
        import imgen as _imgen
    first = (image_models() or DEFAULTS["image_models"])[0]
    return _imgen.build_payload("wan", p, first_model=first)


def to_wan_video_payload(data, b64_fn=None, oss_fn=None):
    
    model = str(data.get("model") or "").strip() or video_models()[0]
    mode = str(data.get("mode") or "text").strip().lower()
    prompt = _ark.translate_prompt_marks(str(data.get("prompt") or ""))
    lim = video_limits(model)

    imgs = [u for u in (data.get("images") or []) if u]
    audios = [u for u in (data.get("audios") or []) if u]
    vids = [u for u in (data.get("videos") or []) if u]
    ff, lf = data.get("first_frame"), data.get("last_frame")


    for label, items, cap in (("参考图", imgs, "max_images"),
                              ("参考视频", vids, "max_videos"),
                              ("参考音频", audios, "max_audios")):
        n = int(lim.get(cap) or 0)
        if n and len(items) > n:
            return None, f"当前万相视频模型{label}最多 {n} 份，你传了 {len(items)} 份。"

    media = []

    def _img_url(u):
        return b64_fn(u) if b64_fn else u

    def _oss_url(u, kind):
        if not oss_fn:
            raise RuntimeError("存在音视频参考素材，但本次调用没有提供临时 URL 上传回调。")
        return oss_fn(u, kind)

    try:
        if mode == "keyframe":


            if imgs or audios or vids:
                return None, ("万相 3.0 的首帧/首尾帧模式不能与参考图/视频/音频混用（官方素材组合规则）。"
                              "请改用「参考生视频」模式，或移除多余素材。")
            if not ff and not lf:
                return None, "首尾帧模式至少需要提供首帧或尾帧图片。"
            if ff:
                media.append({"type": "first_frame", "url": _img_url(ff)})
            if lf:
                media.append({"type": "last_frame", "url": _img_url(lf)})
        else:


            for u in imgs:
                media.append({"type": "reference_image", "url": _img_url(u)})
            for u in vids:
                media.append({"type": "reference_video", "url": _oss_url(u, "video")})
            for u in audios:
                media.append({"type": "reference_audio", "url": _oss_url(u, "audio")})
    except RuntimeError as e:
        return None, str(e)


    inp = {"prompt": prompt}
    if media:
        inp["media"] = media
    elif not prompt:
        return None, "请填写提示词（prompt）。万相 3.0 文生视频需要提示词来描述画面。"



    try:
        dur = int(float(data.get("seconds") or 5))
    except (TypeError, ValueError):
        dur = 5
    lo, hi = lim.get("min_seconds"), lim.get("max_seconds")
    duration = max(int(lo), min(int(hi), dur)) if (lo and hi) else dur

    params = {
        "resolution": "1080P",
        "ratio": "adaptive",
        "duration": duration,
        "audio": False,
        "prompt_extend": False,
        "watermark": False,
    }
    res = str(data.get("size") or "").upper()
    if res in _RESOLUTIONS:
        params["resolution"] = res
    ratio = str(data.get("aspect_ratio") or "").strip()
    if ratio in _RATIOS:
        params["ratio"] = ratio
    if data.get("seed") not in (None, "", -1):
        try:
            s = int(data["seed"])
            if s >= 0:
                params["seed"] = min(s, 2147483647)
        except (TypeError, ValueError):
            pass

    return {"model": model, "input": inp, "parameters": params}, None


def needs_oss_resource_resolve(payload):
    
    try:
        media = (payload.get("input") or {}).get("media") or []
        return any(str(it.get("url") or "").startswith("oss://") for it in media if isinstance(it, dict))
    except Exception:
        return False


def parse_status(body):
    
    if not isinstance(body, dict):
        return "processing", None, None
    out = body.get("output") if isinstance(body.get("output"), dict) else {}
    raw = str(out.get("task_status") or body.get("task_status") or "").upper()
    status = _TASK_STATUS.get(raw, "processing")
    url = out.get("video_url") or body.get("video_url")
    err = None
    if status == "failed":
        err = (out.get("message") or out.get("code") or body.get("message")
               or {"FAILED": "万相 3.0 任务生成失败。", "CANCELED": "万相 3.0 任务已取消。",
                   "UNKNOWN": "任务不存在或已超过 24 小时查询有效期。"}.get(raw, "万相 3.0 任务未完成。"))
    return status, url, err



_MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
             "image/gif": "gif", "image/bmp": "bmp", "video/mp4": "mp4",
             "video/quicktime": "mov", "audio/mpeg": "mp3", "audio/wav": "wav",
             "audio/x-wav": "wav"}


def _material_blob(src):
    
    import requests as _rq
    from urllib.parse import unquote as _unquote
    try:
        import server.core as _core
        import server.tts_client as _ttsclient
        import server.payload_media as _pm
    except ImportError as e:
        raise RuntimeError(f"素材解析模块不可用：{e}")

    src = str(src or "").strip()
    if not src:
        raise RuntimeError("空的素材地址")


    if src.startswith("/api/tts/file/"):
        rel = _unquote(src[len("/api/tts/file/"):].split("?")[0]).replace("\\", "/").lstrip("/")
        if not _ttsclient.is_public_rel(rel):
            raise RuntimeError(f"音频地址不在站内白名单目录内：{src}")
        p = _ttsclient.abs_path(rel)
        if not p or not os.path.isfile(p) or not os.path.realpath(p).startswith(
                os.path.realpath(_ttsclient._STORAGE)):
            raise RuntimeError(f"音频文件不存在：{src}")
        with open(p, "rb") as f:
            return f.read(), os.path.basename(p)

    inline = _core._to_b64_if_local(src)
    if isinstance(inline, str) and inline.startswith("data:"):
        head, _, b64data = inline.partition(",")
        blob = base64.b64decode(b64data)
        mime = head[5:].split(";")[0].strip() or "application/octet-stream"
        ext = _MIME_EXT.get(mime) or (mime.split("/")[-1] if "/" in mime else "bin")
        name = os.path.basename(src.split("?")[0].rstrip("/")) or f"material.{ext}"
        if "." not in name:
            name = f"{name}.{ext}"
        return blob, name

    if src.startswith("http://") or src.startswith("https://"):
        r = _rq.get(src, timeout=(10, 600))
        r.raise_for_status()
        return r.content, os.path.basename(src.split("?")[0]) or "material.bin"

    cand = [src, os.path.join(_ROOT, src.lstrip("/\\"))]
    p = next((x for x in cand if os.path.exists(x)), None)
    if not p:
        raise RuntimeError(f"素材既不是站内文件也不是可下载外链，找不到：{src}")
    with open(p, "rb") as f:
        return f.read(), os.path.basename(p)


def upload_material(src, kind="video", model=None, api_key_override=None):
    
    import requests as _rq
    key = api_key_override or api_key()
    if not key:
        raise RuntimeError("百炼未配置 API Key，无法上传参考素材。")
    mdl = str(model or "").strip() or video_models()[0]
    blob, name = _material_blob(src)
    if not blob:
        raise RuntimeError(f"素材内容为空：{src}")


    safe = re.sub(r"[^\w.\-]", "_", name)[-80:] or f"{kind}.bin"
    safe = f"{int(time.time() * 1000) % 100000000}_{safe}"

    r = _rq.get(uploads_endpoint(),
                params={"action": "getPolicy", "model": mdl},
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=(10, 30))
    if r.status_code != 200:
        raise RuntimeError(f"获取上传凭证失败（{r.status_code}）：{r.text[:180]}")
    try:
        pol = (r.json().get("data") or {})
    except Exception:
        raise RuntimeError(f"上传凭证响应无法解析：{r.text[:180]}")
    host = str(pol.get("upload_host") or "").strip()
    udir = str(pol.get("upload_dir") or "").strip()
    if not host or not udir:
        raise RuntimeError("上传凭证缺少 upload_host / upload_dir。")
    obj_key = f"{udir}/{safe}"
    form = {
        "OSSAccessKeyId": (None, str(pol.get("oss_access_key_id") or "")),
        "Signature": (None, str(pol.get("signature") or "")),
        "policy": (None, str(pol.get("policy") or "")),
        "x-oss-object-acl": (None, str(pol.get("x_oss_object_acl") or "private")),
        "x-oss-forbid-overwrite": (None, str(pol.get("x_oss_forbid_overwrite") or "true")),
        "key": (None, obj_key),
        "success_action_status": (None, "200"),
        "file": (safe, blob),
    }

    up = _rq.post(host, files=form, timeout=(60, 600))
    if up.status_code != 200:
        raise RuntimeError(f"上传素材失败（{up.status_code}）：{up.text[:180]}")
    return f"oss://{obj_key}"



def test_connection(base_url=None, api_key_=None, workspace_id=None, region=None):
    
    import requests as _rq
    key = api_key_ or api_key()
    t0 = time.time()
    out = {"ok": False, "verdict": "unreachable", "detail": "", "latency_ms": 0,
           "tested_at": t0, "base_url": ""}
    if not key:
        out.update(verdict="no_key",
                   detail="未配置百炼 API Key。请在「服务商设置 → 阿里云百炼」填入密钥（或 .env 配置 WAN_API_KEY 后重启）。")
        return out

    b = _norm_url(base_url) if base_url else ""
    if not b:
        ws = str(workspace_id if workspace_id is not None else get("workspace_id") or "").strip()
        rg = str(region if region is not None else get("region") or "").strip() or "cn-beijing"
        b = f"https://{ws}.{rg}.maas.aliyuncs.com" if ws else endpoint()
    out["base_url"] = b.rstrip("/")
    if not b:
        out.update(verdict="unreachable",
                   detail=_NO_ENDPOINT_HINT)
        return out
    try:
        r = _rq.get(b.rstrip("/") + "/api/v1/tasks",
                    params={"page_no": 1, "page_size": 1},
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=(8, 20))
        out["latency_ms"] = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            out.update(ok=True, verdict="connected",
                       detail="密钥 / 业务空间 ID / 地域校验通过（只读查询任务列表，未创建任务、未产生费用）。")
        elif r.status_code in (401, 403):
            out.update(verdict="reachable",
                       detail="地址可达，但密钥被拒。请检查 API Key，以及它与 Endpoint 是否属于同一地域。")
        else:
            try:
                msg = (r.json().get("message") or r.text[:160])
            except Exception:
                msg = r.text[:160]
            out.update(verdict="reachable",
                       detail=f"地址可达，查询返回 {r.status_code}：{msg}")
    except _rq.RequestException as e:
        out["latency_ms"] = int((time.time() - t0) * 1000)
        out.update(verdict="unreachable", detail=f"无法连接百炼 Endpoint：{e}")
    return out
