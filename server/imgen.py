

import math
import re


PIXEL_TIERS = {"1K": 1048576, "1.5K": 2359296, "2K": 4194304,
               "3K": 9437184, "4K": 16777216}






AGNES_TIERS = ("1K", "2K", "3K", "4K")


_SNAP = 8


_RATIO_MIN, _RATIO_MAX = 1.0 / 16.0, 16.0



















CAPS = {

    "doubao-seedream-5-0-pro-260628": {
        "tiers": ["1K", "1.5K", "2K"], "min_px": 921600, "max_px": 4624220,
        "max_ref_images": 10,
        "sequential": False, "seed": False, "png": True,
        "can_t2i": True, "can_edit": True,
    },
    "doubao-seedream-5-0-260128": {
        "tiers": ["2K", "3K", "4K"], "min_px": 3686400, "max_px": 16777216,
        "max_ref_images": 14,
        "sequential": True, "seed": False, "png": True,
        "can_t2i": True, "can_edit": True,
    },
    "doubao-seedream-5-0-lite-260128": {
        "tiers": ["2K", "3K", "4K"], "min_px": 3686400, "max_px": 16777216,
        "max_ref_images": 14,
        "sequential": True, "seed": False, "png": True,
        "can_t2i": True, "can_edit": True,
    },
    "doubao-seedream-4-5-251128": {
        "tiers": ["2K", "4K"], "min_px": 3686400, "max_px": 16777216,
        "max_ref_images": 14,
        "sequential": True, "seed": False, "png": False,
        "can_t2i": True, "can_edit": True,
    },
    "doubao-seedream-4-0-250828": {
        "tiers": ["1K", "2K", "4K"], "min_px": 921600, "max_px": 16777216,
        "max_ref_images": 14,
        "sequential": True, "seed": False, "png": False,
        "can_t2i": True, "can_edit": True,
    },





    "Qwen/Qwen-Image-2.1": {
        "edge_min": 64, "edge_max": 1664,
        "can_t2i": True, "can_edit": True, "seed": True,
        "ratios": ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"],
    },


    "Qwen/Qwen-Image-Edit-2511": {
        "edge_min": 64, "edge_max": 1664,
        "can_t2i": False, "can_edit": True, "seed": True,
        "ratios": ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"],
    },
}


FALLBACK_CAPS = {
    "ark": {"tiers": ["1K", "2K", "3K", "4K"], "min_px": 921600, "max_px": 16777216,
            "max_ref_images": 14,
            "sequential": False, "seed": False, "png": False,
            "can_t2i": True, "can_edit": True},
    "ms": {"edge_min": 64, "edge_max": 1664,
           "can_t2i": True, "can_edit": True, "seed": True},
}


MODEL_PROVIDER = {}
for _m in CAPS:
    MODEL_PROVIDER[_m] = "ms" if _m.startswith("Qwen/") else "ark"


def caps_for(model, provider=None):
    
    m = str(model or "").strip()
    if m in CAPS:
        return dict(CAPS[m])
    prov = provider or MODEL_PROVIDER.get(m, "ark")
    return dict(FALLBACK_CAPS.get(prov, FALLBACK_CAPS["ark"]))


def registered(model):
    
    return str(model or "").strip() in CAPS


def can_t2i(model):
    return bool(caps_for(model).get("can_t2i"))


def can_edit(model):
    return bool(caps_for(model).get("can_edit"))














PROVIDERS = {

    "ark": {
        "label": "方舟",
        "endpoint": "/images/generations",
        "async": False,
        "size_rule": "pixel_range",




        "input": {"max_px": 36000000},
        "fields": [
            {"to": "model", "kind": "model"},
            {"to": "prompt", "kind": "text", "from": "prompt", "default": ""},
            {"to": "size", "kind": "size"},
            {"to": "response_format", "kind": "const", "value": "url"},

            {"to": "watermark", "kind": "const", "value": False},
            {"to": "image", "kind": "media", "from": ["extra_body.image", "images"]},

            {"to": "seed", "kind": "cast_int", "from": "seed", "gate": "seed"},

            {"to": "sequential_image_generation", "kind": "const",
             "value": "disabled", "gate": "sequential"},

            {"to": "output_format", "kind": "const", "value": "png", "gate": "png"},
        ],
    },





    "ms": {
        "label": "魔搭",
        "endpoint": "/images/generations",
        "async": True,
        "size_rule": "edge_range",




        "input": {"edge_max": 2048},
        "fields": [
            {"to": "model", "kind": "model"},
            {"to": "prompt", "kind": "text", "from": "prompt", "default": ""},

            {"to": "image_url", "kind": "media", "from": ["extra_body.image", "images"]},
            {"to": "size", "kind": "size"},
            {"to": "seed", "kind": "cast_int", "from": "seed", "gate": "seed"},
        ],
    },
}


