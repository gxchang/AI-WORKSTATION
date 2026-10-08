

import json
import logging
import os
import re
import sqlite3
import time
import uuid

from flask import Blueprint, jsonify, request

import media_gc as _mgc

import thumbs as _thumbs




_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_ROOT, "data", "app.db")
ASSETS_DIR = os.path.join(_ROOT, "storage", "assets")

IMG_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}
AUD_EXTS = {"mp3", "wav", "m4a", "aac", "ogg", "flac"}
DOC_EXTS = {"pdf", "txt", "md", "json", "csv"}
VID_EXTS = {"mp4", "mov", "webm", "mkv"}
ALLOWED = IMG_EXTS | AUD_EXTS
MAX_LONGVIDEO_ASSETS = 50
VISUALSPEC_VERSION = 1


T_ASSETS = "assets"
T_SUBJECTS = "subjects"


ORIGIN_CREATED = "created"
ORIGIN_UPLOADED = "uploaded"
ORIGINS = (ORIGIN_CREATED, ORIGIN_UPLOADED)


SUBJECT_KINDS = ("character", "scene", "prop")

_ASSET_KIND_TO_SUBJECT_KIND = {
    "character": "character", "voice": "character",
    "scene": "scene", "prop": "prop",
}


assets_bp = Blueprint("longvideo_assets", __name__, url_prefix="/api/assets")

_WAL_SET = False


def connect():
    
    global _WAL_SET


    con = sqlite3.connect(DB_PATH, timeout=30)
    if not _WAL_SET:
        try:
            con.execute("PRAGMA journal_mode=WAL")
            _WAL_SET = True
        except Exception:
            pass
    con.row_factory = sqlite3.Row
    return con


def ensure_assets_table(con):
    

    try:
        has_old = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lv_assets_registry'"
        ).fetchone()
        has_new = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (T_ASSETS,)
        ).fetchone()
        if has_old and not has_new:
            con.execute("ALTER TABLE lv_assets_registry RENAME TO %s" % T_ASSETS)
            con.commit()
    except sqlite3.OperationalError:
        pass


    con.execute(
        """CREATE TABLE IF NOT EXISTS subjects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            kind TEXT,
            appearance TEXT,
            cover TEXT,
            created_at REAL,
            updated_at REAL
        )"""
    )


    con.execute(
        """CREATE TABLE IF NOT EXISTS assets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            type TEXT NOT NULL,
            label TEXT,
            kind TEXT,
            owner TEXT,
            posture TEXT,
            created_at REAL,
            job_id TEXT,
            appearance TEXT,
            subject_id INTEGER,
            origin TEXT,
            origin_session TEXT,
            updated_at REAL
        )"""
    )


    for col, decl in (("cover", "TEXT"),):
        try:
            con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (T_SUBJECTS, col, decl))
        except sqlite3.OperationalError:
            pass
    for col, decl in (("posture", "TEXT"), ("job_id", "TEXT"), ("appearance", "TEXT"),
                      ("subject_id", "INTEGER"), ("origin", "TEXT"),
                      ("origin_session", "TEXT"), ("updated_at", "REAL")):
        try:
            con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (T_ASSETS, col, decl))
        except sqlite3.OperationalError:
            pass


    for ddl in (
        "CREATE INDEX IF NOT EXISTS idx_assets_created ON %s(created_at DESC)" % T_ASSETS,
        "CREATE INDEX IF NOT EXISTS idx_assets_subject ON %s(subject_id)" % T_ASSETS,
        "CREATE INDEX IF NOT EXISTS idx_assets_origin ON %s(origin)" % T_ASSETS,
        "CREATE INDEX IF NOT EXISTS idx_assets_session ON %s(origin_session)" % T_ASSETS,
        "CREATE INDEX IF NOT EXISTS idx_subjects_kind ON %s(kind)" % T_SUBJECTS,
    ):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass
    con.commit()


def _db():
    
    con = connect()
    ensure_assets_table(con)
    return con


def register_assets(app):
    
    app.register_blueprint(assets_bp)
    from .ui import ui_bp
    app.register_blueprint(ui_bp)



