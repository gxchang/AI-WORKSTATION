

import base64
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import uuid
import re
import requests
import sqlite3
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from flask import Flask, request



_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, static_folder=None)



app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024



def _load_env():
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
    except Exception as e:
        print(f"[warn] 读取 .env 失败：{e}")


_load_env()










import server.provider as _provider
import server.ark_provider as _arkprov
import server.ms_provider as _msprov
import server.imgen as _imgen
import media_gc as _mgc
import server.payload_media as _pm
import server.msg_store as _msgst
import assets_api.store as _assets_store

AGNES_API_KEY = _provider.get("api_key")
AGNES_BASE_URL = _provider.get("base_url")
def _cfg_key():
    
    return _provider.get("api_key")
def _cfg_base():
    
    return _provider.get("base_url")
def _cfg_poll():
    
    return _provider.get("poll_endpoint")
DEFAULT_MODEL = (_provider.get("video_models") or ["agnes-video-2.5-flash"])[0]


_BOOT_ID = f"{int(time.time()*1000):x}-{os.getpid()}"






def _build_agnes_session():
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "HEAD", "PUT", "DELETE"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"Connection": "keep-alive"})
    return s


_AGNES_SESSION = _build_agnes_session()


def _build_no_retry_session():
    
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"Connection": "keep-alive"})
    return s


_NO_RETRY_SESSION = _build_no_retry_session()


def _llm_chat_completions(messages, tools=None, tool_choice="auto",
                          model=None, temperature=0.2,
                          max_tokens=4096, timeout=(10, 300), extra=None,
                          use_case="assistant", thinking=True):
    
    try:
        import server.llm as _llm
    except Exception as e:
        return None, f"LLM 分发层不可用：{e}"
    try:
        r = _llm.chat(use_case, messages, model=model, tools=tools,
                      tool_choice=tool_choice, stream=False, thinking=thinking,
                      max_tokens=max_tokens, temperature=temperature, timeout=timeout)
    except Exception as e:
        return None, f"请求 LLM 失败：{type(e).__name__}: {e}"
    if r.status_code != 200:
        try:
            detail = r.json()
            if isinstance(detail, dict):
                msg = detail.get("detail") or (detail.get("error") or {}).get("message") or detail
            else:
                msg = detail
        except Exception:
            msg = r.content.decode("utf-8", errors="replace")[:300]
        return None, f"LLM 拒绝请求（{r.status_code}）：{msg}"
    try:
        return r.json(), ""
    except Exception as e:
        return None, f"无法解析 LLM 响应：{e}"





@app.after_request
def _add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Max-Age"] = "86400"

    ct = (resp.headers.get("Content-Type") or "").lower()
    if "html" in ct or "css" in ct or "javascript" in ct:
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp




ASSETS_DIR = os.path.join(_ROOT, "storage", "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)


HISTORY_FILE = os.path.join(_ROOT, "data", "history.json")


PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


IMG_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}
AUD_EXTS = {"mp3", "wav", "m4a", "aac", "ogg", "flac"}
VID_EXTS = {"mp4", "mov", "webm", "mkv"}
ALLOWED_EXTS = IMG_EXTS | AUD_EXTS | VID_EXTS



MODEL_LIMITS = {
    "agnes-video-2.5-flash": {
        "label": "Agnes 2.5 Video Flash",
        "sizes": ["720P"],
        "min_seconds": 4, "max_seconds": 12,
        "max_images": 5,
        "max_audios": 3,
        "allow_video": False,
        "note": "Flash 专属限制：参考图最多 5 张、参考音频最多 3 段、不支持参考视频、size 固定 720P。",
    },
    "agnes-video-2.5": {
        "label": "Agnes 2.5 Video",
        "sizes": ["720P", "1080P", "1K", "2K"],
        "min_seconds": 4, "max_seconds": 12,
        "max_images": 8,
        "max_audios": 3,
        "allow_video": True,
        "note": "标准版：参考媒体官方上限——图片 8 张 / 音频 3 段 / 视频 1 个（总文件 ≤12）；图片前 5 张免费。",
    },
}

FRONTEND_DIR = _ROOT


def _public_base():
    
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    try:
        return request.host_url.rstrip("/")
    except RuntimeError:
        return ""


def _to_b64_if_local(url):
    
    return _pm.to_data_uri(url, ASSETS_DIR, _public_base())


def _safe_name(name: str) -> str:
    
    return _pm.safe_name(name)
















def _asset_lookup_by_hash(h):
    
    try:
        import asset_index
        hit = asset_index.find_by_hash(h)
        if hit:
            return hit.get("url") or hit.get("name")
    except Exception:
        pass
    return None


def _deinline_payload_media(payload):
    
    out, missed = _pm.offload(payload, ASSETS_DIR, _asset_lookup_by_hash)
    if missed:
        print("[warn] tasks payload 里有 %d 处 base64 内联媒体（共 %.0fKB）在 storage/assets "
              "找不到同一份内容，已原样保留（不丢数据）。请在源头传站内引用而非内联。"
              % (len(missed), sum(missed) / 1024))
    return out


def _inline_payload_media(payload, upstream=None):
    
    return _pm.inline(payload, ASSETS_DIR, _public_base(), _imgen.input_caps(upstream))












DB_FILE = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")



_DB_LOCK = threading.RLock()
_DB_READY = False


