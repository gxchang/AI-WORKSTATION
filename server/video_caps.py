

from . import provider as _provider
from . import ark_provider as _arkprov
from . import runninghub_provider as _rhprov


def video_provider_state():
    
    rh_on = _rhprov.video_ready()
    ark_on = _arkprov.video_ready()
    if rh_on and ark_on:
        winner, conflict = "ark", True
    elif rh_on:
        winner, conflict = "runninghub", False
    elif ark_on:
        winner, conflict = "ark", False
    else:
        winner, conflict = "agnes", False
    labels = {"agnes": "Agnes", "ark": "火山方舟", "runninghub": "RunningHub"}
    return {
        "winner": winner,
        "conflict": conflict,
        "label": labels[winner],
        "providers": {
            "agnes": {"selected": winner == "agnes", "ready": True},
            "ark": {"selected": winner == "ark", "ready": ark_on},
            "runninghub": {"selected": winner == "runninghub", "ready": rh_on},
        },
        "note": ("方舟与 RunningHub 的视频开关同时打开 → 当前按方舟生效；"
                 "到设置页重新勾选一家即可" if conflict else ""),
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