def _safe(filename: str) -> str:
    base = os.path.basename(filename).replace(" ", "_")
    keep = [c for c in base if c.isalnum() or c in "._-"]
    s = "".join(keep) or "file"
    return s[:120]


def asset_name_of(url):
    
    if not url or not isinstance(url, str):
        return None
    s = str(url).split("?", 1)[0].split("#", 1)[0]
    if s.startswith("data:"):
        return None
    m = re.search(r"(?:^|/)assets/([^/]+)$", s)
    if not m:
        return None
    n = os.path.basename(m.group(1))
    return n or None



def register(name, url, type, origin, kind=None, label=None, owner=None, posture=None,
             subject_id=None, origin_session=None, job_id=None, appearance=None):
    
    if not name or not url:
        print("[warn] 资产入库被跳过（缺 name/url）：name=%r url=%r" % (name, url))
        return None
    if origin not in ORIGINS:

        print("[warn] 资产入库 origin 非法（%r，应为 %s），已跳过：%s"
              % (origin, "|".join(ORIGINS), name))
        return None






    _n = asset_name_of(url)
    if _n:
        url = "/assets/" + _n
    try:
        con = _db()
    except Exception as e:
        print("[warn] 资产入库失败（打不开库）%s: %s" % (name, e))
        return None
    try:
        if subject_id is None and kind:
            subject_id = sync_subject(con, owner=owner, kind=kind, label=label)
        now = time.time()
        row = con.execute("SELECT id FROM %s WHERE name=?" % T_ASSETS, (name,)).fetchone()
        if row:
            sets = ["url=?", "type=?", "updated_at=?"]
            vals = [url, type, now]
            if subject_id is not None:
                sets.append("subject_id=?")
                vals.append(subject_id)
            if origin_session:

                sets.append("origin_session=COALESCE(origin_session, ?)")
                vals.append(origin_session)
            vals.append(name)
            con.execute("UPDATE %s SET %s WHERE name=?" % (T_ASSETS, ", ".join(sets)), vals)
        else:
            con.execute(
                "INSERT INTO %s(name,url,type,label,kind,owner,posture,created_at,"
                "job_id,subject_id,origin,origin_session,appearance,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)" % T_ASSETS,
                (name, url, type, label, kind, owner, posture, now,
                 job_id, subject_id, origin, origin_session, appearance, now),
            )
        con.commit()
        return name
    except Exception as e:
        print("[warn] 资产入库失败 %s: %s" % (name, e))
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass


def register_many(items):
    
    out = []
    for it in (items or []):
        try:
            n = register(**it)
        except TypeError as e:
            print("[warn] 资产入库参数不合法（跳过该条）：%s" % e)
            n = None
        if n:
            out.append(n)
    return out


def _strip_markdown_noise(text):
    
    if not text:
        return ""
    t = text
    t = re.sub(r'#{1,6}\s*', '', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'根据图片视觉信息[，,：:]?', '', t)
    t = re.sub(r'角色视觉识别结果[（(][^）)]*[）)]', '', t)
    t = re.sub(r'视觉识别结果[（(][^）)]*[）)]', '', t)
    return t.strip()


def _appearance_to_spec(text, source="registry", label="", kind=""):
    
    if not text:
        return None
    s = text.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "source" in obj:
                if obj.get("raw"):
                    obj["raw"] = _strip_markdown_noise(obj["raw"])
                if kind and not obj.get("kind"):
                    obj["kind"] = kind
                return json.dumps(obj, ensure_ascii=False)
        except Exception:
            pass
    raw = _strip_markdown_noise(s)
    return json.dumps({
        "version": VISUALSPEC_VERSION,
        "source": source,
        "label": label,
        "kind": kind,
        "raw": raw,
        "concrete": {},
    }, ensure_ascii=False)





