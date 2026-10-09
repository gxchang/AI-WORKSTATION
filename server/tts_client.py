
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


UNIFIED_PREVIEW_TEXT = "您好，今天天气不错，一起去公园玩吧。"


SPEED_MIN, SPEED_MAX, SPEED_STEP, SPEED_DEFAULT = 0.25, 4.0, 0.25, 1.0



MAX_REF_BYTES = 15 * 1024 * 1024



_FATAL_CODES = ("no_key", "auth", "quota", "bad_request",
                "ref_too_large", "missing_file", "bad_reference", "empty_text")

_GENDER = ("男", "女")
_AGE = ("幼儿", "少年", "青年", "中年", "老年")
_DIALECT = ("普通话", "方言", "英文")

_LOCK = threading.RLock()




import media_tools as _mt


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
                    audio_path    TEXT DEFAULT '',                -- 参考音频（storage 下相对路径）
                    preview_path  TEXT DEFAULT '',                -- 统一话术试听样本（相对路径，后台线程补写）
                    preview_text  TEXT DEFAULT '',                -- 生成试听样本所用话术（常量 UNIFIED_PREVIEW_TEXT）
                    preview_error TEXT DEFAULT '',                -- 试听样本最近一次生成失败的中文原因
                    created_at    REAL
                )
                """
            )




            for _sql in (
                "ALTER TABLE voices RENAME COLUMN transcript TO preview_text",
                "ALTER TABLE voices ADD COLUMN preview_error TEXT DEFAULT ''",
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



def _post_speech(cfg, payload):
    import requests as _rq

    base, key, _model = cfg
    if not key:
        raise TtsError("未配置音频接口密钥。请在「服务商设置 → 音频生成」填入 OpenRouter Key。",
                       code="no_key")
    url = f"{base}/audio/speech"
    try:
        r = _rq.post(url, headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                     json=payload, timeout=(10, 120))
    except Exception as e:
        raise TtsError(f"无法连接音频接口 {base}：{type(e).__name__}: {e}", code="unreachable")

    if r.status_code == 200 and r.content:
        return r.content

    body = ""
    try:
        body = r.text[:300]
    except Exception:
        pass
    if r.status_code in (401, 403):
        raise TtsError("音频接口鉴权失败（密钥无效或已过期）。请检查 OpenRouter Key。",
                       code="auth", status=r.status_code)
    if r.status_code == 429:
        raise TtsError("音频接口额度已用尽或请求过于频繁（免费模型每日限量）。请稍后再试。",
                       code="quota", status=429)
    if r.status_code == 402:
        raise TtsError("音频接口需要付费额度（HTTP 402）。", code="quota", status=402)
    if r.status_code == 400:
        raise TtsError(f"音频接口拒绝请求（HTTP 400）：{body}", code="bad_request", status=400)
    raise TtsError(f"音频接口返回 HTTP {r.status_code}：{body}", code="http", status=r.status_code)


def cfg_from_provider():
    
    import server.tts_provider as _p
    return _p.get("base_url"), _p.get("api_key"), _p.get("model")


def synthesize(text, speed=SPEED_DEFAULT, reference_data_url=None, cfg=None):
    
    text = (text or "").strip()
    if not text:
        raise TtsError("请输入要合成的文字。", code="empty_text")
    base, key, model = cfg if cfg else cfg_from_provider()
    speed = _norm_speed(speed)
    payload = {"model": model, "input": text, "response_format": "mp3", "speed": speed}
    if reference_data_url:

        payload["input_references"] = [
            {"type": "input_audio", "input_audio": {"data": reference_data_url}}
        ]
    return _post_speech((base, key, model), payload)


def synthesize_candidate(text, speed=SPEED_DEFAULT, reference_data_url=None, cfg=None):
    
    data = synthesize(text, speed, reference_data_url, cfg=cfg)
    rel = _write_audio(data, "mp3", "tts_out")
    dur = audio_duration(abs_path(rel), text=text, speed=_norm_speed(speed))
    return {"path": rel, "url": f"/api/tts/file/{rel}", "duration": dur}


def generate_preview(reference_data_url, speed=SPEED_DEFAULT, cfg=None):
    
    return synthesize_candidate(UNIFIED_PREVIEW_TEXT, speed=1.0,
                                reference_data_url=reference_data_url, cfg=cfg)



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
        "voice_name": row["voice_name"] or "",
        "ref_path": row["ref_path"] or "",
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


def create_job(text, speed=SPEED_DEFAULT, voice_name="", ref_path="", count=2):
    
    init_audio_db()
    jid = uuid.uuid4().hex[:12]
    now = time.time()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO jobs(id,text,speed,voice_name,ref_path,count,status,candidates,errors,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (jid, text, _norm_speed(speed), voice_name or "", ref_path or "", int(count),
                 "processing", "[]", "[]", now, now),
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


def run_job(jid, count=2):
    
    job = get_job(jid)
    if not job:
        return
    cfg = cfg_from_provider()
    ref_data_url = None
    if job.get("ref_path"):
        try:
            ref_data_url = file_to_data_url(job["ref_path"])
        except TtsError as e:
            update_job(jid, status="failed",
                       errors=[{"index": 0, "message": e.message, "code": e.code}])
            return
    cands, errs = [], []
    for i in range(max(1, int(count))):
        fatal = False
        try:
            c = synthesize_candidate(job["text"], speed=job["speed"],
                                     reference_data_url=ref_data_url, cfg=cfg)
            c["index"] = i
            c["voice_name"] = job.get("voice_name") or ""
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


    _register_candidates_assets(cands)


def _register_candidates_assets(cands):
    
    if not cands:
        return []
    out = []
    try:
        import assets_api.store as _store
        items = []
        for c in cands:
            rel = (c or {}).get("path") or ""
            if not rel:
                continue
            url = (c or {}).get("url") or ("/api/tts/file/" + rel)
            items.append({"name": rel, "url": url, "type": "audio",
                          "origin": _store.ORIGIN_CREATED, "kind": "voice"})
        if items:
            out = _store.register_many(items)
    except Exception as e:
        print("[warn] 音频结果入库失败（不影响任务）:", e, flush=True)
    return out












_TTS_STARTED_JOBS = {}
_TTS_DEDUP_LOCK = threading.Lock()


def start_job(jid, count=2):
    
    with _TTS_DEDUP_LOCK:
        if jid in _TTS_STARTED_JOBS:
            print(f"[tts] job {jid} 已在执行，忽略重复启动（避免重复合成计费）")
            return None
        _TTS_STARTED_JOBS[jid] = time.time()

        _now = time.time()
        for k in [k for k, v in _TTS_STARTED_JOBS.items() if _now - v > 3600]:
            _TTS_STARTED_JOBS.pop(k, None)
    t = threading.Thread(target=run_job, args=(jid, count), name=f"tts-job-{jid}", daemon=True)
    t.start()
    return t



def _row_to_voice(row, with_urls=True):
    keys = row.keys()
    txt = (row["preview_text"] or "") if "preview_text" in keys else ""
    err = (row["preview_error"] or "") if "preview_error" in keys else ""
    d = {
        "id": row["id"],
        "name": row["name"],
        "owner": row["owner"],
        "gender": row["gender"] or "",
        "age": row["age"] or "",
        "dialect": row["dialect"] or "",

        "preview_text": txt,
        "preview_error": err,

        "preview_pending": (not row["preview_path"]) and not err,
        "created_at": row["created_at"],
        "has_audio": bool(row["audio_path"]),
        "has_preview": bool(row["preview_path"]),
    }
    if with_urls:
        d["audio_url"] = f"/api/tts/file/{row['audio_path']}" if row["audio_path"] else ""
        d["preview_url"] = f"/api/tts/file/{row['preview_path']}" if row["preview_path"] else ""
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
              owner="mine", make_preview=False):
    
    init_audio_db()
    data, ext, data_url = parse_audio_payload(reference_raw)
    rel = _write_audio(data, ext, "voices")
    vid = uuid.uuid4().hex[:12]
    name = (name or "").strip() or _auto_name(owner)
    gender = _clean_choice(gender, _GENDER)
    age = _clean_choice(age, _AGE)
    dialect = _clean_choice(dialect, _DIALECT)

    preview_rel, preview_err = "", ""
    if make_preview:
        try:
            pv = synthesize_candidate(UNIFIED_PREVIEW_TEXT, speed=1.0, reference_data_url=data_url)
            preview_rel = pv["path"]
        except TtsError as e:
            preview_err = e.message
        except Exception as e:
            preview_err = f"试听样本生成失败：{e}"

    now = time.time()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO voices(id,name,owner,gender,age,dialect,audio_path,preview_path,"
                "preview_text,preview_error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (vid, name, owner, gender, age, dialect, rel, preview_rel,
                 UNIFIED_PREVIEW_TEXT, preview_err, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_voice(vid), preview_err


def _set_voice_preview(vid, rel="", err=""):
    
    with _LOCK:
        conn = _conn()
        try:
            conn.execute("UPDATE voices SET preview_path=?, preview_error=? WHERE id=?",
                         (rel or "", err or "", vid))
            conn.commit()
        finally:
            conn.close()


def run_preview_job(vid):
    
    row = get_voice_row(vid)
    if not row or not row.get("audio_path"):
        return
    try:
        data_url = file_to_data_url(row["audio_path"])
        pv = synthesize_candidate(UNIFIED_PREVIEW_TEXT, speed=1.0, reference_data_url=data_url)
        if get_voice_row(vid):
            _set_voice_preview(vid, pv["path"], "")
        else:

            try:
                os.remove(abs_path(pv["path"]))
            except OSError:
                pass
    except TtsError as e:
        _set_voice_preview(vid, "", e.message)
    except Exception as e:
        _set_voice_preview(vid, "", f"试听样本生成失败：{type(e).__name__}: {e}")


def start_preview_job(vid):
    
    t = threading.Thread(target=run_preview_job, args=(vid,), name=f"tts-preview-{vid}", daemon=True)
    t.start()
    return t


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
