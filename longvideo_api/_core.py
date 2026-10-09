

import os
import io
import re
import json
import time
import base64
import sqlite3
import threading
import uuid
import shutil
import logging
import subprocess

import requests
from flask import Blueprint, request, jsonify, current_app, send_file

import assets_api.store as _assets_store


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(_ROOT, "storage", "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
DB_PATH = os.path.join(_ROOT, "data", "app.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
JOBS_DIR = os.path.join(_ROOT, "storage", "longvideo_jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

AGNES_API_KEY = os.environ.get("AGNES_API_KEY", "")
AGNES_BASE_URL = os.environ.get("AGNES_BASE_URL", "https://api.agnes-ai.cn/v1").rstrip("/")
POLL_ENDPOINT = os.environ.get("POLL_ENDPOINT") or "https://api.agnes-ai.cn/agnesapi"

VIDEO_MODEL = "agnes-video-2.5-flash"
LLM_MODEL = "agnes-2.5-flash"

ALLOWED_LLM_MODELS = ("agnes-2.5-flash", "agnes-3.0-flash")






def _prov():
    
    import server.provider as _provider
    return _provider


def _cfg_key() -> str:
    return _prov().get("api_key")

def _cfg_base() -> str:
    return _prov().get("base_url")

def _cfg_poll() -> str:
    return _prov().get("poll_endpoint")

def _cfg_video_model() -> str:
    return (_cfg_video_models() or [VIDEO_MODEL])[0]

def _cfg_video_models() -> tuple:
    
    return tuple(_prov().get("video_models") or ["agnes-video-2.5-flash", "agnes-video-2.5"])

def _cfg_llm_model() -> str:
    return (_prov().get("llm_models") or [LLM_MODEL])[0]

def _cfg_llm_models() -> tuple:
    return tuple(_prov().get("llm_models") or list(ALLOWED_LLM_MODELS))

IMG_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}
AUD_EXTS = {"mp3", "wav", "m4a", "aac", "ogg", "flac"}
ALLOWED = IMG_EXTS | AUD_EXTS


MAX_REF_IMAGES = 5


MAX_REF_AUDIOS = 3






VISUAL_MATCH_DEFAULT = True


SEG_GAP_SEC = 65



_GAP_MAX_SEC = 900

_MODEL_GAP_BASE = {"agnes-video-2.5-flash": SEG_GAP_SEC, "agnes-video-2.5": SEG_GAP_SEC}

MAX_SEG_SEC = 12
MIN_SEG_SEC = 4


_MODEL_SEC_BOUNDS = {"agnes-video-2.5-flash": (4, 12), "agnes-video-2.5": (4, 12)}


def _seg_bounds(model=None):
    
    m = model or _cfg_video_model()
    if _is_ark_model(m):
        try:
            import server.ark_provider as _ark
            lim = _ark.video_limits(m)
            if lim.get("min_seconds") and lim.get("max_seconds"):
                return int(lim["min_seconds"]), int(lim["max_seconds"])
        except Exception:
            pass
    return _MODEL_SEC_BOUNDS.get(m, (MIN_SEG_SEC, MAX_SEG_SEC))


def _submit_gap_base(model=None):
    
    m = model or _cfg_video_model()
    if _is_ark_model(m):
        try:
            import server.ark_provider as _ark
            lim = _ark.video_limits(m)
            if lim.get("submit_gap_base"):
                return int(lim["submit_gap_base"])
        except Exception:
            pass
    return _MODEL_GAP_BASE.get(m, SEG_GAP_SEC)


def _job_cancelled(job_id):
    
    try:
        c = _db()
        try:
            r = c.execute("SELECT status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
            return bool(r and r["status"] == "cancelled")
        finally:
            c.close()
    except Exception:
        return False


def _cancelable_sleep(job_id, seconds, step=2.0):
    
    deadline = time.time() + max(0.0, seconds)
    while True:
        if _job_cancelled(job_id):
            return True
        remain = deadline - time.time()
        if remain <= 0:
            return False
        time.sleep(min(step, remain))


def _ref_caps(model=None):
    
    m = model or _cfg_video_model()
    if _is_ark_model(m):
        try:
            import server.ark_provider as _ark
            lim = _ark.video_limits(m)
            return int(lim.get("max_images") or 5), int(lim.get("max_audios") or 0)
        except Exception:
            pass
    if m == "agnes-video-2.5":
        return 8, MAX_REF_AUDIOS
    return MAX_REF_IMAGES, MAX_REF_AUDIOS






import media_tools as _mt


def _ffmpeg():
    return _mt.resolve("ffmpeg")


def _ffprobe():
    return _mt.resolve("ffprobe")




_mt.log_status()


def _concat_final(out_dir, ordered):
    
    final = os.path.join(out_dir, "final.mp4")
    if not ordered:
        return False
    if len(ordered) == 1:

        try:
            shutil.copyfile(ordered[0], final)
            return os.path.getsize(final) > 0
        except Exception:
            return False
    list_file = os.path.join(out_dir, "concat.txt")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in ordered:
                f.write(f"file '{p}'\n")
    except Exception:
        return False
    ff = _ffmpeg()
    if not ff:
        return False
    try:
        r = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                            "-c", "copy", final],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    except Exception:
        return False
    ok = (r.returncode == 0 and os.path.exists(final) and os.path.getsize(final) > 0)
    if not ok and os.path.exists(final):
        try:
            os.remove(final)
        except Exception:
            pass
    return ok


def _concat_and_register(job_id, out_dir, ordered):
    
    if not _concat_final(out_dir, ordered):
        return None
    _register_final_asset(job_id)
    return f"/api/jobs/{job_id}/final.mp4"


def _probe_duration(path):
    
    fp = _ffprobe() or _ffmpeg()
    if not fp or not os.path.exists(path):
        return None
    try:
        if "ffprobe" in os.path.basename(fp).lower():
            out = subprocess.run(
                [fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60,
            )
            v = out.stdout.decode().strip()
            if v and v.replace(".", "", 1).replace("-", "", 1).isdigit():
                return float(v)

        out = subprocess.run(
            [fp, "-v", "info", "-hide_banner", "-i", path, "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out.stderr.decode(errors="ignore"))
        if m:
            h, mi, se = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(se)
    except Exception:
        return None
    return None


def _db():


    con = _assets_store.connect()
    _assets_store.ensure_assets_table(con)
    con.execute(
        """CREATE TABLE IF NOT EXISTS lv_jobs(
            id TEXT PRIMARY KEY,
            script TEXT,
            status TEXT,
            segment_count INTEGER,
            final_url TEXT,
            error TEXT,
            created_at REAL,
            updated_at REAL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS lv_segments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            seg_no INTEGER NOT NULL,
            shot_no INTEGER,
            is_continuation INTEGER,
            prompt TEXT,
            seconds INTEGER,
            images_keys TEXT,
            images_urls TEXT,
            audio_urls TEXT,
            status TEXT,
            video_id TEXT,
            video_url TEXT,
            local_path TEXT,
            tail_frame TEXT,
            error TEXT,
            created_at REAL,
            updated_at REAL
        )"""
    )


    try:
        con.execute("ALTER TABLE lv_segments ADD COLUMN mode TEXT")
    except sqlite3.OperationalError:
        pass

    for sql in (
        "ALTER TABLE lv_jobs ADD COLUMN stage TEXT",
        "ALTER TABLE lv_jobs ADD COLUMN assets_json TEXT",
        "ALTER TABLE lv_jobs ADD COLUMN shots_json TEXT",
    ):
        try:
            con.execute(sql)
        except sqlite3.OperationalError:
            pass

    try:
        con.execute("ALTER TABLE lv_segments ADD COLUMN real_seconds REAL")
    except sqlite3.OperationalError:
        pass


    try:
        con.execute("ALTER TABLE lv_jobs ADD COLUMN gen_params_json TEXT")
    except sqlite3.OperationalError:
        pass


    try:
        con.execute("ALTER TABLE lv_jobs ADD COLUMN name TEXT")
    except sqlite3.OperationalError:
        pass




    try:
        con.execute("ALTER TABLE lv_jobs ADD COLUMN session_id TEXT")
    except sqlite3.OperationalError:
        pass

    for sql in (
        "ALTER TABLE lv_segments ADD COLUMN aspect_ratio TEXT",
        "ALTER TABLE lv_segments ADD COLUMN resolution TEXT",
    ):
        try:
            con.execute(sql)
        except sqlite3.OperationalError:
            pass


    try:
        con.execute("ALTER TABLE lv_segments ADD COLUMN audio TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        con.execute("ALTER TABLE lv_segments ADD COLUMN started_at REAL")
    except sqlite3.OperationalError:
        pass



    try:
        con.execute("ALTER TABLE lv_segments ADD COLUMN finished_at REAL")
    except sqlite3.OperationalError:
        pass



    try:
        con.execute("ALTER TABLE lv_segments ADD COLUMN prompt_history TEXT")
    except sqlite3.OperationalError:
        pass



    try:
        con.execute("ALTER TABLE lv_jobs ADD COLUMN shots_history TEXT")
    except sqlite3.OperationalError:
        pass


    try:
        con.execute("ALTER TABLE lv_jobs ADD COLUMN current_shot_ver INTEGER DEFAULT -1")
    except sqlite3.OperationalError:
        pass


    try:
        con.execute("ALTER TABLE lv_jobs ADD COLUMN sb_mode TEXT DEFAULT 'smart'")
    except sqlite3.OperationalError:
        pass
    return con


def _attach_appearance(items):
    
    if not items:
        return items
    con = _db()
    try:
        rows = con.execute(
            "SELECT name, appearance, job_id, type FROM assets").fetchall()
        ap_map = {r["name"]: (r["appearance"] or "") for r in rows}
        owner_map = {r["name"]: r["job_id"] for r in rows}
        type_map = {r["name"]: r["type"] for r in rows}
    finally:
        con.close()
    for it in items:
        n = it.get("name")
        it["appearance"] = ap_map.get(n) or ""

        it["job_id"] = owner_map.get(n)



        if not it.get("type"):
            it["type"] = type_map.get(n) or "image"
    return items





def _mime_of(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "webp":
        return "image/webp"
    if ext == "bmp":
        return "image/bmp"
    if ext == "gif":
        return "image/gif"
    if ext == "mp3":
        return "audio/mpeg"
    if ext == "wav":
        return "audio/wav"
    if ext == "m4a":
        return "audio/mp4"
    if ext == "aac":
        return "audio/aac"
    if ext == "ogg":
        return "audio/ogg"
    if ext == "flac":
        return "audio/flac"
    return "application/octet-stream"


def _local_to_b64(url: str, max_side: int = None) -> str:
    
    if not url or not url.startswith("/assets/"):
        return url
    p = os.path.join(ASSETS_DIR, os.path.basename(url))
    if not os.path.exists(p):
        return url

    if not max_side:
        with open(p, "rb") as f:
            b = f.read()
        return f"data:{_mime_of(p)};base64," + base64.b64encode(b).decode("ascii")

    try:
        from PIL import Image
        import io
        im = Image.open(p)
        if im.mode in ("RGBA", "P", "LA"):
            im = im.convert("RGB")
        if max(im.size) > max_side:
            scale = max_side / max(im.size)
            im = im.resize((int(im.size[0] * scale), int(im.size[1] * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        b = buf.getvalue()
        return "data:image/jpeg;base64," + base64.b64encode(b).decode("ascii")
    except Exception:

        with open(p, "rb") as f:
            b = f.read()
        return f"data:{_mime_of(p)};base64," + base64.b64encode(b).decode("ascii")














INJECT_ABSTRACT_DIMENSIONS = False


def _appearance_to_spec(text, source="registry", label="", kind=""):
    
    return _assets_store._appearance_to_spec(text, source=source, label=label, kind=kind)


def _spec_to_appearance(spec):
    if isinstance(spec, str):
        return spec
    return json.dumps(spec, ensure_ascii=False)


def _appearance_display(ap):
    
    if not ap:
        return ""
    s = ap.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                raw = (obj.get("raw") or "").strip()
                if raw:
                    return raw
                return json.dumps(obj.get("concrete", {}), ensure_ascii=False)
        except Exception:
            pass
    return ap


def _robust_json_loads(text, default=None):
    
    if not text or not isinstance(text, str):
        return default
    s = text.strip()

    try:
        return json.loads(s)
    except Exception:
        pass

    if s.startswith("```"):
        s = re.sub(r'^```[a-zA-Z]*', '', s).strip()
        s = s.rstrip("`").strip()
    s = s.lstrip("\ufeff")
    try:
        return json.loads(s)
    except Exception:
        pass



    fixed = _fix_bare_quotes(s)
    if fixed != s:
        try:
            return json.loads(fixed)
        except Exception:
            s = fixed

    s2 = _escape_raw_control(s)
    if s2 != s:
        try:
            return json.loads(s2)
        except Exception:
            s = s2

    s3 = re.sub(r',\s*([}\]])', r'\1', s)
    if s3 != s:
        try:
            return json.loads(s3)
        except Exception:
            pass
    return default


def _repair_truncated_json(s):
    
    text = (s or "").rstrip()
    if not text:
        return text

    in_str, esc = False, False
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
    if in_str:
        text += '"'

    opens = []
    instr, escp = False, False
    for ch in text:
        if escp:
            escp = False
            continue
        if ch == '\\':
            escp = True
            continue
        if ch == '"':
            instr = not instr
            continue
        if instr:
            continue
        if ch == '{':
            opens.append('{')
        elif ch == '[':
            opens.append('[')
        elif ch == '}':
            if opens and opens[-1] == '{':
                opens.pop()
        elif ch == ']':
            if opens and opens[-1] == '[':
                opens.pop()
    close_map = {'{': '}', '[': ']'}
    return text + ''.join(close_map[o] for o in reversed(opens))


def _recover_shots_array(value):
    
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    s = value.strip()
    if not s:
        return []
    parsed = _robust_json_loads(s, None)
    if isinstance(parsed, list) and parsed:
        return parsed

    start = s.find('[')
    if start == -1:
        return []
    depth, end = 0, -1
    for i in range(start, len(s)):
        ch = s[i]
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
    block = s[start:end + 1] if end != -1 else s[start:]
    parsed = _robust_json_loads(block, None)
    if isinstance(parsed, list) and parsed:
        return parsed

    repaired = _repair_truncated_json(block)
    if repaired != block:
        parsed = _robust_json_loads(repaired, None)
        if isinstance(parsed, list) and parsed:
            return parsed
    return []


def _explicitly_anchored(prompt, name, name_labels):
    
    cset = set(name_labels.get(name, set()))
    cset.add(name)
    for cs in cset:
        if cs and re.search(r'图\s*\d+\s*的\s*' + re.escape(cs), prompt):
            return True
    return False


def _fix_bare_quotes(s):
    
    out = []
    in_str = False
    esc = False
    i = 0
    n = len(s)
    replace_count = 0
    while i < n:
        c = s[i]
        if esc:
            out.append(c)
            esc = False
            i += 1
            continue
        if c == "\\":
            out.append(c)
            esc = True
            i += 1
            continue
        if c == '"':
            if not in_str:
                in_str = True
                out.append(c)
            else:

                j = i + 1
                while j < n and s[j] in " \t\r\n":
                    j += 1
                nxt = s[j] if j < n else ""
                if nxt in (":", ",", "}", "]"):
                    in_str = False
                    out.append(c)
                else:
                    out.append("\u201c")
                    replace_count += 1
            i += 1
            continue
        out.append(c)
        i += 1
    if replace_count:
        print(f"[OPT-诊断] _fix_bare_quotes 替换裸引号 {replace_count} 处", flush=True)
    return "".join(out)


def _escape_raw_control(s):
    
    out = []
    in_str = False
    esc = False
    changed = False
    for c in s:
        if esc:
            out.append(c)
            esc = False
            continue
        if c == "\\":
            out.append(c)
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            out.append(c)
            continue
        if in_str and c in "\n\r\t":
            out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[c])
            changed = True
            continue
        out.append(c)
    return "".join(out) if changed else s







_RECOGNITION_SPEC = {
    "character": {
        "role": "你是严谨的角色设定识别助手，只描述真实看到的视觉信息，不脑补。",
        "user": (
            "请严格按视觉识别，用中文逐条列出该角色{who}的：\n"
            "1) 姿态（拟人直立 / 四足行走，二选一并明确）；\n"
            "2) 外形（毛色、品种特征、体型）；\n"
            "3) 服装（头部配饰的颜色与款式、上装、下装、鞋袜、其他配饰）。\n"
            "只写你真正看到的，不要推测。"
        ),
        "field_label": "外观",
    },
    "scene": {
        "role": "你是严谨的场景设定识别助手，只描述真实看到的视觉信息，不脑补。",
        "user": (
            "请严格按视觉识别，用中文描述该场景/环境{who}的：\n"
            "1) 地点与空间（室内/室外、建筑类型、街道/院落/房间）；\n"
            "2) 建筑与陈设（墙面、门窗、可辨识物体、堆叠物）；\n"
            "3) 植被与自然（树、花、地面材质）；\n"
            "4) 光照与时段（白天/黄昏/夜晚、光源方向）；\n"
            "5) 色调与氛围（整体色彩倾向、情绪）；\n"
            "6) 天气（晴/雨/雾/雪/阴）。\n"
            "7) 空间布局：必须用「方位=内容」列出画面构图（方位仅用 左/右/前/中/后/上/下/远景/中景/近景），"
            "例如「左侧=窗台，右侧=堆纸箱，中景=巷子深处，前景=自行车道」；若画面无明确方位结构，写「整体=一处<简要空间描述>」。\n"
            "只写你真正看到的，不要推测。"
        ),
        "field_label": "场景描述",
    },
    "prop": {
        "role": "你是严谨的道具设定识别助手，只描述真实看到的视觉信息，不脑补。",
        "user": (
            "请严格按视觉识别，用中文描述该道具{who}的：\n"
            "1) 类别与功能；\n"
            "2) 外形与材质；\n"
            "3) 尺寸与显著特征；\n"
            "4) 风格与年代感。\n"
            "只写你真正看到的，不要推测。"
        ),
        "field_label": "道具",
    },
}
_DEFAULT_RECOGNITION_KIND = "character"


def _spec_kind(ap):
    
    if not ap or not str(ap).strip().startswith("{"):
        return ""
    try:
        obj = json.loads(ap)
        if isinstance(obj, dict):
            return (obj.get("kind") or "").strip()
    except Exception:
        pass
    return ""


def _recognize_visual(url: str, label: str = "", kind: str = "character", llm_model: str = LLM_MODEL) -> str:
    
    spec = _RECOGNITION_SPEC.get(kind) or _RECOGNITION_SPEC[_DEFAULT_RECOGNITION_KIND]
    if not url or not url.startswith("/assets/"):
        return ""

    import server.llm as _llm
    if not _llm.caps("storyboard", "vision"):
        print("[OPT-诊断] 识图跳过：当前分镜引擎未声明图片识别能力", flush=True)
        return ""
    b64 = _local_to_b64(url, max_side=1024)
    if b64 == url:
        return ""
    who = f"（{spec['field_label']}：{label}）" if label else ""
    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": spec["role"]},
            {"role": "user", "content": [
                {"type": "text", "text": spec["user"].format(who=who)},
                {"type": "image_url", "image_url": {"url": b64}},
            ]},
        ],
        "temperature": 0.2,
    }
    last = ""



    for _attempt in range(3):
        try:
            r = _llm.chat("storyboard", messages=payload["messages"], model=llm_model,
                          thinking=False, temperature=0.2, timeout=120)
            if r.status_code == 200:
                data = r.json()
                return _spec_to_appearance(_appearance_to_spec(
                    (data["choices"][0]["message"].get("content") or "").strip(),
                    source="registry", label=label, kind=kind))
            if r.status_code == 429:
                time.sleep(5 * (_attempt + 1))
                continue
            return ""
        except Exception:
            time.sleep(2)
            continue
    return last


def _clear_tail_frames(job_id):
    
    con = _db()
    try:
        con.execute(
            "UPDATE lv_segments SET tail_frame=NULL WHERE job_id=? AND tail_frame IS NOT NULL",
            (job_id,),
        )
        con.commit()
    except Exception as e:
        logging.getLogger(__name__).warning("清空 tail_frame 失败 %s: %s", job_id, e)
    finally:
        con.close()


def _extract_tail_frame(mp4_path: str) -> str:
    
    ff = _ffmpeg()
    if not ff or not os.path.exists(mp4_path):
        return ""
    tmp = mp4_path + ".tail.png"
    try:
        subprocess.run(
            [ff, "-y", "-sseof", "-0.3", "-i", mp4_path, "-frames:v", "1", tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
        )
        if not os.path.exists(tmp):
            return ""
        with open(tmp, "rb") as f:
            b = f.read()
        return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    except Exception:
        return ""
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _load_registry_rows(job_id=None):
    
    con = _db()
    try:
        if not job_id:

            return []

        job = con.execute("SELECT assets_json FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        names, local = [], {}
        if job and job["assets_json"]:
            try:
                assets = json.loads(job["assets_json"])
            except Exception:
                assets = []
            for a in assets:

                if isinstance(a, dict):
                    n = a.get("name") or a.get("path")
                else:
                    n = a
                if n:
                    names.append(n)
                    if isinstance(a, dict):
                        local[n] = a
        if not names:
            return []


        placeholders = ",".join("?" * len(names))

        rows = con.execute(
            f"SELECT a.name,a.url,a.type,a.label,a.kind,"
            f"COALESCE(s.name, a.owner) AS owner,a.posture,a.appearance FROM assets a "
            f"LEFT JOIN subjects s ON s.id = a.subject_id "
            f"WHERE a.name IN ({placeholders})",
            names,
        ).fetchall()



        out = []
        for r in rows:
            d = dict(r)
            la = local.get(d["name"]) or {}
            for k in ("label", "kind", "owner", "posture"):
                v = la.get(k)
                if isinstance(v, str) and v.strip():
                    d[k] = v
            out.append(d)
        return out
    finally:
        con.close()








def _allowed_models():
    models = list(_cfg_video_models())
    try:
        import server.ark_provider as _ark
        if _ark.video_ready():
            models += [m for m in _ark.video_models() if m not in models]
    except Exception:
        pass
    return models


def _is_ark_model(model):
    
    if not model:
        return False
    try:
        import server.ark_provider as _ark
        return _ark.is_video_model(model)
    except Exception:
        return False

_ALLOWED_ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9")



_ALLOWED_RESOLUTIONS_ALL = ("720P", "1080P", "1K", "2K")
_ALLOWED_RESOLUTIONS_FLASH = ("720P",)


def _allowed_resolutions(model):
    
    if "flash" in (model or ""):
        return _ALLOWED_RESOLUTIONS_FLASH
    return _ALLOWED_RESOLUTIONS_ALL


def _norm_gen_params(raw):
    
    if not isinstance(raw, dict):
        raw = {}
    model = raw.get("model") if raw.get("model") in _allowed_models() else "agnes-video-2.5-flash"
    out = {
        "model": model,
        "aspect_ratio": raw.get("aspect_ratio") if raw.get("aspect_ratio") in _ALLOWED_ASPECTS else "16:9",
        "resolution": raw.get("resolution") if raw.get("resolution") in _allowed_resolutions(model) else "720P",
    }
    if isinstance(raw.get("style"), str) and raw.get("style").strip():
        out["style"] = raw["style"].strip()[:40]
    return out





def _build_registry_text(rows) -> str:
    
    lines = ["可用素材登记册（『标签』是人类可读的主索引，写分镜时优先按标签精确匹配；images 字段必须填 name 键值；续接段 images[0]='tail'）："]
    img_lines, aud_lines = [], []
    for r in rows:
        if r["type"] == "image":
            kind_lbl = "角色图" if r["kind"] == "character" else ("场景图" if r["kind"] == "scene" else "道具图")
            primary_label = (r["label"] or r["owner"] or r["name"]) or "未命名"
            parts = [f"标签={primary_label}"]
            if r["label"] and r["owner"] and r["label"] != r["owner"]:
                parts.append(f"owner={r['owner']}")
            if r["posture"]:
                parts.append(f"姿态={r['posture']}")
            line = f"- [{kind_lbl}] 标签「{primary_label}」({', '.join(parts)})；name={r['name']}"

            if r.get("appearance"):
                _kind = r.get("kind") or _DEFAULT_RECOGNITION_KIND
                _fl = _RECOGNITION_SPEC.get(_kind, _RECOGNITION_SPEC[_DEFAULT_RECOGNITION_KIND])["field_label"]
                line += f"\n    {_fl}(已视觉识别，写分镜时锁死)：{_appearance_display(r['appearance'])}"
                if _kind == "scene":

                    _lay = re.search(r'空间布局[：:]\s*([\s\S]+)$', _appearance_display(r['appearance']))
                    if _lay:
                        line += f"\n    空间布局(角色可站位点)：{_lay.group(1).strip().strip('。；;')}"
            img_lines.append(line)
        elif r["type"] == "audio":
            primary_label = (r["label"] or r["name"]) or "未命名"
            aud_lines.append((primary_label, r["owner"] or "", r["name"]))
    if img_lines:
        lines.append("\n【图片素材】")
        lines.extend(img_lines)
    else:
        lines.append("\n【图片素材】(暂无)")
    if aud_lines:
        lines.append(
            "\n【已归属的声线】(硬规则：下列『角色 X』有归属声线；本镜只要出现这些角色，"
            "就必须把 X 写入 audio 数组；audio 填『角色 label』，不是『声线 label』，"
            "也禁止写声线 name=xxx)"
        )
        for lbl, owner, name in aud_lines:
            if owner:
                lines.append(f"  - 角色「{owner}」 ← 声线「{lbl}」")
            else:
                lines.append(f"  - 声线「{lbl}」 ← 未归属角色（暂不参与 audio 匹配）")
    else:
        lines.append("\n【已归属的声线】(暂无)")
    return "\n".join(lines)











import os
_PROMPT_PATH = os.path.join(_ROOT, "prompts", "storyboard_llm", "system_prompt.txt")
def _load_system_prompt():
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        return _f.read()
SYSTEM_PROMPT = _load_system_prompt()


def _render_system_prompt(video_model=None):
    
    lo, hi = _seg_bounds(video_model)
    return (_load_system_prompt()
            .replace("{{VIDEO_MODEL}}", video_model or _cfg_video_model())
            .replace("{{SEC_MIN}}", str(lo))
            .replace("{{SEC_MAX}}", str(hi)))


def _optimize(script: str, rows, llm_model: str = LLM_MODEL, video_model: str = None) -> dict:
    
    import server.llm as _llm
    from concurrent.futures import ThreadPoolExecutor

    rows = [dict(r) for r in rows]

    sys_prompt = _render_system_prompt(video_model)
    img_rows = [r for r in rows if r.get("type") == "image" and r.get("url")]

    def _need_rec(r):
        
        ap = r.get("appearance")
        if not ap:
            return True
        sk = _spec_kind(ap)
        cur = r.get("kind") or _DEFAULT_RECOGNITION_KIND
        if not sk:
            return cur != _DEFAULT_RECOGNITION_KIND
        return sk != cur

    missing = [r for r in img_rows if _need_rec(r)]
    if missing:

        def _rec(r):
            ap = _recognize_visual(r["url"], r.get("label") or r.get("name") or "",
                                   r.get("kind") or _DEFAULT_RECOGNITION_KIND,
                                   llm_model=llm_model)
            r["appearance"] = ap
            if ap:
                try:
                    _c = _db()
                    _c.execute(
                        "UPDATE assets SET appearance=? WHERE name=?",
                        (ap, r["name"]),
                    )
                    _c.commit()
                except Exception:
                    pass
            return r
        with ThreadPoolExecutor(max_workers=min(2, len(missing))) as ex:
            list(ex.map(_rec, missing))
    registry_text = _build_registry_text(rows)
    tool_schema = {
        "type": "function",
        "function": {
            "name": "save_shots",
            "description": "保存优化后的结构化分镜数组（所有 shot mode 必为 reference）",
            "parameters": {
                "type": "object",
                "properties": {
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "shot_no": {"type": "integer"},
                                "estimated_seconds": {"type": "integer", "minimum": _seg_bounds(video_model)[0], "maximum": _seg_bounds(video_model)[1]},
                                "mode": {"type": "string", "enum": ["reference"]},
                                "is_continuation": {"type": "boolean"},
                                "characters": {"type": "array", "items": {"type": "object", "properties": {
                                    "label": {"type": "string"}, "matched": {"type": "boolean"},
                                    "voice_source": {"type": "string", "enum": ["reference_audio", "text_voice", "model_default"]},
                                    "position": {"type": "string", "description": "该角色在本镜场景中的画面方位（如'画面左侧的窗台旁''画面中央'）：优先取自场景图登记册给出的「空间布局」方位点（如'左侧=窗台' → 写'画面左侧的窗台旁'）；无场景图时从脚本方位词派生（如'站在巷口' → '巷口'）；确实无依据可留空（不许编造）。注意：**同一方位必须同时写进 prompt 正文该角色的处所短语里（见硬规则 11.1），本字段仅作结构化记录、后端不注入 prompt。**"}
                                }}, "description": "仅填登记册 kind=character 的角色 label；场景（kind=scene）/道具（kind=prop）的 label 严禁写入——场景/道具只通过 images 以 name 引用"},
                                "dialogue": {"type": "array", "items": {"type": "object", "properties": {
                                    "character": {"type": "string"}, "voice": {"type": "string"},
                                    "line": {"type": "string", "description": "该镜此角色台词文本(无台词则整个 dialogue 对象省略,绝不写空字符串,绝不写裸双引号 — 空台词破坏 JSON 解析)"}, "needs_review": {"type": "boolean"}
                                }}},
                                "sfx": {"type": "array", "items": {"type": "string"}},
                                "scene": {"type": "object", "properties": {"text": {"type": "string", "description": "本镜场景/位置描述（场所+方位+陈设+光线与氛围），只写场景本身（场所+方位+陈设+光线与氛围），禁止抄入角色动作/神态/对白——那些统一在 prompt 文本里自然写，由视频模型直接读取"}, "style_anchor": {"type": "string"}}},
                                "images": {"type": "array", "items": {"type": "string"}, "description": "续接段 images[0]='tail'；其余填 registry 的 name 键值，按『角色 > 场景 > 道具』优先级排列，≤5（超出截断）；场景/道具图也在此列出，便于后端按 name 反查并绑定图N。图N 严格对应 images 数组下标（图1=images[0]）。"},
                                "audio": {"type": "array", "items": {"type": "string"}, "description": "本镜『实际有台词』角色的 label 列表（与硬规则7一致：只有 dialogue 里 line 非空的角色才配声）。按对话出现顺序填写，audio[0] 即『音频1』，≤3（Flash 硬上限，超出静默截断）。无台词的角色（纯动作/空镜/画外音）一律不得写入。不得写声线 label（如『三花猫声音』），也不得写声线 name（lv_xxx）。"},
                                "prompt": {"type": "string", "description": "按硬规则3/5/10/11 写：自然语言叙事一段话（禁『图1=』等号式与『SFX：/风格：』标签段）。已登记且有图角色/场景/道具不强制写文字外貌（靠图N 锚定），仅未登记/无图实体在首现处写一行精简外观签名；每处提及都重挂其图N（图N=images 下标）；已登记 posture 角色姿态由后端确定性注入（见硬规则11），LLM 不写姿态前缀。对白格式：『说话动词（音频N）：\"台词\"』（N = 该角色在 audio 数组中的序号：audio[0]→音频1…；无配声角色直接『角色：\"台词\"』）。禁止写声线真名或『老年女声』之类描述——声线由音频N 绑定（audio[0]→音频1…）。动作/微表情/光线/音效/禁止 等镜头级指令直接在 prompt 文本里写足。"}
                            },
                            "required": ["shot_no", "estimated_seconds", "mode", "prompt", "is_continuation", "images"]
                        }
                    }
                },
                "required": ["shots"]
            }
        }
    }
    user_text = (
        "请优化以下脚本为分镜数组。\n\n" + registry_text +
        "\n\n初始脚本：\n" + script
    )



    user_content = [{"type": "text", "text": user_text}]
    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        "tools": [tool_schema],
        "tool_choice": {"type": "function", "function": {"name": "save_shots"}},
        "temperature": 0.2,





        "max_tokens": _llm.max_output_for("storyboard", default=32768),
    }









    print(f"[OPT-诊断] 输入体量: SYSTEM_PROMPT={len(sys_prompt)}字 user_text={len(user_text)}字 "
          f"(合计约{len(SYSTEM_PROMPT)+len(user_text)}字)", flush=True)




    if not _llm.caps("storyboard", "tools"):
        raise RuntimeError(
            "当前分镜引擎模型未声明支持工具调用 —— 分镜依赖强制工具调用（save_shots）"
            "产出结构化结果。请在「服务商设置」更换支持工具调用的模型。")
    _ctx_limit = _llm.ctx_limit("storyboard")
    _est_chars = len(SYSTEM_PROMPT) + len(user_text)
    if _ctx_limit and _est_chars > int(_ctx_limit):
        raise RuntimeError(
            f"脚本体量约 {_est_chars} 字符，超出当前分镜模型的上下文声明（{_ctx_limit} token）—— "
            "请精简脚本或拆段提交；若声明值填错，请在「服务商设置」修正上下文上限。")
    shots, last_err = [], ""
    MAX_CONTENT_RETRIES = 2
    for _attempt in range(MAX_CONTENT_RETRIES + 1):
        if _attempt:
            time.sleep(3)
        _t0 = time.time()
        try:







            r = _llm.chat("storyboard", messages=payload["messages"], model=llm_model,
                          tools=payload.get("tools"), tool_choice=payload.get("tool_choice"),
                          temperature=0.2, max_tokens=payload.get("max_tokens"),
                          timeout=(10, 900))
        except Exception as e:

            last_err = f"网络异常 {type(e).__name__}"
            print(f"[OPT-诊断] 第{_attempt+1}次尝试失败（网络/5xx 已耗尽内部重试）: {last_err} ({e})", flush=True)
            break
        _elapsed = round(time.time() - _t0, 1)
        if r.status_code != 200:
            last_err = f"LLM 返回 {r.status_code}: {r.text[:200]}"
            print(f"[OPT-诊断] 第{_attempt+1}次尝试 HTTP {r.status_code}，耗时{_elapsed}s", flush=True)

            if r.status_code == 429 and _attempt < MAX_CONTENT_RETRIES:
                time.sleep(15)
                continue
            break
        data = r.json()
        _ch = (data.get("choices") or [{}])[0]
        msg = _ch.get("message") or {}
        _usage = data.get("usage") or {}
        print(f"[OPT-诊断] 第{_attempt+1}次尝试 HTTP 200 耗时{_elapsed}s "
              f"finish_reason={_ch.get('finish_reason')} "
              f"prompt_tokens={_usage.get('prompt_tokens')} completion_tokens={_usage.get('completion_tokens')} "
              f"tool_calls={'有' if msg.get('tool_calls') else '无'}", flush=True)
        if not msg.get("tool_calls"):

            last_err = "LLM 未调用 save_shots 工具"
            if _attempt < MAX_CONTENT_RETRIES:
                continue
            break

        args = _robust_json_loads(msg["tool_calls"][0]["function"]["arguments"], None)
        if not isinstance(args, dict):
            last_err = "tool arguments 解析失败（含容错修复后仍失败）"
            print(f"[OPT-诊断] 参数残缺: {last_err}; finish_reason={_ch.get('finish_reason')}", flush=True)
            if _attempt < MAX_CONTENT_RETRIES:
                continue
            break
        shots = _recover_shots_array(args.get("shots", []))
        if shots:
            break
        last_err = "LLM 返回 shots=[]"

        try:
            _raw_args = msg["tool_calls"][0]["function"]["arguments"]
            print(f"[OPT-诊断] 空分镜: args类型={type(args).__name__} keys={list(args.keys()) if isinstance(args, dict) else 'N/A'} "
                  f"raw_args长度={len(_raw_args)} 前6000字={_raw_args[:6000]} 后200字={_raw_args[-200:]}", flush=True)
        except Exception as _e:
            print(f"[OPT-诊断] 空分镜: 无法打印 raw_args ({_e})", flush=True)
        if _attempt < MAX_CONTENT_RETRIES:
            continue
        break
    if not shots:
        raise RuntimeError(
            "优化器未产出任何分镜（已自动重试仍失败）。"
            "请稍等片刻再重试；若反复出现，可缩短脚本或拆成更少的逻辑段再提交。"
        )

    name_to_url = {r["name"]: r["url"] for r in rows}
    owner_to_audio = {r["owner"]: r["url"] for r in rows if r["type"] == "audio" and r["owner"]}


    label_to_audio = {r["label"]: r["url"] for r in rows if r["type"] == "audio" and r["label"]}
    for s in shots:
        s["mode"] = "reference"
        imgs = s.get("images") or []
        resolved_imgs, unresolved = [], []
        cleaned_imgs = []
        for k in imgs:
            if k == "tail":
                resolved_imgs.append("tail")
                cleaned_imgs.append("tail")
            elif k in name_to_url:
                resolved_imgs.append(name_to_url[k])
                cleaned_imgs.append(k)
            else:

                unresolved.append(k)

        s["images_urls"] = resolved_imgs
        s["unresolved_images"] = unresolved

        s["images"] = cleaned_imgs
        auds = s.get("audio") or []
        resolved_auds, kept_labels = [], []
        for who in auds:
            u = owner_to_audio.get(who) or label_to_audio.get(who)
            if u:
                resolved_auds.append(u)
                kept_labels.append(who)


        s["audio_urls"] = resolved_auds
        s["audio"] = kept_labels


        if resolved_auds:
            resolved_audio_keys = set()
            for r in rows:
                if r.get("type") == "audio" and r.get("url") in resolved_auds:
                    if r.get("owner"):
                        resolved_audio_keys.add(r["owner"])
                    if r.get("label"):
                        resolved_audio_keys.add(r["label"])
            for c in (s.get("characters") or []):
                if (c.get("label") or "").strip() in resolved_audio_keys:
                    c["voice_source"] = "reference_audio"




    for _i, _s in enumerate(shots, 1):
        if not isinstance(_s.get("shot_no"), int):
            _s["shot_no"] = _i

    _strictly_validate_shots(shots, rows, script)

    shots = _enforce_visual_lock(shots, rows, script, video_model)


    if not shots:
        raise RuntimeError(
            "优化器未产出任何分镜（LLM 返回 shots=[]）。"
            "请直接重试；若反复出现可缩短脚本或拆成更少的逻辑段再提交。"
        )
    return {"shots": shots}


def _split_script_by_shot(script: str):
    
    return re.split(r'\n?\s*镜头\s*\d+\s*[|:：｜]', script or "")


def _label_candidates_from_name(name: str):
    
    cands = []
    base = os.path.splitext(os.path.basename(name or ""))[0]

    stripped = re.sub(r'^lv_[a-f0-9]{6,}_?', '', base, flags=re.IGNORECASE).strip("_")
    if stripped and stripped != base:
        cands.append(stripped)

        for m in re.findall(r'[\u4e00-\u9fff]+', stripped):
            if len(m) >= 2 and m not in cands:
                cands.append(m)

    if not cands and base:
        for m in re.findall(r'[\u4e00-\u9fff]+', base):
            if len(m) >= 2 and m not in cands:
                cands.append(m)
    return cands


def _norm_text(s):
    
    return re.sub(r'[\s『』「」""“”\'\'《》<> ,。，！？!?；：…—\-_/\\]', '', s or "")


def _str_in_script(needle, hay):
    n = _norm_text(needle)
    h = _norm_text(hay)
    return bool(n) and (n in h)


def _strictly_validate_shots(shots, rows, script):
    
    parts = _split_script_by_shot(script)

    name_to_label = {}
    label_to_names = {}
    name_to_kind = {}




    for r in rows:
        if r.get("type") == "image":
            lab = (r.get("label") or r.get("owner") or "").strip()

            if not lab:
                cands = _label_candidates_from_name(r["name"])
                if cands:
                    lab = cands[0]
            if lab:
                name_to_label[r["name"]] = lab
                label_to_names.setdefault(lab, []).append(r["name"])
            name_to_kind[r["name"]] = (r.get("kind") or "character").strip()

    for s in shots:
        idx = (s.get("shot_no") or 1) - 1

        if 1 <= idx + 1 < len(parts):
            shot_text = parts[idx + 1]
        else:
            shot_text = parts[0] if parts else script
        shot_text = shot_text or ""


        for c in (s.get("characters") or []):
            label = (c.get("label") or "").strip()
            if not label:
                c["matched"] = False
                continue
            matched = _str_in_script(label, shot_text)

            if not matched:
                for r in rows:
                    if r.get("type") == "image":
                        ow = (r.get("owner") or "").strip()
                        lab2 = (r.get("label") or "").strip()
                        if ow and _str_in_script(ow, shot_text) and (label in lab2 or lab2 in label or label in ow):
                            matched = True
                            break

            if not matched:
                for short in re.findall(r'[\u4e00-\u9fff]{2,4}', label):
                    if _str_in_script(short, shot_text):
                        matched = True
                        break
            c["matched"] = bool(matched)


        kept_imgs_names, kept_imgs_urls, removed_names, kept_indices = [], [], [], []
        img_names = s.get("images") or []
        img_urls = s.get("images_urls") or []

        for i, k in enumerate(img_names):
            if k == "tail":
                kept_imgs_names.append(k)
                kept_imgs_urls.append(img_urls[i] if i < len(img_urls) else "tail")
                kept_indices.append(i)
                continue


            _kind = name_to_kind.get(k)
            if _kind in ("scene", "prop") and k in name_to_label:
                kept_imgs_names.append(k)
                kept_imgs_urls.append(img_urls[i] if i < len(img_urls) else None)
                kept_indices.append(i)
                continue
            label = name_to_label.get(k, k)
            in_script = _str_in_script(label, shot_text) if label else False

            if not in_script and label:
                for short in re.split(r'[·•/、（）() ]', label):
                    short = short.strip()
                    if len(short) >= 2 and _str_in_script(short, shot_text):
                        in_script = True
                        break
            if in_script:
                kept_imgs_names.append(k)
                kept_imgs_urls.append(img_urls[i] if i < len(img_urls) else None)
                kept_indices.append(i)
            else:
                removed_names.append(k)
        s["images"] = kept_imgs_names
        s["images_urls"] = kept_imgs_urls

        existing_unresolved = list(s.get("unresolved_images") or [])
        s["unresolved_images"] = [n for n in existing_unresolved if n not in removed_names] + [
            n for n in removed_names if n not in existing_unresolved
        ]


        for d in (s.get("dialogue") or []):
            line = (d.get("line") or "").strip()
            if not line:
                d["needs_review"] = True
                continue
            if _str_in_script(line, shot_text) or _str_in_script(line[: max(4, len(line) // 2)], shot_text):
                d["needs_review"] = bool(d.get("needs_review"))
            else:
                d["needs_review"] = True
                prefix = "[脚本片段中未找到具体台词] "
                if not line.startswith(prefix):
                    d["line"] = prefix + line


        st = dict(s.get("scene") or {})
        txt = (st.get("text") or "").strip()
        if txt and not _str_in_script(txt, shot_text):

            tokens = [t for t in re.split(r'[·•、，, ]', txt) if len(t) >= 2]
            kept_token = next((t for t in tokens if _str_in_script(t, shot_text)), "")
            st["text"] = kept_token
        s["scene"] = st


        kept_sfx = []
        for sx in (s.get("sfx") or []):
            if not sx or _str_in_script(sx, shot_text):
                kept_sfx.append(sx)
            else:

                tokens = [t for t in re.split(r'[、，, ]', sx) if len(t) >= 2]
                if any(_str_in_script(t, shot_text) for t in tokens):
                    kept_sfx.append(sx)
        s["sfx"] = kept_sfx

    return shots


def _concise_signature(ap):
    
    if not ap:
        return ""
    sig = []
    for line in ap.split("\n"):
        line = line.strip()
        if not line:
            continue
        for kw in ("毛色", "体型", "头部配饰", "上装"):
            m = re.search(kw + r"[：:]\s*([^，。；\n（）()]+)", line)
            if m:
                sig.append(m.group(1).strip())
                break
    s = "·".join(sig)
    if len(s) > 40 and '·' in s:
        s = s[:s.rfind('·')]
    return s[:40]


def _appearance_span(prompt, lbl):
    
    pat = re.compile(re.escape(lbl) + r'[（(](?!(?:音频\s*\d+))([\s\S]*?)[）]')
    best = None
    for m in pat.finditer(prompt):
        inner = m.group(1).strip()
        is_voice = bool(re.search(r'嗓音|声线|声|音|老|青|中|女|男|沙哑|清亮|偏低|偏高|软糯|憨|扁|正', inner))
        is_appear = bool(re.search(r'毛色|体型|服装|发型|帽|鞋|·|发带|开衫|裤|袍|衫|矮胖|虎斑|三花|橘', inner))
        if is_appear and not is_voice:
            return m
        if best is None and not is_voice:
            best = m
    return best


def _inject_appearance(prompt, lbl, sig):
    
    if not sig:
        return prompt
    for m in re.finditer(re.escape(lbl), prompt):
        pos = m.end()
        if prompt.count('『', 0, pos) - prompt.count('』', 0, pos) > 0:
            continue
        if pos < len(prompt) and prompt[pos] in '（(':
            continue
        return prompt[:pos] + '（' + sig + '）' + prompt[pos:]
    return prompt





_SHOT_DIRECTIVES = [
    ("performance", "表演"),
    ("micro_expression", "微表情"),
    ("lighting_mood", "光线氛围"),
    ("audio_cue", "音效"),
    ("exclusions", "画面禁止", True),
]


def _enforce_visual_lock(shots, rows, script=None, video_model=None):
    
    label_ap, name_kind, name_label = {}, {}, {}
    for r in rows:
        if r.get("type") == "image":
            lbl = (r.get("label") or "").strip()
            own = (r.get("owner") or "").strip()
            ap_txt = _appearance_display(r.get("appearance") or "")
            if lbl:
                label_ap[lbl] = ap_txt
            if own and own != lbl:
                label_ap[own] = ap_txt
            _prim = lbl or own or r.get("name")
            name_kind[r["name"]] = r.get("kind")
            name_label[r["name"]] = _prim
    audio_labels = set()
    for r in rows:
        if r.get("type") == "audio":
            for k in (r.get("label"), r.get("owner")):
                if k and str(k).strip():
                    audio_labels.add(str(k).strip())


    _img_labels = set()
    for r in rows:
        if r.get("type") == "image" and r.get("url"):
            for _k in (r.get("owner"), r.get("label")):
                if _k and str(_k).strip():
                    _img_labels.add(str(_k).strip())

    label_posture = {}

    _name_labels = {}
    _name_url = {}
    _name_kind = {}
    for r in rows:
        if r.get("type") == "image":
            _n = r.get("name")
            _l = (r.get("label") or "").strip()
            _o = (r.get("owner") or "").strip()
            if _n:
                _name_labels.setdefault(_n, set()).add(_n)
                _name_kind.setdefault(_n, (r.get("kind") or "").strip())
                if r.get("url"):
                    _name_url[_n] = r.get("url")
                if _l:
                    _name_labels[_n].add(_l)
                if _o and _o != _l:
                    _name_labels[_n].add(_o)
        _p = (r.get("posture") or "").strip()
        if _p:
            for _k in (r.get("label"), r.get("owner"), r.get("name")):
                if _k and str(_k).strip():
                    label_posture[str(_k).strip()] = _p
    seg_by_no = {}
    if script:
        parts = _split_script_by_shot(script)
        for sh in shots:
            idx = (sh.get("shot_no") or 1) - 1
            seg_by_no[sh.get("shot_no")] = (parts[idx + 1] if 1 <= idx + 1 < len(parts) else (parts[0] if parts else script)) or ""
    for sh in shots:
        prompt = sh.get("prompt") or ""

        _normalize_images(sh, rows)
        sn = sh.get("shot_no")
        changed = False



        for c in (sh.get("characters") or []):
            lbl = (c.get("label") or "").strip()
            if not lbl or lbl not in label_ap:
                continue
            if lbl in _img_labels:

                _m = re.search(re.escape(lbl) + r"[（(](?!(?:音频\s*\d+))([\s\S]*?)[）)]", prompt)
                if _m and re.search(r"毛色|体型|服装|发型|帽|鞋|·|发带|开衫|裤|袍|衫|矮胖|虎斑|三花|橘", _m.group(1)):

                    new_p = prompt[:_m.start() + len(lbl)] + prompt[_m.end():]
                    new_p = re.sub(r"([，、；])\s*([，、；])+", r"\1", new_p)
                    if new_p != prompt:
                        prompt = new_p
                        changed = True
                continue

            if _appearance_span(prompt, lbl):
                continue
            sig = _concise_signature(label_ap[lbl]) or (label_ap[lbl] or "")[:40]
            if sig:
                new_p = _inject_appearance(prompt, lbl, sig)
                if new_p != prompt:
                    prompt = new_p
                    c["appearance"] = sig
                    changed = True

        for c in (sh.get("characters") or []):
            _pl = (c.get("label") or "").strip()
            _pos = label_posture.get(_pl)
            if not _pos:
                continue
            _np = _inject_posture_everywhere(prompt, _pl, _pos)
            if _np != prompt:
                prompt = _np
                changed = True

        speaking = []
        for d in (sh.get("dialogue") or []):
            ch = (d.get("character") or "").strip()
            line = (d.get("line") or "").strip()
            if ch and line and ch not in speaking:
                speaking.append(ch)
        audio_new = [c for c in speaking if c in audio_labels]
        sh["audio"] = audio_new
        _url_by_owner = {r["owner"]: r["url"] for r in rows if r.get("type") == "audio" and r.get("owner")}
        _url_by_label = {r["label"]: r["url"] for r in rows if r.get("type") == "audio" and r.get("label")}
        sh["audio_urls"] = [
            (_url_by_owner.get(lbl) or _url_by_label.get(lbl))
            for lbl in audio_new
            if (_url_by_owner.get(lbl) or _url_by_label.get(lbl))
        ]





        if audio_new and (sh.get("images") or []):
            _img_chars = {}
            for _r in rows:
                if _r.get("type") == "image" and _r.get("name"):
                    _cands = set()
                    for _k in (_r.get("owner"), _r.get("label")):
                        if _k and str(_k).strip():
                            _cands.add(str(_k).strip())
                    if _cands:
                        _img_chars[_r["name"]] = _cands
            _imgs = list(sh.get("images") or [])
            _iurls = list(sh.get("images_urls") or [])
            _has_tail = bool(_imgs) and _imgs[0] == "tail"
            _head = [_imgs[0]] if _has_tail else []
            _head_u = [_iurls[0]] if _has_tail and _iurls else []
            _body_i = list(range(1 if _has_tail else 0, len(_imgs)))
            _bimgs = [_imgs[i] for i in _body_i]
            _bius = [_iurls[i] if i < len(_iurls) else None for i in _body_i]
            _new_b, _new_bu, _used = [], [], set()
            for _char in audio_new:
                for _j, _img in enumerate(_bimgs):
                    if _j in _used:
                        continue
                    if _char in _img_chars.get(_img, set()):
                        _new_b.append(_img)
                        _new_bu.append(_bius[_j])
                        _used.add(_j)
                        break
            for _j, _img in enumerate(_bimgs):
                if _j in _used:
                    continue
                _new_b.append(_img)
                _new_bu.append(_bius[_j])
            _new_images = _head + _new_b
            _new_urls = _head_u + _new_bu
            if _new_images != _imgs:
                sh["images"] = _new_images
                sh["images_urls"] = _new_urls
                changed = True


        _img_cap = _ref_caps(video_model)[0]
        _imgs_cur = list(sh.get("images") or [])
        _mentioned_names = []
        _seen_n = set()
        for _nm, _cset in _name_labels.items():
            if _nm in _seen_n:
                continue
            _allc = set(_cset)
            _allc.add(_nm)
            for _cs in _allc:
                if _cs and re.search(re.escape(_cs), prompt):
                    _mentioned_names.append(_nm)
                    _seen_n.add(_nm)
                    break
        _new_imgs = list(_imgs_cur)
        _new_urls = list(sh.get("images_urls") or [])
        for _nm in _mentioned_names:
            if _nm in _new_imgs:
                continue
            _is_scene = _name_kind.get(_nm) == "scene"
            _has_scene = any(_name_kind.get(_e) == "scene" for _e in _new_imgs)
            if _is_scene and _has_scene:

                if len(_new_imgs) < _img_cap:
                    continue


                for _i, _e in enumerate(_new_imgs):
                    if _name_kind.get(_e) == "scene" and not _explicitly_anchored(prompt, _e, _name_labels):
                        _new_imgs[_i] = _nm
                        _new_urls[_i] = _name_url.get(_nm)
                        print(f"[INFO] 方案B场景换绑 shot#{sh.get('shot_no')}: 图{_i+1} 由[{_e}]换为[{_nm}]", flush=True)
                        break
                continue
            if len(_new_imgs) >= _img_cap:


                continue
            _new_imgs.append(_nm)
            _new_urls.append(_name_url.get(_nm))
        if _new_imgs != _imgs_cur:
            sh["images"] = _new_imgs
            sh["images_urls"] = _new_urls
            changed = True



        _final_imgs = list(sh.get("images") or [])
        _np, _inj = _inject_ref_tokens(prompt, _final_imgs, audio_new, _name_labels, sh.get("dialogue"), label_posture)
        if _np != prompt:
            prompt = _np
            changed = True
        print(f"[INFO] 引用注入 shot#{sh.get('shot_no')}: 图{_inj['img']} 音频{_inj['aud']}", flush=True)





        for _spk in speaking:
            if _spk not in audio_new:
                sh.setdefault("_bind_warn", []).append("声线未登记：说话角色[%s]无音频引用" % _spk)
        new_p = re.sub(r'([，。、；])\s*([，。、；])+', r'\1', prompt)
        if new_p != prompt:
            prompt = new_p
            changed = True




        st = dict(sh.get("scene") or {})
        if not (st.get("text") or "").strip():
            seg = seg_by_no.get(sh.get("shot_no"), "")
            first = (seg.strip().split("\n")[0][:60] if seg.strip() else "")
            st["text"] = first or "（场景描述缺失，请补充）"
            changed = True
        sh["scene"] = st
        if changed:
            sh["prompt"] = prompt


        _max_iref = max([int(x) for x in re.findall(r'图(\d+)', prompt)] or [0])
        if _max_iref > len(sh.get("images") or []):
            _msg = "提示词引用图%d但images仅%d张" % (_max_iref, len(sh.get("images") or []))
            print(f"[WARN] 绑定自检(方案C) shot#{sh.get('shot_no')}: {_msg}", flush=True)
            sh.setdefault("_bind_warn", []).append(_msg)
        _max_aref = max([int(x) for x in re.findall(r'音频(\d+)', prompt)] or [0])
        if _max_aref > len(sh.get("audio") or []):
            _msg = "提示词引用音频%d但audio仅%d个" % (_max_aref, len(sh.get("audio") or []))
            print(f"[WARN] 绑定自检(方案C) shot#{sh.get('shot_no')}: {_msg}", flush=True)
            sh.setdefault("_bind_warn", []).append(_msg)


        sh["unresolved_images"] = [
            k for k in (sh.get("images") or []) if k != "tail" and k not in _name_url
        ]
    return shots


def _inject_posture_everywhere(prompt, lbl, pos):
    
    pre = pos

    pat = re.compile(r'(?<!' + re.escape(pos) + r')' + re.escape(lbl))
    def _cb(m):
        return pre + m.group(0)
    return pat.sub(_cb, prompt)


_REF_IMGTOK_RE = re.compile(r'图\s*\d+的')
_REF_IMGTOK_PAREN_RE = re.compile(r'[（(]图\s*\d+[）)]')
_REF_IMGDECL_RE = re.compile(r'参考图\s*\d+是')
_REF_AUDTOK_RE = re.compile(r'[（(]音频\s*\d+[）)]')
_REF_LEGACY_AUDIO_RE = re.compile(
    r'角色[「\'\"]?[^」\'\"]{1,12}[」\'\"]?使用音频\s*\d+\s*发声[，、；]?')
_REF_MOUTH_RE = re.compile(r'[，、；]?\s*(?:嘴形与台词同步|口型随台词动)')





_REF_VOICE_PAREN_RE = re.compile(r'[（(][^）)]*(?:声线|嗓音)[^）)]*[）)]')
_REF_VOICE_BARE_RE = re.compile(r'[^\s，。、；：（）()]{0,14}(?:声线|嗓音)地')


def _strip_ref_tokens(prompt):
    
    p = _REF_IMGDECL_RE.sub('参考', prompt)
    p = _REF_IMGTOK_RE.sub('', p)
    p = _REF_IMGTOK_PAREN_RE.sub('', p)
    p = _REF_AUDTOK_RE.sub('', p)
    p = _REF_LEGACY_AUDIO_RE.sub('', p)
    p = _REF_MOUTH_RE.sub('', p)
    p = _REF_VOICE_PAREN_RE.sub('', p)
    p = _REF_VOICE_BARE_RE.sub('', p)
    return p


def _normalize_images(sh, rows):
    
    name_by_key, url_by_name = {}, {}
    for r in rows:
        if r.get("type") == "image":
            nm = r.get("name")
            if nm:
                url_by_name[nm] = r.get("url")
                for k in (nm, r.get("label"), r.get("owner")):
                    if k and str(k).strip():
                        name_by_key.setdefault(str(k).strip(), nm)
    imgs = sh.get("images") or []
    if not imgs:
        return
    new_imgs, seen, new_urls = [], set(), []
    for entry in imgs:
        e = (entry or "").strip()
        if e == "tail":
            new_imgs.append("tail"); new_urls.append(None); seen.add("tail"); continue
        if not e:
            continue
        fn = name_by_key.get(e, e)
        if fn in seen:
            continue
        new_imgs.append(fn)
        new_urls.append(url_by_name.get(fn))
        seen.add(fn)
    sh["images"] = new_imgs
    sh["images_urls"] = new_urls


def _inject_ref_tokens(prompt, images, audio, name_labels, dialogue=None, label_posture=None):
    
    text = _strip_ref_tokens(prompt)


    occ = []
    for i, nm in enumerate(images or [], 1):
        if nm == "tail":
            continue
        for lb in sorted(name_labels.get(nm) or {nm}, key=len, reverse=True):
            for m in re.finditer(re.escape(lb), text):
                occ.append((m.start(), m.end(), lb, i))
    occ.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    kept, last_end = [], -1
    for o in occ:
        if o[0] < last_end:
            continue
        kept.append(o)
        last_end = o[1]
    for (s, e, lb, i) in sorted(kept, key=lambda t: -t[0]):
        head = text[:s]
        ins = s

        mp = re.search(r'（姿态：[^）]*）的$', head)
        if mp:
            ins = mp.start()
        elif label_posture and label_posture.get(lb):


            _pos = label_posture.get(lb)
            _p = head.rfind(_pos)
            if _p != -1 and _p + len(_pos) == s:
                ins = _p
        text = text[:ins] + ("图%d的" % i) + text[ins:]



    n_aud = 0
    SPEAK_RE = re.compile(r'[说说道问答喊叫念唱叹回应]')
    inserts = []
    for i, spk in enumerate(audio or [], 1):
        spk = (spk or "").strip()
        if not spk:
            continue

        lines = [(d.get("line") or "").strip()
                 for d in (dialogue or [])
                 if (d.get("character") or "").strip() == spk and (d.get("line") or "").strip()]
        if not lines:
            print(f"[WARN] 音频注入: 说话角色[{spk}]无台词，音频{i}无锚点", flush=True)
            continue
        for line in lines:
            k = text.find(line[:8])
            if k < 0:
                continue

            q = -1
            for _oc in ('“', '「', '"'):
                _qq = text.rfind(_oc, 0, k)
                if _qq > q:
                    q = _qq
            if q < 0:
                continue

            seg_start = max(text.rfind("。", 0, q), text.rfind("”", 0, q),
                            text.rfind("」", 0, q), text.rfind('"', 0, q))
            seg = text[seg_start + 1: q]

            if spk not in seg:
                continue

            verbs = list(SPEAK_RE.finditer(seg))
            if not verbs:

                continue
            v = verbs[-1]
            verb_end = seg_start + 1 + v.end()
            inserts.append((verb_end, "（音频%d）" % i))
            n_aud += 1

    for pos, marker in sorted(inserts, key=lambda t: -t[0]):
        text = text[:pos] + marker + text[pos:]

    text = re.sub(r'([一-鿿])[，,]([说说道问答喊叫念唱叹回应])', r'\1\2', text)
    text = re.sub(r'（音频(\d)）\s*[，,]\s*(?=[「“"])', r'（音频\1）', text)
    return text, {"img": len(kept), "aud": n_aud}

def _post_with_retry(url, headers=None, json=None, timeout=120, max_retries=2, base_backoff=5):
    
    import requests.exceptions as _rex
    backoff = base_backoff
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(url, headers=headers, json=json, timeout=timeout)
        except (_rex.ReadTimeout, _rex.ConnectionError) as e:
            last_exc = e
            if attempt < max_retries:
                print(f"[WARN] 优化器 POST 网络异常（{type(e).__name__}），{backoff}s 后重试 "
                      f"({attempt + 1}/{max_retries})")
                time.sleep(backoff)
                backoff *= 3
                continue
            raise
        except _rex.RequestException as e:

            raise

        if r.status_code >= 500:
            last_exc = RuntimeError(f"优化器 LLM 返回 {r.status_code}: {r.text[:300]}")
            if attempt < max_retries:
                print(f"[WARN] 优化器 LLM 5xx({r.status_code})，{backoff}s 后重试 "
                      f"({attempt + 1}/{max_retries})")
                time.sleep(backoff)
                backoff *= 3
                continue
            raise last_exc
        return r

    if last_exc:
        raise last_exc
    raise RuntimeError("优化器 POST 重试异常")





class _FakeResp:
    

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._b = body
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._b


def _ark_create_video(images_urls, audio_urls, prompt, seconds, mode="reference", size="720P", model=None):
    
    try:
        import server.ark_provider as _ark
    except Exception as e:
        return _FakeResp(500, {"error": {"message": f"方舟模块不可用：{e}"}})
    payload, err = _ark.to_ark_video_payload(
        {"model": model, "prompt": prompt, "mode": mode, "seconds": seconds, "size": size,
         "images": images_urls or [], "audios": audio_urls or []},
        b64_fn=_local_to_b64)
    if err:
        return _FakeResp(400, {"error": {"message": err}})
    key = _ark.get("api_key") or ""
    if not key:
        return _FakeResp(401, {"error": {"message": "方舟未配置访问密钥"}})
    base = (_ark.get("base_url") or "").rstrip("/")
    try:
        return requests.post(
            f"{base}/contents/generations/tasks",
            json=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=(10, 120),
        )
    except requests.RequestException as e:
        return _FakeResp(503, {"error": {"message": f"请求方舟失败：{e}"}})


def _ark_poll_video(video_id, timeout=600):
    
    import server.ark_provider as _ark
    base = (_ark.get("base_url") or "").rstrip("/")
    key = _ark.get("api_key") or ""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            resp = requests.get(
                f"{base}/contents/generations/tasks/{video_id}",
                headers={"Authorization": f"Bearer {key}"},
                timeout=30,
            )
            body = resp.json()
        except Exception:
            time.sleep(8)
            continue
        st = str(body.get("status") or "").lower()
        if st == "succeeded":
            url = (body.get("content") or {}).get("video_url")
            return ("completed", url) if url else ("failed", None)
        if st in ("failed", "expired", "cancelled"):
            return "failed", None
        time.sleep(8)
    return "timeout", None


def _agnes_create_video(images_urls, audio_urls, prompt, seconds, attempt=0, mode="reference",
                      size="720P", aspect_ratio="16:9", model=None):
    
    if _is_ark_model(model):
        return _ark_create_video(images_urls, audio_urls, prompt, seconds, mode=mode, size=size, model=model)
    payload = {
        "model": model or _cfg_video_model(),
        "prompt": prompt,
        "seconds": str(int(seconds)),
        "mode": mode,
        "size": size,
        "aspect_ratio": aspect_ratio,
    }
    if mode == "reference":
        _img_cap, _aud_cap = _ref_caps(model)
        if images_urls:
            payload["images"] = [_local_to_b64(u) for u in images_urls[:_img_cap]]
        if audio_urls:
            payload["audios"] = [_local_to_b64(u) for u in audio_urls[:_aud_cap]]
    resp = requests.post(
        f"{_cfg_base()}/videos",
        headers={"Authorization": f"Bearer {_cfg_key()}", "Content-Type": "application/json"},
        json=payload, timeout=(10, 300),
    )
    return resp


def _agnes_poll(video_id, timeout=600, model=None):
    
    if _is_ark_model(model):
        return _ark_poll_video(video_id, timeout)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            resp = requests.get(
                _cfg_poll(),
                params={"video_id": video_id, "model_name": model or _cfg_video_model()},
                headers={"Authorization": f"Bearer {_cfg_key()}"},
                timeout=30,
            )
            body = resp.json()
        except Exception:
            time.sleep(8)
            continue
        status = body.get("status") or body.get("task_status") or "processing"
        video_url = (
            (body.get("metadata") or {}).get("url")
            or body.get("video_url") or body.get("url")
            or (body.get("result") or {}).get("video_url")
        )
        if status in ("completed", "success", "done") and video_url:
            return "completed", video_url
        if status in ("failed", "error"):
            return "failed", None
        time.sleep(8)
    return "timeout", None


def _download(url, out_path):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return len(r.content)





lv_bp = Blueprint("longvideo", __name__, url_prefix="/api")


def _archive_segment_video(job_id, seg_no, ver, keep=3):
    
    if not ver or ver <= 0:
        return
    out_dir = os.path.join(JOBS_DIR, job_id)
    main = os.path.join(out_dir, f"seg_{seg_no:02d}.mp4")
    try:
        if not os.path.exists(main):
            return
        dst = os.path.join(out_dir, f"seg_{seg_no:02d}_v{ver}.mp4")
        if os.path.exists(dst):
            os.remove(dst)
        os.rename(main, dst)

        vers = []
        if os.path.isdir(out_dir):
            for f in os.listdir(out_dir):
                m = re.match(rf"seg_{seg_no:02d}_v(\d+)\.mp4$", f)
                if m:
                    vers.append(int(m.group(1)))
        for v in sorted(vers)[:-keep] if len(vers) > keep else []:
            try:
                os.remove(os.path.join(out_dir, f"seg_{seg_no:02d}_v{v}.mp4"))
            except OSError:
                pass
        print(f"[INFO] #260 归档 job={job_id} seg#{seg_no}: 旧画面转存 v{ver}（保留最近 {keep} 版）", flush=True)
    except Exception as e:

        print(f"[WARN] #260 归档失败 job={job_id} seg#{seg_no}: {e}（继续重提，不保留旧版）", flush=True)


def _job_video_model(job_id):
    
    con = _db()
    try:
        row = con.execute(
            "SELECT gen_params_json FROM lv_jobs WHERE id=?", (job_id,)
        ).fetchone()
    finally:
        con.close()
    try:
        gp = json.loads(row["gen_params_json"]) if row and row["gen_params_json"] else {}
    except Exception:
        gp = {}
    return (gp.get("model") or "").strip() or _cfg_video_model()


def _resume_segment(job_id, seg):
    
    video_id = seg["video_id"]
    seg_no = seg["seg_no"]
    print(f"[PIPE] seg#{seg_no} 断点恢复：按 video_id={video_id[:18]}… 继续追踪（不重复提交）", flush=True)
    status, video_url = _agnes_poll(video_id, timeout=900, model=_job_video_model(job_id))
    if status != "completed" or not video_url:
        return False, None, None, f"恢复追踪未完成: {status}"
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)
    local = os.path.join(out_dir, f"seg_{seg_no:02d}.mp4")

    try:
        _download(video_url, local)
    except Exception as e:
        return False, None, None, f"恢复下载失败 {type(e).__name__}: {e}"
    tail = _extract_tail_frame(local)


    _register_segment_asset(job_id, seg_no, local)
    return True, local, tail, None


def _register_segment_asset(job_id, seg_no, local_path):
    
    if not local_path:
        return None
    try:
        return _assets_store.register(
            name="%s/seg_%02d.mp4" % (job_id, seg_no),
            url="/api/jobs/%s/segment/%d.mp4" % (job_id, seg_no),
            type="video",
            origin=_assets_store.ORIGIN_CREATED,
            job_id=job_id,
        )
    except Exception as e:
        print(f"[warn] 视频片段入库失败 job={job_id} seg#{seg_no}: {e}", flush=True)
        return None


def _register_final_asset(job_id):
    
    if not job_id:
        return None
    try:
        return _assets_store.register(
            name="%s/final.mp4" % job_id,
            url="/api/jobs/%s/final.mp4" % job_id,
            type="video",
            origin=_assets_store.ORIGIN_CREATED,
            job_id=job_id,
        )
    except Exception as e:
        print(f"[warn] 成片入库失败 job={job_id}: {e}", flush=True)
        return None


def _gen_segment(job_id, seg, prev_tail_b64):
    






    _c0 = _db()
    try:
        _cur = _c0.execute(
            "SELECT started_at FROM lv_segments WHERE job_id=? AND seg_no=?", (job_id, seg["seg_no"])
        ).fetchone()
    finally:
        _c0.close()
    if not (_cur and _cur["started_at"]):
        _update_seg(job_id, seg["seg_no"], started_at=time.time())




    seg_model = _job_video_model(job_id)

    mode = "reference"








    _stored_imgs = seg.get("images_keys") or seg.get("images") or "[]"
    if isinstance(_stored_imgs, str):
        try:
            _stored_imgs = json.loads(_stored_imgs)
        except Exception:
            _stored_imgs = []
    _slot0_is_tail = bool(_stored_imgs) and _stored_imgs[0] == "tail"
    images_urls = []
    if seg["is_continuation"] and prev_tail_b64 and _slot0_is_tail:
        images_urls.append(prev_tail_b64)
    for u in (json.loads(seg["images_urls"] or "[]")):
        if u == "tail":

            continue
        if u is None:




            continue
        images_urls.append(u)
    audio_urls = json.loads(seg["audio_urls"] or "[]")
    _img_cap, _aud_cap = _ref_caps(seg_model)
    if len(images_urls) > _img_cap:
        images_urls = images_urls[:_img_cap]


    if len(audio_urls) > _aud_cap:
        audio_urls = audio_urls[:_aud_cap]


    if not images_urls and not audio_urls:
        mode = "text"

    prompt = seg["prompt"]




    prompt = re.sub(r"[​‌‍⁠﻿]", "", prompt)







    if _slot0_is_tail and not (seg["is_continuation"] and prev_tail_b64):
        def _renum(m):
            _n = int(m.group(1))
            return "图%d" % (_n - 1) if _n > 1 else ""
        prompt = re.sub(r"图\s*(\d+)", _renum, prompt)
        prompt = re.sub(r"[（(]\s*[）)]", "", prompt)

    _audio_labels = json.loads(seg.get("audio") or "[]")
    if audio_urls and _audio_labels:




        prompt = re.sub(r"[（(]\s*音频\s*(\d+)\s*[)）]", r"<Audio \1>", prompt)




        prompt = re.sub(r"音频\s*(\d+)", r"<Audio \1>", prompt)


        prompt = re.sub(r"<Audio\s*(\d+)\s*>",
                        lambda m: m.group(0) if int(m.group(1)) <= len(audio_urls) else "",
                        prompt)








    if images_urls:
        prompt = re.sub(r"参考图\s*(\d+)", lambda m: f"<Picture {m.group(1)}>", prompt)
        prompt = re.sub(r"图\s*(\d+)", lambda m: f"<Picture {m.group(1)}>", prompt)

        prompt = re.sub(r"<Picture\s*(\d+)\s*>",
                        lambda m: m.group(0) if int(m.group(1)) <= len(images_urls) else "",
                        prompt)









    if seg["is_continuation"] and _slot0_is_tail and prev_tail_b64 and "<Picture 1>" not in prompt:
        prompt = "<Picture 1> " + prompt



    for _i in range(1, len(audio_urls) + 1):
        _tag = "<Audio %d>" % _i
        if _tag not in prompt:
            _who = _audio_labels[_i - 1] if _i - 1 < len(_audio_labels) else "?"
            print(f"[WARN] 音频未绑定 job={job_id} shot#{seg.get('shot_no')}: 音频{_i}[{_who}] "
                  f"已发送但提示词无 {_tag} 引用（需在提示词中提及该角色名，或写成规范的（音频{_i}））",
                  flush=True)

    _img_names = seg.get("images_keys") or seg.get("images") or []
    if isinstance(_img_names, str):
        try:
            _img_names = json.loads(_img_names)
        except Exception:
            _img_names = []
    for _i in range(1, len(images_urls) + 1):
        _tag = "<Picture %d>" % _i
        if _tag not in prompt:
            _who = _img_names[_i - 1] if _i - 1 < len(_img_names) else "?"
            print(f"[WARN] 图片未绑定 job={job_id} shot#{seg.get('shot_no')}: 图{_i}[{_who}] "
                  f"已发送但提示词无 {_tag} 引用（需在提示词中提及该素材名）",
                  flush=True)
    _lo, _hi = _seg_bounds(seg_model)
    seconds = max(_lo, min(_hi, int(seg["seconds"] or 5)))

    size = (seg.get("resolution") or "").strip() or "720P"
    aspect = (seg.get("aspect_ratio") or "").strip() or "16:9"



    is_paid = "flash" not in (seg_model or "")
    max_attempts = 3 if is_paid else 6
    poll_timeout = 1200 if is_paid else 600

    video_id = None
    _last_err = ""
    for attempt in range(max_attempts):
        if _job_cancelled(job_id):
            return False, None, None, "任务已停止（cancel），中止提交"
        try:
            resp = _agnes_create_video(images_urls, audio_urls, prompt, seconds, attempt, mode,
                                       size=size, aspect_ratio=aspect, model=seg_model)
        except requests.RequestException as e:
            _last_err = f"网络异常 {type(e).__name__}: {e}"
            if _cancelable_sleep(job_id, SEG_GAP_SEC):
                return False, None, None, "任务已停止（cancel），中止重试提交"
            continue
        if resp.status_code == 429:
            _last_err = "429 限流"
            gap = min(_JOB_GAP.get(job_id, SEG_GAP_SEC) * 2, _GAP_MAX_SEC)
            _JOB_GAP[job_id] = gap
            wait = gap
            print(f"[WARN] 提交限流(429) job={job_id} seg#{seg['seg_no']} 第{attempt + 1}/{max_attempts}次，"
                  f"{wait}s 后重试（发射间隔自适应→{gap}s）", flush=True)
            if _cancelable_sleep(job_id, wait):
                return False, None, None, "任务已停止（cancel），中止重试提交"
            continue
        if resp.status_code >= 500:


            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            _last_err = f"Agnes {resp.status_code}: {str(detail)[:200]}"
            gap = min(_JOB_GAP.get(job_id, SEG_GAP_SEC) * 2, _GAP_MAX_SEC)
            _JOB_GAP[job_id] = gap
            wait = gap
            print(f"[WARN] 平台瞬态({resp.status_code}) job={job_id} seg#{seg['seg_no']} "
                  f"第{attempt + 1}/{max_attempts}次，{wait}s 后重试（发射间隔自适应→{gap}s）: {str(detail)[:160]}", flush=True)
            if _cancelable_sleep(job_id, wait):
                return False, None, None, "任务已停止（cancel），中止重试提交"
            continue
        if resp.status_code != 200:

            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            return False, None, None, f"Agnes 拒绝({resp.status_code}): {detail}"
        body = resp.json()
        video_id = body.get("video_id") or body.get("id") or body.get("task_id")
        break
    if not video_id:
        return False, None, None, f"创建视频任务失败（已自动重试{max_attempts}次）：{_last_err or '限流/网络'}"


    _JOB_LAST_SUBMIT[job_id] = time.time()
    _JOB_GAP[job_id] = _submit_gap_base(seg_model)


    con = _db()
    try:
        con.execute("UPDATE lv_segments SET video_id=?, status='processing', updated_at=? WHERE job_id=? AND seg_no=?",
                    (video_id, time.time(), job_id, seg["seg_no"]))
        con.commit()
    finally:
        con.close()

    status, video_url = _agnes_poll(video_id, timeout=poll_timeout, model=seg_model)
    if status != "completed" or not video_url:
        return False, None, None, f"轮询未完成: {status}"

    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)
    local = os.path.join(out_dir, f"seg_{seg['seg_no']:02d}.mp4")


    try:
        _download(video_url, local)
    except Exception as e:
        return False, None, None, f"下载失败: {e}"
    tail_b64 = _extract_tail_frame(local)
    _register_segment_asset(job_id, seg["seg_no"], local)
    return True, local, tail_b64, None



_JOB_THREADS = {}





_JOB_LAST_SUBMIT = {}
_JOB_GAP = {}


def _ensure_running(job_id):
    
    t = _JOB_THREADS.get(job_id)
    if t and t.is_alive():
        return False
    th = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    _JOB_THREADS[job_id] = th
    th.start()
    return True


def _run_job(job_id):
    
    _JOB_THREADS[job_id] = threading.current_thread()
    con = _db()
    try:
        job = con.execute("SELECT * FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        seg_list = [dict(r) for r in con.execute(
            "SELECT * FROM lv_segments WHERE job_id=? ORDER BY seg_no", (job_id,)
        ).fetchall()]
    finally:
        con.close()
    if not job:
        return

    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)
    tails = {}
    seg_paths = {}
    results = {}
    state = {"stop_emit": False, "cancelled": False}
    _JOB_GAP[job_id] = _submit_gap_base(_job_video_model(job_id))


    for seg in seg_list:
        lp = seg.get("local_path")
        if lp and os.path.exists(lp):
            try:
                _finished_from_file = os.path.getmtime(lp)
            except OSError:
                _finished_from_file = time.time()
            tails[seg["seg_no"]] = seg.get("tail_frame") or _extract_tail_frame(lp)
            seg_paths[seg["seg_no"]] = lp
            _update_seg(job_id, seg["seg_no"], status="completed", finished_at=_finished_from_file)

            _JOB_LAST_SUBMIT[job_id] = time.time() - SEG_GAP_SEC

    def _cancelled():
        return _job_cancelled(job_id)

    def _gate():
        
        while not state["cancelled"]:
            now = time.time()
            anchor = _JOB_LAST_SUBMIT.get(job_id)
            if anchor is None:
                _JOB_LAST_SUBMIT[job_id] = now
                return
            wait = _JOB_GAP.get(job_id, SEG_GAP_SEC) - (now - anchor)
            if wait <= 0:
                _JOB_LAST_SUBMIT[job_id] = now
                return
            time.sleep(min(wait, 2.0))

    def _worker(seg, prev_tail):
        
        try:


            if (seg.get("video_id") and seg.get("status") == "processing"
                    and not (seg.get("local_path") and os.path.exists(seg.get("local_path")))):
                ok, local, tail, err = _resume_segment(job_id, seg)
            else:
                ok, local, tail, err = _gen_segment(job_id, seg, prev_tail)
        except Exception as e:
            ok, local, tail, err = False, None, None, f"生成线程异常 {type(e).__name__}: {e}"
        results[seg["seg_no"]] = {"ok": ok, "local": local, "tail": tail, "err": err}
        if ok:
            tails[seg["seg_no"]] = tail
            seg_paths[seg["seg_no"]] = local
            _update_seg(job_id, seg["seg_no"], status="completed",
                        local_path=local, tail_frame=tail, finished_at=time.time())
        else:

            if _cancelled():
                _update_seg(job_id, seg["seg_no"], status="cancelled", error=err)
            else:
                _update_seg(job_id, seg["seg_no"], status="failed", error=err)
                state["stop_emit"] = True

    threads = []
    emitted = set()

    def _emit(seg, prev_tail):
        t = threading.Thread(target=_worker, args=(seg, prev_tail), daemon=True)
        threads.append(t)
        t.start()
        emitted.add(seg["seg_no"])
        alive = sum(1 for x in threads if x.is_alive())
        print(f"[PIPE] 发射 seg#{seg['seg_no']}（{'续接' if seg['is_continuation'] else '非续接'}，"
              f"已发射 {len(emitted) + len(seg_paths)}/{len(seg_list)}，在飞 {alive}）", flush=True)



    _last_hb = 0.0
    while not state["stop_emit"] and not state["cancelled"]:
        try:

            if time.time() - _last_hb >= 30:
                print(f"[PIPE] 心跳：已发射={sorted(emitted)} 完成={sorted(seg_paths)} "
                      f"stop_emit={state['stop_emit']}", flush=True)
                _last_hb = time.time()
            if len(emitted) + len(seg_paths) >= len(seg_list):
                break
            if _cancelled():
                state["cancelled"] = True
                print(f"[INFO] 任务 {job_id} 已 cancelled，中止后续段发射", flush=True)
                break
            picked = None
            for idx, seg in enumerate(seg_list):
                n = seg["seg_no"]
                if n in emitted or n in seg_paths:
                    continue
                if seg["is_continuation"] and idx > 0:
                    dep_no = seg_list[idx - 1]["seg_no"]
                    if dep_no not in tails:
                        continue
                    picked = (seg, tails[dep_no])
                else:
                    picked = (seg, None)
                break
            if picked is None:
                time.sleep(2)
                continue
            seg, prev_tail = picked
            _gate()
            if state["stop_emit"] or state["cancelled"]:
                break
            _emit(seg, prev_tail)
        except Exception:


            import traceback as _tb
            print(f"[PIPE] ⚠️ 调度循环异常（已捕获继续）：\n{_tb.format_exc()}", flush=True)
            time.sleep(2)

    for t in threads:
        t.join()

    if state["cancelled"]:

        _JOB_THREADS.pop(job_id, None)
        _JOB_LAST_SUBMIT.pop(job_id, None); _JOB_GAP.pop(job_id, None)
        return





    _still_owned = True
    con = _db()
    try:
        _cur = con.execute("SELECT status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        _still_owned = bool(_cur) and _cur["status"] == "processing"
    finally:
        con.close()
    if not _still_owned:
        print(f"[INFO] 任务 {job_id} 已非 processing（外部已重置/删除），本轮生成结果作废，不写终态",
              flush=True)
        _JOB_THREADS.pop(job_id, None)
        _JOB_LAST_SUBMIT.pop(job_id, None); _JOB_GAP.pop(job_id, None)
        return

    failed = [n for n, r in results.items() if not r["ok"]]
    ok = (not failed) and len(seg_paths) == len(seg_list)
    if ok:


        ordered = [seg_paths[k] for k in sorted(seg_paths)]
        final_url = _concat_and_register(job_id, out_dir, ordered)
        _update_job(job_id, status="completed", final_url=final_url, error=None)


        _clear_tail_frames(job_id)




        for k in sorted(seg_paths):
            d = _probe_duration(seg_paths[k])
            if d:
                con = _db()
                try:
                    con.execute("UPDATE lv_segments SET real_seconds=? WHERE job_id=? AND seg_no=?",
                                (d, job_id, k))
                    con.commit()
                finally:
                    con.close()
    else:
        _update_job(job_id, status="failed", error="部分片段生成失败")
    _JOB_THREADS.pop(job_id, None)
    _JOB_LAST_SUBMIT.pop(job_id, None); _JOB_GAP.pop(job_id, None)


def _update_seg(job_id, seg_no, **fields):
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [job_id, seg_no]
    con = _db()
    try:
        con.execute(f"UPDATE lv_segments SET {cols} WHERE job_id=? AND seg_no=?", vals)
        con.commit()
    finally:
        con.close()


def _seg_jsonl(d, k):
    
    v = d.get(k) if isinstance(d, dict) else None
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    try:
        x = json.loads(v)
        return x if isinstance(x, list) else []
    except Exception:
        return []


def _update_job(job_id, **fields):
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [job_id]
    con = _db()
    try:
        con.execute(f"UPDATE lv_jobs SET {cols} WHERE id=?", vals)
        con.commit()
    finally:
        con.close()


@lv_bp.route("/optimizer", methods=["POST"])
def api_optimizer():
    


    try:
        import server.llm as _llm
        _ok, _why = _llm.configured("storyboard")
    except Exception:
        _ok, _why = (bool(_cfg_key()), "")
    if not _ok:
        return jsonify(error=_why or "尚未配置访问密钥（服务商设置或 .env）"), 500
    data = request.get_json(silent=True) or {}
    script = (data.get("script") or "").strip()
    job_id = (data.get("job_id") or "").strip() or None



    import server.llm as _llm
    llm_model = (data.get("llm_model") or "").strip()
    _allowed = _llm.models_for("storyboard")
    _fb = _llm.default_model("storyboard")
    print(f"[OPT-诊断] 收到请求 llm_model={llm_model!r} 后端={_llm.route('storyboard')} -> 实际采用={ (llm_model if llm_model in _allowed else _fb)!r}", flush=True)
    if llm_model not in _allowed:
        llm_model = _fb
    if not script:
        return jsonify(error="缺少 script"), 400
    video_model = (data.get("video_model") or "").strip() or None
    rows = _load_registry_rows(job_id)
    try:
        result = _optimize(script, rows, llm_model, video_model)
    except RuntimeError as e:

        import traceback as _tb
        return jsonify(error=str(e),
                       detail="优化器调用失败：长脚本偶发（网络超时 / 模型未走工具）。请直接重试；"
                              "若反复出现可缩短脚本或拆段提交。",
                       trace=_tb.format_exc(limit=4)), 502
    except Exception as e:
        import traceback as _tb
        return jsonify(error=f"优化失败：{e}", trace=_tb.format_exc(limit=4)), 500

    if isinstance(result, dict):
        result["llm_model"] = llm_model


        result["video_model"] = video_model or _cfg_video_model()
        result["sec_bounds"] = list(_seg_bounds(video_model))
    return jsonify(result)


@lv_bp.route("/jobs", methods=["POST"])
def api_create_job():
    
    if not _cfg_key():
        return jsonify(error="尚未配置访问密钥（服务商设置或 .env）"), 500
    data = request.get_json(silent=True) or {}
    script = (data.get("script") or "").strip()
    shots = data.get("shots")
    job_id = (data.get("job_id") or "").strip() or None


    gen_params = _norm_gen_params(data.get("gen_params"))

    if not shots:
        if not script:
            return jsonify(error="需要 script 或 shots"), 400
        rows = _load_registry_rows(job_id)
        try:
            opt = _optimize(script, rows, video_model=gen_params["model"])
            shots = opt["shots"]
        except Exception as e:
            return jsonify(error=f"优化失败：{e}"), 500
    if not shots:
        return jsonify(error="未产出分镜"), 400

    assets_json = json.dumps(data.get("assets", []), ensure_ascii=False)
    shots_json = json.dumps(shots, ensure_ascii=False)
    gen_params_json = json.dumps(gen_params, ensure_ascii=False)




    _name_provided = "name" in data
    name = None
    _old_hist = {}
    con = _db()
    try:
        existing = job_id and con.execute(
            "SELECT id,status FROM lv_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if existing:



            if existing["status"] == "processing":
                return jsonify(error="该任务正在生成中，请等待完成后再操作"), 409



            _proc = con.execute(
                "SELECT COUNT(*) c FROM lv_segments WHERE job_id=? AND status='processing'",
                (job_id,),
            ).fetchone()["c"]
            if _proc:
                return jsonify(error=f"该任务有 {_proc} 个段落正在重提，请等待其完成后再重新生成全部"), 409




            for _r in con.execute(
                "SELECT seg_no,prompt,prompt_history FROM lv_segments WHERE job_id=? AND prompt_history IS NOT NULL",
                (job_id,),
            ):
                if _r["prompt_history"]:
                    _old_hist[_r["seg_no"]] = _r["prompt_history"]
            con.execute("DELETE FROM lv_segments WHERE job_id=?", (job_id,))
            if _name_provided:
                name = (data.get("name") or "").strip()[:60] or None
            else:

                _cur = con.execute("SELECT name FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
                name = _cur["name"] if _cur else None



            con.execute(
                "UPDATE lv_jobs SET status=?, stage=?, script=?, segment_count=?, assets_json=?, shots_json=?, gen_params_json=?, name=?, final_url=NULL, updated_at=? WHERE id=?",
                ("processing", "生成中", script, len(shots), assets_json, shots_json, gen_params_json, name, time.time(), job_id),
            )
        else:
            job_id = uuid.uuid4().hex[:12]
            if _name_provided:
                _ins_name = (data.get("name") or "").strip()[:60] or None
            else:
                _t = time.gmtime(time.time() + 8 * 3600)
                _ins_name = f"任务 {_t.tm_mon}/{_t.tm_mday} {_t.tm_hour:02d}:{_t.tm_min:02d}"
            con.execute(
                "INSERT INTO lv_jobs(id,script,status,stage,segment_count,assets_json,shots_json,gen_params_json,name,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, script, "processing", "生成中", len(shots), assets_json, shots_json, gen_params_json, _ins_name, time.time(), time.time()),
            )

        seg_aspect = gen_params.get("aspect_ratio") or ""
        seg_resolution = gen_params.get("resolution") or ""



        _sb_lo, _sb_hi = _seg_bounds(gen_params["model"])
        for idx, s in enumerate(shots, start=1):
            aspect = (s.get("aspect_ratio") or "").strip() or seg_aspect
            resolution = (s.get("resolution") or "").strip() or seg_resolution
            try:
                _sec = int(s.get("estimated_seconds") or 5)
            except (TypeError, ValueError):
                _sec = 5
            _sec = max(_sb_lo, min(_sb_hi, _sec))
            con.execute(
                """INSERT INTO lv_segments(job_id,seg_no,shot_no,is_continuation,prompt,seconds,
                   images_keys,images_urls,audio_urls,audio,mode,aspect_ratio,resolution,status,started_at,created_at,updated_at,prompt_history)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, idx, s.get("shot_no", idx),
                    1 if s.get("is_continuation") else 0,
                    s.get("prompt", ""), _sec,
                    json.dumps(s.get("images", []), ensure_ascii=False),
                    json.dumps(s.get("images_urls", []), ensure_ascii=False),
                    json.dumps(s.get("audio_urls", []), ensure_ascii=False),
                    json.dumps(s.get("audio", []), ensure_ascii=False),
                    s.get("mode", "reference"),
                    aspect, resolution,
                    "pending", 0.0, time.time(), time.time(),
                    _old_hist.get(idx),
                ),
            )




        try:
            _purge_stale_seg_files(job_id, len(shots))
        except Exception as e:
            logging.getLogger(__name__).warning("清理多余段文件异常 %s: %s", job_id, e)

        _sid = (data.get("session_id") or data.get("sessionId") or "").strip()
        if job_id and _sid:
            con.execute("UPDATE lv_jobs SET session_id=? WHERE id=?", (_sid, job_id))
        con.commit()
    finally:
        con.close()

    _ensure_running(job_id)
    return jsonify(job_id=job_id, segment_count=len(shots), status="processing")


@lv_bp.route("/jobs/draft", methods=["POST"])
def api_save_draft():
    
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    stage = data.get("stage") or "素材登记"
    script = data.get("script", "")
    assets = data.get("assets", [])
    shots = data.get("shots", [])

    gen_params = _norm_gen_params(data.get("gen_params"))





    _has_name_in_payload = "name" in data
    if _has_name_in_payload:
        _new_name = (data.get("name") or "").strip()[:60] or None
    else:
        _new_name = None
    assets_json = json.dumps(assets, ensure_ascii=False)
    shots_json = json.dumps(shots, ensure_ascii=False)
    gen_params_json = json.dumps(gen_params, ensure_ascii=False)
    con = _db()
    try:
        row = job_id and con.execute("SELECT id FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if row:
            if _has_name_in_payload:
                con.execute(
                    "UPDATE lv_jobs SET stage=?, script=?, assets_json=?, shots_json=?, segment_count=?, gen_params_json=?, name=?, updated_at=? WHERE id=?",
                    (stage, script, assets_json, shots_json, len(shots), gen_params_json, _new_name, time.time(), job_id),
                )
            else:
                con.execute(
                    "UPDATE lv_jobs SET stage=?, script=?, assets_json=?, shots_json=?, segment_count=?, gen_params_json=?, updated_at=? WHERE id=?",
                    (stage, script, assets_json, shots_json, len(shots), gen_params_json, time.time(), job_id),
                )
        else:
            job_id = uuid.uuid4().hex[:12]
            if _has_name_in_payload:
                _ins_name = _new_name
            else:

                _t = time.gmtime(time.time() + 8 * 3600)
                _ins_name = f"任务 {_t.tm_mon}/{_t.tm_mday} {_t.tm_hour:02d}:{_t.tm_min:02d}"
            con.execute(
                "INSERT INTO lv_jobs(id,script,status,stage,segment_count,assets_json,shots_json,gen_params_json,name,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, script, "draft", stage, len(shots), assets_json, shots_json, gen_params_json, _ins_name, time.time(), time.time()),
            )

        _sid = (data.get("session_id") or data.get("sessionId") or "").strip() if isinstance(data, dict) else ""
        if job_id and _sid:
            con.execute("UPDATE lv_jobs SET session_id=? WHERE id=?", (_sid, job_id))
        con.commit()
    finally:
        con.close()
    return jsonify(job_id=job_id, status="draft", stage=stage, gen_params=gen_params)


@lv_bp.route("/jobs/<job_id>", methods=["GET"])
def api_get_job(job_id):
    con = _db()
    try:
        job = con.execute("SELECT * FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        segs = con.execute(
            "SELECT seg_no,shot_no,is_continuation,prompt,seconds,status,local_path,video_id,error,mode,"
            "audio,audio_urls,images_keys,images_urls,started_at,finished_at,real_seconds,created_at,updated_at,prompt_history "
            "FROM lv_segments WHERE job_id=? ORDER BY seg_no", (job_id,)
        ).fetchall()
    finally:
        con.close()
    def _jsonl(d, k):
        v = d.get(k)
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return v
        try:
            return json.loads(v)
        except Exception:
            return []
    job = dict(job)
    seg_norm = []
    for s in segs:
        s = dict(s)
        s["audio"] = _jsonl(s, "audio")
        s["audio_urls"] = _jsonl(s, "audio_urls")
        s["images_keys"] = _jsonl(s, "images_keys")
        s["images_urls"] = _jsonl(s, "images_urls")
        s["prompt_history"] = _jsonl(s, "prompt_history")
        seg_norm.append(s)

    try:
        _sh = json.loads(job.get("shots_history") or "[]")
        if not isinstance(_sh, list):
            _sh = []
    except Exception:
        _sh = []
    shots_hist_meta = [
        {"idx": i, "ts": v.get("ts"), "source": v.get("source") or "",
         "shot_count": len(v.get("shots") or [])}
        for i, v in enumerate(_sh)
    ]
    return jsonify(
        job=job,
        segments=seg_norm,
        final_url=job.get("final_url"),
        script=job.get("script"),
        stage=job.get("stage"),
        assets=_attach_appearance(json.loads(job.get("assets_json") or "[]")),
        shots=json.loads(job.get("shots_json") or "[]"),
        gen_params=_norm_gen_params(json.loads(job.get("gen_params_json") or "{}")),
        shots_history=shots_hist_meta,
        current_shot_ver=job.get("current_shot_ver"),
    )


@lv_bp.route("/jobs", methods=["GET"])
def api_list_jobs():
    
    import datetime as _dt
    con = _db()
    try:
        rows = con.execute(
            "SELECT id,status,stage,segment_count,created_at,updated_at,error,name "
            "FROM lv_jobs ORDER BY created_at DESC"
        ).fetchall()
        items = []
        for j in rows:
            j = dict(j)
            segs = con.execute(
                "SELECT status FROM lv_segments WHERE job_id=?", (j["id"],)
            ).fetchall()
            done = sum(1 for s in segs if s["status"] == "completed")
            stage = j.get("stage") or (
                "生成中" if j["status"] == "processing" else
                "成片预览" if j["status"] == "completed" else
                "失败" if j["status"] == "failed" else
                "草稿"
            )


            _name = (j.get("name") or "").strip()
            if not _name:
                _local = _dt.datetime.utcfromtimestamp(j["created_at"]) + _dt.timedelta(hours=8)
                _name = f"任务 {_local.month}/{_local.day} {_local.hour:02d}:{_local.minute:02d}"
            items.append({
                "job_id": j["id"],
                "status": j["status"],
                "stage": stage,
                "name": _name,
                "segment_count": j["segment_count"],
                "done_count": done,
                "created_at": j["created_at"],
                "error": j["error"],
            })
    finally:
        con.close()
    return jsonify(jobs=items)


@lv_bp.route("/jobs/<job_id>", methods=["PATCH"])
def api_patch_job(job_id):
    
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str):
        return jsonify(error="name 必须是字符串"), 400
    name = name.strip()

    import logging as _lg
    _lg.warning(f"PATCH /api/jobs/{job_id} name_repr={name!r} len={len(name)}")


    if not name:
        return jsonify(error="任务名不能为空"), 400
    if len(name) > 60:
        return jsonify(error="name 长度需在 1–60 字符之间"), 400
    con = _db()
    try:
        row = con.execute("SELECT id FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return jsonify(error="job not found"), 404
        con.execute("UPDATE lv_jobs SET name=?, updated_at=? WHERE id=?", (name, time.time(), job_id))
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, name=name)


@lv_bp.route("/jobs/<job_id>/resume", methods=["POST"])
def api_resume_job(job_id):
    
    con = _db()
    try:
        job = con.execute("SELECT id,status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        con.close()
    if not job:
        return jsonify(error="not found"), 404
    if job["status"] not in ("processing", "pending", "running"):
        return jsonify(ok=True, skipped=True, status=job["status"])
    _ensure_running(job_id)
    return jsonify(ok=True, job_id=job_id)


@lv_bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def api_cancel_job(job_id):
    
    con = _db()
    try:
        job = con.execute("SELECT id,status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        if job["status"] in ("completed", "failed", "cancelled", "draft"):
            return jsonify(ok=True, skipped=True, status=job["status"])
        con.execute("UPDATE lv_jobs SET status='cancelled', updated_at=? WHERE id=?",
                    (time.time(), job_id))



        con.execute("UPDATE lv_segments SET status='cancelled', updated_at=? WHERE job_id=? AND status='pending'",
                    (time.time(), job_id))
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, job_id=job_id, status="cancelled")


@lv_bp.route("/jobs/<job_id>/retry", methods=["POST"])
def api_retry_job(job_id):
    
    con = _db()
    try:
        job = con.execute("SELECT id,status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        if job["status"] == "completed":
            return jsonify(ok=True, skipped=True, status="completed")
        con.execute(
            "UPDATE lv_segments SET status='pending', error=NULL, started_at=0, video_id=NULL "
            "WHERE job_id=? AND status IN ('failed','pending','cancelled')", (job_id,)
        )
        con.execute("UPDATE lv_jobs SET status='processing', error=NULL, updated_at=? WHERE id=?", (time.time(), job_id))
        con.commit()
    finally:
        con.close()
    _ensure_running(job_id)
    return jsonify(ok=True, job_id=job_id, status="processing")


@lv_bp.route("/jobs/<job_id>/reedit", methods=["POST"])
def api_reedit_job(job_id):
    
    con = _db()
    try:
        job = con.execute("SELECT id,status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        if job["status"] == "processing":
            return jsonify(error="任务生成中，请等待完成后再重新编排"), 409
        if job["status"] == "draft":
            return jsonify(ok=True, skipped=True, status="draft")
        con.execute("UPDATE lv_jobs SET status='draft', error=NULL, updated_at=? WHERE id=?",
                    (time.time(), job_id))
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, job_id=job_id, status="draft")


@lv_bp.route("/jobs/<job_id>/shots/archive", methods=["POST"])
def api_archive_shots(job_id):
    
    data = request.get_json(silent=True) or {}
    shots = data.get("shots")
    source = (data.get("source") or "").strip()
    if not isinstance(shots, list) or not shots:
        return jsonify(error="shots 必须为非空数组"), 400
    con = _db()
    try:
        job = con.execute("SELECT shots_history FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        try:
            hist = json.loads(job["shots_history"] or "[]")
            if not isinstance(hist, list):
                hist = []
        except Exception:
            hist = []
        new_entry = {"ts": time.time(), "shots": shots, "source": source or "分镜稿", "shot_count": len(shots)}
        hist.append(new_entry)
        _CAP = 30
        if len(hist) > _CAP:
            hist = hist[-_CAP:]
        _new_idx = len(hist) - 1
        con.execute("UPDATE lv_jobs SET shots_history=?, current_shot_ver=? WHERE id=?",
                    (json.dumps(hist, ensure_ascii=False), _new_idx, job_id))
        con.commit()
        return jsonify(ok=True, versions=len(hist), idx=_new_idx)
    finally:
        con.close()


@lv_bp.route("/jobs/<job_id>/shots_history/current", methods=["PUT"])
def api_set_current_shots_history(job_id):
    
    data = request.get_json(silent=True) or {}
    idx = data.get("idx")
    if not isinstance(idx, int):
        return jsonify(error="idx 必须为整数"), 400
    con = _db()
    try:
        job = con.execute("SELECT shots_history FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        try:
            hist = json.loads(job["shots_history"] or "[]")
            if not isinstance(hist, list):
                hist = []
        except Exception:
            hist = []
        if idx < -1 or idx >= len(hist):
            return jsonify(error="版本不存在"), 404
        con.execute("UPDATE lv_jobs SET current_shot_ver=? WHERE id=?", (idx, job_id))
        con.commit()
        return jsonify(ok=True, idx=idx)
    finally:
        con.close()


@lv_bp.route("/jobs/<job_id>/shots_history/<int:idx>", methods=["PUT"])
def api_update_shots_history(job_id, idx):
    
    data = request.get_json(silent=True) or {}
    shots = data.get("shots")
    if not isinstance(shots, list):
        return jsonify(error="shots 必须为数组"), 400
    con = _db()
    try:
        job = con.execute("SELECT shots_history FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        try:
            hist = json.loads(job["shots_history"] or "[]")
            if not isinstance(hist, list):
                hist = []
        except Exception:
            hist = []
        if idx < 0 or idx >= len(hist):
            return jsonify(error="版本不存在"), 404
        hist[idx]["shots"] = shots
        hist[idx]["shot_count"] = len(shots)
        if data.get("source"):
            hist[idx]["source"] = data["source"]
        con.execute("UPDATE lv_jobs SET shots_history=? WHERE id=?",
                    (json.dumps(hist, ensure_ascii=False), job_id))
        con.commit()
        return jsonify(ok=True, idx=idx)
    finally:
        con.close()


@lv_bp.route("/jobs/<job_id>/shots_history/<int:idx>", methods=["GET"])
def api_get_shots_history(job_id, idx):
    
    con = _db()
    try:
        job = con.execute("SELECT shots_history FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        try:
            hist = json.loads(job["shots_history"] or "[]")
        except Exception:
            hist = []
        if idx < 0 or idx >= len(hist):
            return jsonify(error="版本不存在"), 404
        return jsonify(ok=True, version=hist[idx])
    finally:
        con.close()


@lv_bp.route("/jobs/<job_id>/shots_history/<int:idx>", methods=["DELETE"])
def api_delete_shots_history(job_id, idx):
    
    con = _db()
    try:
        job = con.execute("SELECT shots_history FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return jsonify(error="not found"), 404
        try:
            hist = json.loads(job["shots_history"] or "[]")
            if not isinstance(hist, list):
                hist = []
        except Exception:
            hist = []
        if idx < 0 or idx >= len(hist):
            return jsonify(error="版本不存在"), 404
        hist.pop(idx)
        con.execute("UPDATE lv_jobs SET shots_history=? WHERE id=?",
                    (json.dumps(hist, ensure_ascii=False), job_id))
        con.commit()
        return jsonify(ok=True, versions=len(hist))
    finally:
        con.close()


@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>/history/<int:idx>", methods=["DELETE"])
def api_delete_segment_history(job_id, seg_no, idx):
    
    data = request.get_json(silent=True) or {}
    video_ver = data.get("video_ver")
    ver = data.get("ver")
    con = _db()
    try:
        seg = con.execute(
            "SELECT prompt_history FROM lv_segments WHERE job_id=? AND seg_no=?",
            (job_id, seg_no),
        ).fetchone()
        if not seg:
            return jsonify(error="not found"), 404
        try:
            hist = json.loads(seg["prompt_history"] or "[]")
            if not isinstance(hist, list):
                hist = []
        except Exception:
            hist = []
        del_i = idx
        if ver is not None:
            del_i = next((i for i, h in enumerate(hist) if h.get("ver") == ver), idx)
        if del_i < 0 or del_i >= len(hist):
            return jsonify(error="版本不存在"), 404
        hist.pop(del_i)
        con.execute("UPDATE lv_segments SET prompt_history=? WHERE job_id=? AND seg_no=?",
                    (json.dumps(hist, ensure_ascii=False), job_id, seg_no))
        con.commit()
    finally:
        con.close()




    removed_video = None
    return jsonify(ok=True, removed_video=removed_video)



def _purge_stale_seg_files(job_id, keep_count):
    
    d = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(d):
        return 0
    pat = re.compile(r"^seg_(\d+)(?:_v\d+)?\.mp4$")
    n = 0
    for f in os.listdir(d):
        m = pat.match(f)
        if not m:
            continue
        if int(m.group(1)) > keep_count:
            try:
                os.remove(os.path.join(d, f))
                n += 1
            except OSError as e:
                logging.getLogger(__name__).warning("清理多余段文件失败 %s: %s", f, e)
    if n:
        logging.getLogger(__name__).info("任务 %s：已清理 %d 个多余段文件（保留 %d 段）",
                                         job_id, n, keep_count)
    return n


def _seg_files(job_id, seg_no):
    
    d = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(d):
        return []
    pat = re.compile(r"^seg_%02d(?:_v\d+)?\.mp4$" % seg_no)
    return [os.path.join(d, f) for f in os.listdir(d) if pat.match(f)]


def _remove_shot_data(job_id, index):
    
    try:
        index = int(index)
    except (TypeError, ValueError):
        return 400, {"error": "index 需为整数（被删镜头在 shots 中的下标，从 0 起）"}
    if index < 0:
        return 400, {"error": "index 不能为负"}
    drop_no = index + 1
    con = _db()
    try:
        job = con.execute("SELECT id,status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return 404, {"error": "not found", "job_id": job_id}
        if job["status"] != "draft":
            return 409, {"error": "已开始生成的任务不可删除镜头（请先「解锁编辑」）",
                         "status": job["status"]}
        rows = con.execute(
            "SELECT seg_no FROM lv_segments WHERE job_id=? ORDER BY seg_no", (job_id,)
        ).fetchall()
        seg_nos = [r["seg_no"] for r in rows]
        dropped_files = _seg_files(job_id, drop_no)
        if drop_no in seg_nos:
            con.execute("DELETE FROM lv_segments WHERE job_id=? AND seg_no=?", (job_id, drop_no))

        for n in [x for x in seg_nos if x > drop_no]:
            con.execute("UPDATE lv_segments SET seg_no=? WHERE job_id=? AND seg_no=?",
                        (n - 1, job_id, n))

        con.execute("UPDATE lv_jobs SET final_url=NULL, updated_at=? WHERE id=?", (time.time(), job_id))
        con.commit()
    finally:
        con.close()

    removed = 0
    try:
        for p in dropped_files:
            try:
                os.remove(p)
                removed += 1
            except OSError as e:
                logging.getLogger(__name__).warning("删除段文件失败 %s: %s", p, e)
        for n in sorted([x for x in seg_nos if x > drop_no]):
            for src in _seg_files(job_id, n):
                dst = re.sub(r"seg_%02d" % n, "seg_%02d" % (n - 1), os.path.basename(src))
                try:
                    os.replace(src, os.path.join(os.path.dirname(src), dst))
                except OSError as e:
                    logging.getLogger(__name__).warning("段文件改名失败 %s: %s", src, e)
        d = os.path.join(JOBS_DIR, job_id)
        for extra in ("final.mp4", "concat.txt"):
            p = os.path.join(d, extra)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
    except Exception as e:
        logging.getLogger(__name__).warning("删除镜头后的文件整理异常 %s: %s", job_id, e)
    return 200, {"ok": True, "job_id": job_id, "index": index,
                 "seg_no_dropped": drop_no, "files_removed": removed}


@lv_bp.route("/jobs/<job_id>/shots/remove", methods=["POST"])
def api_remove_shot(job_id):
    
    data = request.get_json(silent=True) or {}
    status, payload = _remove_shot_data(job_id, data.get("index"))
    return jsonify(payload), status







_APP_DB = os.environ.get("APP_DB_PATH") or os.path.join(_ROOT, "data", "app.db")


def _js_num_str(v):
    
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return "" if v is None else str(v)


def _purge_session_refs(job_id):
    
    if not job_id or not os.path.isfile(_APP_DB):
        return 0
    removed = 0
    try:
        con = sqlite3.connect(_APP_DB, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            for tbl in ("sessions", "agent_sessions"):
                try:
                    rows = con.execute("SELECT id, data FROM %s" % tbl).fetchall()
                except sqlite3.OperationalError:
                    continue
                for r in rows:
                    try:
                        obj = json.loads(r["data"] or "{}")
                    except Exception:
                        continue
                    msgs = obj.get("messages")
                    if not isinstance(msgs, list):
                        continue
                    idxs = [i for i, m in enumerate(msgs)
                            if isinstance(m, dict) and m.get("longvideoJob") == job_id]
                    if not idxs:
                        continue
                    hit = [msgs[i] for i in idxs]
                    _drop = set(idxs)
                    keep = [m for i, m in enumerate(msgs) if i not in _drop]
                    tomb = obj.get("deletedMsgs")
                    if not isinstance(tomb, list):
                        tomb = []
                    for m in hit:
                        fp = _js_num_str(m.get("time")) + "|" + (m.get("type") or "")
                        if fp not in tomb:
                            tomb.append(fp)
                    obj["messages"] = keep
                    obj["deletedMsgs"] = tomb
                    con.execute("UPDATE %s SET data=? WHERE id=?" % tbl,
                                (json.dumps(obj, ensure_ascii=False), r["id"]))
                    removed += len(hit)
            con.commit()
        finally:
            con.close()
    except Exception as e:
        logging.getLogger(__name__).warning("清理会话中的悬空任务引用失败 %s: %s", job_id, e)
    if removed:
        logging.getLogger(__name__).info("删除任务 %s：已清掉 %d 处会话引用气泡", job_id, removed)
    return removed


def _job_static_name(job_id, basename):
    
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(job_id))[:48]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", str(basename))
    name = "%s__%s" % (safe, base)
    if os.path.exists(os.path.join(ASSETS_DIR, name)):
        stem, ext = os.path.splitext(name)
        name = "%s_%d%s" % (stem, int(time.time()), ext)
    return name


def _delete_job(job_id):
    
    con = _db()
    migrated, kept = 0, 0
    try:
        job = con.execute("SELECT id FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return 404, {"error": "not found", "job_id": job_id}
        con.execute("DELETE FROM lv_segments WHERE job_id=?", (job_id,))

        priv = con.execute(
            "SELECT name,url FROM assets WHERE job_id=?", (job_id,)
        ).fetchall()
        dyn_prefix = "/api/jobs/%s/" % job_id
        for r in priv:
            u = r["url"] or ""
            new_url = None
            if u.startswith(dyn_prefix):

                src = os.path.join(JOBS_DIR, job_id, os.path.basename(u))
                static_name = _job_static_name(job_id, os.path.basename(u))
                if os.path.isfile(src):
                    try:
                        shutil.copy2(src, os.path.join(ASSETS_DIR, static_name))
                        new_url = "/assets/" + static_name
                        migrated += 1
                    except Exception as e:
                        logging.getLogger(__name__).warning(
                            "删除任务 %s：成片/分段迁移失败，保留原状 %s: %s", job_id, u, e)
            if new_url:
                con.execute("UPDATE assets SET job_id=NULL, url=? WHERE name=?",
                            (new_url, r["name"]))
            else:
                con.execute("UPDATE assets SET job_id=NULL WHERE name=?", (r["name"],))
                kept += 1
                logging.getLogger(__name__).info(
                    "删除任务 %s：资产 %s 已脱离任务，保留在资产库", job_id, r["name"])
        con.execute("DELETE FROM lv_jobs WHERE id=?", (job_id,))

        try:
            _assets_store.prune_orphan_subjects(con)
        except Exception:
            pass
        con.commit()
    finally:
        con.close()

    d = os.path.join(JOBS_DIR, job_id)
    if os.path.isdir(d):
        try:
            shutil.rmtree(d)
        except Exception as e:
            logging.getLogger(__name__).warning("删除任务目录失败 %s: %s", d, e)

    n_ref = _purge_session_refs(job_id)
    return 200, {"ok": True, "job_id": job_id, "sessionRefsRemoved": n_ref,
                 "assetsMigrated": migrated, "assetsKept": kept}


@lv_bp.route("/jobs/<job_id>", methods=["DELETE"])
def api_delete_job(job_id):
    
    status, payload = _delete_job(job_id)
    return jsonify(payload), status


@lv_bp.route("/jobs/delete_batch", methods=["POST"])
def api_delete_jobs_batch():
    
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify(error="需要 ids 数组"), 400
    results = []
    for jid in ids:
        s, p = _delete_job(jid)
        results.append({"job_id": jid, "ok": s == 200, "error": p.get("error") if s != 200 else None})
    return jsonify(ok=sum(1 for r in results if r["ok"]), total=len(results), results=results)


def _regen_segment_worker(job_id, seg_no, seg, prev_tail, archive_ver=0, prev_status="failed"):
    
    try:

        if archive_ver:
            _archive_segment_video(job_id, seg_no, archive_ver)
        success, local, tail, err = _gen_segment(job_id, seg, prev_tail)
        if not success:

            if _job_cancelled(job_id):
                _update_seg(job_id, seg_no, status="cancelled", error=err)
                print(f"[INFO] 单段重提随任务停止而中止 job={job_id} seg#{seg_no}", flush=True)
                return
            _update_seg(job_id, seg_no, status="failed", error=err)



            _update_job(job_id, status="failed")
            print(f"[INFO] 单段重提失败 job={job_id} seg#{seg_no}: {err}", flush=True)
            return
        _update_seg(job_id, seg_no, status="completed", local_path=local, tail_frame=tail, finished_at=time.time())




        d = _probe_duration(local)
        if d:
            con = _db()
            try:
                con.execute("UPDATE lv_segments SET real_seconds=? WHERE job_id=? AND seg_no=?",
                            (d, job_id, seg_no))
                con.commit()
            finally:
                con.close()


        con = _db()
        try:
            unfinished = con.execute(
                "SELECT COUNT(*) c FROM lv_segments WHERE job_id=? AND status != 'completed'", (job_id,)
            ).fetchone()["c"]
        finally:
            con.close()
        if unfinished:

            _t = _JOB_THREADS.get(job_id)
            if _t and _t.is_alive():
                print(f"[INFO] 单段重提完成 job={job_id} seg#{seg_no}: 任务还有 {unfinished} 段未完成，成片待收尾", flush=True)
                return


            if not _job_cancelled(job_id) and prev_status in ("failed", "cancelled"):
                _update_job(job_id, status=prev_status)
            print(f"[INFO] 单段重提完成 job={job_id} seg#{seg_no}: 任务还有 {unfinished} 段未完成，"
                  f"主线已死 → 任务回 {prev_status}", flush=True)
            return
        con = _db()
        try:
            all_segs = con.execute(
                "SELECT seg_no,local_path,status FROM lv_segments WHERE job_id=? ORDER BY seg_no", (job_id,)
            ).fetchall()
        finally:
            con.close()
        out_dir = os.path.join(JOBS_DIR, job_id)
        seg_paths = {s["seg_no"]: s["local_path"] for s in all_segs if s["local_path"] and os.path.exists(s["local_path"])}
        ordered = [seg_paths[k] for k in sorted(seg_paths)]
        final_url = _concat_and_register(job_id, out_dir, ordered)


        if not _job_cancelled(job_id):
            _update_job(job_id, status="completed", final_url=final_url, error=None)


        _clear_tail_frames(job_id)
        print(f"[INFO] 单段重提收尾 job={job_id}: 全部段完成，已重拼成片", flush=True)
    except Exception as e:

        try:
            _st = "cancelled" if _job_cancelled(job_id) else "failed"
            _update_seg(job_id, seg_no, status=_st, error=f"重提异常 {type(e).__name__}: {e}")
        except Exception:
            pass
        print(f"[ERROR] 单段重提异常 job={job_id} seg#{seg_no}: {type(e).__name__}: {e}", flush=True)


@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>/regen", methods=["POST"])
def api_regen_segment(job_id, seg_no):
    
    if not _cfg_key():
        return jsonify(error="尚未配置访问密钥（服务商设置或 .env）"), 500
    data = request.get_json(silent=True) or {}
    new_prompt = (data.get("prompt") or "").strip()
    con = _db()
    try:
        seg = con.execute(
            "SELECT * FROM lv_segments WHERE job_id=? AND seg_no=?", (job_id, seg_no)
        ).fetchone()
        if not seg:
            return jsonify(error="segment not found"), 404
        seg = dict(seg)
    finally:
        con.close()

    if seg["status"] == "processing":
        return jsonify(error="该段正在生成中，请稍候"), 409



    new_seconds = data.get("seconds")
    _sec_changed = False
    if new_seconds is not None:
        try:
            new_seconds = int(new_seconds)
        except (TypeError, ValueError):
            new_seconds = None
        _lo, _hi = _seg_bounds()
        if new_seconds is not None and _lo <= new_seconds <= _hi and new_seconds != seg["seconds"]:
            _sec_changed = True
    _prompt_changed = bool(new_prompt) and new_prompt != (seg.get("prompt") or "")


    _archive_ver = 0
    if _prompt_changed or _sec_changed:
        try:
            hist = json.loads(seg.get("prompt_history") or "[]")
            if not isinstance(hist, list):
                hist = []
        except Exception:
            hist = []


        hist.append({
            "ver": max([h.get("ver") or 0 for h in hist] + [len(hist)]) + 1,
            "ts": time.time(),
            "prompt": seg.get("prompt") or "",
            "seconds": seg.get("seconds"),

            "images": _seg_jsonl(seg, "images_keys"),
            "images_urls": _seg_jsonl(seg, "images_urls"),
            "audio": _seg_jsonl(seg, "audio"),
            "audio_urls": _seg_jsonl(seg, "audio_urls"),
        })
        _update_seg(job_id, seg_no, prompt_history=json.dumps(hist, ensure_ascii=False))
        _archive_ver = hist[-1]["ver"]
    if new_prompt:
        seg["prompt"] = new_prompt
        _update_seg(job_id, seg_no, prompt=new_prompt)
    if _sec_changed:
        seg["seconds"] = new_seconds
        _update_seg(job_id, seg_no, seconds=new_seconds)


    prev_tail = None
    if seg["is_continuation"]:
        con = _db()
        try:
            prev = con.execute(
                "SELECT tail_frame,local_path FROM lv_segments WHERE job_id=? AND seg_no<? ORDER BY seg_no DESC LIMIT 1",
                (job_id, seg_no),
            ).fetchone()
        finally:
            con.close()
        if prev:
            prev = dict(prev)
            prev_tail = prev.get("tail_frame") or (prev.get("local_path") and _extract_tail_frame(prev["local_path"]))


    _update_seg(job_id, seg_no, status="processing", error=None, started_at=time.time())




    con = _db()
    try:
        _prev = con.execute("SELECT status FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        prev_status = _prev["status"] if _prev else "failed"
    finally:
        con.close()
    _update_job(job_id, status="processing")
    threading.Thread(target=_regen_segment_worker, args=(job_id, seg_no, seg, prev_tail, _archive_ver, prev_status), daemon=True).start()
    return jsonify(ok=True, job_id=job_id, seg_no=seg_no, status="processing")


@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>/history", methods=["GET"])
def api_segment_history(job_id, seg_no):
    
    con = _db()
    try:
        seg = con.execute(
            "SELECT prompt,seconds,images_keys,images_urls,audio,audio_urls,prompt_history,updated_at "
            "FROM lv_segments WHERE job_id=? AND seg_no=?",
            (job_id, seg_no),
        ).fetchone()
    finally:
        con.close()
    if not seg:
        return jsonify(error="segment not found"), 404
    seg = dict(seg)
    try:
        hist = json.loads(seg.get("prompt_history") or "[]")
        if not isinstance(hist, list):
            hist = []
    except Exception:
        hist = []

    for i, h in enumerate(hist):
        if not h.get("ver"):
            h["ver"] = i + 1
    current = {
        "prompt": seg.get("prompt") or "",
        "seconds": seg.get("seconds"),
        "updated_at": seg.get("updated_at"),
        "images": _seg_jsonl(seg, "images_keys"),
        "images_urls": _seg_jsonl(seg, "images_urls"),
        "audio": _seg_jsonl(seg, "audio"),
        "audio_urls": _seg_jsonl(seg, "audio_urls"),
    }


    out_dir = os.path.join(JOBS_DIR, job_id)
    videos = []
    _pat = re.compile(rf"seg_{seg_no:02d}_v(\d+)\.mp4$")
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            m = _pat.search(f)
            if m:
                v = int(m.group(1))
                videos.append({"v": v, "url": f"/api/jobs/{job_id}/segment/{seg_no}/v/{v}.mp4"})
    videos.sort(key=lambda x: x["v"], reverse=True)
    return jsonify(history=hist, current=current, videos=videos)


@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>/v/<int:ver>.mp4")
def api_segment_version_mp4(job_id, seg_no, ver):
    
    if not (1 <= ver <= 99):
        return jsonify(error="bad version"), 400
    p = os.path.join(JOBS_DIR, job_id, f"seg_{seg_no:02d}_v{ver}.mp4")
    if not os.path.exists(p):
        return jsonify(error="not found"), 404
    from flask import send_file
    return send_file(p, mimetype="video/mp4")



def _deleted_job_asset_file(name):
    
    try:
        con = _db()
        try:
            row = con.execute("SELECT url FROM assets WHERE name=?", (name,)).fetchone()
        finally:
            con.close()
    except Exception:
        return None
    u = ((row["url"] if row else "") or "")
    if not u.startswith("/assets/"):
        return None
    p = os.path.join(ASSETS_DIR, os.path.basename(u))
    return p if os.path.isfile(p) else None


@lv_bp.route("/jobs/<job_id>/final.mp4")
def api_final_mp4(job_id):
    p = os.path.join(JOBS_DIR, job_id, "final.mp4")
    if not os.path.exists(p):

        gp = _deleted_job_asset_file("%s/final.mp4" % job_id)
        if not gp:
            return jsonify(error="not ready"), 404
        p = gp
    from flask import send_file
    return send_file(p, mimetype="video/mp4")



@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>.mp4")
def api_segment_mp4(job_id, seg_no):
    p = os.path.join(JOBS_DIR, job_id, f"seg_{seg_no:02d}.mp4")
    if not os.path.exists(p):
        gp = _deleted_job_asset_file("%s/seg_%02d.mp4" % (job_id, seg_no))
        if not gp:
            return jsonify(error="not ready"), 404
        p = gp
    from flask import send_file
    return send_file(p, mimetype="video/mp4")



@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>/thumb")
def api_segment_thumb(job_id, seg_no):
    try:
        return _api_segment_thumb_impl(job_id, seg_no)
    except Exception:
        import traceback
        traceback.print_exc()
        return jsonify(error="thumb failed"), 500






@lv_bp.route("/jobs/<job_id>/segment/<int:seg_no>/tail.png")
def api_segment_tail(job_id, seg_no):
    try:
        return _api_segment_tail_impl(job_id, seg_no)
    except Exception:
        import traceback
        traceback.print_exc()
        return jsonify(error="tail failed"), 500


def _api_segment_tail_impl(job_id, seg_no):
    
    con = _db()
    try:
        seg = con.execute(
            "SELECT is_continuation, status, tail_frame, local_path "
            "FROM lv_segments WHERE job_id=? AND seg_no=?",
            (job_id, seg_no),
        ).fetchone()
    finally:
        con.close()
    if not seg:
        return jsonify(error="no tail"), 404
    tail_raw = seg["tail_frame"]
    if not tail_raw:
        lp = seg["local_path"]
        if lp and os.path.isfile(lp):
            try:
                tail_raw = _extract_tail_frame(lp)
            except Exception as e:
                logging.getLogger(__name__).warning("按需重抽尾帧失败 %s#%s: %s", job_id, seg_no, e)
                tail_raw = None
    if not tail_raw:
        return jsonify(error="no tail"), 404

    try:
        b64 = tail_raw.split(",", 1)[1]
        png = base64.b64decode(b64)
    except Exception:
        return jsonify(error="decode failed"), 500
    if not png:
        return jsonify(error="empty"), 404

    try:
        if _ffmpeg():
            _p = subprocess.run(
                [_ffmpeg(), "-y", "-i", "pipe:0", "-vf", "scale=480:-1",
                 "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg",
                 "-loglevel", "error", "-"],
                input=png, capture_output=True, timeout=15,
            )
            if _p.returncode == 0 and _p.stdout:
                return send_file(io.BytesIO(_p.stdout), mimetype="image/jpeg")
    except Exception:
        pass

    return send_file(io.BytesIO(png), mimetype="image/png")

def _api_segment_thumb_impl(job_id, seg_no):
    con = _db()
    try:
        seg = con.execute(
            "SELECT status,local_path,tail_frame FROM lv_segments WHERE job_id=? AND seg_no=?",
            (job_id, seg_no),
        ).fetchone()
    finally:
        con.close()
    if not seg or seg["status"] != "completed":
        return jsonify(error="not ready"), 404
    png = None
    ff = _ffmpeg()
    if ff and seg["local_path"] and os.path.exists(seg["local_path"]):




        try:
            _p = subprocess.run(
                [ff, "-y", "-ss", "0.4", "-i", seg["local_path"],
                 "-frames:v", "1", "-vf", "scale=320:-1",
                 "-f", "image2pipe", "-vcodec", "png",
                 "-loglevel", "error", "-"],
                capture_output=True, timeout=30,
            )
            if _p.returncode == 0 and _p.stdout:
                png = _p.stdout
        except Exception:
            png = None
    if not png and seg["tail_frame"]:
        try:
            png = base64.b64decode(seg["tail_frame"].split(",", 1)[1])
        except Exception:
            png = None
    if not png:
        return jsonify(error="no thumb"), 404
    return send_file(io.BytesIO(png), mimetype="image/png")




@lv_bp.route("/longvideo_ui.js")
def ui_js():
    from .ui import build_ui_js
    try:
        js = build_ui_js()
    except Exception as e:
        return jsonify(error="ui build failed: %s" % e), 500
    return js, 200, {"Content-Type": "application/javascript"}


def _resume_stuck_jobs():
    
    try:
        con = _db()
        try:
            rows = con.execute(
                "SELECT id FROM lv_jobs WHERE status IN ('processing','pending','running')"
            ).fetchall()
        finally:
            con.close()
        for r in rows:
            jid = r["id"]
            logging.getLogger(__name__).info("启动续跑卡住任务 %s", jid)
            _ensure_running(jid)
    except Exception as e:
        logging.getLogger(__name__).warning("启动续跑扫描失败：%s", e)


def register_longvideo(app):
    
    app.register_blueprint(lv_bp)

    _resume_stuck_jobs()