_SELECT_ASSET = (
    "SELECT a.id, a.name, a.url, a.type, a.label, a.kind, "
    "       COALESCE(s.name, a.owner) AS owner, "
    "       a.posture, a.appearance, a.created_at, a.job_id, "
    "       a.subject_id, s.name AS subject_name, s.kind AS subject_kind, "
    "       COALESCE(NULLIF(a.origin,''), 'uploaded') AS origin, a.origin_session, a.updated_at "
    "FROM %s a LEFT JOIN %s s ON s.id = a.subject_id" % (T_ASSETS, T_SUBJECTS)
)


def resolve_subject(con, name, kind=None, appearance=None):
    
    name = (name or "").strip()
    if not name:
        return None
    now = time.time()
    row = con.execute("SELECT id FROM %s WHERE name=?" % T_SUBJECTS, (name,)).fetchone()
    if row:
        if appearance:
            con.execute("UPDATE %s SET appearance=?, updated_at=? WHERE id=?" % T_SUBJECTS,
                        (appearance, now, row["id"]))
        return row["id"]
    cur = con.execute(
        "INSERT INTO %s(name,kind,appearance,created_at,updated_at) VALUES(?,?,?,?,?)" % T_SUBJECTS,
        (name, kind or "character", appearance, now, now),
    )
    return cur.lastrowid


def lookup_subject_id(con, name):
    
    name = (name or "").strip()
    if not name:
        return None
    row = con.execute("SELECT id FROM %s WHERE name=?" % T_SUBJECTS, (name,)).fetchone()
    return row["id"] if row else None


def sync_subject(con, owner=None, kind=None, label=None):
    
    k = (kind or "").strip()
    if k in ("character", "voice"):
        nm = (label or "").strip() if k == "character" else ""
        nm = nm or (owner or "").strip()
        return resolve_subject(con, nm, kind="character")
    if k in ("scene", "prop"):
        return lookup_subject_id(con, label)
    return None


def prune_orphan_subjects(con):
    
    rows = con.execute(
        "SELECT id, name FROM %s WHERE id NOT IN "
        "(SELECT subject_id FROM %s WHERE subject_id IS NOT NULL)" % (T_SUBJECTS, T_ASSETS)
    ).fetchall()
    if not rows:
        return []
    con.execute("DELETE FROM %s WHERE id IN (%s)"
                % (T_SUBJECTS, ",".join("?" * len(rows))), [r["id"] for r in rows])
    return [r["name"] for r in rows]