AGNES_ENDPOINT = "/images/generations"













IMAGE_PROVIDERS = (
    {"key": "ark", "label": "豆包 Seedream（火山方舟）"},
    {"key": "ms", "label": "魔搭 ModelScope"},
    {"key": "agnes", "label": "Agnes"},
)
IMAGE_PROVIDER_ORDER = tuple(p["key"] for p in IMAGE_PROVIDERS)
IMAGE_PROVIDER_LABELS = {p["key"]: p["label"] for p in IMAGE_PROVIDERS}

IMAGE_PROVIDER_HOSTS = tuple(k for k in IMAGE_PROVIDER_ORDER if k != "agnes")


def resolve_image_provider(enabled, ready):
    
    en = [k for k in IMAGE_PROVIDER_ORDER
          if k in IMAGE_PROVIDER_HOSTS and k in set(enabled or ())]
    selected = en[0] if en else "agnes"
    rd = {k: bool((ready or {}).get(k)) for k in IMAGE_PROVIDER_ORDER}
    rd["agnes"] = True
    winner = selected if rd.get(selected) else "agnes"
    conflict = len(en) > 1
    fallback = winner != selected
    if fallback:
        note = ("已选定「%s」，但它尚未就绪（未开启或未配置密钥）→ 生图实际仍走「%s」。"
                % (IMAGE_PROVIDER_LABELS[selected], IMAGE_PROVIDER_LABELS[winner]))
    elif conflict:
        note = ("检测到多家同时开启（%s），已按优先级取「%s」；保存一次「生图服务商」即可收敛为一家。"
                % ("、".join(IMAGE_PROVIDER_LABELS[k] for k in en), IMAGE_PROVIDER_LABELS[winner]))
    else:
        note = ""
    return {"winner": winner, "selected": selected, "enabled": en, "conflict": conflict,
            "fallback": fallback, "ready": rd, "note": note}


def input_caps(prov):
    
    spec = (PROVIDERS.get(str(prov or "").lower()) or {}).get("input")
    return dict(spec) if isinstance(spec, dict) else {}





def _ratio_pair(ratio):
    
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[:：xX*/]\s*(\d+(?:\.\d+)?)\s*$", str(ratio or ""))
    if not m:
        return (1.0, 1.0)
    a, b = float(m.group(1)), float(m.group(2))
    return (a, b) if a > 0 and b > 0 else (1.0, 1.0)


