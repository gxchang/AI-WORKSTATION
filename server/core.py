

import base64
import json
import os
import threading
import time
import uuid
import re
import requests
import sqlite3
import unicodedata
from urllib.parse import unquote
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from flask import Flask, request, jsonify, send_from_directory, send_file, Response, abort



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


MAX_ASSETS = 12



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
            conn.commit()
        finally:
            conn.close()


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


def _create_task(kind, model, payload, video_id=None, media_hint=None, session_id=None, upstream=None):
    


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
        "created_at": time.time(),
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
_MS_POLL_TIMEOUT = 420


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
            timeout=(15, 120),
        )
    except requests.RequestException as e:
        return None, f"网络异常：{type(e).__name__}: {e}"
    if r.status_code != 200:
        return None, f"{label} 拒绝请求（{r.status_code}）：{_err_text(r)}"
    try:
        tid = (r.json() or {}).get("task_id")
    except Exception:
        tid = None
    if not tid:
        return None, f"{label} 未返回 task_id，无法轮询任务状态"
    print(f"[ms-submit] {time.strftime('%H:%M:%S')} 上游任务已创建 task_id={tid}")
    return tid, None


def _ms_wait(base, key, label, task_id):
    
    hs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
          "X-ModelScope-Task-Type": "image_generation"}
    t0 = time.time()
    while time.time() - t0 < _MS_POLL_TIMEOUT:
        time.sleep(_MS_POLL_INTERVAL)
        try:
            q = _AGNES_SESSION.get(f"{base}/tasks/{task_id}", headers=hs, timeout=(10, 60))
        except requests.RequestException as e:
            return False, None, f"轮询任务时网络异常：{type(e).__name__}: {e}"
        if q.status_code != 200:
            return False, None, f"{label} 轮询失败（{q.status_code}）：{_err_text(q)}"
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

    return False, None, f"{label} 生图超时（{_MS_POLL_TIMEOUT} 秒内未完成），请稍后重试"


def _submit_image(payload, upstream=None, ms_task_id=None):
    
    up = str(upstream or "").lower()
    if up == "ark":
        base, key, label = _arkprov.get("base_url"), _arkprov.get("api_key"), "方舟"
    elif up == "ms":
        base, key, label = _msprov.get("base_url"), _msprov.get("api_key"), "魔搭"
    else:
        base, key, label = _cfg_base(), _cfg_key(), "Agnes"



    wire = _inline_payload_media(payload, up)

    if up == "ms":

        if not ms_task_id:
            ms_task_id, err = _ms_create(base, key, label, wire)
            if not ms_task_id:
                return False, None, err, None
        ok, urls, err = _ms_wait(base, key, label, ms_task_id)
        return ok, urls, err, ms_task_id



    try:
        resp = _NO_RETRY_SESSION.post(
            f"{base}/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=wire,
            timeout=(15, 300),
        )
    except requests.RequestException as e:
        return False, None, f"网络异常：{type(e).__name__}: {e}", None
    if resp.status_code != 200:
        msg = _err_text(resp)
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
_PERSIST_TIMEOUT = (10, 120)


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
_PERSIST_VIDEO_TIMEOUT = (10, 300)


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


def _register_generated_video(url, session_id=None):
    
    try:
        n = _assets_store.asset_name_of(url)
        if not n:
            print(f"[warn] 生成视频未落盘为站内文件，跳过登记：{str(url)[:120]}")
            return None
        return _assets_store.register(
            name=n, url=url, type="video",
            origin=_assets_store.ORIGIN_CREATED,
            origin_session=session_id,
        )
    except Exception as e:
        print("[warn] 视频结果入库失败（不影响任务）:", e, flush=True)
        return None




















def _register_generated_images(urls, session_id=None):
    
    items = []
    for u in (urls or []):
        n = _assets_store.asset_name_of(u)
        if n:
            items.append({"name": n, "url": u, "type": "image",
                          "origin": _assets_store.ORIGIN_CREATED,
                          "origin_session": session_id})
    return _assets_store.register_many(items) if items else []


def _submit_image_to_agnes(payload):
    
    return _submit_image(payload, "agnes")



_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()




_TASK_PROGRESS_LOCKS = {}
_TASK_PROGRESS_LOCKS_LOCK = threading.Lock()


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