@assets_bp.route("/batch_upload", methods=["POST"])
def batch_upload():
    
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="no files"), 400

    job_id = (request.form.get("job_id") or "").strip() or None
    con = _db()
    try:





        existing = con.execute(
            "SELECT COUNT(*) c FROM assets WHERE job_id=? AND type IN ('image','audio')",
            (job_id,)
        ).fetchone()["c"]
    finally:
        con.close()
    if existing + len(files) > MAX_LONGVIDEO_ASSETS:
        return jsonify(error=f"超出长视频素材上限 {MAX_LONGVIDEO_ASSETS}"), 413

    out = []
    con = _db()
    try:
        for f in files:
            if not f or not f.filename:
                continue
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext not in ALLOWED:
                return jsonify(error=f"不支持的类型 .{ext}"), 400
            typ = "image" if ext in IMG_EXTS else "audio"


            h, dedup, name, url = None, False, None, None
            try:
                import asset_index
                h = asset_index.content_hash(f)
                hit = asset_index.find_by_hash(h)
                if hit and os.path.isfile(os.path.join(ASSETS_DIR, hit["name"])):
                    name, url, dedup = hit["name"], hit["url"], True
            except Exception as e:
                print("[WARN] 素材内容索引不可用，回退直接上传:", e, flush=True)
                h = None
            if not dedup:
                name = f"lv_{uuid.uuid4().hex[:12]}_{_safe(f.filename)}"
                if not name.lower().endswith("." + ext):
                    name += "." + ext
                f.save(os.path.join(ASSETS_DIR, name))
                url = f"/assets/{name}"
                try:
                    if h:
                        import asset_index
                        asset_index.remember(
                            h, name, url,
                            os.path.getsize(os.path.join(ASSETS_DIR, name)), ext,
                        )
                except Exception as e:
                    print("[WARN] 素材内容索引写入失败:", e, flush=True)

            label0 = f.filename.rsplit(".", 1)[0] if "." in f.filename else f.filename

            con.execute(
                "INSERT OR IGNORE INTO assets(name,url,type,label,created_at,job_id,origin) "
                "VALUES(?,?,?,?,?,?,?)",
                (name, url, typ, label0, time.time(), job_id, ORIGIN_UPLOADED),
            )
            out.append({"name": name, "url": url, "type": typ, "label": label0, "dedup": dedup})
        con.commit()






        if job_id and out:
            try:
                r = con.execute("SELECT assets_json FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
                if r:
                    cur = json.loads(r["assets_json"]) if r["assets_json"] else []
                    existing_names = {a.get("name") for a in cur if isinstance(a, dict)}
                    new_assets = [a for a in out if a["name"] not in existing_names]
                    if new_assets:

                        for a in new_assets: a["created_at"] = time.time()
                        cur.extend(new_assets)
                        con.execute(
                            "UPDATE lv_jobs SET assets_json=?, updated_at=? WHERE id=?",
                            (json.dumps(cur, ensure_ascii=False), time.time(), job_id),
                        )
                        con.commit()
            except Exception as e:

                print("[batch_upload] 同步 lv_jobs.assets_json 失败（不影响主流程）:", e)
    finally:
        con.close()
    return jsonify(uploaded=out)


@assets_bp.route("/register", methods=["POST"])
def register_labels():
    
    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return jsonify(error="expect list"), 400
    con = _db()
    try:
        for item in data:
            name = item.get("name")
            if not name:
                continue
            label, kind = item.get("label"), item.get("kind")
            owner, posture = item.get("owner"), item.get("posture")
            ap = item.get("appearance")
            fields = ["label=?", "kind=?", "owner=?", "posture=?", "updated_at=?"]
            vals = [label, kind, owner, posture, time.time()]
            if (kind or "").strip() in ("character", "voice", "scene", "prop"):
                fields.append("subject_id=?")
                vals.append(sync_subject(con, owner=owner, kind=kind, label=label))
            if ap is not None:

                fields.append("appearance=?")
                vals.append(_appearance_to_spec(ap))
            vals.append(name)
            con.execute("UPDATE assets SET %s WHERE name=?" % ", ".join(fields), vals)
        gone = prune_orphan_subjects(con)
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, orphan_subjects_removed=gone)


@assets_bp.route("/registry", methods=["GET"])
def registry():
    
    job_id = request.args.get("job_id") or None
    con = _db()
    try:
        if job_id:
            rows = con.execute(
                _SELECT_ASSET + " WHERE a.job_id=? OR a.job_id IS NULL ORDER BY a.id",
                (job_id,),
            ).fetchall()
        else:
            rows = con.execute(_SELECT_ASSET + " ORDER BY a.id").fetchall()
    finally:
        con.close()
    return jsonify(items=[dict(r) for r in rows])


@assets_bp.route("/shared", methods=["GET"])
def shared():
    
    con = _db()
    try:
        rows = con.execute(_SELECT_ASSET + " WHERE a.job_id IS NULL ORDER BY a.id").fetchall()
    finally:
        con.close()
    return jsonify(items=[dict(r) for r in rows])







_LIST_PAGE_SIZE_DEFAULT = 60
_LIST_PAGE_SIZE_MAX = 200