def _db_conn():


    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _DB_LOCK:
        conn = _db_conn()
        try:




            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as e:
                print("[warn] 主库切 WAL 失败（不影响功能，仍可用回滚日志模式）：%s" % e)
            conn.execute("CREATE TABLE IF NOT EXISTS tasks (tid TEXT PRIMARY KEY, status TEXT, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, name TEXT, created_at INTEGER, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, data TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


            conn.execute("CREATE TABLE IF NOT EXISTS agent_sessions (id TEXT PRIMARY KEY, name TEXT, created_at INTEGER, data TEXT)")

            conn.execute("CREATE TABLE IF NOT EXISTS deleted_sessions "
                         "(id TEXT PRIMARY KEY, deleted_at INTEGER)")
            conn.commit()
        finally:
            conn.close()


def _tombstoned_session_ids(conn):
    
    try:
        return {r[0] for r in conn.execute("SELECT id FROM deleted_sessions")}
    except sqlite3.Error:
        return set()


def _server_tombstones():
    
    _ensure_db()
    try:
        conn = _db_conn()
        try:
            return [r[0] for r in conn.execute("SELECT id FROM deleted_sessions")]
        finally:
            conn.close()
    except Exception:
        return []


def _mark_session_deleted(conn, ids):
    
    now = int(time.time() * 1000)
    for sid in (ids or []):
        if not sid:
            continue
        conn.execute(
            "INSERT INTO deleted_sessions(id, deleted_at) VALUES(?,?) "
            "ON CONFLICT(id) DO UPDATE SET deleted_at=excluded.deleted_at", (sid, now))


def _ensure_db():
    global _DB_READY
    if not _DB_READY:
        _init_db()
        _DB_READY = True



_ensure_db()


def _table_empty(table):
    with _DB_LOCK:
        conn = _db_conn()
        try:
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        finally:
            conn.close()
    return n == 0


def _migrate_legacy_json():
    

    if os.path.isfile(TASKS_FILE) and _table_empty("tasks"):
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f) or {}
            _save_tasks({"tasks": d.get("tasks", {}) if isinstance(d, dict) else {}})
            os.rename(TASKS_FILE, TASKS_FILE + ".migrated.bak")
            print("[migrate] tasks.json 已导入 SQLite")
        except Exception as e:
            print(f"[migrate] tasks 失败：{e}")

    if os.path.isfile(SESSIONS_FILE) and _table_empty("sessions"):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f) or {}
            _save_sessions({
                "sessions": d.get("sessions", []) if isinstance(d, dict) else [],
                "currentId": d.get("currentId") if isinstance(d, dict) else None,
            })
            os.rename(SESSIONS_FILE, SESSIONS_FILE + ".migrated.bak")
            print("[migrate] sessions.json 已导入 SQLite")
        except Exception as e:
            print(f"[migrate] sessions 失败：{e}")

    if os.path.isfile(HISTORY_FILE) and _table_empty("history"):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                rows = json.load(f) or []
            _save_history(rows)
            os.rename(HISTORY_FILE, HISTORY_FILE + ".migrated.bak")
            print("[migrate] history.json 已导入 SQLite")
        except Exception as e:
            print(f"[migrate] history 失败：{e}")


def _load_history():
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT data FROM history").fetchall()
        finally:
            conn.close()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["data"]))
        except Exception:
            pass
    return out


def _save_history(rows):
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            conn.execute("DELETE FROM history")
            for i, row in enumerate(rows or []):
                rid = (row.get("id") if isinstance(row, dict) else None) or f"h{i}"
                conn.execute("INSERT INTO history(id, data) VALUES(?,?)",
                             (str(rid), json.dumps(row, ensure_ascii=False)))
            conn.commit()
        finally:
            conn.close()









TASKS_FILE = os.path.join(_ROOT, "data", "tasks.json")
_TASKS_LOCK = _DB_LOCK


def _load_tasks():
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT tid, data FROM tasks").fetchall()
        finally:
            conn.close()
    tasks = {}
    for r in rows:
        try:
            tasks[r["tid"]] = json.loads(r["data"])
        except Exception:
            pass
    return {"tasks": tasks}


def _save_tasks(data):
    _ensure_db()
    tasks = (data or {}).get("tasks", {})
    with _DB_LOCK:
        conn = _db_conn()
        try:
            for tid, rec in tasks.items():
                status = rec.get("status") if isinstance(rec, dict) else None
                conn.execute(
                    "INSERT INTO tasks(tid, status, data) VALUES(?,?,?) "
                    "ON CONFLICT(tid) DO UPDATE SET status=excluded.status, data=excluded.data",
                    (tid, status, json.dumps(rec, ensure_ascii=False)),
                )
            conn.commit()
        finally:
            conn.close()


def _create_task(kind, model, payload, video_id=None, media_hint=None, session_id=None, upstream=None,
                 ratio=None, user_params=None, patch_mask=False):
    


    payload = _deinline_payload_media(payload)
    tid = uuid.uuid4().hex[:16]
    record = {
        "id": tid,
        "kind": kind,
        "model": model,
        "media": media_hint or ("image" if kind == "image" else "video"),
        "video_id": video_id,
        "session_id": session_id,
        "upstream": upstream,
        "status": "processing",
        "video_url": None,
        "image_urls": None,
        "error": None,
        "payload": payload,



        **({"ratio": str(ratio).strip()} if ratio and str(ratio).strip() else {}),






        **({"user_params": user_params} if isinstance(user_params, dict) and user_params else {}),



        **({"patch_mask": True} if patch_mask else {}),
        "created_at": time.time(),








        "submitted_at": None,
        "updated_at": time.time(),
        "finished_at": None,
    }
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            conn.execute("INSERT INTO tasks(tid, status, data) VALUES(?,?,?)",
                         (tid, record["status"], json.dumps(record, ensure_ascii=False)))
            conn.commit()
        finally:
            conn.close()
    return tid, record


def _strip_patch_mask(rec):
    
    if not rec.get("patch_mask"):
        return
    p = rec.get("payload")
    if not isinstance(p, dict):
        return
    try:
        import server.imgen as _im
        keys = ["images", _im.media_key(rec.get("upstream"))]
    except Exception:
        keys = ["images", "image", "image_url"]
    for k in dict.fromkeys(keys):
        imgs = p.get(k)
        if isinstance(imgs, list) and len(imgs) > 1:
            p[k] = [imgs[0]]


def _update_task(tid, **fields):
    
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT data FROM tasks WHERE tid=?", (tid,)).fetchone()
            if not row:
                return None
            rec = json.loads(row["data"])
            rec.update(fields)
            rec["updated_at"] = time.time()
            if fields.get("status") in ("completed", "failed"):
                rec["finished_at"] = rec.get("finished_at") or time.time()



            if fields.get("status") == "completed":
                _strip_patch_mask(rec)
            conn.execute("UPDATE tasks SET status=?, data=? WHERE tid=?",
                         (rec.get("status"), json.dumps(rec, ensure_ascii=False), tid))
            conn.commit()
        finally:
            conn.close()
    return rec


