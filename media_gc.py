
import os
import re
import sqlite3
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
_APP_DB = os.path.join(_ROOT, "data", "app.db")


ROOTS = {
    "assets": os.path.join(_ROOT, "storage", "assets"),
    "voices": os.path.join(_ROOT, "storage", "voices"),
    "tts_out": os.path.join(_ROOT, "storage", "tts_out"),
    "tts_ref": os.path.join(_ROOT, "storage", "tts_ref"),
}
_AUDIO_KINDS = ("voices", "tts_out", "tts_ref")
_RE_ASSET = re.compile(r"/assets/([^\"'\\\s?#]+)")
_RE_TTSFILE = re.compile(r"/api/tts/file/([^\"'\\\s?#]+)")

_AGE_GUARD_SEC = 30.0
_LOCK = threading.RLock()







_REF_SOURCES = (
    ("sessions",       "id",  ("data",),                                    "blob"),
    ("agent_sessions", "id",  ("data",),                                    "blob"),
    ("tasks",          "tid", ("data",),                                    "blob"),
    ("history",        "id",  ("data",),                                    "blob"),
    ("jobs",           "id",  ("ref_path",),                                "path"),
    ("jobs",           "id",  ("candidates",),                              "blob"),
    ("voices",         "id",  ("audio_path", "preview_path"),               "path"),
    ("assets",         "id",  ("name", "url"),                              "path"),
    ("lv_segments",    "id",  ("images_keys", "images_urls", "audio_urls"), "blob"),
    ("lv_jobs",        "id",  ("assets_json", "shots_json"),                "blob"),
)


_SOURCE_LABEL = {
    "sessions": "会话", "agent_sessions": "智能会话", "tasks": "生成任务", "history": "生成历史",
    "jobs": "音频任务", "voices": "音色库", "assets": "资产库",
    "lv_segments": "长视频分镜", "lv_jobs": "长视频任务",
}

_LABEL_SQL = {
    "sessions":       "SELECT name   FROM sessions       WHERE id=?",
    "agent_sessions": "SELECT name   FROM agent_sessions WHERE id=?",
    "tasks":          "SELECT status FROM tasks          WHERE tid=?",
    "jobs":           "SELECT text   FROM jobs           WHERE id=?",
    "voices":         "SELECT name   FROM voices         WHERE id=?",
    "assets":         "SELECT label  FROM assets         WHERE id=?",
    "lv_jobs":        "SELECT name   FROM lv_jobs        WHERE id=?",
    "lv_segments":    "SELECT job_id FROM lv_segments    WHERE id=?",
}


def _ro(path):
    
    c = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def _base(name):
    
    name = os.path.basename(str(name or ""))
    return re.sub(r"[\x00-\x1f/\\]", "_", name)


def _norm_asset(raw):
    
    if not raw or not isinstance(raw, str):
        return None
    n = _base(raw)
    return n if n and n not in (".", "..") else None


def _norm_audio(raw):
    
    if not raw or not isinstance(raw, str):
        return None
    s = raw.replace("\\", "/")
    i = s.find("/api/tts/file/")
    if i >= 0:
        s = s[i + len("/api/tts/file/"):]
    s = s.lstrip("/")
    s = re.split(r"[\"'?\s]", s)[0]
    parts = [p for p in s.split("/") if p]
    if len(parts) >= 2 and parts[0] in _AUDIO_KINDS:
        n = _base("/".join(parts[1:]))
        return "%s/%s" % (parts[0], n) if n else None
    return None


def _refs_of_value(value, vkind):
    
    out = set()
    if not value or not isinstance(value, str):
        return out
    if vkind == "blob":
        for m in _RE_ASSET.findall(value):
            n = _norm_asset(m)
            if n:
                out.add(("assets", n))
        for m in _RE_TTSFILE.findall(value):
            n = _norm_audio(m)
            if n:
                out.add(("audio", n))
        return out


    a = _norm_audio(value)
    if a:
        out.add(("audio", a))
        return out
    s = value.replace("\\", "/").split("?")[0].split("#")[0]
    parts = [p for p in s.split("/") if p]
    if len(parts) == 1 or (len(parts) == 2 and parts[0] == "assets"):
        n = _norm_asset(parts[-1] if parts else "")
        if n:
            out.add(("assets", n))
    return out


def iter_refs():
    
    if not os.path.isfile(_APP_DB):
        return
    try:
        c = _ro(_APP_DB)
    except Exception as e:
        print(f"[warn] media_gc 打不开 app.db（将保守跳过回收）：{e}")
        return
    try:
        for t, idcol, cols, vkind in _REF_SOURCES:
            try:
                have = {r[1] for r in c.execute("PRAGMA table_info(%s)" % t)}
            except sqlite3.OperationalError:
                continue
            if not have:
                continue
            use = [x for x in cols if x in have]
            if not use:
                continue
            idsexpr = idcol if idcol in have else "NULL"
            try:
                rows = c.execute("SELECT %s AS __id, %s FROM %s"
                                 % (idsexpr, ", ".join(use), t))
            except sqlite3.OperationalError:
                continue
            for r in rows:
                refs = set()
                for col in use:
                    refs |= _refs_of_value(r[col], vkind)
                if refs:
                    yield t, r["__id"], refs
    finally:
        c.close()