@assets_bp.route("/list", methods=["GET"])
def list_assets():
    
    tab = (request.args.get("tab") or "").strip()
    typ = (request.args.get("type") or "").strip()
    kind = (request.args.get("kind") or "").strip()
    subj = (request.args.get("subject") or "").strip()
    try:
        page = max(1, int(request.args.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.args.get("size") or _LIST_PAGE_SIZE_DEFAULT)
    except (TypeError, ValueError):
        size = _LIST_PAGE_SIZE_DEFAULT
    size = max(1, min(_LIST_PAGE_SIZE_MAX, size))

    where, args = [], []
    if tab in ORIGINS:

        where.append("COALESCE(NULLIF(a.origin,''),'uploaded')=?")
        args.append(tab)
    if typ:
        where.append("a.type=?")
        args.append(typ)
    if kind:
        where.append("a.kind=?")
        args.append(kind)
    if subj:
        if subj == "none":
            where.append("a.subject_id IS NULL")
        elif subj.isdigit():
            where.append("a.subject_id=?")
            args.append(int(subj))
    wsql = (" WHERE " + " AND ".join(where)) if where else ""

    con = _db()
    try:
        total = con.execute(
            "SELECT COUNT(*) c FROM %s a%s" % (T_ASSETS, wsql), args
        ).fetchone()["c"]
        rows = con.execute(
            _SELECT_ASSET + wsql + " ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?",
            args + [size, (page - 1) * size],
        ).fetchall()
    finally:
        con.close()
    pages = (total + size - 1) // size if size else 0
    return jsonify(items=[dict(r) for r in rows], total=total, page=page,
                   size=size, pages=pages)


@assets_bp.route("/subjects", methods=["GET"])
def list_subjects():
    
    con = _db()
    try:
        rows = con.execute(
            "SELECT s.id, s.name, s.kind, s.cover, "
            "  (SELECT COUNT(*) FROM %s a WHERE a.subject_id=s.id) AS n "
            "FROM %s s ORDER BY n DESC, s.name" % (T_ASSETS, T_SUBJECTS)
        ).fetchall()
        ungrouped = con.execute(
            "SELECT COUNT(*) c FROM %s WHERE subject_id IS NULL" % T_ASSETS
        ).fetchone()["c"]
    finally:
        con.close()
    return jsonify(items=[dict(r) for r in rows], ungrouped=ungrouped)


@assets_bp.route("/set_cover", methods=["POST"])
def set_subject_cover():
    
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    con = _db()
    try:
        row = con.execute("SELECT subject_id FROM %s WHERE name=?" % T_ASSETS,
                          (name,)).fetchone()
        if not row:
            return jsonify(error="资产不存在"), 404
        sid = row["subject_id"]
        if not sid:
            return jsonify(error="该资产尚未归入任何主体，无法设为封面"), 400
        con.execute("UPDATE %s SET cover=?, updated_at=? WHERE id=?" % T_SUBJECTS,
                    (name, time.time(), sid))
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, subject_id=sid, cover=name)


@assets_bp.route("/move", methods=["POST"])
def move_assets():
    
    data = request.get_json(silent=True) or {}
    names = data.get("names") or []
    if not isinstance(names, list) or not names:
        return jsonify(error="names required (array)"), 400
    has_kind, kind = "kind" in data, data.get("kind")
    has_subj, subj = "subject_id" in data, data.get("subject_id")
    if not (has_kind or has_subj):
        return jsonify(error="需要 kind 或 subject_id 之一"), 400
    if has_subj:
        try:
            subj = None if subj in (None, "", "none") else int(subj)
        except (TypeError, ValueError):
            return jsonify(error="subject_id 必须是整数或 null"), 400

    con = _db()
    updated = []
    try:
        if has_subj and subj is not None:
            srow = con.execute("SELECT kind FROM %s WHERE id=?" % T_SUBJECTS,
                               (subj,)).fetchone()
            skind = srow["kind"] if srow else None
        else:
            skind = None
        for n in names:
            if not n:
                continue
            row = con.execute(
                "SELECT id, kind FROM %s WHERE name=?" % T_ASSETS, (n,)
            ).fetchone()
            if not row:
                continue
            sets, vals = ["updated_at=?"], [time.time()]
            if has_kind:
                sets.append("kind=?")
                vals.append(kind)
            if has_subj:
                sets.append("subject_id=?")
                vals.append(subj)

                if skind and not (row["kind"] or "").strip():
                    sets.append("kind=?")
                    vals.append(skind)
            vals.append(n)
            con.execute("UPDATE %s SET %s WHERE name=?" % (T_ASSETS, ", ".join(sets)), vals)
            updated.append(n)
        gone = prune_orphan_subjects(con)
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, updated=updated, count=len(updated),
                   orphan_subjects_removed=gone)