def _query_agnes_video(video_id, model_name):
    
    try:
        resp = _AGNES_SESSION.get(
            _cfg_poll(),
            params={"video_id": video_id, "model_name": model_name},
            headers={"Authorization": f"Bearer {_cfg_key()}"},
            timeout=30,
        )
    except requests.RequestException as e:
        return "processing", None, None
    try:
        body = resp.json()
    except Exception:
        return "processing", None, None
    status = body.get("status") or body.get("task_status") or "processing"
    video_url = (
        (body.get("metadata") or {}).get("url")
        or body.get("video_url")
        or body.get("url")
        or (body.get("result") or {}).get("video_url")
    )
    err_msg = body.get("error") if isinstance(body.get("error"), (str, dict)) else None
    return status, video_url, err_msg


def _err_text(resp):
    
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text
    if isinstance(detail, dict):
        err = detail.get("error")
        return (detail.get("detail")
                or (err.get("message") if isinstance(err, dict) else err)
                or str(detail))
    return str(detail)














_MS_POLL_INTERVAL = 4


def _ms_create(base, key, label, wire):
    
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}




    _refs = wire.get("image_url")
    print(f"[ms-submit] {time.strftime('%H:%M:%S')} POST {base}/images/generations "
          f"model={wire.get('model')} n={wire.get('n', '(unset)')} "
          f"refs={(len(_refs) if isinstance(_refs, list) else (1 if _refs else 0))} "
          f"keys={sorted(wire.keys())}")

    try:
        r = _NO_RETRY_SESSION.post(
            f"{base}/images/generations",
            headers=dict(hdr, **{"X-ModelScope-Async-Mode": "true"}),
            json=wire,
            timeout=(15, 3600),
        )
    except requests.RequestException as e:





        if isinstance(e, requests.exceptions.ConnectionError):
            return None, f"[可重试] 连接失败（请求未送达上游）：{type(e).__name__}: {e}"
        return None, (f"[不可重试] 提交读超时（请求已送达上游，任务可能已创建、可能已计费；"
                      f"不自动重试，请到魔搭控制台核对后再决定是否重试）：{type(e).__name__}: {e}")
    if r.status_code != 200:
        _t = _err_text(r)
        if _is_upstream_busy(r.status_code, _t):


            return None, f"[上游忙] {label} 暂时无法接受新任务（HTTP {r.status_code}）：{_t}"
        return None, f"{label} 拒绝请求（{r.status_code}）：{_t}"
    try:
        tid = (r.json() or {}).get("task_id")
    except Exception:
        tid = None
    if not tid:
        return None, f"{label} 未返回 task_id，无法轮询任务状态"
    print(f"[ms-submit] {time.strftime('%H:%M:%S')} 上游任务已创建 task_id={tid}")
    return tid, None


def _ms_wait(base, key, label, task_id, local_tid=None):
    
    hs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
          "X-ModelScope-Task-Type": "image_generation"}






    fail_streak = 0
    while True:
        if _is_task_canceled(local_tid):
            return False, None, "任务已被用户取消（服务端已停止查询）"
        time.sleep(_MS_POLL_INTERVAL if fail_streak == 0
                   else min(30, 4 * (2 ** min(fail_streak - 1, 4))))
        try:
            q = _AGNES_SESSION.get(f"{base}/tasks/{task_id}", headers=hs, timeout=(10, 120))
        except requests.RequestException as e:
            fail_streak += 1
            if fail_streak == 1 or fail_streak % 10 == 0:
                print(f"[ms-wait] 第 {fail_streak} 次查状态网络异常（任务仍在后台，继续等）："
                      f"{type(e).__name__}: {e}")
            continue
        if q.status_code == 404:

            return False, None, f"{label} 任务在上游不存在（已被清理或失效），无法继续等待"
        if q.status_code != 200:

            fail_streak += 1
            if fail_streak == 1 or fail_streak % 10 == 0:
                print(f"[ms-wait] 第 {fail_streak} 次查状态非 200（HTTP {q.status_code}，"
                      f"任务仍在后台，继续等）")
            continue
        fail_streak = 0
        try:
            d = q.json() or {}
        except Exception:
            continue
        st = d.get("task_status")
        if st == "SUCCEED":
            urls = [u for u in (d.get("output_images") or []) if u]
            if not urls:
                return False, None, "生图成功，但服务端未返回图片地址，请重试"



            print(f"[ms-result] {time.strftime('%H:%M:%S')} task_id={task_id} "
                  f"output_images count={len(urls)}（采用第 1 张）")


            urls = urls[:1]


            return True, [_persist_generated_image(u, prefix="ms") for u in urls], None
        if st == "FAILED":
            return False, None, f"{label} 生成失败：{json.dumps(d, ensure_ascii=False)[:240]}"





def _mark_submitted(local_tid):
    
    if not local_tid:
        return
    try:
        rec = _get_task(local_tid) or {}
        if rec.get("submitted_at"):
            return
        _update_task(local_tid, submitted_at=time.time())
    except Exception as e:
        print(f"[warn] submitted_at 落库失败（不影响提交与生成）：{e}")













_MAX_INFLIGHT_IMG = 4
_IMG_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_INFLIGHT_IMG, thread_name_prefix="img-run")




_IMG_INFLIGHT = set()


_BUSY_PAT = re.compile(
    r"concurren|并发|排队|count_limit|too many|rate[ _-]?limit|throttl|capacity|system is busy|"
    r"busy|繁忙|稍后再试|超出.*限制", re.I)


def _is_upstream_busy(status_code=None, text=None):
    
    try:
        if int(status_code) == 429:
            return True
    except Exception:
        pass
    try:
        return bool(text) and bool(_BUSY_PAT.search(str(text)))
    except Exception:
        return False


def _clear_submitted(local_tid):
    
    if not local_tid:
        return
    try:
        rec = _get_task(local_tid) or {}
        if not rec.get("submitted_at"):
            return
        _update_task(local_tid, submitted_at=None, busy_at=time.time(),
                     busy_count=int(rec.get("busy_count") or 0) + 1,
                     busy_reason=rec.get("busy_reason"))
    except Exception as e:
        print(f"[warn] submitted_at 回滚失败（不影响后续重提）：{e}")


