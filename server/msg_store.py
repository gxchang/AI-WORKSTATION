

import json


DENY_KEYS = frozenset({"__proto__", "constructor", "prototype"})


BIG_MSG_BYTES = 256 * 1024


def sanitize_message(m):
    
    if not isinstance(m, dict):
        return None
    out = {}
    for k, v in m.items():
        if not isinstance(k, str) or k in DENY_KEYS:
            continue
        out[k] = v
    return out


def sanitize_messages(msgs):
    
    keep, dropped, big = [], 0, []
    for m in (msgs or []):
        if not isinstance(m, dict) or "type" not in m:
            dropped += 1
            continue
        out = sanitize_message(m)
        keep.append(out)
        try:
            n = len(json.dumps(out, ensure_ascii=False))
        except (TypeError, ValueError):

            n = 0
        if n > BIG_MSG_BYTES:
            big.append((out.get("type"), n))
    return keep, dropped, big




































ID_KEYS = ("videoId", "taskId")


TERMINAL_RANK = {"completed": 4, "failed": 3, "cancelled": 2, "processing": 1, "creating": 0}
_RANK_DEFAULT = 1


def _js_num_str(v):
    
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if v is None:
        return "null"
    return str(v)


def msg_fingerprint(m):
    
    if not isinstance(m, dict):
        return "|"
    ts = "undefined" if "time" not in m else _js_num_str(m.get("time"))
    return ts + "|" + str(m.get("type") or "")


def msg_id(m):
    
    if not isinstance(m, dict):
        return None
    for k in ID_KEYS:
        v = m.get(k)
        if v not in (None, "", 0, False):
            return str(v)
    au = m.get("audio")
    if isinstance(au, dict) and au.get("jobId"):
        return str(au["jobId"])
    return None


def msg_key(m):
    
    i = msg_id(m)
    return ("id:" + i) if i else ("fp:" + msg_fingerprint(m))


def msg_keys(m):
    
    out = ["fp:" + msg_fingerprint(m)]
    i = msg_id(m)
    if i:
        out.insert(0, "id:" + i)
    return out


def is_blank(v):
    
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, tuple, dict, set)):
        return len(v) == 0
    return False


def has_interval(m):
    
    try:
        s, f = m.get("startedAt"), m.get("finishedAt")
        return s is not None and f is not None and float(f) > float(s)
    except (TypeError, ValueError):
        return False


def merge_msg(base, fill):
    
    if not isinstance(base, dict):
        return sanitize_message(fill) if isinstance(fill, dict) else base
    if not isinstance(fill, dict):
        return base
    out = dict(base)
    if TERMINAL_RANK.get(str(fill.get("status") or "").lower(), _RANK_DEFAULT) > \
       TERMINAL_RANK.get(str(base.get("status") or "").lower(), _RANK_DEFAULT):
        out["status"] = fill.get("status")
    if has_interval(fill) and not has_interval(base):
        out["startedAt"], out["finishedAt"] = fill.get("startedAt"), fill.get("finishedAt")
    for k, v in fill.items():
        if k in DENY_KEYS:
            continue
        if k not in out:
            out[k] = v
        elif is_blank(out.get(k)) and not is_blank(v):
            out[k] = v
    return out


def merge_messages(client_msgs, stored_msgs, tombstones=None):
    
    tombs = set(str(x) for x in (tombstones or []))
    out, index = [], {}

    def _register(m, pos):
        for k in msg_keys(m):
            index.setdefault(k, pos)

    for src in (client_msgs, stored_msgs):
        for m in (src or []):
            if not isinstance(m, dict) or "type" not in m:
                continue
            if tombs and msg_fingerprint(m) in tombs:
                continue


            mid = msg_id(m)
            hit = index.get("id:" + mid) if mid else None
            if hit is None:
                cand = index.get("fp:" + msg_fingerprint(m))
                if cand is not None:
                    oid = msg_id(out[cand])


                    if not (oid and mid and oid != mid):
                        hit = cand
            if hit is not None:
                merged = merge_msg(out[hit], m)
                out[hit] = merged
                _register(merged, hit)
            else:
                out.append(m)
                _register(m, len(out) - 1)
    return out
