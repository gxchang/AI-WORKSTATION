

import base64
import hashlib
import io
import math
import os
import re
from urllib.parse import unquote, urlparse


MEDIA_MIN = 64 * 1024

_DATA_URI_RE = re.compile(r"^data:([\w.+-]+/[\w.+-]+);base64,(.+)$", re.S)

MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
    "aac": "audio/aac", "ogg": "audio/ogg", "flac": "audio/flac",

    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "avi": "video/x-msvideo", "mkv": "video/x-matroska",
}


def safe_name(name):
    
    name = os.path.basename(str(name or ""))
    name = re.sub(r"[\x00-\x1f/\\]", "_", name)
    return name[:80] or "file"


def _asset_path(assets_dir, name):
    return os.path.join(assets_dir, safe_name(name))


def _resolve_local(url, assets_dir, public_base=""):
    
    if not url or not isinstance(url, str):
        return None, None
    if public_base and url.startswith(public_base + "/assets/"):
        name = url[len(public_base) + len("/assets/"):]
    elif url.startswith("/assets/"):
        name = url[len("/assets/"):]
    else:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.path.startswith("/assets/"):
            return None, None
        name = parsed.path[len("/assets/"):]



    if "%" in name:
        name = unquote(name)
    full = _asset_path(assets_dir, name)
    if not os.path.isfile(full):
        return None, None
    return full, name


def asset_local_path(url, assets_dir, public_base=""):
    
    return _resolve_local(url, assets_dir, public_base)[0]




_FIT_OUT = {"png": "image/png",
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp"}


def fit_scale(w, h, caps):
    
    s = 1.0
    emax = caps.get("edge_max")
    if emax:
        try:
            emax = int(emax)
            if emax > 0 and max(w, h) > emax:
                s = min(s, float(emax) / float(max(w, h)))
        except (TypeError, ValueError):
            pass
    mpx = caps.get("max_px")
    if mpx:
        try:
            mpx = int(mpx)
            if mpx > 0 and w * h * s * s > mpx:
                s = min(s, math.sqrt(float(mpx) / float(w * h)))
        except (TypeError, ValueError):
            pass
    return s


def fit_image(full, ext, caps):
    
    if not caps or ext not in _FIT_OUT:
        return None
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(full) as im:
            if getattr(im, "n_frames", 1) != 1:
                return None
            w, h = im.size
            if not w or not h:
                return None
            s = fit_scale(w, h, caps)
            if s >= 1.0:
                return None
            nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))



            alpha = ("A" in im.mode) or ("transparency" in im.info)
            px = im.convert("RGBA") if alpha else im.convert("RGB")
            px = px.resize((nw, nh), Image.LANCZOS)
            out = io.BytesIO()
            mime = _FIT_OUT[ext]
            if mime == "image/png":
                px.save(out, "PNG", optimize=True)
            elif mime == "image/webp":
                px.save(out, "WEBP", quality=92, method=4)
            else:
                px.save(out, "JPEG", quality=92, subsampling=0)
            data = out.getvalue()
    except Exception:
        return None
    if not data:
        return None
    return data, mime, "%dx%d→%dx%d" % (w, h, nw, nh)


def to_data_uri(url, assets_dir, public_base="", caps=None):
    
    if not url or not isinstance(url, str):
        return url
    full, name = _resolve_local(url, assets_dir, public_base)
    if not full:
        return url
    ext = safe_name(name).rsplit(".", 1)[-1].lower()
    mime = MIME_BY_EXT.get(ext, "application/octet-stream")
    fitted = fit_image(full, ext, caps) if mime.startswith("image/") else None
    if fitted:
        data, mime, note = fitted
        print("[media] 参考图 %s 超上游输入图上限（%s）→ 已等比缩到 %s"
              % (safe_name(name), caps, note.split("→")[-1]))
    else:
        with open(full, "rb") as fh:
            data = fh.read()
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def inline(payload, assets_dir, public_base="", caps=None):
    
    if isinstance(payload, str):
        return to_data_uri(payload, assets_dir, public_base, caps)
    if isinstance(payload, list):
        return [inline(x, assets_dir, public_base, caps) for x in payload]
    if isinstance(payload, dict):
        return {k: inline(v, assets_dir, public_base, caps) for k, v in payload.items()}
    return payload


def rev_lookup(blob, assets_dir, lookup=None):
    
    if not blob:
        return None
    h = hashlib.sha256(blob).hexdigest()
    if lookup is not None:
        try:
            hit = lookup(h)
        except Exception:
            hit = None
        if hit:
            nm = safe_name(hit)
            if nm and os.path.isfile(_asset_path(assets_dir, nm)):
                return "/assets/" + nm
    try:
        n = len(blob)
        for fn in os.listdir(assets_dir):
            p = os.path.join(assets_dir, fn)
            try:
                if not os.path.isfile(p) or os.path.getsize(p) != n:
                    continue
                with open(p, "rb") as fh:
                    if hashlib.sha256(fh.read()).hexdigest() == h:
                        return "/assets/" + safe_name(fn)
            except OSError:
                continue
    except OSError:
        pass
    return None


def _offload_walk(obj, assets_dir, lookup, missed):
    if isinstance(obj, str):
        if len(obj) < MEDIA_MIN or not obj.startswith("data:"):
            return obj
        m = _DATA_URI_RE.match(obj)
        if not m:
            return obj
        try:
            blob = base64.b64decode(m.group(2), validate=False)
        except Exception:
            return obj
        ref = rev_lookup(blob, assets_dir, lookup)
        if ref:
            return ref
        missed.append(len(obj))
        return obj
    if isinstance(obj, list):
        return [_offload_walk(x, assets_dir, lookup, missed) for x in obj]
    if isinstance(obj, dict):
        return {k: _offload_walk(v, assets_dir, lookup, missed) for k, v in obj.items()}
    return obj


def offload(payload, assets_dir, lookup=None):
    
    missed = []
    out = _offload_walk(payload, assets_dir, lookup, missed)
    return out, missed