def _task_stage(rec):
    
    if not isinstance(rec, dict):
        return "queued"
    if rec.get("submitted_at"):
        return "generating"
    st = rec.get("status")
    if st in ("completed", "failed", "cancelled"):
        return st
    if rec.get("busy_at"):
        return "busy"
    return "queued"


def _queue_depth(tid):
    
    try:
        with _TASKS_LOCK:
            d = _load_tasks()
        cur = (d.get("tasks", {}) or {}).get(tid) or {}
        if cur.get("submitted_at"):
            return 0
        pend = sorted(
            ((r.get("created_at") or 0), t)
            for t, r in (d.get("tasks", {}) or {}).items()
            if r.get("status") == "processing" and not r.get("submitted_at")
        )
        for i, (_, t) in enumerate(pend):
            if t == tid:
                return i
    except Exception:
        return 0
    return 0


def _submit_image(payload, upstream=None, ms_task_id=None, on_submitted=None, local_tid=None):
    
    up = str(upstream or "").lower()
    if up == "ark":
        base, key, label = _arkprov.get("base_url"), _arkprov.get("api_key"), "方舟"
    elif up == "ms":
        base, key, label = _msprov.get("base_url"), _msprov.get("api_key"), "魔搭"
    else:
        base, key, label = _cfg_base(), _cfg_key(), "Agnes"



    wire = _inline_payload_media(payload, up)

    if up == "ms":

        if _is_task_canceled(local_tid):
            return False, None, "任务已被用户取消（服务端未提交）", None

        if not ms_task_id:



            _mark_submitted(local_tid)
            ms_task_id, err = _ms_create(base, key, label, wire)
            if not ms_task_id:

                if err and err.startswith("[上游忙]"):
                    _clear_submitted(local_tid)
                return False, None, err, None





            if on_submitted:
                try:
                    on_submitted(ms_task_id)
                except Exception as e:
                    print(f"[warn] on_submitted 落库失败（task_id 已拿到，轮询继续）：{e}")
        ok, urls, err = _ms_wait(base, key, label, ms_task_id, local_tid=local_tid)
        return ok, urls, err, ms_task_id





    _mark_submitted(local_tid)
    try:
        resp = _NO_RETRY_SESSION.post(
            f"{base}/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=wire,




            timeout=(15, 3600),
        )
    except requests.RequestException as e:


        if isinstance(e, requests.exceptions.ConnectionError):
            return False, None, f"[可重试] 连接失败（请求未送达上游）：{type(e).__name__}: {e}", None
        return False, None, (f"[不可重试] 提交读超时（上游可能已在生成，重试会重复计费；"
                             f"请稍后重试）：{type(e).__name__}: {e}"), None
    if resp.status_code != 200:
        msg = _err_text(resp)
        if _is_upstream_busy(resp.status_code, msg):

            _clear_submitted(local_tid)
            return False, None, (f"[上游忙] {label} 暂时无法接受新任务"
                                 f"（HTTP {resp.status_code}）：{msg}"), None
        if resp.status_code >= 500 and isinstance(msg, str) and "internal" in msg.lower():
            hint = f"{label} 服务返回内部错误"
            imgs = (payload.get("extra_body") or {}).get("image") or payload.get("image")
            if imgs:
                hint += "。常见原因：参考图无效、过小或格式不被支持，建议换一张 ≥ 256×256 的 PNG/JPG 重新尝试。"
            return False, None, hint, None
        return False, None, f"{label} 拒绝请求（{resp.status_code}）：{msg}", None
    body = resp.json()
    data_list = body.get("data") or []
    items = [item.get("url") or (("data:image/png;base64," + item["b64_json"]) if item.get("b64_json") else None) for item in data_list if item]
    items = [u for u in items if u]
    if not items:
        return False, None, "生图成功，但服务端未返回图片地址，请重试", None






    items = [_persist_generated_image(u, prefix=("ark" if up == "ark" else "agnes")) for u in items]
    return True, items, None, None















_PERSIST_MAX_BYTES = 64 * 1024 * 1024
_PERSIST_TIMEOUT = (10, 600)


def _persist_generated_image(url, prefix="ark"):
    
    if not url or not isinstance(url, str):
        return url
    u = url.strip()

    if u.startswith("/assets/"):
        return u
    if PUBLIC_BASE_URL and u.startswith(PUBLIC_BASE_URL + "/assets/"):
        return u

    tmp = None
    try:
        if u.startswith("data:"):
            head, _, b64 = u.partition(",")
            if not head.startswith("data:image/") or ";base64" not in head:
                return url
            blob = base64.b64decode(b64, validate=False)
            ext = (head[5:].split(";", 1)[0].split("/")[-1] or "png").lower()
            ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(ext, ext)
            if ext not in IMG_EXTS:
                ext = "png"
        else:
            if not re.match(r"^https?://", u, re.I):
                return url
            r = _AGNES_SESSION.get(u, stream=True, timeout=_PERSIST_TIMEOUT)
            if r.status_code != 200:
                print(f"[warn] 生成结果落盘失败（HTTP {r.status_code}）：{u[:120]}")
                return url
            cl = r.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > _PERSIST_MAX_BYTES:
                print(f"[warn] 生成结果过大（{cl} 字节）放弃落盘：{u[:120]}")
                return url
            chunks, size = [], 0
            for c in r.iter_content(65536):
                if not c:
                    continue
                size += len(c)
                if size > _PERSIST_MAX_BYTES:
                    print(f"[warn] 生成结果超过 {_PERSIST_MAX_BYTES} 字节放弃落盘：{u[:120]}")
                    return url
                chunks.append(c)
            blob = b"".join(chunks)
            ext, _mime = _infer_ext_and_mime(u, r.headers.get("Content-Type"))
            if ext not in IMG_EXTS:
                ext = "png"
        if not blob:
            return url

        name = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
        full = os.path.join(ASSETS_DIR, name)
        tmp = full + ".part"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, full)
        tmp = None
    except Exception as e:
        print(f"[warn] 生成结果落盘异常（{type(e).__name__}: {e}）：{u[:120]}")
        return url
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    local = f"/assets/{name}"
    if PUBLIC_BASE_URL:
        local = f"{PUBLIC_BASE_URL}/assets/{name}"
    print(f"[info] 生成结果已落盘：{local}（{len(blob)} 字节）")
    return local