def collect_refs():
    
    assets, audio = set(), set()
    try:
        for _t, _rid, refs in iter_refs():
            for kind, key in refs:
                (assets if kind == "assets" else audio).add(key)
    except Exception as e:
        print(f"[warn] media_gc 收集引用失败（将保守跳过回收）：{e}")
    return {"assets": assets, "audio": audio}


def find_references(kind, key, limit=8):
    
    hits, seen = [], set()
    try:
        for t, rid, refs in iter_refs():
            if (kind, key) in refs and (t, rid) not in seen:
                seen.add((t, rid))
                hits.append((t, rid))
                if len(hits) >= limit:
                    break
    except Exception as e:
        print(f"[warn] media_gc 查引用出处失败（{kind}/{key}）：{e}")
    out = []
    try:
        c = _ro(_APP_DB)
        try:
            for t, rid in hits:
                label = ""
                sql = _LABEL_SQL.get(t)
                if sql and rid is not None:
                    try:
                        row = c.execute(sql, (rid,)).fetchone()
                        label = (row[0] or "") if row else ""
                    except sqlite3.OperationalError:
                        label = ""
                out.append({"source": _SOURCE_LABEL.get(t, t), "table": t,
                            "id": rid, "label": str(label)[:60]})
        finally:
            c.close()
    except Exception:
        out = [{"source": _SOURCE_LABEL.get(t, t), "table": t, "id": r, "label": ""}
               for t, r in hits]
    return out


def _resolve(kind, name):
    
    root = ROOTS.get(kind)
    if not root:
        return None
    n = _base(name)
    if not n or n in (".", ".."):
        return None
    p = os.path.join(root, n)
    try:
        if os.path.dirname(os.path.realpath(p)) != os.path.realpath(root):
            return None
    except OSError:
        return None
    return p


def _forget_index(name):
    
    try:
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        import asset_index
        asset_index.forget(name=name)
    except Exception as e:
        print(f"[warn] media_gc 清 asset_index 失败（{name}）：{e}")


def reclaim(pairs, min_age_sec=_AGE_GUARD_SEC, refs=None):
    
    out = {"removed": [], "kept": [], "skipped": [], "errors": []}
    refs = refs or collect_refs()
    now = time.time()
    seen = set()
    with _LOCK:
        for kind, name in (pairs or []):
            n = _base(name)
            if not n:
                continue
            if (kind, n) in seen:
                continue
            seen.add((kind, n))
            key = n if kind == "assets" else "%s/%s" % (kind, n)
            rset = refs["assets"] if kind == "assets" else refs["audio"]
            if key in rset or n in rset:
                out["kept"].append((kind, n))
                continue
            p = _resolve(kind, n)
            if not p:
                out["errors"].append((kind, n, "路径不在白名单目录内"))
                continue
            if not os.path.isfile(p):
                out["skipped"].append((kind, n, "文件不存在"))
                continue
            try:
                if now - os.path.getmtime(p) < min_age_sec:
                    out["skipped"].append((kind, n, "文件过新（可能正在写入）"))
                    continue
                size = os.path.getsize(p)
                os.remove(p)
                out["removed"].append((kind, n, size))
                if kind == "assets":
                    _forget_index(n)
            except Exception as e:
                out["errors"].append((kind, n, f"{type(e).__name__}: {e}"))
    return out


def urls_in(blob):
    
    if not blob or not isinstance(blob, str):
        return []
    return (["/assets/" + m for m in _RE_ASSET.findall(blob)]
            + ["/api/tts/file/" + m for m in _RE_TTSFILE.findall(blob)])


def urls_to_pairs(urls):
    
    pairs, seen = [], set()
    for u in (urls or []):
        if not u or not isinstance(u, str):
            continue
        for raw in _RE_ASSET.findall(u):
            n = _norm_asset(raw)
            if n and ("assets", n) not in seen:
                seen.add(("assets", n))
                pairs.append(("assets", n))
        for raw in _RE_TTSFILE.findall(u):
            a = _norm_audio(raw)
            if a:
                kind, n = a.split("/", 1)
                if (kind, n) not in seen:
                    seen.add((kind, n))
                    pairs.append((kind, n))
    return pairs


def reclaim_urls(urls, refs=None, min_age_sec=_AGE_GUARD_SEC):
    
    return reclaim(urls_to_pairs(urls), refs=refs, min_age_sec=min_age_sec)


def sweep(dry_run=True, min_age_sec=_AGE_GUARD_SEC):
    
    refs = collect_refs()
    report = {}
    for kind, root in ROOTS.items():
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            p = os.path.join(root, fn)
            if not os.path.isfile(p):
                continue
            key = fn if kind == "assets" else "%s/%s" % (kind, fn)
            rset = refs["assets"] if kind == "assets" else refs["audio"]
            if key in rset:
                continue
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            report.setdefault(kind, []).append((fn, size))
    count = sum(len(v) for v in report.values())
    total = sum(s for v in report.values() for _n, s in v)
    if dry_run:
        return {"dry_run": True, "orphans": report, "count": count, "bytes": total}
    res = {"dry_run": False, "removed": [], "count": 0, "bytes": 0}
    for kind, items in report.items():
        r = reclaim([(kind, n) for n, _s in items], min_age_sec=min_age_sec, refs=refs)
        for k, n, sz in r["removed"]:
            res["removed"].append((k, n, sz))
            res["count"] += 1
            res["bytes"] += sz
    return res