def _snap(v, up=None):
    
    v = int(v)
    if up is True:
        return max(_SNAP, ((v + _SNAP - 1) // _SNAP) * _SNAP)
    if up is False:
        return max(_SNAP, (v // _SNAP) * _SNAP)
    return max(_SNAP, int(round(v / float(_SNAP))) * _SNAP)


def _clamp_tier(size, tiers):
    
    tpx = float(PIXEL_TIERS.get(str(size).upper(), 0) or 0)
    best, bd = tiers[0], None
    for x in tiers:
        d = abs(math.log(PIXEL_TIERS[x] / tpx)) if tpx > 0 else 0
        if bd is None or d < bd:
            best, bd = x, d
    return best


def resolve_tier(size, caps):
    
    tiers = (caps or {}).get("tiers") or FALLBACK_CAPS["ark"]["tiers"]
    t = str(size or "").upper().strip()
    if t in tiers:
        return t
    if t in PIXEL_TIERS:
        return _clamp_tier(t, tiers)
    return tiers[0]


def nearest_tier_by_px(px, allowed=None):
    
    try:
        px = float(px)
    except (TypeError, ValueError):
        px = 0.0
    pool = [t for t in (allowed or PIXEL_TIERS) if t in PIXEL_TIERS] or list(PIXEL_TIERS)
    if px <= 0:
        return pool[0]
    best, bd = pool[0], None
    for t in pool:
        d = abs(math.log(PIXEL_TIERS[t] / px))
        if bd is None or d < bd:
            best, bd = t, d
    return best


def parse_src_size(v):
    
    m = re.match(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$", str(v or ""))
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    return (w * h) if (w > 0 and h > 0) else None


def _size_by_pixel_range(tier, a, b, caps, src_px=None):
    
    if src_px:
        target = float(src_px)
    else:
        t = resolve_tier(tier, caps)
        target = float(PIXEL_TIERS[t])
    lo = float(caps.get("min_px") or FALLBACK_CAPS["ark"]["min_px"])
    hi = float(caps.get("max_px") or FALLBACK_CAPS["ark"]["max_px"])
    r = min(_RATIO_MAX, max(_RATIO_MIN, a / b))

    w = _snap(math.sqrt(target * r))
    h = _snap(math.sqrt(target / r))
    for _ in range(8):
        px = w * h
        if lo <= px <= hi:
            break
        grow = px < lo
        s = math.sqrt((lo if grow else hi) / px)
        w = _snap(w * s, grow)
        h = _snap(h * s, grow)
    return f"{w}x{h}"


def _size_by_edge_range(tier, a, b, caps, src_px=None):
    
    lo = float(caps.get("edge_min") or FALLBACK_CAPS["ms"]["edge_min"])
    hi = float(caps.get("edge_max") or FALLBACK_CAPS["ms"]["edge_max"])
    if src_px:
        target = float(src_px)
    else:
        target = float(PIXEL_TIERS.get(str(tier or "").upper().strip())
                       or PIXEL_TIERS["1K"])
    r = min(_RATIO_MAX, max(_RATIO_MIN, a / b))

    w0 = math.sqrt(target * r)
    h0 = math.sqrt(target / r)
    longest = max(w0, h0)
    if longest > hi:
        s = hi / longest
        w0 *= s
        h0 *= s
    shortest = min(w0, h0)
    if shortest < lo:
        s = lo / shortest
        w0 *= s
        h0 *= s

    w = _snap(w0)
    h = _snap(h0)
    w = int(max(lo, min(hi, w)))
    h = int(max(lo, min(hi, h)))
    return f"{w}x{h}"


def solve_size(tier, ratio, rule, caps, src_px=None, allowed_tiers=None):
    
    if rule == "tier_string":
        if src_px:
            return nearest_tier_by_px(src_px, allowed_tiers)
        return str(tier or "").upper().strip() or "1K"
    a, b = _ratio_pair(ratio)
    if rule == "edge_range":
        return _size_by_edge_range(tier, a, b, caps or {}, src_px=src_px)
    return _size_by_pixel_range(tier, a, b, caps or {}, src_px=src_px)


def tier_fits(tier, ratio, rule, caps):
    
    px = PIXEL_TIERS.get(str(tier or "").upper().strip())
    if not px:
        return False
    if rule == "tier_string":
        return True
    a, b = _ratio_pair(ratio)
    r = min(_RATIO_MAX, max(_RATIO_MIN, a / b))
    ideal_w = _snap(math.sqrt(px * r))
    ideal_h = _snap(math.sqrt(px / r))
    try:
        got = solve_size(tier, ratio, rule, caps)
        w, h = (int(x) for x in got.split("x"))
    except Exception:
        return False
    return abs(w - ideal_w) <= _SNAP and abs(h - ideal_h) <= _SNAP


def reachable_tiers(provider, caps_map, ratio="1:1"):
    
    rule = "pixel_range" if provider == "ark" else "edge_range"
    out = []
    for t in ("1K", "2K", "3K", "4K"):
        for c in (caps_map or {}).values():
            if c.get("tiers") and rule == "pixel_range":
                hit = t in c["tiers"]
            else:
                hit = tier_fits(t, ratio, rule, c)
            if hit:
                if t not in out:
                    out.append(t)
                break
    return out





def _pick(p, src):
    
    paths = [src] if isinstance(src, str) else list(src or [])
    for path in paths:
        cur = p
        for part in str(path).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur:
            return cur
    return None


def build_payload(provider, payload, first_model=None):
    
    spec = PROVIDERS.get(provider)
    if not spec:
        raise ValueError(f"未登记的生图服务商：{provider}")
    p = payload or {}

    model = str(p.get("model") or "").strip() or str(first_model or "").strip()
    caps = caps_for(model, provider)

    out = {}
    for f in spec["fields"]:
        to = f["to"]
        kind = f["kind"]

        if kind == "const":
            if f.get("gate") and not caps.get(f["gate"]):
                continue
            out[to] = f["value"]
            continue

        if kind == "model":
            if model:
                out[to] = model
            continue

        if kind == "size":

            out[to] = solve_size(p.get("size"), p.get("ratio"), spec["size_rule"], caps,
                                 src_px=parse_src_size(p.get("src_size")))
            continue

        if kind == "text":
            v = p.get(f.get("from") or to)
            out[to] = v if v not in (None, "") else f.get("default", "")
            continue

        if kind == "media":
            v = _pick(p, f.get("from") or to)
            if isinstance(v, str):
                v = [v]
            v = [x for x in (v or []) if x]
            if v:
                out[to] = v
            continue

        if kind == "cast_int":
            if f.get("gate") and not caps.get(f["gate"]):
                continue
            raw = _pick(p, f.get("from") or to)
            if raw in (None, ""):
                continue
            try:
                out[to] = int(raw)
            except (TypeError, ValueError):
                pass
            continue

    return out


def model_limits_map(provider):
    
    out = {}
    for m, c in CAPS.items():
        if MODEL_PROVIDER.get(m) == provider:
            out[m] = dict(c)
    return out