_VID_EXTS = {"mp4", "mov", "webm", "mkv"}
_PERSIST_VIDEO_MAX_BYTES = 256 * 1024 * 1024
_PERSIST_VIDEO_TIMEOUT = (10, 600)


def _persist_generated_video(url, prefix="vid"):
    
    if not url or not isinstance(url, str):
        return url
    u = url.strip()
    if u.startswith("/assets/"):
        return u
    if PUBLIC_BASE_URL and u.startswith(PUBLIC_BASE_URL + "/assets/"):
        return u
    if not re.match(r"^https?://", u, re.I):
        return url
    tmp = None
    try:
        r = _AGNES_SESSION.get(u, stream=True, timeout=_PERSIST_VIDEO_TIMEOUT)
        if r.status_code != 200:
            print(f"[warn] 生成视频落盘失败（HTTP {r.status_code}）：{u[:120]}")
            return url
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > _PERSIST_VIDEO_MAX_BYTES:
            print(f"[warn] 生成视频过大（{cl} 字节）放弃落盘：{u[:120]}")
            return url
        chunks, size = [], 0
        for c in r.iter_content(1 << 16):
            if not c:
                continue
            size += len(c)
            if size > _PERSIST_VIDEO_MAX_BYTES:
                print(f"[warn] 生成视频超过落盘上限放弃：{u[:120]}")
                return url
            chunks.append(c)
        blob = b"".join(chunks)
        if not blob:
            return url
        ext, _mime = _infer_ext_and_mime(u, r.headers.get("Content-Type"))
        if ext not in _VID_EXTS:
            ext = "mp4"
        name = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
        full = os.path.join(ASSETS_DIR, name)
        tmp = full + ".part"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, full)
        tmp = None
    except Exception as e:
        print(f"[warn] 生成视频落盘异常（{type(e).__name__}: {e}）：{u[:120]}")
        return url
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    local = f"/assets/{name}"
    if PUBLIC_BASE_URL:
        local = f"{PUBLIC_BASE_URL}/assets/{name}"
    print(f"[info] 生成视频已落盘：{local}（{len(blob)} 字节）")
    return local



VIDEO_PARAM_CAP = {"size": "sizes"}

VIDEO_NON_PARAM_CAPS = frozenset({"label", "note", "min_seconds", "max_seconds",
                                  "max_images", "max_audios", "allow_video"})


def _video_param_cap():
    
    return dict(VIDEO_PARAM_CAP)


def _video_caps_for(model):
    
    m = str(model or "").strip()
    if not m:
        return {}
    return MODEL_LIMITS.get(m) or getattr(_arkprov, "VIDEO_MODEL_LIMITS", {}).get(m) or {}


def _register_generated_video(url, payload, session_id=None):
    
    if not payload:
        print("[warn] 视频入库**没有来历**（payload 为空）—— 预览窗将永远没有生成信息；"
              "调用点必须把提交时的实参传下来（ADR-0020：参数跟着产物走）", flush=True)
    try:
        n = _assets_store.asset_name_of(url)
        if not n:
            print(f"[warn] 生成视频未落盘为站内文件，跳过登记：{str(url)[:120]}")
            return None
        return _assets_store.register(
            name=n, url=url, type="video",
            origin=_assets_store.ORIGIN_CREATED,
            origin_session=session_id,
            meta=_assets_store.build_provenance(
                              payload=_assets_store.fit_payload(
                                  payload, _video_caps_for((payload or {}).get("model")),
                                  _video_param_cap()),
                              model=(payload or {}).get("model")),
        )
    except Exception as e:
        print("[warn] 视频结果入库失败（不影响任务）:", e, flush=True)
        return None




















def _image_dims_of(name):
    
    if not name:
        return None
    try:
        from PIL import Image
        _p = os.path.join(ASSETS_DIR, name)
        if not os.path.isfile(_p):
            return None
        with Image.open(_p) as _im:
            _w, _h = _im.size
        if _w and _h:
            return (int(_w), int(_h))
    except Exception:
        return None
    return None


def _stamp_actual_resolution(meta, name):
    
    _wh = _image_dims_of(name)
    if not _wh:
        return meta
    _prov = meta if isinstance(meta, dict) else {}
    _p = dict(_prov.get("payload") or {})
    _p["resolution"] = "%dx%d" % _wh
    _out = dict(_prov)
    _out["payload"] = _p
    return _out


def _register_generated_images(urls, session_id=None, payload=None, ratio=None, upstream=None):
    
    items = []

    _caps = _imgen.caps_for((payload or {}).get("model") or "", "ark" if upstream == "ark" else None) \
        if isinstance(payload, dict) else {}
    prov = _assets_store.build_provenance(
        payload=_assets_store.fit_payload(payload, _caps, _imgen.param_cap_map()), ratio=ratio)
    for u in (urls or []):
        n = _assets_store.asset_name_of(u)
        if not n:
            continue
        _meta = _stamp_actual_resolution(prov, n)
        items.append({"name": n, "url": u, "type": "image",
                      "origin": _assets_store.ORIGIN_CREATED,
                      "origin_session": session_id,
                      "meta": _meta})
    return _assets_store.register_many(items) if items else []


def _submit_image_to_agnes(payload):
    
    return _submit_image(payload, "agnes")



_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()




_TASK_PROGRESS_LOCKS = {}
_TASK_PROGRESS_LOCKS_LOCK = threading.Lock()










_CANCELED_TASKS = set()
_CANCELED_LOCK = threading.Lock()


def _mark_task_canceled(tid):
    with _CANCELED_LOCK:
        _CANCELED_TASKS.add(tid)


def _is_task_canceled(tid):
    if not tid:
        return False
    with _CANCELED_LOCK:
        return tid in _CANCELED_TASKS