@assets_bp.route("/promote", methods=["POST"])
def promote():
    
    data = request.get_json(silent=True) or {}
    job_id = (data.get("job_id") or "").strip() or None
    names = data.get("names") or []
    if not job_id:
        return jsonify(error="需要 job_id"), 400
    if not isinstance(names, list) or not names:
        return jsonify(error="需要 names 数组"), 400
    ann = {}
    for it in (data.get("items") or []):
        if isinstance(it, dict) and it.get("name"):
            ann[it["name"]] = it
    con = _db()
    gone = 0
    try:
        promoted = []
        for n in names:
            cur = con.execute(
                "UPDATE assets SET job_id=NULL WHERE name=? AND job_id=?",
                (n, job_id),
            )
            if cur.rowcount:
                promoted.append(n)
                it = ann.get(n)
                if it:
                    fields = ["label=?", "kind=?", "owner=?", "posture=?", "updated_at=?"]
                    vals = [it.get("label"), it.get("kind"), it.get("owner"), it.get("posture"), time.time()]
                    k = (it.get("kind") or "").strip()
                    if k in ("character", "voice", "scene", "prop"):
                        fields.append("subject_id=?")
                        vals.append(sync_subject(con, owner=it.get("owner"), kind=k, label=it.get("label")))
                    ap = it.get("appearance")
                    if ap is not None:
                        fields.append("appearance=?")
                        vals.append(_appearance_to_spec(ap))
                    vals.append(n)
                    con.execute(
                        "UPDATE assets SET %s WHERE name=? AND job_id IS NULL" % ", ".join(fields),
                        vals,
                    )
        gone = prune_orphan_subjects(con)
        con.commit()
    finally:
        con.close()
    return jsonify(ok=True, promoted=promoted, count=len(promoted), orphan_subjects_removed=gone)


def _file_fate(name, url=None):
    
    fn = os.path.basename(str(url or name or ""))
    if not fn:
        return {"purged": False, "bytes": 0, "reason": "not-local", "still_referenced": []}
    if url and not str(url).startswith("/"):
        return {"purged": False, "bytes": 0, "reason": "not-local", "still_referenced": []}


    pairs = _mgc.urls_to_pairs([url]) if url else [("assets", fn)]
    if not pairs:
        return {"purged": False, "bytes": 0, "reason": "not-local", "still_referenced": []}
    kind, key = pairs[0]
    try:
        r = _mgc.reclaim([(kind, key)])
    except Exception as e:
        logging.getLogger(__name__).warning("回收资产文件失败 %s: %s", key, e)
        return {"purged": False, "bytes": 0, "reason": "error",
                "still_referenced": [], "detail": "%s: %s" % (type(e).__name__, e)}
    if r["removed"]:
        return {"purged": True, "bytes": r["removed"][0][2], "reason": "purged",
                "still_referenced": []}
    if r["kept"]:
        return {"purged": False, "bytes": 0, "reason": "still-referenced",
                "still_referenced": _mgc.find_references(kind, key)}
    why = r["skipped"][0][2] if r["skipped"] else (r["errors"][0][2] if r["errors"] else "")
    reason = "too-new" if "过新" in why else ("missing" if "不存在" in why else "error")
    return {"purged": False, "bytes": 0, "reason": reason, "still_referenced": [],
            "detail": why}


