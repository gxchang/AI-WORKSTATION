
import base64
import binascii
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))





_DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")
_STORAGE = os.path.join(_ROOT, "storage")
_VOICES_DIR = os.path.join(_STORAGE, "voices")
_OUT_DIR = os.path.join(_STORAGE, "tts_out")


_REF_DIR = os.path.join(_STORAGE, "tts_ref")


_PUBLIC_DIRS = ("voices", "tts_out", "tts_ref")


_JOBS_KEEP = 300


SPEED_MIN, SPEED_MAX, SPEED_STEP, SPEED_DEFAULT = 0.25, 4.0, 0.25, 1.0



MAX_REF_BYTES = 15 * 1024 * 1024



_FATAL_CODES = ("no_key", "auth", "quota", "bad_request",
                "ref_too_large", "missing_file", "bad_reference", "empty_text")

_GENDER = ("男", "女")
_AGE = ("幼儿", "少年", "青年", "中年", "老年")
_DIALECT = ("普通话", "方言", "英文")

_LOCK = threading.RLock()




import media_tools as _mt




try:
    from . import tts_adapters as _adapters
except ImportError:
    import tts_adapters as _adapters
try:
    from . import tts_models as _tmodels
except ImportError:
    import tts_models as _tmodels


class TtsError(Exception):
    

    def __init__(self, message, code="error", status=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status



def ensure_dirs():
    for d in (_VOICES_DIR, _OUT_DIR, _REF_DIR):
        os.makedirs(d, exist_ok=True)


def _conn():
    conn = sqlite3.connect(_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_audio_db():
    
    ensure_dirs()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS voices (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    owner         TEXT NOT NULL DEFAULT 'mine',   -- preset | mine
                    gender        TEXT DEFAULT '',
                    age           TEXT DEFAULT '',
                    dialect       TEXT DEFAULT '',
                    audio_path    TEXT DEFAULT '',                -- 参考音频（storage 下相对路径）；试听即播放它
                    preview_path  TEXT DEFAULT '',                -- 已废弃：原统一话术试听样本，现已不再生成/写入
                    preview_text  TEXT DEFAULT '',                -- 已废弃：随 preview_path 一并停用
                    preview_error TEXT DEFAULT '',                -- 已废弃：随 preview_path 一并停用
                    created_at    REAL
                )
                """
            )




            for _sql in (
                "ALTER TABLE voices RENAME COLUMN transcript TO preview_text",
                "ALTER TABLE voices ADD COLUMN preview_error TEXT DEFAULT ''",


                "ALTER TABLE jobs ADD COLUMN model_id TEXT DEFAULT ''",


                "ALTER TABLE jobs ADD COLUMN voice_desc TEXT DEFAULT ''",




                "ALTER TABLE jobs ADD COLUMN preset_voice TEXT DEFAULT ''",
            ):
                try:
                    conn.execute(_sql)
                except sqlite3.OperationalError:
                    pass


            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id         TEXT PRIMARY KEY,
                    text       TEXT NOT NULL,
                    speed      REAL DEFAULT 1.0,
                    voice_name TEXT DEFAULT '',
                    ref_path   TEXT DEFAULT '',                  -- 参考音频副本（storage/tts_ref/）
                    model_id   TEXT DEFAULT '',                  -- 本次用的模型（能力表里的 id，或用户自填名）
                    voice_desc TEXT DEFAULT '',                  -- 专业模式「音色描述」（→ user，不出声）
                    preset_voice TEXT DEFAULT '',                -- 厂商预置音色 id（官方配音；无本地文件）
                    count      INTEGER DEFAULT 2,
                    status     TEXT DEFAULT 'processing',        -- processing | completed | failed
                    candidates TEXT DEFAULT '[]',                 -- JSON 数组
                    errors     TEXT DEFAULT '[]',                 -- JSON 数组
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()



def _clean_choice(v, allowed):
    v = (v or "").strip()
    return v if v in allowed else ""


def _norm_speed(s):
    try:
        s = float(s)
    except (TypeError, ValueError):
        return SPEED_DEFAULT
    if s < SPEED_MIN:
        s = SPEED_MIN
    if s > SPEED_MAX:
        s = SPEED_MAX

    s = round(round(s / SPEED_STEP) * SPEED_STEP, 2)
    return s



_EXT_BY_MIME = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/flac": "flac", "audio/x-flac": "flac",
    "audio/ogg": "ogg", "audio/webm": "webm", "audio/mp4": "m4a",
}
_MIME_BY_EXT = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac",
    "ogg": "audio/ogg", "webm": "audio/webm", "m4a": "audio/mp4",
}


def parse_audio_payload(raw):
    
    if not raw or not isinstance(raw, str):
        raise TtsError("未收到参考音频数据。", code="bad_reference")
    s = raw.strip()
    mime = ""
    if s.startswith("data:"):
        try:
            head, b64 = s.split(",", 1)
        except ValueError:
            raise TtsError("参考音频格式不正确（data URL 缺失逗号）。", code="bad_reference")
        mm = re.match(r"data:([^;]+)", head)
        mime = (mm.group(1) if mm else "").lower()
        payload = b64
    else:
        payload = s


    _b64_max = (MAX_REF_BYTES // 3) * 4
    if len(payload) > _b64_max:

        _mb = len(payload) * 3 / 4 / 1024 / 1024
        raise TtsError(
            f"参考音频过大（约 {_mb:.1f} MB），上限 {MAX_REF_BYTES // 1024 // 1024} MB。"
            "请压缩或裁剪后重试——上游接口对参考音频有硬性体积限制。",
            code="ref_too_large",
        )
    try:
        data = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        raise TtsError("参考音频 base64 解码失败。", code="bad_reference")
    if not data:
        raise TtsError("参考音频为空。", code="bad_reference")
    if len(data) > MAX_REF_BYTES:
        raise TtsError(
            f"参考音频过大（{len(data) / 1024 / 1024:.1f} MB），上限 "
            f"{MAX_REF_BYTES // 1024 // 1024} MB。请压缩或裁剪后重试——上游接口对参考音频有硬性体积限制。",
            code="ref_too_large",
        )
    ext = _EXT_BY_MIME.get(mime, "")
    if not ext:
        ext = "mp3"
    return data, ext, f"data:{_MIME_BY_EXT.get(ext, 'audio/mpeg')};base64,{base64.b64encode(data).decode()}"


def _write_audio(data, ext, subdir):
    
    ensure_dirs()
    name = f"{uuid.uuid4().hex}.{ext}"
    abspath = os.path.join(_STORAGE, subdir, name)
    with open(abspath, "wb") as f:
        f.write(data)
    return f"{subdir}/{name}"


def abs_path(rel):
    
    if not rel:
        return ""
    return os.path.join(_STORAGE, rel.replace("/", os.sep))


def file_to_data_url(rel):
    
    p = abs_path(rel)
    if not p or not os.path.isfile(p):
        raise TtsError(f"参考音频文件不存在：{rel}", code="missing_file")
    ext = os.path.splitext(p)[1].lstrip(".").lower()
    mime = _MIME_BY_EXT.get(ext) or mimetypes.guess_type(p)[0] or "audio/mpeg"
    with open(p, "rb") as f:
        b = f.read()
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def is_public_rel(rel):
    
    if not rel:
        return False
    rel = rel.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return False
    top = rel.split("/", 1)[0]
    return top in _PUBLIC_DIRS



def _ffprobe_duration(path):
    exe = _mt.resolve("ffprobe")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        v = out.stdout.strip()
        if v:
            return round(float(v), 2)
    except Exception:
        return None
    return None


def _estimate_duration(text, speed):
    
    n = len(re.sub(r"\s+", "", text or ""))
    return round(max(1.0, n / 4.5 / max(0.25, speed)), 1)


def audio_duration(path, text="", speed=1.0):
    d = _ffprobe_duration(path)
    if d is not None:
        return d
    return _estimate_duration(text, speed)



def cfg_now():
    
    import server.tts_provider as _p
    st = _p.provider_state()
    p = st["winner"]
    return {
        "provider": p,
        "base_url": _p.get("base_url", p),
        "key": _p.get("api_key", p),
        "models": _p.models(p),
        "state": st,
    }


def resolve_model(cfg, model_id=""):
    
    mid = (model_id or "").strip()
    if mid:
        return mid
    lst = cfg.get("models") or []
    return lst[0] if lst else ""


def _call_upstream(intent):
    
    try:
        return _adapters.synthesize(intent)
    except _adapters.UpstreamError as e:
        raise TtsError(e.message, code=e.code, status=e.status)


def synthesize(text, speed=SPEED_DEFAULT, reference_data_url="", reference_path="",
               model_id="", cfg=None, optimize_text_preview=None, voice_desc="", preset_voice=""):
    
    text = (text or "").strip()
    if not text:
        raise TtsError("请输入要合成的文字。", code="empty_text")
    cfg = cfg or cfg_now()
    mid = resolve_model(cfg, model_id)
    intent = {
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "key": cfg["key"],
        "model": mid,

        "caps": _tmodels.caps_for(mid, cfg["provider"]),
        "text": text,
        "speed": _norm_speed(speed),
        "ref_data_url": reference_data_url or "",
        "ref_path": reference_path or "",

        "optimize_text_preview": optimize_text_preview,

        "voice_desc": voice_desc or "",


        "preset_voice": (preset_voice or "").strip(),
    }
    return _call_upstream(intent)


def optimize_preview(text, model_id="", cfg=None):
    
    text = (text or "").strip()
    if not text:
        return ""
    cfg = cfg or cfg_now()
    mid = resolve_model(cfg, model_id)
    intent = {
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "key": cfg["key"],
        "model": mid,
        "caps": _tmodels.caps_for(mid, cfg["provider"]),
        "text": text,
        "speed": _norm_speed(SPEED_DEFAULT),
        "ref_data_url": "",
        "ref_path": "",
        "optimize_text_preview": True,
    }
    try:
        res = _call_upstream(intent)
    except TtsError:
        return ""
    if isinstance(res, dict):
        return (res.get("text") or "").strip()
    return ""


def synthesize_candidate(text, speed=SPEED_DEFAULT, reference_data_url="", reference_path="",
                         model_id="", cfg=None, optimize_text_preview=None, voice_desc="",
                         preset_voice=""):
    
    res = synthesize(text, speed, reference_data_url, reference_path, model_id,
                     cfg=cfg, optimize_text_preview=optimize_text_preview, voice_desc=voice_desc,
                     preset_voice=preset_voice)
    data = res.get("data") if isinstance(res, dict) else res
    spoken = (res.get("text") or "").strip() if isinstance(res, dict) else ""
    rel = _write_audio(data, "mp3", "tts_out")
    dur = audio_duration(abs_path(rel), text=text, speed=_norm_speed(speed))
    return {"path": rel, "url": f"/api/tts/file/{rel}", "duration": dur,
            "model_id": resolve_model(cfg or cfg_now(), model_id),
            "text": spoken}



def _job_to_dict(row):
    if not row:
        return None

    def _load(s):
        try:
            v = json.loads(s or "[]")
            return v if isinstance(v, list) else []
        except Exception:
            return []

    cands = _load(row["candidates"])
    return {
        "id": row["id"],
        "text": row["text"],
        "speed": row["speed"] if row["speed"] is not None else SPEED_DEFAULT,



        "count": row["count"] if "count" in row.keys() else None,
        "voice_name": row["voice_name"] or "",
        "ref_path": row["ref_path"] or "",


        "model_id": (row["model_id"] if "model_id" in row.keys() else "") or "",

        "voice_desc": (row["voice_desc"] if "voice_desc" in row.keys() else "") or "",

        "preset_voice": (row["preset_voice"] if "preset_voice" in row.keys() else "") or "",
        "status": row["status"] or "processing",
        "candidates": cands,
        "errors": _load(row["errors"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "done": (row["status"] or "") in ("completed", "failed"),
    }


def create_reference(data, ext):
    
    rel = _write_audio(data, ext, "tts_ref")
    _register_reference_asset(rel)
    return rel


def _register_reference_asset(rel):
    
    if not rel:
        return None
    try:
        import assets_api.store as _store
        return _store.register(
            name=rel, url="/api/tts/file/" + rel, type="audio",
            origin=_store.ORIGIN_UPLOADED, kind="voice",
        )
    except Exception as e:
        print("[warn] 参考音频入库失败（不影响生成）:", e, flush=True)
        return None


def create_job(text, speed=SPEED_DEFAULT, voice_name="", ref_path="", count=2, model_id="", voice_desc="",
               preset_voice=""):
    
    init_audio_db()
    jid = uuid.uuid4().hex[:12]
    now = time.time()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO jobs(id,text,speed,voice_name,ref_path,model_id,count,status,candidates,errors,created_at,updated_at,voice_desc,preset_voice) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (jid, text, _norm_speed(speed), voice_name or "", ref_path or "",
                 (model_id or "").strip(), int(count),
                 "processing", "[]", "[]", now, now, (voice_desc or "").strip(),
                 (preset_voice or "").strip()),
            )

            conn.execute(
                "DELETE FROM jobs WHERE id NOT IN "
                "(SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?)",
                (_JOBS_KEEP,),
            )
            conn.commit()
        finally:
            conn.close()
    return get_job(jid)


def update_job(jid, **fields):
    
    if not fields:
        return
    sets, args = [], []
    for k, v in fields.items():
        if k in ("candidates", "errors"):
            v = json.dumps(v or [], ensure_ascii=False)
        sets.append(f"{k}=?")
        args.append(v)
    sets.append("updated_at=?")
    args.append(time.time())
    args.append(jid)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", args)
            conn.commit()
        finally:
            conn.close()


def get_job(jid):
    
    init_audio_db()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            return _job_to_dict(row)
        finally:
            conn.close()


def list_jobs(ids=None, status=None):
    init_audio_db()
    sql = "SELECT * FROM jobs WHERE 1=1"
    args = []
    if ids:
        ph = ",".join("?" for _ in ids)
        sql += f" AND id IN ({ph})"
        args.extend(ids)
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY created_at ASC"
    with _LOCK:
        conn = _conn()
        try:
            return [_job_to_dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()


def run_job(jid, count=2, optimize_text_preview=None, caps=None):
    
    job = get_job(jid)
    if not job:
        return


    model_id = job.get("model_id") or ""
    cfg = cfg_now()
    ref_path = job.get("ref_path") or ""
    ref_data_url = ""
    if ref_path:
        try:
            ref_data_url = file_to_data_url(ref_path)
        except TtsError as e:
            update_job(jid, status="failed",
                       errors=[{"index": 0, "message": e.message, "code": e.code}])
            return
    cands, errs = [], []
    vdesc = job.get("voice_desc") or ""
    pvoice = job.get("preset_voice") or ""
    for i in range(max(1, int(count))):
        fatal = False
        try:
            c = synthesize_candidate(job["text"], speed=job["speed"],
                                     reference_data_url=ref_data_url,
                                     reference_path=ref_path,
                                     model_id=model_id, cfg=cfg,
                                     optimize_text_preview=optimize_text_preview,
                                     voice_desc=vdesc,
                                     preset_voice=pvoice)
            c["index"] = i
            c["voice_name"] = job.get("voice_name") or ""


            c["finishedAt"] = time.time()
            cands.append(c)
        except TtsError as e:
            errs.append({"index": i, "message": e.message, "code": e.code})
            fatal = e.code in _FATAL_CODES
        except Exception as e:
            errs.append({"index": i, "message": f"生成异常：{type(e).__name__}: {e}", "code": "error"})
        update_job(jid, candidates=cands, errors=errs, status="processing")
        if fatal:
            break
    update_job(jid, candidates=cands, errors=errs,
               status=("completed" if cands else "failed"))



    _register_candidates_assets(cands, job, caps)


def _register_candidates_assets(cands, job=None, caps=None):
    
    if not cands:
        return []
    out = []
    try:
        import assets_api.store as _store
        job = job or {}
        items = []
        for c in cands:
            c = c or {}
            rel = c.get("path") or ""
            if not rel:
                continue
            url = c.get("url") or ("/api/tts/file/" + rel)


            raw = {
                "text": job.get("text") or c.get("text") or "",
                "voice": job.get("voice_name") or c.get("voice_name") or "",
                "speed": job.get("speed"),
                "voice_desc": job.get("voice_desc") or "",
                "preset_voice": job.get("preset_voice") or "",
                "count": job.get("count"),
                "duration": c.get("duration"),





                "audio_url": ("/api/tts/file/" + str(job.get("ref_path"))) if job.get("ref_path") else "",
            }



            raw = _store.fit_payload(raw, (caps or {}).get("caps"), (caps or {}).get("param_cap"))
            raw = {k: v for k, v in raw.items() if v not in (None, "")}
            items.append({"name": rel, "url": url, "type": "audio",
                          "origin": _store.ORIGIN_CREATED, "kind": "voice",
                          "meta": _store.build_provenance(
                              payload=raw, model=job.get("model_id") or c.get("model_id"))})
        if items:
            out = _store.register_many(items)
    except Exception as e:
        print("[warn] 音频结果入库失败（不影响任务）:", e, flush=True)
    return out












_TTS_STARTED_JOBS = {}
_TTS_DEDUP_LOCK = threading.Lock()


def start_job(jid, count=2, optimize_text_preview=None, caps=None):
    
    with _TTS_DEDUP_LOCK:
        if jid in _TTS_STARTED_JOBS:
            print(f"[tts] job {jid} 已在执行，忽略重复启动（避免重复合成计费）")
            return None
        _TTS_STARTED_JOBS[jid] = time.time()

        _now = time.time()
        for k in [k for k, v in _TTS_STARTED_JOBS.items() if _now - v > 3600]:
            _TTS_STARTED_JOBS.pop(k, None)
    t = threading.Thread(target=run_job, args=(jid, count, optimize_text_preview, caps),
                         name=f"tts-job-{jid}", daemon=True)
    t.start()
    return t



def _row_to_voice(row, with_urls=True):
    d = {
        "id": row["id"],
        "name": row["name"],
        "owner": row["owner"],
        "gender": row["gender"] or "",
        "age": row["age"] or "",
        "dialect": row["dialect"] or "",
        "created_at": row["created_at"],
        "has_audio": bool(row["audio_path"]),
    }
    if with_urls:
        d["audio_url"] = f"/api/tts/file/{row['audio_path']}" if row["audio_path"] else ""
    return d


def list_voices(owner=None, gender=None, age=None, dialect=None):
    init_audio_db()
    sql = "SELECT * FROM voices WHERE 1=1"
    args = []
    if owner in ("preset", "mine"):
        sql += " AND owner=?"
        args.append(owner)
    if gender in _GENDER:
        sql += " AND gender=?"
        args.append(gender)
    if age in _AGE:
        sql += " AND age=?"
        args.append(age)
    if dialect in _DIALECT:
        sql += " AND dialect=?"
        args.append(dialect)
    sql += " ORDER BY created_at ASC, name ASC"
    with _LOCK:
        conn = _conn()
        try:
            rows = conn.execute(sql, args).fetchall()
            return [_row_to_voice(r) for r in rows]
        finally:
            conn.close()


def get_voice(vid):
    init_audio_db()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT * FROM voices WHERE id=?", (vid,)).fetchone()
            return _row_to_voice(row) if row else None
        finally:
            conn.close()


def get_voice_row(vid):
    
    init_audio_db()
    with _LOCK:
        conn = _conn()
        try:
            row = conn.execute("SELECT * FROM voices WHERE id=?", (vid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def _auto_name(owner):
    with _LOCK:
        conn = _conn()
        try:
            n = conn.execute("SELECT COUNT(*) AS c FROM voices WHERE owner=?", (owner,)).fetchone()["c"]
        finally:
            conn.close()
    return f"我的音色 {n + 1}" if owner == "mine" else f"预装音色 {n + 1}"


def add_voice(reference_raw, name="", gender="", age="", dialect="",
              owner="mine"):
    
    init_audio_db()
    data, ext, data_url = parse_audio_payload(reference_raw)
    rel = _write_audio(data, ext, "voices")
    vid = uuid.uuid4().hex[:12]
    name = (name or "").strip() or _auto_name(owner)
    gender = _clean_choice(gender, _GENDER)
    age = _clean_choice(age, _AGE)
    dialect = _clean_choice(dialect, _DIALECT)

    now = time.time()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO voices(id,name,owner,gender,age,dialect,audio_path,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (vid, name, owner, gender, age, dialect, rel, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_voice(vid)


def update_voice(vid, name=None, gender=None, age=None, dialect=None):
    
    init_audio_db()
    row = get_voice_row(vid)
    if not row:
        return None
    sets, args = [], []
    if name is not None:
        nm = (name or "").strip()
        if not nm:
            raise TtsError("音色名称不能为空。", code="bad_name")
        sets.append("name=?")
        args.append(nm)
    if gender is not None:
        sets.append("gender=?")
        args.append(_clean_choice(gender, _GENDER))
    if age is not None:
        sets.append("age=?")
        args.append(_clean_choice(age, _AGE))
    if dialect is not None:
        sets.append("dialect=?")
        args.append(_clean_choice(dialect, _DIALECT))
    if sets:
        args.append(vid)
        with _LOCK:
            conn = _conn()
            try:
                conn.execute(f"UPDATE voices SET {', '.join(sets)} WHERE id=?", args)
                conn.commit()
            finally:
                conn.close()
    return get_voice(vid)


def delete_voice(vid):
    
    init_audio_db()
    row = get_voice_row(vid)
    if not row:
        return False
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("DELETE FROM voices WHERE id=?", (vid,))
            conn.commit()
        finally:
            conn.close()
    return True


def count_voices(owner=None):
    init_audio_db()
    sql = "SELECT COUNT(*) AS c FROM voices"
    args = []
    if owner in ("preset", "mine"):
        sql += " WHERE owner=?"
        args.append(owner)
    with _LOCK:
        conn = _conn()
        try:
            return conn.execute(sql, args).fetchone()["c"]
        finally:
            conn.close()