def _get_task_progress_lock(tid):
    with _TASK_PROGRESS_LOCKS_LOCK:
        if tid not in _TASK_PROGRESS_LOCKS:
            _TASK_PROGRESS_LOCKS[tid] = threading.Lock()
        return _TASK_PROGRESS_LOCKS[tid]


def _get_task(tid):
    
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT data FROM tasks WHERE tid=?", (tid,)).fetchone()
            if not row:
                return None
            return json.loads(row["data"])
        finally:
            conn.close()


def _run_image_task(tid, rec):
    
    try:
        _progress_one(tid, rec)
    except Exception as e:
        print(f"[error] 生图任务 {tid} 推进异常：{type(e).__name__}: {e}")


def _requeue_busy():
    
    try:
        with _TASKS_LOCK:
            d = _load_tasks()
        tasks = (d.get("tasks") or {})
        inflight = [t for t, r in tasks.items()
                    if r.get("kind") == "image" and r.get("status") == "processing"
                    and r.get("submitted_at")]
        if inflight:
            return
        busy = sorted(
            ((r.get("busy_at") or 0), t)
            for t, r in tasks.items()
            if r.get("kind") == "image" and r.get("status") == "processing"
            and r.get("busy_at") and not r.get("submitted_at")
        )
        if not busy:
            return
        _, tid = busy[0]
        _n = int((tasks.get(tid) or {}).get("busy_count") or 0)

        _update_task(tid, busy_at=None, error=None)
        print(f"[requeue] 接口已空出位置：任务 {tid} 重新提交（此前被判忙 {_n} 次）")
    except Exception as e:
        print(f"[warn] _requeue_busy 异常：{e}")


def _task_worker():
    
    while True:
        try:
            with _TASKS_LOCK:
                d = _load_tasks()
                processing = [(tid, r) for tid, r in d.get("tasks", {}).items()
                              if r.get("status") == "processing"]
            for tid, rec in processing:
                if rec.get("kind") == "image":
                    if rec.get("busy_at"):
                        continue
                    if tid in _IMG_INFLIGHT:
                        continue
                    _IMG_INFLIGHT.add(tid)
                    _IMG_EXECUTOR.submit(_run_image_task, tid, rec) \
                        .add_done_callback(lambda _f, _t=tid: _IMG_INFLIGHT.discard(_t))
                else:
                    _progress_one(tid, rec)
            _requeue_busy()
        except Exception as e:
            print(f"[warn] _task_worker tick 异常：{e}")
        time.sleep(5)


def _progress_one(tid, rec):
    
    lock = _get_task_progress_lock(tid)
    if not lock.acquire(blocking=False):

        return
    try:

        rec = _get_task(tid)
        if not rec or rec.get("status") != "processing":
            return
        kind = rec.get("kind")
        payload = rec.get("payload") or {}
        model = rec.get("model")
        if kind == "video":
            video_id = rec.get("video_id")
            if not video_id:

                return
            st, vurl, eobj = _query_agnes_video(video_id, model)
            if st in ("completed", "success", "done") and vurl:



                _vurl = _persist_generated_video(vurl)
                _update_task(tid, status="completed", video_url=_vurl, error=None)


                _register_generated_video(_vurl, session_id=rec.get("session_id"),
                                          payload=rec.get("payload"))
            elif st in ("failed", "error", "cancelled"):
                err_msg = eobj if isinstance(eobj, str) else (eobj.get("message") if isinstance(eobj, dict) else None) or f"视频任务失败（{st}）"
                _update_task(tid, status="failed", error=err_msg)

        elif kind == "image":


            if rec.get("busy_at"):
                return









            ok, image_urls, err_msg, attempts = False, None, None, 0
            ms_tid = rec.get("upstream_task_id") or None

            def _persist_utid(utid, _tid=tid):


                _update_task(_tid, upstream_task_id=utid)

            for attempt in range(1, 4):
                attempts = attempt


                if _is_task_canceled(tid):
                    _update_task(tid, status="cancelled", error="用户取消（worker 已停止）",
                                 finished_at=time.time())
                    return
                if not ms_tid:



                    _fresh = _get_task(tid) or {}
                    ms_tid = _fresh.get("upstream_task_id") or ms_tid
                try:
                    ok, image_urls, err_msg, ms_tid = _submit_image(
                        payload, rec.get("upstream"), ms_tid,
                        on_submitted=_persist_utid, local_tid=tid)
                except Exception as e:



                    ok, image_urls = False, None
                    err_msg = f"服务端内部错误（{type(e).__name__}: {e}），已停止重试"
                    print(f"[error] 任务 {tid} 生图异常：{type(e).__name__}: {e}")
                    break
                if ms_tid:

                    _update_task(tid, upstream_task_id=ms_tid)
                if ok:
                    break

                if _is_task_canceled(tid):
                    _update_task(tid, status="cancelled", error="用户取消（worker 已停止）",
                                 finished_at=time.time())
                    return





                if err_msg and err_msg.startswith("[上游忙]"):
                    _update_task(tid, error=None, submitted_at=None,
                                 busy_at=time.time(), busy_reason=err_msg)
                    print(f"[busy] 任务 {tid} 被接口拒收，退回排队：{err_msg}")
                    return




                transient = bool(err_msg) and err_msg.startswith("[可重试]")
                if not transient:
                    break
                if attempt < 3:
                    time.sleep(2)
            if ok:
                _update_task(tid, status="completed", image_urls=image_urls, error=None)



                _sync_result_to_session(
                    session_id=rec.get("session_id"),
                    dedup_key=tid,
                    kind="image",
                    model=model,
                    media_url=image_urls[0],
                    prompt=(rec.get("payload") or {}).get("prompt", ""),
                    image_urls=image_urls,


                    started_at=rec.get("submitted_at") or rec.get("created_at"),
                    finished_at=rec.get("finished_at"),
                )


                _register_generated_images(image_urls, session_id=rec.get("session_id"),
                                           payload=rec.get("user_params") or rec.get("payload"),
                                           ratio=rec.get("ratio"),
                                           upstream=rec.get("upstream"))
            else:
                suffix = f"（已重试 {attempts} 次）" if attempts > 1 else ""
                _update_task(tid, status="failed", error=(err_msg or "生图失败") + suffix)
    finally:
        lock.release()