def _task_worker():
    
    while True:
        try:
            with _TASKS_LOCK:
                d = _load_tasks()
                processing = [(tid, r) for tid, r in d.get("tasks", {}).items()
                              if r.get("status") == "processing"]
            for tid, rec in processing:
                _progress_one(tid, rec)
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

                _register_generated_video(_vurl, session_id=rec.get("session_id"))
            elif st in ("failed", "error", "cancelled"):
                err_msg = eobj if isinstance(eobj, str) else (eobj.get("message") if isinstance(eobj, dict) else None) or f"视频任务失败（{st}）"
                _update_task(tid, status="failed", error=err_msg)

        elif kind == "image":







            ok, image_urls, err_msg, attempts = False, None, None, 0
            ms_tid = rec.get("upstream_task_id") or None
            for attempt in range(1, 4):
                attempts = attempt
                if not ms_tid:



                    _fresh = _get_task(tid) or {}
                    ms_tid = _fresh.get("upstream_task_id") or ms_tid
                ok, image_urls, err_msg, ms_tid = _submit_image(payload, rec.get("upstream"), ms_tid)
                if ms_tid:

                    _update_task(tid, upstream_task_id=ms_tid)
                if ok:
                    break

                transient = (
                    err_msg
                    and ("网络异常" in err_msg
                         or "Connection" in err_msg
                         or "RemoteDisconnected" in err_msg
                         or "Timeout" in err_msg
                         or "5xx" in err_msg
                         or "500" in err_msg
                         or "502" in err_msg
                         or "503" in err_msg
                         or "504" in err_msg)
                )
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
                    started_at=rec.get("created_at"),
                    finished_at=rec.get("finished_at"),
                )


                _register_generated_images(image_urls, session_id=rec.get("session_id"))
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



    _pruned_urls, _pruned_ids, _pruned_tids = [], [], []
    with _DB_LOCK:
        conn = _db_conn()
        try:
            stored_tombs, stored_msgs = {}, {}
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


            if ids:
                placeholders = ",".join("?" * len(ids))
                _keep = set(ids)
                _pruned_ids = [r["id"] for r in conn.execute("SELECT id FROM sessions")
                               if r["id"] not in _keep]
                if _pruned_ids:
                    _ph = ",".join("?" * len(_pruned_ids))
                    for r in conn.execute(
                            "SELECT data FROM sessions WHERE id IN (%s)" % _ph, _pruned_ids):
                        _pruned_urls.extend(_mgc.urls_in(r["data"]))
                conn.execute(f"DELETE FROM sessions WHERE id NOT IN ({placeholders})", ids)
            else:


                _pruned_ids = [r["id"] for r in conn.execute("SELECT id FROM sessions")]
                for r in conn.execute("SELECT data FROM sessions"):
                    _pruned_urls.extend(_mgc.urls_in(r["data"]))
                conn.execute("DELETE FROM sessions")

            if _pruned_ids:
                for r in conn.execute("SELECT tid, data FROM tasks"):
                    try:
                        if json.loads(r["data"] or "{}").get("session_id") in _pruned_ids:
                            _pruned_tids.append(r["tid"])
                    except Exception:
                        continue
                for t in _pruned_tids:
                    conn.execute("DELETE FROM tasks WHERE tid=?", (t,))

                _pruned_urls.extend(_purge_history_rows(conn, _pruned_ids))
            if current_id is not None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('currentId', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (current_id,),
                )
            conn.commit()
        finally:
            conn.close()


    if _pruned_urls:
        try:
            _r = _mgc.reclaim_urls(_pruned_urls)
            if _r["removed"]:
                print(f"[sessions] 已回收 {len(_r['removed'])} 个无引用媒体文件"
                      f"（{sum(s for _k, _n, s in _r['removed']) / 1024:.0f} KB）"
                      f"；另清理 {len(_pruned_tids)} 条任务行")
        except Exception as e:
            print(f"[warn] 会话 prune 后的媒体回收失败（不影响保存）：{e}")


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
        try:
            _r = _mgc.reclaim_urls(_pruned_urls)
            if _r["removed"]:
                print(f"[agent_sessions] 已回收 {len(_r['removed'])} 个无引用媒体文件"
                      f"（{sum(s for _k, _n, s in _r['removed']) / 1024:.0f} KB）")
        except Exception as e:
            print(f"[warn] 助手会话 prune 后的媒体回收失败（不影响保存）：{e}")


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


__all__ = ['AGNES_API_KEY', 'AGNES_BASE_URL', 'ALLOWED_EXTS', 'ASSETS_DIR', 'AUD_EXTS', 'DB_FILE', 'DEFAULT_MODEL', 'DOWNLOAD_ALLOW_HOSTS', 'FRONTEND_DIR', 'HISTORY_FILE', 'IMG_EXTS', 'MAX_ASSETS', 'MODEL_LIMITS', 'POLL_ENDPOINT', 'PUBLIC_BASE_URL', 'SESSIONS_FILE', 'TASKS_FILE', 'VID_EXTS', '_AGNES_SESSION', '_DB_LOCK', '_DB_READY', '_EXT_MIME', '_ROOT', '_TASKS_LOCK', '_WORKER_LOCK', '_WORKER_STARTED', '_add_cors', '_build_agnes_session', '_create_task', '_db_conn', '_deinline_payload_media', '_ensure_db', '_infer_ext_and_mime',
 '_init_db', '_inline_payload_media', '_load_env', '_load_history', '_load_sessions', '_load_tasks', '_migrate_legacy_json', '_persist_generated_image', '_progress_one', '_public_base', '_purge_history_rows', '_query_agnes_video', '_safe_name', '_save_history', '_save_sessions', '_save_tasks', '_start_worker_once', '_submit_image', '_submit_image_to_agnes', '_sync_result_to_session', '_table_empty', '_task_worker', '_to_b64_if_local', '_update_task', 'app']