def _strip_job_reference(con, job_id, name):
    
    try:
        r = con.execute("SELECT assets_json FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if not r:
            return False
        cur = json.loads(r["assets_json"]) if r["assets_json"] else []
        if not isinstance(cur, list):
            return False
        keep = [a for a in cur if not (isinstance(a, dict) and a.get("name") == name)]
        if len(keep) == len(cur):
            return False
        con.execute("UPDATE lv_jobs SET assets_json=?, updated_at=? WHERE id=?",
                    (json.dumps(keep, ensure_ascii=False), time.time(), job_id))
        return True
    except Exception as e:
        logging.getLogger(__name__).warning("摘除 lv_jobs 引用失败 %s/%s: %s", job_id, name, e)
        return False


def _delete_one(name, from_job=None):
    
    con = _db()
    url = None
    try:
        row = con.execute("SELECT url FROM assets WHERE name=?", (name,)).fetchone()
        if not row:
            return 404, {"ok": False, "error": "not found", "name": name}
        url = row["url"]
        con.execute("DELETE FROM assets WHERE name=?", (name,))
        if from_job:
            _strip_job_reference(con, from_job, name)

        try:
            prune_orphan_subjects(con)
        except Exception:
            pass
        con.commit()
    finally:
        con.close()


    try:
        import asset_index
        asset_index.forget(name=name)
    except Exception as e:
        logging.getLogger(__name__).warning("清理内容索引失败 %s: %s", name, e)
    fate = _file_fate(name, url)






    if fate.get("purged"):
        try:
            _thumbs.sweep_orphans()
        except Exception as e:
            logging.getLogger(__name__).warning("清理孤儿缩略图失败: %s", e)
    return 200, {
        "ok": True, "name": name, "deleted": True,
        "purged": fate["purged"], "bytes_freed": fate["bytes"],
        "file_reason": fate["reason"], "still_referenced": fate["still_referenced"],
    }


def delete_names(names, from_job=None):
    
    res = {"count": 0, "deleted": [], "purged_count": 0, "bytes_freed": 0,
           "failed": [], "still_referenced": {}}
    for n in (names or []):
        st, pl = _delete_one(n, from_job=from_job)
        if st != 200:
            res["failed"].append({"name": n, "error": pl.get("error")})
            continue
        res["count"] += 1
        res["deleted"].append(n)
        if pl.get("purged"):
            res["purged_count"] += 1
            res["bytes_freed"] += pl.get("bytes_freed") or 0
        if pl.get("still_referenced"):
            res["still_referenced"][n] = pl["still_referenced"]
    return res


@assets_bp.route("/delete/<name>", methods=["DELETE"])
def delete_asset(name):
    
    data = request.get_json(silent=True) or {}
    status, payload = _delete_one(name, from_job=data.get("from_job"))
    return jsonify(payload), status


@assets_bp.route("/delete_batch", methods=["POST"])
def delete_assets_batch():
    
    data = request.get_json(silent=True) or {}
    names = data.get("names") or []
    if not isinstance(names, list) or not names:
        return jsonify(error="names required (array)"), 400
    res = delete_names(names, from_job=data.get("from_job") or None)
    return jsonify(ok=True, **res)


def session_assets(sid):
    
    if not sid:
        return []
    names = set()
    con = _db()
    try:
        blobs = []
        for sql, args in (("SELECT data FROM sessions WHERE id=?", (sid,)),
                          ("SELECT data FROM agent_sessions WHERE id=?", (sid,))):
            try:
                blobs += [r["data"] for r in con.execute(sql, args)]
            except sqlite3.OperationalError:
                pass
        try:
            for r in con.execute("SELECT data FROM tasks"):
                if json.loads(r["data"] or "{}").get("session_id") == sid:
                    blobs.append(r["data"])
        except sqlite3.OperationalError:
            pass
        try:
            for r in con.execute("SELECT data FROM history"):
                if str(json.loads(r["data"] or "{}").get("sessionId") or "") == str(sid):
                    blobs.append(r["data"])
        except sqlite3.OperationalError:
            pass
        for b in blobs:
            for m in _mgc._RE_ASSET.findall(b or ""):
                n = _mgc._norm_asset(m)
                if n:
                    names.add(n)
        if not names:
            return []
        ph = ",".join("?" * len(names))
        rows = con.execute(_SELECT_ASSET + " WHERE a.name IN (%s)" % ph,
                           sorted(names)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


@assets_bp.route("/by_session/<sid>", methods=["GET"])
def assets_by_session(sid):
    
    items = session_assets(sid)
    if (request.args.get("count") or "") == "1":
        return jsonify(count=len(items))
    return jsonify(count=len(items), items=items)