def _start_worker_once():
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        t = threading.Thread(target=_task_worker, name="task-worker", daemon=True)
        t.start()
        _WORKER_STARTED = True
        print("[info] 任务持久化 worker 已启动")









@app.before_request
def _boot_task_worker():
    _start_worker_once()


























SESSIONS_FILE = os.path.join(_ROOT, "data", "sessions.json")


def _load_sessions():
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT data FROM sessions").fetchall()
            cur = conn.execute("SELECT value FROM meta WHERE key='currentId'").fetchone()
        finally:
            conn.close()
    sessions = []
    for r in rows:
        try:
            sessions.append(json.loads(r["data"]))
        except Exception:
            pass
    current_id = cur["value"] if cur else None
    return {"sessions": sessions, "currentId": current_id}


def _merge_tombstones(sess, stored_tombs):
    
    try:
        old = stored_tombs.get(sess.get("id")) or []
        if not old:
            return sess
        cur = sess.get("deletedMsgs")
        cur = list(cur) if isinstance(cur, list) else []
        merged = cur + [f for f in old if f not in cur]
        if len(merged) != len(cur):
            sess = dict(sess)
            sess["deletedMsgs"] = merged
    except Exception:
        pass
    return sess


def _purge_history_rows(conn, sids):
    
    if not conn or not sids:
        return []
    keep = {str(x) for x in sids if x}
    if not keep:
        return []
    urls, dead = [], []
    for r in conn.execute("SELECT id, data FROM history"):
        try:
            if str(json.loads(r["data"] or "{}").get("sessionId") or "") in keep:
                urls.extend(_mgc.urls_in(r["data"]))
                dead.append(r["id"])
        except Exception:
            continue
    for i in dead:
        conn.execute("DELETE FROM history WHERE id=?", (i,))
    return urls


def _save_sessions(data):
    _ensure_db()
    sessions = (data or {}).get("sessions", [])
    current_id = (data or {}).get("currentId")



    force = bool((data or {}).get("force"))
    ids = [s["id"] for s in sessions if isinstance(s, dict) and "id" in s]












    with _DB_LOCK:
        conn = _db_conn()
        try:
            stored_tombs, stored_msgs = {}, {}


            _tomb = _tombstoned_session_ids(conn)
            if not force:
                for row in conn.execute("SELECT id, data FROM sessions"):
                    try:
                        obj = json.loads(row[1])
                        ms = obj.get("messages")
                        stored_msgs[row[0]] = ms if isinstance(ms, list) else []
                        tm = obj.get("deletedMsgs")
                        stored_tombs[row[0]] = tm if isinstance(tm, list) else []
                    except Exception:
                        stored_msgs[row[0]] = []
            for s in sessions:
                if not isinstance(s, dict) or "id" not in s:
                    continue



                if s["id"] in _tomb:
                    continue
                s = _merge_tombstones(s, stored_tombs)
                incoming = s.get("messages") or []









                if not force:
                    stored = stored_msgs.get(s["id"]) or []
                    if stored:
                        merged = _msgst.merge_messages(incoming, stored, tombstones=s.get("deletedMsgs"))
                        if len(merged) != len(incoming):
                            print(f"[sessions] {s['id']} 消息级合并：客户端 {len(incoming)} 条 + 服务端独有 "
                                  f"{len(merged) - len(incoming)} 条（含兜底写回的结果消息）")
                        s = dict(s, messages=merged)
                conn.execute(
                    "INSERT INTO sessions(id, name, created_at, data) VALUES(?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET name=excluded.name, created_at=excluded.created_at, data=excluded.data",
                    (s["id"], s.get("name"), s.get("createdAt"), json.dumps(s, ensure_ascii=False)),
                )



            if current_id is not None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('currentId', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (current_id,),
                )
            conn.commit()
        finally:
            conn.close()








def _load_agent_sessions():
    
    _ensure_db()
    with _DB_LOCK:
        conn = _db_conn()
        try:
            rows = conn.execute("SELECT data FROM agent_sessions").fetchall()
            cur = conn.execute("SELECT value FROM meta WHERE key='agentCurrentId'").fetchone()
        finally:
            conn.close()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["data"]))
        except Exception:
            pass
    return {"sessions": out, "currentId": cur["value"] if cur else None}


def _save_agent_sessions(data):
    
    _ensure_db()
    sessions = (data or {}).get("sessions", [])
    current_id = (data or {}).get("currentId")
    force = bool((data or {}).get("force"))
    ids = [s["id"] for s in sessions if isinstance(s, dict) and "id" in s]


    _pruned_urls, _pruned_ids = [], []
    with _DB_LOCK:
        conn = _db_conn()
        try:
            stored_msgs, stored_tombs = {}, {}
            if not force:
                for row in conn.execute("SELECT id, data FROM agent_sessions"):
                    try:
                        obj = json.loads(row[1])
                        ms = obj.get("messages")
                        stored_msgs[row[0]] = ms if isinstance(ms, list) else []
                        tm = obj.get("deletedMsgs")
                        stored_tombs[row[0]] = tm if isinstance(tm, list) else []
                    except Exception:
                        stored_msgs[row[0]] = []
            for s in sessions:
                if not isinstance(s, dict) or "id" not in s:
                    continue
                s = _merge_tombstones(s, stored_tombs)
                incoming = s.get("messages") or []


                if not force:
                    stored = stored_msgs.get(s["id"]) or []
                    if stored:
                        merged = _msgst.merge_messages(incoming, stored, tombstones=s.get("deletedMsgs"))
                        if len(merged) != len(incoming):
                            print(f"[agent_sessions] {s['id']} 消息级合并：客户端 {len(incoming)} 条 + "
                                  f"服务端独有 {len(merged) - len(incoming)} 条")
                        s = dict(s, messages=merged)
                conn.execute(
                    "INSERT INTO agent_sessions(id, name, created_at, data) VALUES(?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET name=excluded.name, created_at=excluded.created_at, data=excluded.data",
                    (s["id"], s.get("name"), s.get("createdAt"), json.dumps(s, ensure_ascii=False)),
                )

            if ids:
                placeholders = ",".join("?" * len(ids))
                _keep = set(ids)
                _pruned_ids = [r["id"] for r in conn.execute("SELECT id FROM agent_sessions")
                               if r["id"] not in _keep]
                if _pruned_ids:
                    _ph = ",".join("?" * len(_pruned_ids))
                    for r in conn.execute(
                            "SELECT data FROM agent_sessions WHERE id IN (%s)" % _ph, _pruned_ids):
                        _pruned_urls.extend(_mgc.urls_in(r["data"]))
                conn.execute(f"DELETE FROM agent_sessions WHERE id NOT IN ({placeholders})", ids)
            else:

                _pruned_ids = [r["id"] for r in conn.execute("SELECT id FROM agent_sessions")]
                for r in conn.execute("SELECT data FROM agent_sessions"):
                    _pruned_urls.extend(_mgc.urls_in(r["data"]))
                conn.execute("DELETE FROM agent_sessions")

            if _pruned_ids:
                _tids = []
                for r in conn.execute("SELECT tid, data FROM tasks"):
                    try:
                        if json.loads(r["data"] or "{}").get("session_id") in _pruned_ids:
                            _tids.append(r["tid"])
                    except Exception:
                        continue
                for t in _tids:
                    conn.execute("DELETE FROM tasks WHERE tid=?", (t,))

                _pruned_urls.extend(_purge_history_rows(conn, _pruned_ids))
            if current_id is not None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('agentCurrentId', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (current_id,),
                )
            conn.commit()
        finally:
            conn.close()

    if _pruned_urls:
        print(f"[agent_sessions] prune 保留 {len(_pruned_urls)} 个媒体 URL 对应文件（不删）")


