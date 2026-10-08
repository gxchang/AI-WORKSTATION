

import os
import re
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_ROOT, "storage", "assets")
DIR = os.path.join(_ROOT, "storage", "thumbs")













STEPS = (128, 192, 320, 640, 1280)
DEFAULT_W = 320
_HARD_MAX = 4096
QUALITY = 80
_AGE_GUARD_SEC = 30.0


_RE = re.compile(r"^(.+)\.w(\d{1,4})\.webp$")

_PIL_READY = None


def _pil():
    
    global _PIL_READY
    if _PIL_READY is None:
        try:
            from PIL import Image, ImageOps
            _PIL_READY = (Image, ImageOps)
        except Exception:
            _PIL_READY = False
    return _PIL_READY or None


def thumb_name(src_basename, w):
    
    return "%s.w%d.webp" % (src_basename, int(w))


def thumb_path(src_basename, w):
    return os.path.join(DIR, thumb_name(src_basename, w))


def source_of(thumb_basename):
    
    m = _RE.match(str(thumb_basename or ""))
    return m.group(1) if m else None


def snap_w(w):
    
    try:
        v = int(w)
    except (TypeError, ValueError):
        return DEFAULT_W
    if v <= 0 or v > _HARD_MAX:
        return DEFAULT_W
    return min(STEPS, key=lambda s: (abs(s - v), s))


def ensure(src_full, w, quality=QUALITY):
    
    pil = _pil()
    if not pil or not src_full:
        return None
    w = snap_w(w)
    try:
        base = os.path.basename(src_full)
        if not base:
            return None
        tp = thumb_path(base, w)

        try:
            if os.path.isfile(tp) and os.path.getmtime(tp) >= os.path.getmtime(src_full):
                return tp
        except OSError:
            return None
        Image, ImageOps = pil
        os.makedirs(DIR, exist_ok=True)
        tmp = "%s.tmp%d" % (tp, os.getpid())
        try:
            with Image.open(src_full) as im:
                try:
                    im = ImageOps.exif_transpose(im) or im
                except Exception:
                    pass

                alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
                im = im.convert("RGBA" if alpha else "RGB")
                im.thumbnail((w, w), Image.LANCZOS)
                im.save(tmp, "WEBP", quality=quality, method=4)
            os.replace(tmp, tp)
        except Exception:
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return None
        return tp
    except Exception:
        return None


def sweep_orphans(min_age_sec=_AGE_GUARD_SEC):
    
    removed = []
    try:
        if not os.path.isdir(DIR):
            return removed
        now = time.time()
        for fn in sorted(os.listdir(DIR)):
            src = source_of(fn)
            if src and os.path.isfile(os.path.join(_SRC_DIR, src)):
                continue
            p = os.path.join(DIR, fn)
            try:
                if not os.path.isfile(p):
                    continue
                if now - os.path.getmtime(p) < min_age_sec:
                    continue
                os.remove(p)
                removed.append(fn)
            except OSError:
                pass
    except OSError:
        pass
    return removed


def purge_for(src_basename):
    
    out = []
    base = os.path.basename(str(src_basename or ""))
    if not base:
        return out
    try:
        if not os.path.isdir(DIR):
            return out
        for fn in sorted(os.listdir(DIR)):
            if source_of(fn) != base:
                continue
            p = os.path.join(DIR, fn)
            try:
                os.remove(p)
                out.append(fn)
            except OSError:
                pass
    except OSError:
        pass
    return out


def stats():
    
    n = b = orph = 0
    try:
        for fn in sorted(os.listdir(DIR)):
            p = os.path.join(DIR, fn)
            if not os.path.isfile(p):
                continue
            n += 1
            try:
                b += os.path.getsize(p)
            except OSError:
                pass
            src = source_of(fn)
            if not (src and os.path.isfile(os.path.join(_SRC_DIR, src))):
                orph += 1
    except OSError:
        pass
    return {"count": n, "bytes": b, "orphans": orph}
