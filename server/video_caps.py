

from . import provider as _provider
from . import ark_provider as _arkprov
from . import runninghub_provider as _rhprov


def video_provider_state():
    

    legacy = []
    if bool(_arkprov.get("video_enabled")):
        legacy.append("ark")
    if _rhprov.video_enabled():
        legacy.append("runninghub")
    winner = _provider.get_choice("video", legacy)
    labels = {"agnes": "Agnes", "ark": "火山方舟", "runninghub": "RunningHub"}
    keys = {
        "agnes": bool(_provider.get("api_key")),
        "ark": bool(_arkprov.get("api_key")),
        "runninghub": _rhprov.api_key(),
    }
    conflict = len(legacy) > 1
    return {
        "winner": winner,
        "conflict": conflict,
        "label": labels.get(winner, winner),
        "providers": {k: {"selected": winner == k, "ready": bool(keys[k])}
                      for k in labels},
        "note": ("尚未配置访问密钥。请点击左侧「服务商设置」填入密钥（或 .env 配置 AGNES_API_KEY 后重启）。" if not keys.get(winner)
                 else ("方舟与 RunningHub 的视频开关同时打开 → 重新勾选一家即可收敛。"
                       if conflict else "")),
    }


def video_provider_models():
    
    st = video_provider_state()
    if st["winner"] == "ark":
        ms = list(_arkprov.video_models())
        return ms, {m: _arkprov.video_limits(m) for m in ms}
    if st["winner"] == "runninghub":
        ms = list(_rhprov.video_models())
        return ms, {m: _rhprov.limits(m) for m in ms}
    return list(_provider.get("video_models") or ["agnes-video-2.5-flash", "agnes-video-2.5"]), {}


def model_limits(model):
    
    m = str(model or "").strip()
    if not m:
        return {}
    try:
        if _rhprov.is_video_model(m):
            return _rhprov.limits(m) or {}
    except Exception:
        pass
    try:
        if _arkprov.is_video_model(m):
            return _arkprov.video_limits(m) or {}
    except Exception:
        pass
    from . import core as _core
    return (_core.MODEL_LIMITS.get(m) or {})


def ref_caps(model):
    
    m = str(model or "").strip()
    lim = model_limits(m) or {}
    is_ark = False
    try:
        is_ark = bool(_arkprov.is_video_model(m)) if m else False
    except Exception:
        is_ark = False
    try:
        mi = int(lim.get("max_images") or 5)
    except Exception:
        mi = 5
    try:
        ma = int(lim.get("max_audios") or (0 if is_ark else 3))
    except Exception:
        ma = 0 if is_ark else 3
    return (mi, ma)