def _sync_result_to_session(session_id, dedup_key, kind, model, media_url, prompt="",
                            params=None, assets=None, started_at=None, finished_at=None,
                            image_urls=None):
    
    if not session_id or not media_url:
        return
    now = time.time()


    t_start = started_at or now
    t_end = finished_at or now
    bot_msg = {
        "type": "bot",
        "prompt": prompt or "",
        "mode": None,
        "assets": list(assets or []),
        "params": params or {},
        "videoUrl": media_url,
        "media": ("image" if kind == "image" else None),
        "error": None,
        "status": "completed",
        "time": t_start,
        "videoId": dedup_key,
        "model": model,
        "startedAt": t_start,
        "finishedAt": t_end,
        "tokens": None,
        "cancelled": False,
    }
    if kind == "image":

        urls = [u for u in (image_urls or [media_url]) if u]
        bot_msg["imageUrls"] = urls
        bot_msg["taskId"] = dedup_key
    with _DB_LOCK:
        conn = _db_conn()
        try:
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                return
            sess = json.loads(row["data"])
            msgs = sess.get("messages", [])
            key = _msgst.msg_key(bot_msg)
            hit = None
            for i, m in enumerate(msgs):
                if isinstance(m, dict) and m.get("type") == "bot" and _msgst.msg_key(m) == key:
                    hit = i
                    break
            if hit is None:
                msgs.append(bot_msg)
                action = "写入"
            else:

                msgs[hit] = _msgst.merge_msg(msgs[hit], bot_msg)
                action = "补全"
            sess["messages"] = msgs
            conn.execute("UPDATE sessions SET data=? WHERE id=?",
                         (json.dumps(sess, ensure_ascii=False), session_id))
            conn.commit()
            print(f"[sessions] 任务完成，已{action}会话 {session_id} 的结果消息（{kind} {dedup_key}）")
        finally:
            conn.close()












DOWNLOAD_ALLOW_HOSTS = ("agnes-ai.space",)


_EXT_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
    "aac": "audio/aac", "ogg": "audio/ogg", "flac": "audio/flac",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
    "avi": "video/x-msvideo", "mkv": "video/x-matroska",
}


def _infer_ext_and_mime(url, content_type):
    
    from urllib.parse import urlparse

    path = (urlparse(url).path or "")
    seg = path.rsplit("/", 1)[-1]
    ext = ""
    if "." in seg:
        cand = seg.rsplit(".", 1)[-1].lower()

        if cand.isalpha() and 1 <= len(cand) <= 5:
            ext = cand
    if ext in _EXT_MIME:
        return ext, _EXT_MIME[ext]

    ct = (content_type or "").split(";")[0].strip().lower()
    for e, m in _EXT_MIME.items():
        if m == ct:
            return e, m

    if ct.startswith("image/"):
        return "png", ct or "image/png"
    if ct.startswith("video/"):
        return "mp4", ct or "video/mp4"
    if ct.startswith("audio/"):
        return "mp3", ct or "audio/mpeg"
    return "bin", ct or "application/octet-stream"


__all__ = ['AGNES_API_KEY', 'AGNES_BASE_URL', 'ALLOWED_EXTS', 'ASSETS_DIR', 'AUD_EXTS', 'DB_FILE', 'DEFAULT_MODEL', 'DOWNLOAD_ALLOW_HOSTS', 'FRONTEND_DIR', 'HISTORY_FILE', 'IMG_EXTS', 'MODEL_LIMITS', 'PUBLIC_BASE_URL', 'SESSIONS_FILE', 'TASKS_FILE', 'VID_EXTS', '_AGNES_SESSION', '_DB_LOCK', '_DB_READY', '_EXT_MIME', '_ROOT', '_TASKS_LOCK', '_WORKER_LOCK', '_WORKER_STARTED', '_add_cors', '_build_agnes_session', '_create_task', '_db_conn', '_deinline_payload_media', '_ensure_db', '_infer_ext_and_mime',
 '_init_db', '_inline_payload_media', '_load_env', '_load_history', '_load_sessions', '_load_tasks', '_migrate_legacy_json', '_persist_generated_image', '_progress_one', '_public_base', '_purge_history_rows', '_query_agnes_video', '_safe_name', '_save_history', '_save_sessions', '_save_tasks', '_start_worker_once', '_submit_image', '_submit_image_to_agnes', '_sync_result_to_session', '_table_empty', '_task_worker', '_to_b64_if_local', '_update_task', 'app']
