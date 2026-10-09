
import sys
from flask import request, jsonify, send_file, send_from_directory, Response, abort, session, make_response




import server.core as _core_mod
import server.provider as _provider
import server.tts_provider as _ttsprov
import server.ark_provider as _arkprov
import server.ms_provider as _msprov
import server.llm as _llm
import server.agent_runs as _runst
import server.imgen as _imgen
import media_gc as _mgc
import thumbs as _thumbs

import server.tts_client as _ttsclient
import server.msg_store as _msgst
import assets_api.store as _assets_store
_THIS_MODULE = sys.modules[__name__]
for _n in dir(_core_mod):
    if not (_n.startswith("__") and _n.endswith("__")):
        setattr(_THIS_MODULE, _n, getattr(_core_mod, _n))

import uuid, time
import queue as _queue, threading as _threading
from longvideo_api._core import _db as _lv_db

@app.route("/<path:_any>", methods=["OPTIONS"])
def _preflight(_any):
    return ("", 204)
@app.route("/favicon.ico")
def _favicon():


    return ("", 204)
@app.route("/api/upload", methods=["POST"])
def api_upload():
    
    if "file" not in request.files:
        return jsonify({"error": "未找到上传文件。"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "文件名为空。"}), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXTS:
        return jsonify({"error": f"不支持的文件类型 .{ext}（仅支持图片/音频/视频）"}), 400
    kind = "image" if ext in IMG_EXTS else ("video" if ext in VID_EXTS else "audio")

    if kind == "video":
        f.stream.seek(0, 2)
        _vsz = f.stream.tell()
        f.stream.seek(0)
        if _vsz > 256 * 1024 * 1024:
            return jsonify({"error": f"视频过大（{_vsz // (1024 * 1024)}MB），参考视频上限 256MB。"}), 400


    h = None
    try:
        import asset_index
        h = asset_index.content_hash(f)
        hit = asset_index.find_by_hash(h)
        if hit and os.path.isfile(os.path.join(ASSETS_DIR, hit["name"])):
            url = f"{_public_base()}/assets/{hit['name']}"


            _register_uploaded_asset(hit["name"], url, kind)
            return jsonify({"url": url, "kind": kind, "name": f.filename, "dedup": True})
    except Exception as e:
        print("[WARN] 素材内容索引不可用，回退直接上传:", e, flush=True)
        h = None

    short = uuid.uuid4().hex[:10]
    orig = _safe_name(f.filename.rsplit(".", 1)[0])
    final_name = f"{short}_{orig}.{ext}"
    f.save(os.path.join(ASSETS_DIR, final_name))
    url = f"{_public_base()}/assets/{final_name}"
    try:
        if h:
            import asset_index
            asset_index.remember(
                h, final_name, f"/assets/{final_name}",
                os.path.getsize(os.path.join(ASSETS_DIR, final_name)), ext,
            )
    except Exception as e:
        print("[WARN] 素材内容索引写入失败:", e, flush=True)


    _register_uploaded_asset(final_name, url, kind)
    return jsonify({"url": url, "kind": kind, "name": f.filename, "dedup": False})


def _register_uploaded_asset(name, url, kind):
    
    try:
        return _assets_store.register(
            name=name, url=url, type=kind,
            origin=_assets_store.ORIGIN_UPLOADED,
            label=os.path.splitext(os.path.basename(name))[0] or None,
        )
    except Exception as e:
        print("[WARN] 上传结果入库失败（不影响上传）:", e, flush=True)
        return None
def _resolve_asset_file(name):
    
    name = _safe_name(name)

    cands = [name]
    if "%" in name:
        try:
            cands.append(unquote(name))
        except Exception:
            pass
    try:
        cands.append(name.encode("latin-1").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    cands.append(unicodedata.normalize("NFC", name))


    m = re.search(r"[0-9a-fA-F]{10}", name)
    if m:
        key = m.group(0)
        for fn in os.listdir(ASSETS_DIR):
            if key in fn:
                cands.append(fn)
                break

    target = unicodedata.normalize("NFC", name).lower()
    for fn in os.listdir(ASSETS_DIR):
        if unicodedata.normalize("NFC", fn).lower() == target:
            cands.append(fn)
            break
    for c in cands:
        full = os.path.join(ASSETS_DIR, _safe_name(c))
        if os.path.isfile(full):
            return full
    return None


def _thumb_or_original(full):
    
    raw = request.args.get("w")
    if not raw:
        return full
    try:
        w = int(raw)
    except (TypeError, ValueError):
        return full
    if w <= 0 or w > 4096:
        return full
    return _thumbs.ensure(full, w) or full


@app.route("/assets/<path:name>")
def serve_asset(name):
    
    full = _resolve_asset_file(name)
    if not full:
        abort(404)
    return send_file(_thumb_or_original(full))

@app.route("/")
def index():
    resp = make_response(send_from_directory(FRONTEND_DIR, "index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
@app.route("/api/config")
def api_config():


    _vm = _provider.get("video_models") or ["agnes-video-2.5-flash", "agnes-video-2.5"]







    _img_st = _img_provider_state()
    _img_prov = _img_st["winner"]
    _img_src = _IMG_PROV_SRC.get(_img_prov, _IMG_PROV_SRC["agnes"])
    _img_models, _img_limits = _img_src["models"](), _img_src["limits"]()
    _img_label = _imgen.IMAGE_PROVIDER_LABELS.get(_img_prov, "Agnes")






    if _arkprov.video_ready():
        _ark_vm = _arkprov.video_models()
        _vm_out = list(_ark_vm)
    else:
        _ark_vm = []
        _vm_out = list(_vm)
    _video_limits = dict(MODEL_LIMITS)
    for _m in _ark_vm:
        _video_limits[_m] = _arkprov.video_limits(_m)



    _lv0 = _video_limits.get(_vm[0]) or {}
    _lv_sec_bounds = [int(_lv0.get("min_seconds") or 4), int(_lv0.get("max_seconds") or 12)]





    def _img_prov_block(key):
        return {
            "enabled": bool(_IMG_ENABLED_SRC[key]()),
            "ready": bool(_img_st["ready"].get(key)),
            "selected": _img_st["selected"] == key,
            "active": _img_prov == key,
        }

    return jsonify({
        "model": _vm_out[0],
        "free": True,
        "hasKey": bool(_cfg_key()),
        "maxAssets": MAX_ASSETS,
        "sizes": ["720P", "1080P", "1K", "2K"],
        "modelLimits": _video_limits,
        "models": list(_video_limits.keys()),
        "lvSecBounds": _lv_sec_bounds,
        "bootId": _BOOT_ID,

        "provider": {
            "baseUrl": _cfg_base(),
            "hasKey": bool(_cfg_key()),
            "videoModels": _vm_out,
            "imageModels": _img_models,
            "llmModels": _provider.get("llm_models"),
            "agentModels": _provider.get("agent_models"),

            "assistantLlmModels": _llm.models_for("assistant"),
            "storyboardLlmModels": _llm.models_for("storyboard"),

            "imageProvider": _img_prov,
            "imageProviderLabel": _img_label,

            "imageProviderSelected": _img_st["selected"],
            "imageProviderConflict": _img_st["conflict"],
            "imageProviderFallback": _img_st["fallback"],
            "imageProviderNote": _img_st["note"],

            "imageProviderChoices": [
                {"key": k, "label": _imgen.IMAGE_PROVIDER_LABELS[k],
                 "host": k != "agnes", "ready": bool(_img_st["ready"].get(k)),
                 "selected": _img_st["selected"] == k, "active": _img_prov == k}
                for k in _imgen.IMAGE_PROVIDER_ORDER
            ],
            "imageModelLimits": _img_limits,



            "ark": dict(_img_prov_block("ark"),
                        hasKey=bool(_arkprov.get("api_key")),
                        fallbackReason=_arkprov.active_state()[1]),
            "ms": dict(_img_prov_block("ms"),
                       hasKey=bool(_msprov.get("api_key")),
                       fallbackReason=_msprov.active_state()[1]),
        },
    })


@app.route("/api/debug/llm_route")
def api_debug_llm_route():
    
    from flask import request
    use_case = request.args.get("use_case", "assistant")
    try:
        be = _llm.route(use_case)
        ok, reason = _llm.configured(use_case)
        res = _llm._resolve_now(use_case)
        return jsonify({
            "use_case": use_case,
            "backend": be,
            "configured": ok,
            "reason": reason,
            "models": _llm.models_for(use_case),
            "default_model": _llm.default_model(use_case),
            "resolve": res,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400










_VIDEO_SUBMIT_DEDUP = {}
_VIDEO_DEDUP_LOCK = _threading.Lock()
_VIDEO_DEDUP_WINDOW = 8.0


def _video_fingerprint(data):
    
    import hashlib as _hl

    def _brief(v):

        s = "" if v is None else str(v)
        return s if len(s) <= 160 else "%d:%s" % (len(s), s[:64])

    d = data or {}
    parts = [
        _brief(d.get("model")), _brief(d.get("mode")), _brief(d.get("prompt")),
        _brief(d.get("seconds")), _brief(d.get("size")), _brief(d.get("aspect_ratio")),
        _brief(d.get("seed")), _brief(d.get("sessionId")),
        _brief(d.get("images")), _brief(d.get("audios")), _brief(d.get("videos")),
        _brief(d.get("first_frame")), _brief(d.get("last_frame")),
    ]
    return _hl.md5("|".join(parts).encode("utf-8")).hexdigest()


def _video_dedup_hit(data):
    
    fp = _video_fingerprint(data)
    with _VIDEO_DEDUP_LOCK:
        hit = _VIDEO_SUBMIT_DEDUP.get(fp)
        if hit and (time.time() - hit[1]) < _VIDEO_DEDUP_WINDOW:
            print(f"[generate] 命中重复提交指纹，复用已有任务（不重新提交、不计费）rid={hit[0].get('rid')}")
            return dict(hit[0]), 200
    return None


def _video_dedup_remember(data, resp):
    
    fp = _video_fingerprint(data)
    with _VIDEO_DEDUP_LOCK:
        _VIDEO_SUBMIT_DEDUP[fp] = (dict(resp), time.time())
        now = time.time()
        for k in [k for k, v in _VIDEO_SUBMIT_DEDUP.items()
                  if now - v[1] > _VIDEO_DEDUP_WINDOW * 4]:
            _VIDEO_SUBMIT_DEDUP.pop(k, None)


def _submit_video(data):
    
    model = str(data.get("model") or "").strip()
    if not model:
        model = (_arkprov.video_models()[0] if _arkprov.video_ready()
                 else (_provider.get("video_models") or ["agnes-video-2.5-flash"])[0])
    if _arkprov.is_video_model(model):
        _out = _submit_video_to_ark(data)
    else:
        _out = _submit_video_to_agnes(data)

    if isinstance(_out, tuple) and len(_out) == 2 and _out[1] == 200:
        try:
            _video_dedup_remember({**data, "model": model}, _out[0])
        except Exception:
            pass
    return _out


def _submit_video_to_ark(data):
    
    if not _arkprov.get("video_enabled"):
        return {"error": "方舟视频未启用。请在「服务商设置 → 火山方舟」勾选视频开关（与生图开关相互独立）。"}, 400
    if not _arkprov.get("api_key"):
        return {"error": "方舟未配置访问密钥。请在「服务商设置 → 火山方舟」填入 API Key。"}, 400
    model = str(data.get("model") or "").strip() or (_arkprov.video_models()[0])
    payload, err = _arkprov.to_ark_video_payload({**data, "model": model}, b64_fn=_to_b64_if_local)
    if err:
        return {"error": err}, 400

    base = (_arkprov.get("base_url") or "").rstrip("/")
    key = _arkprov.get("api_key") or ""
    try:
        resp = requests.post(
            f"{base}/contents/generations/tasks",
            json=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=(10, 60),
        )
    except requests.RequestException as e:
        return {"error": f"请求方舟 API 失败：{e}"}, 502
    if resp.status_code != 200:
        try:
            _e = resp.json().get("error")
            _code = (_e.get("code") if isinstance(_e, dict) else "") or ""
            msg = (_e.get("message") if isinstance(_e, dict) else _e) or resp.text[:160]
        except Exception:
            _code, msg = "", resp.text[:160]
        if _code == "ModelNotOpen":
            msg = f"模型 {model} 未在你的方舟账号开通。请到火山方舟控制台「开通管理」页开通该模型后重试（开通免费，生成按量计费）。"
        return {"error": f"方舟拒绝请求（{resp.status_code}）：{msg}"}, resp.status_code
    try:
        body = resp.json()
    except Exception:
        return {"error": f"无法解析方舟响应：{resp.text[:160]}"}, 502
    video_id = body.get("id") or body.get("task_id")
    if not video_id:
        return {"error": f"方舟响应缺少任务 ID：{str(body)[:160]}"}, 502


    rid = uuid.uuid4().hex[:12]
    record = {
        "id": rid,
        "video_id": video_id,
        "upstream": "ark",
        "sessionId": data.get("sessionId"),
        "model": model,
        "mode": data.get("mode", "text"),
        "prompt": str(data.get("prompt") or ""),
        "params": {
            "seconds": payload.get("duration"),
            "aspect_ratio": payload.get("ratio"),
            "size": payload.get("resolution"),
            "seed": payload.get("seed"),
        },
        "assets": data.get("assets") or [],
        "created_at": time.time(),
        "video_url": None,
        "status": "processing",
    }
    rows = _load_history()
    rows.insert(0, record)
    _save_history(rows)
    return {"video_id": video_id, "rid": rid, "raw": body, "upstream": "ark"}, 200


def _submit_video_to_agnes(data):
    
    if not _cfg_key():
        return {"error": "尚未配置访问密钥。请点击左侧「服务商设置」填入接口地址与密钥（或 .env 配置 AGNES_API_KEY 后重启）。"}, 500

    mode = data.get("mode", "text")


    allowed_models = _provider.get("video_models") or ["agnes-video-2.5-flash", "agnes-video-2.5"]
    model = data.get("model", allowed_models[0])
    if model not in allowed_models:
        model = allowed_models[0]

    payload = {
        "model": model,
        "prompt": data.get("prompt", ""),
        "seconds": str(data.get("seconds", "5")),
        "mode": mode,
    }



    if model == "agnes-video-2.5-flash":
        size = "720P"
    else:
        allowed = ["720P", "1080P", "1K", "2K"]
        size = (data.get("size") or "720P").upper()
        if size not in allowed:
            size = "720P"
    payload["size"] = size


    AR_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9"}
    ar = (data.get("aspect_ratio") or "").strip()
    if ar in AR_RATIOS:
        payload["aspect_ratio"] = ar
    if data.get("seed") is not None and data.get("seed") != "":
        try:
            payload["seed"] = int(data["seed"])
        except (TypeError, ValueError):
            pass

    if mode == "keyframe":
        if data.get("first_frame"):
            payload["first_frame"] = _to_b64_if_local(data["first_frame"])
        if data.get("last_frame"):
            payload["last_frame"] = _to_b64_if_local(data["last_frame"])
        if not payload.get("first_frame") and not payload.get("last_frame"):
            return {"error": "首尾帧模式至少需要提供首帧或尾帧图片 URL。"}, 400
    elif mode == "reference":
        images = [u for u in (data.get("images") or []) if u]
        audios = [u for u in (data.get("audios") or []) if u]
        videos = [u for u in (data.get("videos") or []) if u]
        if not images and not audios and not videos:
            return {"error": "全能参考模式至少需要提供一张参考图片、一个参考音频或一段参考视频 URL。"}, 400



        if model == "agnes-video-2.5-flash" and len(images) > 5:
            return {"error": f"当前模型（Agnes 2.5 Video Flash）参考图片最多 5 张，你传了 {len(images)} 张。"}, 400

        if model == "agnes-video-2.5-flash" and len(audios) > 3:
            return {"error": f"当前模型（Agnes 2.5 Video Flash）参考音频最多 3 段，你传了 {len(audios)} 段。请删减音频素材后重试。"}, 400

        if model == "agnes-video-2.5-flash" and videos:
            return {"error": "当前模型（Agnes 2.5 Video Flash）不支持参考视频，请切换到 Agnes 2.5 Video 标准版，或移除视频素材。"}, 400
        if images:
            payload["images"] = [_to_b64_if_local(u) for u in images]
        if audios:
            payload["audios"] = [_to_b64_if_local(u) for u in audios]
        if videos:
            payload["videos"] = [_to_b64_if_local(u) for u in videos]



    if not payload.get("prompt"):
        return {"error": "请填写提示词（prompt）。Agnes 视频生成的「文生视频 / 全能参考 / 首尾帧」三种模式都需要提示词来描述画面。"}, 400


    try:
        _approx = len(json.dumps(payload).encode("utf-8"))
        imgs = len(images) if "images" in locals() else 0
        auds = len(audios) if "audios" in locals() else 0
        vids = len(videos) if "videos" in locals() else 0
        print(f"[generate] model={model} mode={mode} size={size} seconds={payload.get('seconds')} imgs={imgs} auds={auds} vids={vids} approxBody={_approx/1024:.1f}KB")
    except Exception:
        pass





    resp = None
    last_err = None
    for _att in range(1, 4):
        try:
            resp = requests.post(
                f"{_cfg_base()}/videos",
                headers={
                    "Authorization": f"Bearer {_cfg_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(10, 300),
            )
            break
        except requests.exceptions.ReadTimeout as e:

            last_err = e
            print(f"[generate] 读超时（请求已送达服务端，不重试以免重复生成计费）：{e}")
            break
        except (requests.ConnectionError, requests.exceptions.ConnectTimeout) as e:

            last_err = e
            print(f"[generate] Agnes 连接失败/连接超时（第 {_att} 次）：{type(e).__name__}: {e}" + ("" if _att >= 3 else "，2s 后重试…"))
            if _att < 3:
                time.sleep(2)
        except requests.RequestException as e:

            last_err = e
            print(f"[generate] requests.post 异常（第 {_att} 次）：{type(e).__name__}: {e}" + ("" if _att >= 3 else "，2s 后重试…"))
            if _att < 3:
                time.sleep(2)
    if resp is None:
        print(f"[generate] 3 次重试后仍失败：{type(last_err).__name__}: {last_err}")
        return {"error": f"请求 Agnes API 失败：{last_err}"}, 502

    if resp.status_code != 200:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text

        if isinstance(detail, dict):
            msg = detail.get("detail") or (detail.get("error") or {}).get("message") or detail
        else:
            msg = detail
        return {"error": f"Agnes 拒绝请求（{resp.status_code}）：{msg}"}, resp.status_code

    body = resp.json()
    video_id = body.get("video_id") or body.get("id") or body.get("task_id")


    rid = uuid.uuid4().hex[:12]
    record = {
        "id": rid,
        "video_id": video_id,
        "upstream": "agnes",
        "sessionId": data.get("sessionId"),
        "model": model,
        "mode": mode,
        "prompt": payload["prompt"],
        "params": {
            "seconds": payload.get("seconds"),
            "aspect_ratio": payload.get("aspect_ratio"),
            "size": payload.get("size"),
            "seed": payload.get("seed"),
        },
        "assets": data.get("assets") or [],
        "created_at": time.time(),
        "video_url": None,
        "status": "processing",
    }
    rows = _load_history()
    rows.insert(0, record)
    _save_history(rows)

    return {"video_id": video_id, "rid": rid, "raw": body}, 200

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or {}



    _hit = _video_dedup_hit(data)
    if _hit is not None:
        return jsonify(_hit[0]), _hit[1]
    body, code = _submit_video(data)
    return jsonify(body), code
def _src_wh(v):
    
    m = re.match(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$", str(v or ""))
    if not m:
        return 0, 0
    w, h = int(m.group(1)), int(m.group(2))
    if 1 <= w <= 99999 and 1 <= h <= 99999:
        return w, h
    return 0, 0


def _image_pixel_size(url):
    
    if not url or not isinstance(url, str):
        return None, None
    try:
        from PIL import Image as _PIL
        import io as _io
        import base64 as _b64
        if url.startswith("data:"):
            _m = re.match(r"^data:[^;]+;base64,(.+)$", url, re.S)
            if not _m:
                return None, None
            with _PIL.open(_io.BytesIO(_b64.b64decode(_m.group(1)))) as im:
                return im.size
        full = _pm.asset_local_path(url, ASSETS_DIR, _public_base())
        if not full:
            return None, None
        with _PIL.open(full) as im:
            return im.size
    except Exception:
        return None, None













_IMG_SUBMIT_DEDUP = {}
_IMG_DEDUP_LOCK = _threading.Lock()
_IMG_DEDUP_WINDOW = 8.0
def _img_fingerprint(model, prompt, images, size, ratio, seed, session_id, upstream):
    import hashlib as _hl
    parts = [str(model), str(prompt), str(tuple(images or [])), str(size),
             str(ratio), str(seed), str(session_id), str(upstream)]
    return _hl.md5("|".join(parts).encode("utf-8")).hexdigest()


def _submit_image_task(data):
    


    _prov = _img_provider_now()
    use_ark = (_prov == "ark")
    use_ms = (_prov == "ms")

    if not use_ark and not use_ms and not _cfg_key():
        tip = "尚未配置访问密钥。请点击左侧「服务商设置」填入密钥（或 .env 配置 AGNES_API_KEY 后重启）。"
        if _arkprov.get("enabled") and not _arkprov.get("api_key"):
            tip = ("「豆包生图」已开启但未填 ARK 访问密钥，已回落 Agnes —— 而 Agnes 也未配密钥。"
                   "请在「服务商设置」里补齐其中任意一个（Agnes 页或豆包生图页）。")
        elif _msprov.get("enabled") and not _msprov.get("api_key"):
            tip = ("「魔搭生图」已开启但未填 ModelScope 访问令牌，已回落 Agnes —— 而 Agnes 也未配密钥。"
                   "请在「服务商设置」里补齐其中任意一个（Agnes 页或魔搭页）。")
        return {"error": tip}, 500

    if use_ark:
        allowed_models = _arkprov.image_models()
        _caps_of = _arkprov.model_limits
    elif use_ms:
        allowed_models = _msprov.image_models()
        _caps_of = _msprov.model_limits
    else:
        allowed_models = _provider.get("image_models") or ["agnes-image-2.1-flash", "agnes-image-2.5-flash"]
        _caps_of = None

    _ref_imgs = [u for u in (data.get("images") or []) if u]
    model = str(data.get("model") or "").strip()
    if model not in allowed_models:
        model = ""
    if not model:




        if _caps_of:
            _want = "can_edit" if _ref_imgs else "can_t2i"
            _cands = [m for m in allowed_models if _caps_of(m).get(_want)]
            if not _cands:
                _what = "带参考图的编辑" if _ref_imgs else "文生图"
                return {"error": f"当前生图服务商下没有可用于「{_what}」的模型，"
                                 f"请在「服务商设置」里补充合适的模型（或关掉该服务商回落 Agnes）。"}, 400
            model = _cands[0]
        else:
            model = allowed_models[0]


    size = (data.get("size") or "1K").upper()
    if use_ark:

        size = _arkprov.resolve_tier(size, _arkprov.model_limits(model))
    elif size not in _imgen.AGNES_TIERS:
        size = "1K"
    ratio = (data.get("ratio") or data.get("aspect_ratio") or "").strip()
    images = _ref_imgs







    src_size = ""
    if images and not (data.get("size") or "").strip():
        _w = _h = 0


        _cw, _ch = _src_wh(data.get("src_size"))
        if _cw and _ch:
            _w, _h = _cw, _ch
        else:
            _w, _h = _image_pixel_size(images[0])
        if _w and _h:
            src_size = "%dx%d" % (_w, _h)


            if not ratio:
                ratio = "%d:%d" % (_w, _h)


    prompt = (data.get("prompt") or "").strip()
    if not prompt and not images:
        return {"error": "请填写提示词，或在图生图模式下上传至少一张参考图片。"}, 400


    if images:
        try:
            from PIL import Image as _PIL
            import io as _io
            import base64 as _b64
            import re as _re
            MIN_EDGE = 256
            for idx, u in enumerate(images):
                b = None
                if u.startswith("data:"):
                    m = _re.match(r"^data:[^;]+;base64,(.+)$", u, _re.S)
                    if m: b = _b64.b64decode(m.group(1))
                else:
                    continue
                if not b: continue
                im = _PIL.open(_io.BytesIO(b))
                w, h = im.size
                if w < MIN_EDGE or h < MIN_EDGE:
                    return {"error": f"参考图 {idx+1} 尺寸过小（{w}×{h}，至少需要 {MIN_EDGE}×{MIN_EDGE}）。请换一张更大的图，或在图片编辑器里放大后再上传。"}, 400
        except Exception:
            pass


    payload = {"model": model, "prompt": prompt}
    if src_size:
        payload["src_size"] = src_size





    if src_size and not (use_ark or use_ms):
        payload["size"] = _imgen.solve_size(size, ratio, "tier_string", None,
                                            src_px=_imgen.parse_src_size(src_size),
                                            allowed_tiers=_imgen.AGNES_TIERS)
    else:
        payload["size"] = size
    if ratio:
        payload["ratio"] = ratio
    if data.get("seed") not in (None, ""):
        try:
            payload["seed"] = int(data["seed"])
        except (TypeError, ValueError):
            pass
    extra = {"response_format": "url"}
    if images:




        extra["image"] = list(images)
    payload["extra_body"] = extra

    upstream = None
    if use_ark:


        _ref_cap = (_arkprov.model_limits(model) or {}).get("max_ref_images")
        if _ref_cap and isinstance(payload.get("image"), list) and len(payload["image"]) > _ref_cap:
            payload["image"] = payload["image"][:_ref_cap]
        payload = _arkprov.to_ark_payload(payload)
        upstream = "ark"
    elif use_ms:



        payload = _msprov.to_ms_payload(payload)
        upstream = "ms"



    _fp = _img_fingerprint(model, prompt, images, size, ratio,
                           data.get("seed"), data.get("sessionId"), upstream)
    with _IMG_DEDUP_LOCK:
        _now = time.time()
        _dup = _IMG_SUBMIT_DEDUP.get(_fp)
        if _dup and (_now - _dup[1]) < _IMG_DEDUP_WINDOW:
            return {"task_id": _dup[0], "status": "processing", "dedup": True,
                    "message": "已复用本次提交的生成任务"}, 200

        tid, _ = _create_task("image", model, payload, media_hint="image",
                              session_id=data.get("sessionId"), upstream=upstream)
        _IMG_SUBMIT_DEDUP[_fp] = (tid, _now)

        if len(_IMG_SUBMIT_DEDUP) > 256:
            _exp = _now - _IMG_DEDUP_WINDOW
            for _k in [k for k, v in _IMG_SUBMIT_DEDUP.items() if v[1] < _exp]:
                _IMG_SUBMIT_DEDUP.pop(_k, None)


    return {"task_id": tid, "status": "processing",
            "size": str((payload or {}).get("size") or ""),
            "model": model}, 200

@app.route("/api/image/generate", methods=["POST"])
def api_image_generate():
    data = request.get_json(silent=True) or {}
    body, code = _submit_image_task(data)
    return jsonify(body), code




def _agent_llm_model():
    am = _provider.get("agent_models") or ["agnes-3.0-flash"]
    return am[0]



AGENT_SYSTEM_PROMPT = (
    "你是工具调用层，根据用户自然语言意图选择合适的接口去调用。\n"
    "\n"
    "【通用约定】\n"
    "1. 意图能用工具完成就调用工具，不要只回文字。\n"
    "2. 生成类任务：参数缺失时按常识补全（未说时长用 5 秒、未说画幅用 16:9），不要反问用户。\n"
    "3. 生成提示词扩写成具体、可拍摄的画面描述，不要照抄用户口语。\n"
    "4. 模式选择：默认 text；用户提供了参考图/音频/视频用 reference；用户明确要求首帧或尾帧用 keyframe。\n"
    "5. 不要编造素材 URL，只能使用用户提供的素材。\n"
    "6. 用户只是闲聊、询问或做与接口无关的事，直接回文字，不要强行调用工具。\n"
    "7. 排版：正文按语义分段，段与段之间空一行；作文/文案/脚本等多段内容严禁挤成一大段。\n"
    "\n"
    "【长视频草稿任务：必须分三步，每步都要等用户确认，严禁一步完成】\n"
    "8. 用户要「做长视频 / 生成漫剧 / 开长视频任务」时，按下面三步走，且每步之间必须停下来等用户确认，"
    "不得在未确认的情况下把脚本+素材一次性塞进某个工具：\n"
    "   · 第1步（不调工具）：先分析脚本，抽取其中的角色 / 场景 / 道具，列出每项的【名称 + 类型 + 生成提示词】，"
    "用文字呈现给用户确认。这一步不要调用任何工具，等用户说「可以 / 没问题 / 确认」再继续。\n"
    "   · 第2步（generate_longvideo_assets）：用户确认提示词后，调用 generate_longvideo_assets 逐张生成素材图，"
    "把图片展示给用户。**这一步只生图、不建任务**。\n"
    "     若用户后续要求修改某张素材（如'第一张重画'、'角色变形了'）：必须继续调用 generate_longvideo_assets，"
    "传入完整的最新素材清单——已满意的素材保留其 url，需要重绘的素材保留 label/kind/prompt 但不带 url；"
    "工具会自动跳过带 url 的项、只重绘缺 url 的项，并返回完整清单。严禁用 generate_image 处理长视频素材修改，"
    "因为那样生成的图不会进入长视频素材清单。\n"
    "   · 第3步（submit_longvideo_job）：用户看完图、确认素材无误后，调用 submit_longvideo_job，"
    "把脚本 + 已生成素材（每项带 url）提交建草稿。\n"
    "   严禁在未获用户明确确认前调用 generate_longvideo_assets 或 submit_longvideo_job。"
)





AGENT_THINKING_PARAMS = {"chat_template_kwargs": {"enable_thinking": True}}



AGENT_MAX_TOKENS = 32768





_IMG_TIERS_ALL = ["1K", "2K", "3K", "4K"]
_IMG_RATIOS_ALL = ["1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"]



_IMG_PROV_SRC = {
    "ark": {"models": _arkprov.image_models, "limits": _arkprov.model_limits_map, "caps": _arkprov.model_limits},
    "ms": {"models": _msprov.image_models, "limits": _msprov.model_limits_map, "caps": _msprov.model_limits},
    "agnes": {"models": lambda: (_provider.get("image_models") or ["agnes-image-2.1-flash", "agnes-image-2.5-flash"]),
              "limits": lambda: {}, "caps": None},
}

_IMG_ENABLED_SRC = {"ark": lambda: bool(_arkprov.get("enabled")), "ms": lambda: bool(_msprov.get("enabled"))}
_IMG_READY_SRC = {"ark": lambda: _arkprov.active(), "ms": lambda: _msprov.active()}

_IMG_SAVE_MODS = (("ark", _arkprov), ("ms", _msprov))

_IMG_EXCLUSIVE_DONE = {"done": False}


def _img_enabled_hosts():
    
    out = []
    for k in _imgen.IMAGE_PROVIDER_HOSTS:
        get = _IMG_ENABLED_SRC.get(k)
        if get and get():
            out.append(k)
    return out


def _img_provider_state():
    
    st = _imgen.resolve_image_provider(
        _img_enabled_hosts(),
        {k: f() for k, f in _IMG_READY_SRC.items()},
    )

    if st["conflict"] and not _IMG_EXCLUSIVE_DONE["done"]:
        try:
            _img_apply_exclusive(st["winner"])
            st = _imgen.resolve_image_provider(_img_enabled_hosts(),
                                               {k: f() for k, f in _IMG_READY_SRC.items()})
            print("[img-provider] 检测到多家生图服务商同时开启 → 已按优先级收敛为「%s」"
                  % _imgen.IMAGE_PROVIDER_LABELS.get(st["winner"], st["winner"]))
        except Exception as e:
            print("[img-provider] 互斥收敛失败（忽略）：%s" % e)
        _IMG_EXCLUSIVE_DONE["done"] = True
    return st


def _img_apply_exclusive(chosen):
    
    key = str(chosen or "").strip().lower()
    if key not in _imgen.IMAGE_PROVIDER_ORDER:
        raise ValueError("未知的生图服务商：%r" % chosen)
    for k, mod in _IMG_SAVE_MODS:
        if k in _imgen.IMAGE_PROVIDER_HOSTS:
            mod.save({"enabled": key == k})
    return key


def _img_provider_now():
    
    return _img_provider_state()["winner"]


def _img_sizes_for_agent():
    
    prov = _img_provider_now()
    if prov == "ark":
        out = []
        for c in _arkprov.model_limits_map().values():
            for t in (c.get("tiers") or []):
                if t not in out:
                    out.append(t)




        return sorted(out, key=lambda x: _imgen.PIXEL_TIERS.get(x, 0)) if out else list(_IMG_TIERS_ALL)
    if prov == "ms":
        out = _imgen.reachable_tiers("ms", _msprov.model_limits_map())

        return [t for t in _IMG_TIERS_ALL if t in out] or ["1K"]
    return list(_IMG_TIERS_ALL)


def _img_ratios_for_agent():
    
    if _img_provider_now() != "ms":
        return list(_IMG_RATIOS_ALL)
    allowed = []
    for c in _msprov.model_limits_map().values():
        for r in (c.get("ratios") or []):
            if r not in allowed:
                allowed.append(r)
    if not allowed:
        return list(_IMG_RATIOS_ALL)
    return [r for r in _IMG_RATIOS_ALL if r in allowed] or list(_IMG_RATIOS_ALL)






MULTI_ANGLE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_multi_angle",
        "description": "把一张**已有的图**换个机位重新拍（多角度 / 换视角 / 改景别）。"
                       "用于「换个角度看看 / 转成俯视 / 从侧面拍 / 拉近一点 / 拍个特写」这类需求。"
                       "与 generate_image 的区别：本工具专管**机位变化**，角度用数值精确表达，不要写成散文。",
        "parameters": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "要改机位的那张图的 URL（必填）"},
                "horizontal": {"type": "number",
                               "description": "水平角（度）：正数向右转、负数向左转、0 = 不左右转"},
                "vertical": {"type": "number",
                             "description": "垂直角（度）：正数俯视、负数仰视、0 = 不上下变"},
                "shot": {"type": "string", "enum": ["closeup", "wide"],
                         "description": "景别：closeup=特写、wide=广角；不改景别则不传"},
                "ratio": {"type": "string",
                          "description": "输出画幅（如 16:9 / 9:16），缺省 16:9"},
            },
            "required": ["image"],
        },
    },
}


def _agent_tools():
    
    tools = json.loads(json.dumps(AGENT_TOOLS, ensure_ascii=False))
    sizes, ratios = _img_sizes_for_agent(), _img_ratios_for_agent()
    for t in tools:
        fn = t.get("function") or {}
        if fn.get("name") == "generate_image":
            props = ((fn.get("parameters") or {}).get("properties")) or {}
            if isinstance(props.get("size"), dict):
                props["size"]["enum"] = sizes
                props["size"]["description"] = "分辨率，缺省 1K（可选值随生图服务商与模型变化）"
            if isinstance(props.get("ratio"), dict):
                props["ratio"]["enum"] = ratios
        if fn.get("name") == "generate_video":

            if _arkprov.video_ready():
                _vmodel = _arkprov.video_models()[0]
                _vlim = _arkprov.video_limits(_vmodel)
            else:
                _vmodel = (_provider.get("video_models") or ["agnes-video-2.5-flash"])[0]
                _vlim = MODEL_LIMITS.get(_vmodel) or {}
            _lo, _hi = int(_vlim.get("min_seconds") or 4), int(_vlim.get("max_seconds") or 12)
            vprops = ((fn.get("parameters") or {}).get("properties")) or {}
            if isinstance(vprops.get("seconds"), dict):
                vprops["seconds"]["enum"] = [str(s) for s in range(_lo, _hi + 1)]
                vprops["seconds"]["description"] = f"时长（秒），缺省 5（{_vmodel} 支持 {_lo}~{_hi}s）"
            if isinstance(vprops.get("size"), dict) and _vlim.get("sizes"):
                vprops["size"]["enum"] = list(_vlim["sizes"])

            _vcap_img, _vcap_aud = int(_vlim.get("max_images") or 5), int(_vlim.get("max_audios") or 0)
            _vcap_vid = 1 if _vlim.get("allow_video") else 0
            for _k, _cap in (("images", _vcap_img), ("audios", _vcap_aud), ("videos", _vcap_vid)):
                if isinstance(vprops.get(_k), dict) and isinstance(vprops[_k].get("items"), dict):
                    vprops[_k]["maxItems"] = _cap



    if _multi_angle_available():
        tools.append(json.loads(json.dumps(MULTI_ANGLE_TOOL, ensure_ascii=False)))
    return tools


def _angle_prompt(args):
    
    a = args or {}

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    h, v = _num(a.get("horizontal")), _num(a.get("vertical"))
    shot = str(a.get("shot") or "").strip().lower()

    parts = []


    h = float(h) % 360.0
    if 0 < h <= 180:
        parts.append("将镜头向右转%d度" % int(round(h)))
    elif h > 180:
        parts.append("将镜头向左转%d度" % int(round(360 - h)))


    if abs(v) >= 1:
        if v > 0:
            parts.append("从上方%d度俯拍" % int(round(v)))
        else:
            parts.append("从下方%d度仰拍" % int(round(-v)))
    if shot == "closeup":
        parts.append("将镜头转为特写镜头")
    elif shot == "wide":
        parts.append("将镜头转为广角镜头")
    if not parts:
        return "", "没给出任何机位变化：horizontal / vertical 至少给一个非 0 的值，或给 shot=closeup|wide。"
    return "，".join(parts), ""



















MS_ANGLE_MODEL = "Qwen/Qwen-Image-2.1"


def _multi_angle_available():
    
    prov = _img_provider_now()
    caps = _IMG_PROV_SRC.get(prov, {}).get("caps")
    if not caps:

        return bool(_cfg_key())
    return any(caps(m).get("can_edit") for m in _IMG_PROV_SRC[prov]["models"]())


def _multi_angle_model():
    
    prov = _img_provider_now()
    if prov == "agnes":
        return ""
    src = _IMG_PROV_SRC.get(prov) or {}
    models, caps = src.get("models"), src.get("caps")
    if not models or not caps:
        return ""
    models = models()
    if prov == "ms" and MS_ANGLE_MODEL in models:
        return MS_ANGLE_MODEL
    for m in models:
        if caps(m).get("can_edit"):
            return m
    return ""


def _multi_angle_submit(args, session_id):
    
    if not _multi_angle_available():
        return {"kind": "error",
                "error": "当前生图服务商下没有可用于「带参考图的编辑」的模型，无法换机位。"
                         "请在「服务商设置」里补充合适的可编辑模型，或切换到有编辑能力的服务商。"}, False
    img = str(args.get("image") or "").strip()
    if not img:
        return {"kind": "error", "error": "generate_multi_angle 需要 image（要改机位的那张图的 URL）。"}, False

    prompt, err = _angle_prompt(args)
    if err:
        return {"kind": "error", "error": err}, False

    model = _multi_angle_model()





    payload = {
        "prompt": prompt,
        "images": [img],
        "sessionId": session_id,
    }
    if model:
        payload["model"] = model
    if args.get("ratio"):
        payload["ratio"] = args["ratio"]
    body, code = _submit_image_task(payload)
    if code != 200:
        return {"kind": "image", "error": body.get("error") or "换机位提交失败", "code": code}, False

    return {"kind": "image",
            "task_id": body.get("task_id"),
            "status": body.get("status"),
            "prompt": prompt,
            "size": body.get("size") or payload.get("size"),
            "ratio": payload.get("ratio")}, True


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_video",
            "description": "根据提示词生成一段视频。用于「生成视频 / 做一段短片 / 出片」这类需求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "扩写后的具体画面描述"},
                    "mode": {"type": "string", "enum": ["text", "reference", "keyframe"], "description": "生成模式，缺省 text"},
                    "seconds": {"type": "string", "enum": ["4", "5", "6", "7", "8", "9", "10", "11", "12"], "description": "时长（秒），缺省 5"},
                    "size": {"type": "string", "enum": ["720P", "1080P", "1K", "2K"]},
                    "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]},
                    "images": {"type": "array", "items": {"type": "string"}, "description": "参考图 URL（reference 模式）"},
                    "audios": {"type": "array", "items": {"type": "string"}, "description": "参考音频 URL"},
                    "videos": {"type": "array", "items": {"type": "string"}, "description": "参考视频 URL"},
                    "first_frame": {"type": "string", "description": "首帧图 URL（keyframe 模式）"},
                    "last_frame": {"type": "string", "description": "尾帧图 URL（keyframe 模式）"}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "根据提示词生成一张图片。用于「画一张图 / 生成图片 / 出素材图」这类需求。不用于长视频流程中的素材修改——长视频素材必须用 generate_longvideo_assets 生成或重绘。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "扩写后的画面描述"},
                    "size": {"type": "string", "enum": ["1K", "2K", "3K", "4K"], "description": "分辨率，缺省 1K"},
                    "ratio": {"type": "string", "enum": ["1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"]},
                    "images": {"type": "array", "items": {"type": "string"}, "description": "参考图 URL（图生图）"}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_longvideo_assets",
            "description": "（长视频流程第2步：须先与用户确认提示词清单）根据素材清单逐张生成素材图，并返回每张图的 URL 预览。**本工具只生图、不建任务**。生成后把图片展示给用户，等用户确认无误，再用 submit_longvideo_job 提交建草稿。支持局部修改：清单中已带 url 的项会被保留、不会重复生成；需要重绘的项保留 label/kind/prompt 但不带 url。用户要求修改某张素材时，必须继续调用本工具，严禁用 generate_image 处理长视频素材。",
            "parameters": {
                "type": "object",
                "properties": {
                    "assets": {
                        "type": "array",
                        "description": "素材清单（角色 / 场景 / 道具），每项生成一张图。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "素材名（角色名 / 场景名 / 道具名），须与脚本称呼一致"},
                                "kind": {"type": "string", "enum": ["character", "scene", "prop"], "description": "素材类型"},
                                "prompt": {"type": "string", "description": "生成该素材图的画面描述（扩写后的具体画面）"},
                                "owner": {"type": "string", "description": "归属角色 label（kind=character 时填，用于绑定声线）"},
                                "posture": {"type": "string", "description": "可选：姿态 / 外观描述"},
                                "size": {"type": "string", "description": "可选分辨率"},
                                "ratio": {"type": "string", "description": "可选画幅"},
                                "images": {"type": "array", "items": {"type": "string"}, "description": "可选参考图 URL（图生图）"}
                            },
                            "required": ["label", "kind", "prompt"]
                        }
                    }
                },
                "required": ["assets"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_longvideo_job",
            "description": "（长视频流程第3步：须用户先看素材图确认）把一份脚本 + 已生成的素材图（每项带 url）落成一个长视频草稿任务。用于用户确认素材无误后提交。返回任务 job_id，用户可在长视频工作台继续（点智能分镜接生成）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "故事脚本文本（用户自带或已与助手确认）。可空，由用户在长视频侧补全。"},
                    "job_id": {"type": "string", "description": "可选：已有草稿任务 id，传入则更新该任务（替换素材）而非新建。"},
                    "assets": {
                        "type": "array",
                        "description": "已生成的素材（每项须带 url，来自 generate_longvideo_assets 的结果）。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "素材唯一文件名（必须原样带回 generate_longvideo_assets 返回的 name 字段，不要改名或省略，否则分镜后图片无法被找到）"},
                                "label": {"type": "string", "description": "素材名"},
                                "kind": {"type": "string", "enum": ["character", "scene", "prop"], "description": "素材类型"},
                                "url": {"type": "string", "description": "素材图 URL（来自 generate_longvideo_assets 的结果）"},
                                "owner": {"type": "string", "description": "归属角色 label"},
                                "posture": {"type": "string", "description": "可选：姿态 / 外观描述"}
                            },
                            "required": ["label", "kind", "url"]
                        }
                    }
                },
                "required": ["assets"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "register_assets",
            "description": "把已知 URL 的素材追加登记到已有长视频任务（写 assets，name 与 jobs.assets_json 对齐）。一般补充素材用；多数场景 generate_longvideo_assets + submit_longvideo_job 两步完成即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "目标草稿任务 id"},
                    "assets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "素材名（与 jobs.assets_json 对齐）"},
                                "url": {"type": "string", "description": "素材图 URL"},
                                "label": {"type": "string", "description": "展示名"},
                                "kind": {"type": "string", "enum": ["character", "scene", "prop"]},
                                "owner": {"type": "string"},
                                "posture": {"type": "string"}
                            },
                            "required": ["name", "url", "kind"]
                        }
                    }
                },
                "required": ["job_id", "assets"]
            }
        }
    }
]


def _lv_upsert_assets(con, job_id, assets):
    
    written = []
    for a in (assets or []):
        name = a.get("name")
        url = a.get("url")
        if not name or not url:
            continue
        label = a.get("label") or name
        kind = a.get("kind") or "prop"
        owner = a.get("owner")
        posture = a.get("posture")
        typ = a.get("type") or "image"
        origin = a.get("origin") or _assets_store.ORIGIN_UPLOADED

        sid = _assets_store.sync_subject(con, owner=owner, kind=kind, label=a.get("label"))
        now = time.time()
        cur = con.execute("SELECT name FROM assets WHERE name=?", (name,)).fetchone()
        if cur:
            con.execute(
                "UPDATE assets SET label=?,kind=?,owner=?,posture=?,job_id=?,origin=?,subject_id=?,updated_at=? "
                "WHERE name=?",
                (label, kind, owner, posture, job_id, origin, sid, now, name),
            )
        else:
            con.execute(
                "INSERT INTO assets(name,url,type,label,kind,owner,posture,job_id,created_at,origin,subject_id,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, url, typ, label, kind, owner, posture, job_id, now, origin, sid, now),
            )
        written.append(name)
    con.commit()
    return written


def _lv_generate_assets(assets, on_progress=None, on_item=None):
    
    norm, failed = [], []
    _assets = list(assets or [])
    _total = len(_assets)
    if _total == 0:
        return norm, failed


    _prov = _img_provider_now()
    _psrc = _IMG_PROV_SRC.get(_prov, _IMG_PROV_SRC["agnes"])


    _caps = _psrc["caps"]
    _cands = [m for m in _psrc["models"]() if (_caps(m) if _caps else {}).get("can_t2i")] if _caps \
        else list(_psrc["models"]())
    _img_model = (_cands or _psrc["models"]() or [""])[0]
    for _i, a in enumerate(_assets):
        label = a.get("label") or ""

        if a.get("url"):
            norm.append({
                "name": a.get("name") or f"lv_{uuid.uuid4().hex[:10]}_{_safe_name(label or 'asset')}",
                "url": a.get("url"),
                "type": "image",
                "label": label,
                "kind": a.get("kind") or "prop",
                "owner": a.get("owner"),
                "posture": a.get("posture"),
                "created_at": a.get("created_at") or time.time(),

                "origin": _assets_store.ORIGIN_UPLOADED,
            })
            if on_progress:
                try:
                    on_progress(_i + 1, _total, label or "已有素材")
                except Exception:
                    pass
            if on_item:
                try:
                    on_item(_i, norm[-1])
                except Exception:
                    pass
            continue
        prompt = a.get("prompt") or label or ""
        if not prompt:
            failed.append({"label": label, "error": "素材缺少 prompt，无法生图"})
            if on_progress:
                try:
                    on_progress(_i + 1, _total, (label or "?") + "（缺提示词，已跳过）")
                except Exception:
                    pass
            continue



        _payload = {"prompt": prompt, "model": _img_model}
        if a.get("images"):
            _payload["images"] = a.get("images")
        if a.get("size"):
            _payload["size"] = a.get("size")
        if a.get("ratio"):
            _payload["ratio"] = a.get("ratio")
        _upstream = None


        if _prov == "ark":
            _payload = _arkprov.to_ark_payload(_payload)
            _upstream = "ark"
        elif _prov == "ms":
            _payload = _msprov.to_ms_payload(_payload)
            _upstream = "ms"
        try:
            ok, urls, err = _core_mod._submit_image(_payload, _upstream)
        except Exception as e:
            failed.append({"label": a.get("label"), "error": f"生成失败：{type(e).__name__}: {e}"})
            if on_progress:
                try:
                    on_progress(_i + 1, _total, (label or "?") + "（失败）")
                except Exception:
                    pass
            continue
        if not ok or not urls:
            failed.append({"label": a.get("label"), "error": err})
            if on_progress:
                try:
                    on_progress(_i + 1, _total, (label or "?") + "（失败）")
                except Exception:
                    pass
            continue
        nm = a.get("name") or f"lv_{uuid.uuid4().hex[:10]}_{_safe_name(a.get('label') or 'asset')}"
        norm.append({
            "name": nm,
            "url": urls[0],
            "type": "image",
            "label": a.get("label") or nm,
            "kind": a.get("kind") or "prop",
            "owner": a.get("owner"),
            "posture": a.get("posture"),
            "created_at": time.time(),

            "origin": _assets_store.ORIGIN_CREATED,
        })





        try:
            _assets_store.register(
                name=nm, url=urls[0], type="image",
                origin=_assets_store.ORIGIN_CREATED,
                label=a.get("label") or nm,
                kind=a.get("kind") or "prop",
                owner=a.get("owner"), posture=a.get("posture"),
            )
        except Exception as _reg_e:
            print(f"[warn] 素材图登记失败（不影响生成）: {_reg_e}", flush=True)
        if on_item:
            try:
                on_item(_i, norm[-1])
            except Exception:
                pass


        if on_progress:
            try:
                on_progress(_i + 1, _total, a.get("label") or nm)
            except Exception:
                pass
    return norm, failed


def _lv_submit_job(script, assets_with_url, job_id=None, session_id=None):
    
    con = _lv_db()
    try:
        norm = [a for a in (assets_with_url or []) if a.get("url")]
        failed = [{"label": a.get("label"), "error": "素材缺少 url（未生成成功）"}
                  for a in (assets_with_url or []) if not a.get("url")]
        if not norm:
            return None, None, 0, failed




        for a in norm:
            if a.get("name"):
                continue
            _lb = a.get("label") or "asset"
            _u = (a.get("url") or "").split("?")[0]
            _e = _u.rsplit(".", 1)[-1].lower() if "." in _u else ""
            _ext = ("." + _e) if _e in ("png", "jpg", "jpeg", "webp", "gif") else ""
            a["name"] = f"lv_{uuid.uuid4().hex[:10]}_{_safe_name(_lb)}{_ext}"


        _names = [a.get("name") for a in norm if a.get("name")]
        _type_map = {}
        if _names:
            _rows = con.execute(
                f"SELECT name,type FROM assets WHERE name IN ({','.join('?'*len(_names))})", _names).fetchall()
            _type_map = {r["name"]: r["type"] for r in _rows}
        for a in norm:
            a["type"] = a.get("type") or _type_map.get(a.get("name")) or "image"
        t = time.gmtime(time.time() + 8 * 3600)
        default_name = f"任务 {t.tm_mon}/{t.tm_mday} {t.tm_hour:02d}:{t.tm_min:02d}"
        assets_json = json.dumps(norm, ensure_ascii=False)
        existing = job_id and con.execute("SELECT id FROM lv_jobs WHERE id=?", (job_id,)).fetchone()
        if existing:
            con.execute(
                "UPDATE lv_jobs SET script=?, assets_json=?, stage=?, segment_count=?, updated_at=? WHERE id=?",
                (script or "", assets_json, "素材登记", 0, time.time(), job_id),
            )
            if norm:
                con.execute(
                    "DELETE FROM assets WHERE job_id=? AND name NOT IN "
                    "(SELECT json_extract(value,'$.name') FROM json_each(?))",
                    (job_id, assets_json),
                )
        else:
            job_id = uuid.uuid4().hex[:12]
            con.execute(
                "INSERT INTO lv_jobs(id,script,status,stage,segment_count,assets_json,shots_json,gen_params_json,name,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, script or "", "draft", "素材登记", 0, assets_json, "[]", "{}", default_name, time.time(), time.time()),
            )
        if norm:
            _lv_upsert_assets(con, job_id, norm)


        if job_id and session_id:
            try:
                con.execute("UPDATE lv_jobs SET session_id=? WHERE id=?", (session_id, job_id))
            except Exception as e:
                print(f"[warn] 写入长视频任务的 session_id 失败（不影响建任务）：{e}")
        con.commit()
    finally:
        con.close()
    return job_id, default_name, len(norm), failed


def _agent_tool_events(name, args, session_id, holder, on_item=None):
    
    q = _queue.Queue()

    def _work():
        try:
            item, _ok = _agent_run_tool(
                name, args, session_id,
                on_progress=lambda done, total, label: q.put(("p", (done, total, label))),
                on_item=on_item,
            )
            q.put(("r", item))
        except Exception as e:
            q.put(("e", f"{type(e).__name__}: {e}"))

    _threading.Thread(target=_work, daemon=True).start()




    while True:
        try:
            kind, payload = q.get(timeout=2.0)
        except _queue.Empty:
            yield {"type": "tool_progress", "text": "仍在执行中…（长视频素材逐张生成，请稍候）"}
            continue
        if kind == "p":
            done, total, label = payload
            txt = f"正在生成素材 {done}/{total}" + (f"：{label}" if label else "")
            yield {"type": "tool_progress", "done": done, "total": total,
                   "label": label, "text": txt}
            continue
        if kind == "e":
            holder["error"] = f"工具 {name} 执行失败：{payload}"
        else:
            holder["item"] = payload
        return


def _agent_run_tool(name, args, session_id, on_progress=None, on_item=None):
    
    if name == "generate_video":
        payload = {
            "prompt": args.get("prompt") or "",
            "mode": args.get("mode") or "text",
            "seconds": args.get("seconds"),
            "size": args.get("size"),
            "aspect_ratio": args.get("aspect_ratio"),
            "images": args.get("images") or [],
            "audios": args.get("audios") or [],
            "videos": args.get("videos") or [],
            "first_frame": args.get("first_frame"),
            "last_frame": args.get("last_frame"),
            "sessionId": session_id,
        }
        body, code = _submit_video(payload)
        if code == 200:
            return {
                "kind": "video",
                "video_id": body.get("video_id"),
                "rid": body.get("rid"),
                "prompt": payload["prompt"],
                "mode": payload["mode"],
                "seconds": payload.get("seconds") or "5",
                "aspect_ratio": payload.get("aspect_ratio"),
                "size": payload.get("size"),
            }, True
        return {"kind": "video", "error": body.get("error"), "code": code}, False

    if name == "generate_image":
        payload = {
            "prompt": args.get("prompt") or "",
            "size": args.get("size"),
            "ratio": args.get("ratio"),
            "images": args.get("images") or [],
            "sessionId": session_id,
        }
        body, code = _submit_image_task(payload)
        if code == 200:
            return {
                "kind": "image",
                "task_id": body.get("task_id"),
                "status": body.get("status"),
                "prompt": payload["prompt"],
                "size": payload.get("size"),
                "ratio": payload.get("ratio"),
            }, True
        return {"kind": "image", "error": body.get("error"), "code": code}, False

    if name == "generate_multi_angle":



        return _multi_angle_submit(args, session_id)

    if name == "generate_longvideo_assets":
        assets = args.get("assets") or []


        if not assets:
            return {"kind": "error",
                    "error": "generate_longvideo_assets 需要非空的 assets 素材清单（每项含 label/kind/prompt）。"
                             "请先规划角色/场景/道具的生成提示词，待用户确认后再调用本工具，不要发空参数。"}, False
        norm, failed = _lv_generate_assets(assets, on_progress=on_progress, on_item=on_item)
        if not norm:
            first = next((f.get("error") for f in failed if f.get("error")), "未知原因")
            return {"kind": "error",
                    "error": f"{len(failed)} 个素材全部生成失败，未生成任何图片。首个原因：{first}"}, False

        item = {
            "kind": "longvideo_assets",
            "assets": [{"url": a.get("url"), "label": a.get("label"),
                        "name": a.get("name"), "kind": a.get("kind")} for a in norm],
            "failed": failed,
        }
        return item, True

    if name == "submit_longvideo_job":
        script = args.get("script") or ""
        assets = args.get("assets") or []
        if not assets:
            return {"kind": "error",
                    "error": "submit_longvideo_job 需要非空的 assets（每项须带 url，来自 generate_longvideo_assets 的结果）。"
                             "请先调用 generate_longvideo_assets 生成素材，等用户确认后再提交。"}, False

        missing = [a.get("label") or "?" for a in assets if not a.get("url")]
        if missing:
            return {"kind": "error",
                    "error": f"以下素材缺少 url，无法提交：{', '.join(missing)}。请先调用 generate_longvideo_assets 生成它们。"}, False
        jid, jname, cnt, failed = _lv_submit_job(script, assets, args.get("job_id"),
                                                 session_id=session_id)
        if not jid:
            first = next((f.get("error") for f in failed if f.get("error")), "未知原因")
            return {"kind": "error",
                    "error": f"提交失败：{first}"}, False
        item = {
            "kind": "longvideo_job",
            "job_id": jid,
            "name": jname,
            "asset_count": cnt,
            "failed": failed,
        }
        return item, True

    if name == "register_assets":
        job_id = args.get("job_id")
        assets = args.get("assets") or []
        if not job_id:
            return {"kind": "longvideo_assets", "error": "缺少 job_id"}, False
        con = _lv_db()
        try:
            names = _lv_upsert_assets(con, job_id, assets)
        finally:
            con.close()
        return {"kind": "longvideo_assets", "job_id": job_id, "count": len(names)}, True

    return {"kind": "unknown", "error": f"未知工具：{name}"}, False


def _agent_split_think(raw):
    
    t = (raw or "").strip()
    if not t.startswith("【思考】"):
        return "", t
    rest = t[4:].lstrip()
    nl = rest.find("\n")
    if nl < 0:
        return rest.strip(), ""
    return rest[:nl].strip(), rest[nl:].strip()













AGENT_HISTORY_TOKEN_BUDGET = 30000
AGENT_HISTORY_MAX_ENTRIES = 200




AGENT_HISTORY_HARD_CAP = 150000


def _agent_est_tokens(content):
    
    return len(str(content or ""))


def _agent_pick_history(hist):
    
    if not isinstance(hist, list):
        return [], 0
    valid = [h for h in hist
             if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")]
    if not valid:
        return [], 0
    pool = valid[-AGENT_HISTORY_MAX_ENTRIES:]
    kept, used = [], 0
    for h in reversed(pool):
        t = _agent_est_tokens(h.get("content"))
        if t > AGENT_HISTORY_HARD_CAP:
            continue
        if kept and used + t > AGENT_HISTORY_TOKEN_BUDGET:
            break
        kept.append(h)
        used += t
    kept.reverse()
    return kept, len(valid) - len(kept)


def _agent_history_messages(messages, hist):
    
    picked, dropped = _agent_pick_history(hist)
    if dropped:
        messages.append({"role": "system",
                         "content": "[已省略较早的 %d 条对话]" % dropped})
    for h in picked:
        messages.append({"role": h["role"], "content": h["content"]})
    return dropped




AGENT_MAX_VISION_IMAGES = 4


def _agent_normalize_assets(assets):
    
    out = []
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        url = (a.get("url") or "").strip()
        if not url:
            continue
        kind = a.get("kind") or "image"
        if kind not in ("image", "audio", "video"):
            kind = "image"
        out.append({"kind": kind, "url": url, "name": (a.get("name") or "").strip()})
    return out


def _agent_asset_manifest(assets):
    
    if not assets:
        return ""
    seq = {"image": 0, "audio": 0, "video": 0}
    tag = {"image": "图", "audio": "音", "video": "视"}
    rows = []
    for a in assets:
        seq[a["kind"]] += 1
        suffix = f"（{a['name']}）" if a["name"] else ""
        rows.append(f"{tag[a['kind']]}{seq[a['kind']]} = {a['url']}{suffix}")
    return (
        "【用户本轮附带的素材】\n" + "\n".join(rows) + "\n"
        "用法：当用户要求以这些素材作为参考时，直接把对应 URL 填进工具参数——"
        "图片填 generate_video.images 或 generate_image.images，"
        "音频填 generate_video.audios，视频填 generate_video.videos，"
        "并把 mode 设为 reference（首帧/尾帧诉求则填 first_frame / last_frame，mode=keyframe）。"
        "只准使用上面列出的 URL，不要编造素材地址。"
    )


def _agent_user_message(text, assets):
    
    imgs = [a["url"] for a in assets if a["kind"] == "image"]
    imgs = imgs[:AGENT_MAX_VISION_IMAGES]
    if not imgs:
        return text
    parts = [{"type": "text", "text": text}]
    for u in imgs:
        parts.append({"type": "image_url", "image_url": {"url": _to_b64_if_local(u)}})
    return parts


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"



_RUN_SUBS = {}
_RUN_SUBS_LOCK = _threading.Lock()


def _run_sub(run_id):
    q = _queue.Queue()
    with _RUN_SUBS_LOCK:
        _RUN_SUBS.setdefault(run_id, []).append(q)
    return q


def _run_unsub(run_id, q):
    with _RUN_SUBS_LOCK:
        lst = _RUN_SUBS.get(run_id) or []
        if q in lst:
            lst.remove(q)
        if not lst:
            _RUN_SUBS.pop(run_id, None)


def _run_pub(run_id, ev):
    
    with _RUN_SUBS_LOCK:
        subs = list(_RUN_SUBS.get(run_id) or [])
    for q in subs:
        try:
            q.put_nowait(ev)
        except Exception:
            pass


_SSE_HEADERS = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _run_snapshot_events(row):
    
    st = row.get("state") or {}
    status = row.get("status")
    evs = []
    if st.get("tool_running_text"):
        evs.append({"type": "tool_running", "phase": "tool", "text": st["tool_running_text"]})


    if st.get("manifest_items"):
        evs.append({"type": "tool_manifest", "items": st["manifest_items"]})
    elif st.get("manifest_labels"):
        evs.append({"type": "tool_manifest", "labels": st["manifest_labels"]})
    total = (st.get("progress") or {}).get("total") or 0
    done_items = st.get("items_done") or {}
    for i in sorted(done_items.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
        it = done_items[i] or {}
        _ev = {"type": "tool_progress", "done": int(i) + 1,
               "total": total or (int(i) + 1), "label": it.get("label") or ""}

        if it.get("url"):
            _ev["items"] = [{"index": int(i), "name": it.get("name"), "url": it.get("url"),
                             "label": it.get("label"), "kind": it.get("kind")}]
        evs.append(_ev)
    prog = st.get("progress") or {}
    if total and prog.get("done"):
        _lbl = prog.get("label") or ""
        evs.append({"type": "tool_progress", "done": prog.get("done"), "total": total,
                    "label": _lbl,
                    "text": f"正在生成素材 {prog.get('done')}/{total}" + (f"：{_lbl}" if _lbl else "")})
    if status == "done":
        evs.append({"type": "done", **(row.get("result") or {})})
    elif status == "error":
        evs.append({"type": "error", "error": row.get("error") or "任务失败"})
    elif status == "interrupted":
        evs.append({"type": "error", "error": row.get("error") or "服务重启导致任务中断，请重新发送。"})
    return evs


def _agent_done_payload(items, body, think):
    
    ok_items = [i for i in items if i.get("kind") in ("video", "image", "longvideo_job", "longvideo_assets")]
    if len(ok_items) == 1 and len(items) == 1:
        kind = ok_items[0]["kind"]
    elif ok_items:
        kind = "multi"
    elif items:
        kind = "error"
    else:
        kind = "text"

    if kind == "video":
        it = ok_items[0]
        summary = f"已提交视频生成（{it.get('mode') or 'text'} 模式 · {it.get('seconds') or '5'} 秒）。"
    elif kind == "image":
        summary = "已提交图片生成。"
    elif kind == "longvideo_job":
        it = ok_items[0]
        summary = f"已创建长视频任务《{it.get('name')}》，点击前往长视频工作台继续。"
    elif kind == "longvideo_assets":
        summary = f"已登记 {len(ok_items)} 批素材到长视频任务。"
    elif kind == "multi":
        summary = f"已提交 {len(ok_items)} 个生成任务。"
    elif kind == "error":
        first_err = next((i.get("error") for i in items if i.get("error")), "工具执行失败")
        summary = f"生成失败：{first_err}"
    else:
        summary = ""
    return {"type": "done", "kind": kind, "text": body, "think": think,
            "summary": summary, "items": items,
            "backend": _llm.route("assistant"), "model": _llm.default_model("assistant")}


def _run_tool_phase(run_id, name, args, session_id):
    



    _asset_total = 0
    if name == "generate_longvideo_assets" and isinstance(args.get("assets"), list):
        _assets = args["assets"]
        _asset_total = len(_assets)
        _manifest_items = []
        for i, a in enumerate(_assets):
            a = a or {}
            _manifest_items.append({
                "index": i,
                "label": str(a.get("label") or a.get("name") or f"素材{i+1}")[:32],
                "kind": a.get("kind") or "prop",
                "url": a.get("url") or "",
            })
        _runst.merge_state(run_id, manifest_items=_manifest_items, manifest_labels=[m["label"] for m in _manifest_items])
        _run_pub(run_id, {"type": "tool_manifest", "items": _manifest_items})

    def _on_item(i, it):


        _runst.merge_state_sub(run_id, "items_done", str(i),
                               {"name": it.get("name"), "url": it.get("url"),
                                "label": it.get("label"), "kind": it.get("kind")})

        _run_pub(run_id, {"type": "tool_progress", "done": i + 1, "total": _asset_total or (i + 1),
                          "label": it.get("label") or "",
                          "text": f"正在生成素材 {i + 1}/{_asset_total or (i + 1)}" + (f"：{it.get('label')}" if it.get("label") else ""),
                          "items": [{"index": i, "name": it.get("name"), "url": it.get("url"),
                                     "label": it.get("label"), "kind": it.get("kind")}]})

    _holder = {}
    for _ev in _agent_tool_events(name, args, session_id, _holder, on_item=_on_item):
        _run_pub(run_id, _ev)
        if _ev.get("type") == "tool_progress" and _ev.get("total"):
            _runst.merge_state(run_id, progress={"done": _ev.get("done"), "total": _ev.get("total"),
                                                 "label": _ev.get("label")})
    item = _holder.get("item")
    if item is None:
        item = {"kind": "error", "error": _holder.get("error") or f"工具 {name} 未返回结果"}
    return [item]


def _agent_run_pipeline(run_id, messages, session_id):
    
    acc = ""
    think_acc = ""
    tc_buf = {}
    tc_announced = False
    try:
        _runst.mark(run_id, status="streaming")


        if not _llm.caps("assistant", "tools"):
            msg = ("当前助手模型未声明支持工具调用 —— 猫灵助手依赖工具编排执行任务。"
                   "请在「服务商设置」更换支持工具调用的模型（或勾选该模型的能力声明）。")
            _runst.mark(run_id, status="error", error=msg)
            _run_pub(run_id, {"type": "error", "error": msg})
            return


        _last = messages[-1] if messages else None
        _has_img = (isinstance(_last, dict) and isinstance(_last.get("content"), list)
                    and any(isinstance(p, dict) and p.get("type") == "image_url" for p in _last["content"]))
        if _has_img and not _llm.caps("assistant", "vision"):
            msg = ("当前助手模型未声明支持图片识别 —— 请在「服务商设置」勾选该模型的能力声明，"
                   "或去掉消息里的图片后重发。")
            _runst.mark(run_id, status="error", error=msg)
            _run_pub(run_id, {"type": "error", "error": msg})
            return


        r = _llm.chat("assistant", messages, tools=_agent_tools(), tool_choice="auto",
                      stream=True, max_tokens=_llm.max_output_for("assistant", AGENT_MAX_TOKENS),
                      timeout=(10, 600))
        if r.status_code != 200:
            try:
                d = r.json()
                msg = d.get("detail") or (d.get("error") or {}).get("message") or d
            except Exception:
                msg = r.content.decode("utf-8", errors="replace")[:300]
            _runst.mark(run_id, status="error", error=f"LLM 拒绝请求（{r.status_code}）：{msg}")
            _run_pub(run_id, {"type": "error", "error": f"LLM 拒绝请求（{r.status_code}）：{msg}"})
            return


        for raw in r.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except Exception:
                continue
            delta = ((obj.get("choices") or [{}])[0].get("delta") or {})

            rc = delta.get("reasoning_content")
            if rc:
                if think_acc and rc.startswith(think_acc) and len(rc) > len(think_acc):
                    inc = rc[len(think_acc):]
                elif think_acc and rc == think_acc and len(think_acc) >= 64:
                    inc = ""
                else:
                    inc = rc
                if inc:
                    think_acc += inc
                    _run_pub(run_id, {"type": "reasoning", "text": inc})
            c = delta.get("content")
            if c:
                if acc and c.startswith(acc) and len(c) > len(acc):
                    inc = c[len(acc):]
                elif acc and c == acc and len(acc) >= 64:
                    inc = ""
                else:
                    inc = c
                if inc:
                    acc += inc
                    _run_pub(run_id, {"type": "delta", "text": inc})

            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)
                b = tc_buf.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    b["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    b["name"] = fn["name"]


                    if not tc_announced:
                        tc_announced = True
                        _run_pub(run_id, {"type": "tool_running", "phase": "tool",
                                          "text": "正在整理生成清单…"})
                if fn.get("arguments"):
                    b["args"] += fn["arguments"]


        think = think_acc.strip()
        if think:
            body = acc.strip()
        else:
            think, body = _agent_split_think(acc)


        if not tc_buf:
            done_ev = _agent_done_payload([], body, think)
            _runst.mark(run_id, status="done", result=done_ev,
                        state={"text": body, "think": think})
            _run_pub(run_id, done_ev)
            return


        parsed = []
        for idx in sorted(tc_buf.keys()):
            b = tc_buf[idx]
            _name = b.get("name") or ""
            try:
                _args = json.loads(b.get("args") or "{}")
            except Exception:
                parsed.append((None, None, {"kind": "error",
                                            "error": f"参数解析失败：{str(b.get('args'))[:120]}"}))
                continue
            parsed.append((_name, _args, None))
        _tool_names = sorted({n for n, _a, _e in parsed if n})
        _tool_msg = "正在生成长视频素材图…" if "generate_longvideo_assets" in _tool_names else "正在调用工具执行任务…"
        _resumable = next(((n, a) for n, a, _e in parsed if n == "generate_longvideo_assets"), None)
        _runst.mark(run_id, status="tooling", tool_name=",".join(_tool_names),
                    args=(_resumable[1] if _resumable else None),
                    state={"text": body, "think": think, "tool_running_text": _tool_msg})
        _run_pub(run_id, {"type": "tool_running", "text": _tool_msg,
                          "tools": _tool_names, "phase": "tool"})
        items = []
        for _name, _args, _pre_err in parsed:
            if _pre_err:
                items.append(_pre_err)
                continue
            items.extend(_run_tool_phase(run_id, _name, _args, session_id))
        done_ev = _agent_done_payload(items, body, think)
        _runst.mark(run_id, status="done", result=done_ev)
        _run_pub(run_id, done_ev)
    except Exception as e:
        err = f"助手任务异常：{type(e).__name__}: {e}"
        try:
            _runst.mark(run_id, status="error", error=err)
        except Exception:
            pass
        _run_pub(run_id, {"type": "error", "error": err})
    finally:
        _run_pub(run_id, None)


def _agent_run_resume(run_id):
    
    row = _runst.get(run_id)
    if not row:
        return
    st = row.get("state") or {}
    body, think = st.get("text") or "", st.get("think") or ""
    name = (row.get("tool_name") or "").split(",")[0].strip()
    args = row.get("args") or {}
    session_id = row.get("session_id")
    try:
        if name != "generate_longvideo_assets" or not isinstance(args.get("assets"), list):
            _runst.mark(run_id, status="interrupted",
                        error="服务重启导致任务中断（该工具不支持断点续跑），请重新发送。")
            _run_pub(run_id, {"type": "error",
                              "error": "服务重启导致任务中断（该工具不支持断点续跑），请重新发送。"})
            return
        done_items = st.get("items_done") or {}
        resumed = 0
        for i, a in enumerate(args["assets"]):
            it = done_items.get(str(i)) or {}
            if it.get("url") and not (a or {}).get("url"):
                a["url"] = it["url"]
                resumed += 1
        print(f"[agent-runs] 续跑 {run_id}：{resumed}/{len(args['assets'])} 张已完成，跳过重复生成",
              flush=True)
        _run_pub(run_id, {"type": "tool_running", "phase": "tool",
                          "text": st.get("tool_running_text") or "正在生成长视频素材图…"})
        items = _run_tool_phase(run_id, name, args, session_id)
        done_ev = _agent_done_payload(items, body, think)
        _runst.mark(run_id, status="done", result=done_ev)
        _run_pub(run_id, done_ev)
    except Exception as e:
        err = f"续跑失败：{type(e).__name__}: {e}"
        try:
            _runst.mark(run_id, status="error", error=err)
        except Exception:
            pass
        _run_pub(run_id, {"type": "error", "error": err})
    finally:
        _run_pub(run_id, None)


def _recover_agent_runs():
    
    def _go():
        time.sleep(2.0)
        try:
            n = _runst.interrupt_streaming()
            if n:
                print(f"[agent-runs] 服务重启：{n} 个思考期任务已标记中断", flush=True)
            for rid in _runst.claim_resumable():
                print(f"[agent-runs] 发现可续跑任务 {rid}，正在恢复…", flush=True)
                _threading.Thread(target=_agent_run_resume, args=(rid,), daemon=True,
                                  name=f"agent-resume-{rid}").start()
            _runst.prune(days=7)
        except Exception as e:
            print(f"[warn] agent_runs 恢复扫描失败：{e}", flush=True)
    _threading.Thread(target=_go, daemon=True, name="agent-runs-recovery").start()


_recover_agent_runs()


@app.route("/api/agent_stream", methods=["POST"])
def api_agent_stream():
    
    if not _cfg_key():
        return jsonify({"error": "尚未配置访问密钥。请点击左侧「服务商设置」填入接口地址与密钥。"}), 500
    _assist_ok, _assist_reason = _llm.configured("assistant")
    if not _assist_ok:
        return jsonify({"error": _assist_reason}), 500
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "请输入内容。"}), 400
    session_id = data.get("sessionId")
    assets = _agent_normalize_assets(data.get("assets"))


    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    manifest = _agent_asset_manifest(assets)
    if manifest:
        messages.append({"role": "system", "content": manifest})
    _agent_history_messages(messages, data.get("history"))
    messages.append({"role": "user", "content": _agent_user_message(text, assets)})

    run_id = _runst.create(session_id)
    q = _run_sub(run_id)
    _threading.Thread(target=_agent_run_pipeline, args=(run_id, messages, session_id),
                      daemon=True, name=f"agent-run-{run_id}").start()

    def gen():
        try:
            yield _sse({"type": "run", "id": run_id})
            while True:
                try:
                    ev = q.get(timeout=2.0)
                except _queue.Empty:
                    yield ": ping\n\n"
                    continue
                if ev is None:
                    return
                yield _sse(ev)
                if ev.get("type") in ("done", "error"):
                    return
        finally:
            _run_unsub(run_id, q)

    return Response(gen(), headers=_SSE_HEADERS)


@app.route("/api/agent_run/<run_id>/stream", methods=["GET"])
def api_agent_run_stream(run_id):
    
    row = _runst.get(run_id)
    if not row:
        return jsonify({"error": "任务不存在或已过期"}), 404

    def gen():
        last_sig = None
        t0 = time.time()
        while True:
            row = _runst.get(run_id)
            if not row:
                yield _sse({"type": "error", "error": "任务记录已丢失"})
                return
            sig = json.dumps([row.get("status"), row.get("state")], ensure_ascii=False)
            if sig != last_sig:
                last_sig = sig
                for ev in _run_snapshot_events(row):
                    yield _sse(ev)
                    if ev.get("type") in ("done", "error"):
                        return
            if row.get("status") in _runst.TERMINAL:
                return
            if time.time() - t0 > 7200:
                yield _sse({"type": "error", "error": "任务跟踪超时，请刷新页面重试"})
                return
            time.sleep(1.5)
            yield ": ping\n\n"

    return Response(gen(), headers=_SSE_HEADERS)


@app.route("/api/agent_runs/active", methods=["GET"])
def api_agent_runs_active():
    
    sid = request.args.get("sessionId") or ""
    row = _runst.active_by_session(sid)
    if not row:
        return jsonify({"run": None})
    return jsonify({"run": {"id": row["id"], "status": row["status"],
                            "tool_name": row.get("tool_name"),
                            "createdAt": row.get("created_at")}})
@app.route("/api/agent", methods=["POST"])
def api_agent():
    
    if not _cfg_key():
        return jsonify({"error": "尚未配置访问密钥。请点击左侧「服务商设置」填入接口地址与密钥。"}), 500
    _assist_ok, _assist_reason = _llm.configured("assistant")
    if not _assist_ok:
        return jsonify({"error": _assist_reason}), 500

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "请输入内容。"}), 400

    session_id = data.get("sessionId")
    assets = _agent_normalize_assets(data.get("assets"))


    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    manifest = _agent_asset_manifest(assets)
    if manifest:
        messages.append({"role": "system", "content": manifest})
    _agent_history_messages(messages, data.get("history"))
    messages.append({"role": "user", "content": _agent_user_message(text, assets)})






    body, err = _llm_chat_completions(messages, tools=_agent_tools(), tool_choice="auto",
                                      max_tokens=_llm.max_output_for("assistant", AGENT_MAX_TOKENS),
                                      timeout=(10, 900))
    if err:
        return jsonify({"error": err}), 502

    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = (msg.get("content") or "").strip()
    tool_calls = msg.get("tool_calls") or []

    think = (msg.get("reasoning_content") or "").strip()
    if not think:
        think, content = _agent_split_think(content)


    if not tool_calls:
        return jsonify({
            "ok": True, "kind": "text",
            "text": content or "（模型没有返回内容。若想生成，可把需求说得更具体，或切到手动模式。）",
            "think": think,
            "summary": "", "items": [],
            "backend": _llm.route("assistant"),
            "model": _llm.default_model("assistant"),
        })


    items = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except Exception:
            items.append({"kind": "error", "error": f"参数解析失败：{str(raw_args)[:120]}"})
            continue
        item, _ok = _agent_run_tool(name, args, session_id)
        items.append(item)

    ok_items = [i for i in items if i.get("kind") in ("video", "image", "longvideo_job", "longvideo_assets")]
    if len(ok_items) == 1 and len(items) == 1:
        kind = ok_items[0]["kind"]
    elif ok_items:
        kind = "multi"
    else:
        kind = "error"


    if kind == "video":
        it = ok_items[0]
        summary = f"已提交视频生成（{it.get('mode') or 'text'} 模式 · {it.get('seconds') or '5'} 秒）。"
    elif kind == "image":
        summary = "已提交图片生成。"
    elif kind == "longvideo_job":
        it = ok_items[0]
        summary = f"已创建长视频任务《{it.get('name')}》，点击前往长视频工作台继续。"
    elif kind == "longvideo_assets":
        summary = f"已登记 {len(ok_items)} 批素材到长视频任务。"
    elif kind == "multi":
        summary = f"已提交 {len(ok_items)} 个生成任务。"
    else:
        first_err = next((i.get("error") for i in items if i.get("error")), "工具执行失败")
        summary = f"生成失败：{first_err}"

    return jsonify({"ok": True, "kind": kind, "text": content, "think": think,
                    "summary": summary, "items": items,
                    "backend": _llm.route("assistant"),
                    "model": _llm.default_model("assistant")})
@app.route("/api/agent_sessions", methods=["GET"])
def api_agent_sessions_get():
    
    return jsonify(_load_agent_sessions())
@app.route("/api/agent_sessions", methods=["POST"])
def api_agent_sessions_post():
    
    data = request.get_json(silent=True) or {}
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        return {"error": "sessions 必须是数组。"}, 400
    if not sessions and not bool(data.get("force")):
        if _load_agent_sessions().get("sessions"):
            return jsonify({"ok": True, "skipped": True, "reason": "refuse-empty-overwrite"})
    _save_agent_sessions({
        "sessions": [s for s in sessions if isinstance(s, dict) and "id" in s],
        "currentId": data.get("currentId"),
        "force": bool(data.get("force")),
    })
    return jsonify({"ok": True, "count": len(sessions)})
@app.route("/api/task/<tid>")
def api_task(tid):
    
    with _TASKS_LOCK:
        d = _load_tasks()
    rec = d.get("tasks", {}).get(tid)
    if not rec:
        return jsonify({"error": f"未找到任务 {tid}"}), 404
    return jsonify({
        "task_id": rec.get("id"),
        "kind": rec.get("kind"),
        "model": rec.get("model"),
        "status": rec.get("status"),
        "video_url": rec.get("video_url"),
        "image_urls": rec.get("image_urls"),
        "error": rec.get("error"),
        "video_id": rec.get("video_id"),
        "created_at": rec.get("created_at"),
        "finished_at": rec.get("finished_at"),
    })
@app.route("/api/tasks")
def api_tasks():
    
    with _TASKS_LOCK:
        d = _load_tasks()
    rows = []
    for tid, rec in d.get("tasks", {}).items():
        rows.append({
            "task_id": tid,
            "kind": rec.get("kind"),
            "status": rec.get("status"),
            "model": rec.get("model"),
            "video_id": rec.get("video_id"),
            "created_at": rec.get("created_at"),
            "finished_at": rec.get("finished_at"),
            "has_result": bool(rec.get("video_url") or rec.get("image_urls")),
        })

    rows.sort(key=lambda r: (r.get("created_at") or 0), reverse=True)
    return jsonify({"count": len(rows), "tasks": rows})
def _backfill_video_history(video_id, video_url, model_name):
    
    rows = _load_history()
    matched = None
    for r in rows:
        if r.get("video_id") == video_id:
            r["status"] = "completed"
            r["video_url"] = video_url

            r["finished_at"] = r.get("finished_at") or time.time()
            matched = r
            break
    _save_history(rows)

    if matched:
        _sync_result_to_session(
            session_id=matched.get("sessionId"),
            dedup_key=video_id,
            kind="video",
            model=matched.get("model") or model_name,
            media_url=video_url,
            prompt=matched.get("prompt", ""),
            params=matched.get("params"),
            assets=matched.get("assets"),
            started_at=matched.get("created_at"),
            finished_at=matched.get("finished_at"),
        )


def _find_history_by_video_id(video_id):
    
    for r in _load_history():
        if r.get("video_id") == video_id:
            return r
    return None


def _finalize_video_result(video_id, video_url, model_name, prefix="vid"):
    
    matched = _find_history_by_video_id(video_id)
    prior = (matched or {}).get("video_url") or ""
    if prior and _assets_store.asset_name_of(prior):
        local = prior
    else:
        local = _persist_generated_video(video_url, prefix=prefix)


    _register_generated_video(local, session_id=(matched or {}).get("sessionId"))
    _backfill_video_history(video_id, local, model_name)
    return local


def _ark_video_status(video_id, model_name):
    
    base = (_arkprov.get("base_url") or "").rstrip("/")
    key = _arkprov.get("api_key") or ""
    if not key:
        return jsonify({"error": "方舟未配置访问密钥，无法查询任务状态。"}), 502
    try:
        resp = requests.get(
            f"{base}/contents/generations/tasks/{video_id}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=(10, 30),
        )
    except requests.RequestException as e:
        return jsonify({"error": f"查询失败：{e}"}), 502
    try:
        body = resp.json()
    except Exception:
        return jsonify({"error": f"无法解析查询结果：{resp.text[:160]}"}), 502
    if resp.status_code == 404:
        return jsonify({"status": "failed", "video_url": None,
                        "error": "方舟任务不存在或已被清理（任务记录保留期有限）。", "raw": body})
    if resp.status_code != 200:
        try:
            _e = body.get("error")
            msg = (_e.get("message") if isinstance(_e, dict) else _e) or resp.text[:160]
        except Exception:
            msg = resp.text[:160]
        return jsonify({"error": f"方舟查询失败（{resp.status_code}）：{msg}"}), resp.status_code

    raw_status = str(body.get("status") or "").lower()
    status = {"queued": "processing", "running": "processing",
              "succeeded": "completed", "failed": "failed",
              "expired": "failed", "cancelled": "failed"}.get(raw_status, "processing")
    video_url = (body.get("content") or {}).get("video_url")
    err_msg = None
    if status == "failed":
        _e = body.get("error")
        err_msg = (_e.get("message") if isinstance(_e, dict) else _e) or {
            "expired": "方舟任务超时过期。", "cancelled": "方舟任务已取消。",
        }.get(raw_status, f"方舟生成失败（{raw_status or '未知状态'}）。")

    if status == "completed" and video_url:

        video_url = _finalize_video_result(video_id, video_url, model_name, prefix="ark")

    return jsonify({"status": status, "video_url": video_url, "error": err_msg, "raw": body})


@app.route("/api/status")
def api_status():
    video_id = request.args.get("video_id")
    if not video_id:
        return jsonify({"error": "缺少 video_id 参数。"}), 400

    model_name = request.args.get(
        "model_name",
        (_provider.get("video_models") or ["agnes-video-2.5-flash"])[0],
    )




    if _arkprov.is_video_model(model_name) or str(video_id).startswith("cgt"):
        return _ark_video_status(video_id, model_name)

    try:
        resp = _AGNES_SESSION.get(
            _cfg_poll(),
            params={"video_id": video_id, "model_name": model_name},
            headers={"Authorization": f"Bearer {_cfg_key()}"},
            timeout=30,
        )
    except requests.RequestException as e:
        return jsonify({"error": f"查询失败：{e}"}), 502

    try:
        body = resp.json()
    except Exception:
        return jsonify({"error": f"无法解析查询结果：{resp.text}"}), 502

    status = body.get("status") or body.get("task_status") or "processing"

    video_url = (
        (body.get("metadata") or {}).get("url")
        or body.get("video_url")
        or body.get("url")
        or (body.get("result") or {}).get("video_url")
    )


    if status in ("completed", "success", "done") and video_url:
        video_url = _finalize_video_result(video_id, video_url, model_name)

    return jsonify({
        "status": status,
        "video_url": video_url,
        "error": body.get("error"),
        "raw": body,
    })
@app.route("/api/history")
def api_history():
    rows = _load_history()

    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "model": r.get("model"),
            "mode": r.get("mode"),
            "prompt": r.get("prompt"),
            "params": r.get("params"),
            "assets": r.get("assets"),
            "created_at": r.get("created_at"),
            "video_url": r.get("video_url"),
            "status": r.get("status"),
        })
    return jsonify(out)
@app.route("/api/result/<rid>")
def api_result(rid):
    rows = _load_history()
    for r in rows:
        if r.get("id") == rid:
            return jsonify({
                "id": r.get("id"),
                "model": r.get("model"),
                "mode": r.get("mode"),
                "prompt": r.get("prompt"),
                "params": r.get("params"),
                "assets": r.get("assets"),
                "created_at": r.get("created_at"),
                "video_url": r.get("video_url"),
                "status": r.get("status"),
            })
    return jsonify({"error": "未找到该生成记录。"}), 404
@app.route("/api/sessions", methods=["GET"])
def api_get_sessions():
    payload = _load_sessions()



    payload["deletedIds"] = _server_tombstones()
    return jsonify(payload)
@app.route("/api/sessions", methods=["POST"])
def api_post_sessions():
    data = request.get_json(silent=True) or {}
    sessions = data.get("sessions")
    current_id = data.get("currentId")
    if not isinstance(sessions, list):
        return jsonify({"error": "sessions 必须是数组。"}), 400


    if not sessions and not bool(data.get("force")):
        if _load_sessions().get("sessions"):
            return jsonify({"ok": True, "skipped": True, "reason": "refuse-empty-overwrite"})
    clean = []
    _dropped_total, _big_total = 0, []
    for s in sessions:
        if not isinstance(s, dict) or "id" not in s:
            continue
        s.setdefault("name", "未命名会话")
        s.setdefault("createdAt", time.time())
        s.setdefault("messages", [])





        s["messages"], _d, _b = _msgst.sanitize_messages(s.get("messages"))
        _dropped_total += _d
        _big_total.extend(_b)
        clean.append(s)
    if _big_total:
        print("[warn] 会话消息里出现过大的条目（未丢弃，仅告警）：%s" % (_big_total,))
    _save_sessions({"sessions": clean, "currentId": current_id})
    return jsonify({"ok": True, "count": len(clean)})
@app.route("/api/sessions/<sid>", methods=["DELETE"])
def api_delete_session(sid):
    
    _ensure_db()
    with_assets = str(request.args.get("with_assets") or "") in ("1", "true", "yes")
    _urls, _ntask, _nhist = [], 0, 0
    _asset_names, _assets_res = [], None
    with _DB_LOCK:
        conn = _db_conn()
        try:
            before = conn.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
            if before:
                _urls = _mgc.urls_in(before["data"])

            if with_assets:
                _asset_names = [a["name"] for a in _assets_store.session_assets(sid)]

            tids = []
            for r in conn.execute("SELECT tid, data FROM tasks"):
                try:
                    if json.loads(r["data"] or "{}").get("session_id") == sid:
                        tids.append(r["tid"])
                except Exception:
                    continue
            for t in tids:
                conn.execute("DELETE FROM tasks WHERE tid=?", (t,))
            _ntask = len(tids)

            _h0 = conn.execute("SELECT COUNT(*) AS c FROM history").fetchone()["c"]
            _urls.extend(_core_mod._purge_history_rows(conn, [sid]))
            _nhist = _h0 - conn.execute("SELECT COUNT(*) AS c FROM history").fetchone()["c"]
            conn.execute("DELETE FROM sessions WHERE id=?", (sid,))


            _mark_session_deleted(conn, [sid])
            cur = conn.execute("SELECT value FROM meta WHERE key='currentId'").fetchone()
            new_cur = cur["value"] if cur else None
            if new_cur == sid:
                first = conn.execute(
                    "SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                new_cur = first["id"] if first else None
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('currentId', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (new_cur,),
                )
            conn.commit()
            existed = before is not None
        finally:
            conn.close()




    _freed, _freed_n = 0, 0


    if with_assets and _asset_names:
        try:
            _assets_res = _assets_store.delete_names(_asset_names)
        except Exception as e:
            print(f"[warn] 删会话时移除资产库条目失败（不影响删会话）：{e}")
    return jsonify({"ok": True, "deleted": existed, "currentId": new_cur,
                    "tasksRemoved": _ntask, "historyRemoved": _nhist,
                    "filesRemoved": _freed_n, "bytesFreed": _freed,
                    "assetsRemoved": (_assets_res or {}).get("count", 0),
                    "assetsFilesPurged": (_assets_res or {}).get("purged_count", 0),
                    "assetsBytesFreed": (_assets_res or {}).get("bytes_freed", 0),
                    "assetsStillReferenced": (_assets_res or {}).get("still_referenced", {})})


@app.route("/api/media/reclaim", methods=["POST"])
def api_media_reclaim():
    
    data = request.get_json(silent=True) or {}
    urls = data.get("urls") or []
    if not isinstance(urls, list):
        return jsonify({"error": "urls 需为数组"}), 400
    try:
        r = _mgc.reclaim_urls(urls)
    except Exception as e:
        return jsonify({"error": f"回收失败：{type(e).__name__}: {e}"}), 500
    return jsonify({
        "ok": True,
        "removed": [{"kind": k, "name": n, "size": s} for k, n, s in r["removed"]],
        "kept": len(r["kept"]),
        "skipped": [{"kind": k, "name": n, "why": w} for k, n, w in r["skipped"]],
        "errors": [{"kind": k, "name": n, "why": w} for k, n, w in r["errors"]],
        "bytesFreed": sum(s for _k, _n, s in r["removed"]),
    })


def _rel_to_tts_url(rel):
    
    s = str(rel or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in s.split("/") if p]
    if len(parts) >= 2 and parts[0] in ("voices", "tts_out", "tts_ref"):
        return "/api/tts/file/%s/%s" % (parts[0], os.path.basename(parts[1]))
    return ""


@app.route("/api/media/purge", methods=["POST"])
def api_media_purge():
    
    data = request.get_json(silent=True) or {}
    urls = data.get("urls") or []
    video_ids = data.get("videoIds") or []
    tts_job_ids = data.get("ttsJobIds") or []
    for v in (urls, video_ids, tts_job_ids):
        if not isinstance(v, list):
            return jsonify({"error": "urls / videoIds / ttsJobIds 均需为数组"}), 400
    _ensure_db()
    _cand = [u for u in urls if isinstance(u, str)]
    _vset = {str(x) for x in video_ids if x}
    _jset = {str(x) for x in tts_job_ids if x}
    _ntask = _nhist = _njob = 0
    with _DB_LOCK:
        conn = _db_conn()
        try:

            for tid in _vset:
                row = conn.execute("SELECT data FROM tasks WHERE tid=?", (tid,)).fetchone()
                if not row:
                    continue
                _cand.extend(_mgc.urls_in(row["data"]))
                conn.execute("DELETE FROM tasks WHERE tid=?", (tid,))
                _ntask += 1

            if _vset:
                dead = []
                for r in conn.execute("SELECT id, data FROM history"):
                    try:
                        d = json.loads(r["data"] or "{}")
                    except Exception:
                        continue
                    if str(d.get("video_id") or "") in _vset or str(r["id"] or "") in _vset:
                        _cand.extend(_mgc.urls_in(r["data"]))
                        dead.append(r["id"])
                for i in dead:
                    conn.execute("DELETE FROM history WHERE id=?", (i,))
                _nhist = len(dead)

            for jid in _jset:
                row = conn.execute("SELECT ref_path, candidates FROM jobs WHERE id=?", (jid,)).fetchone()
                if row:
                    _cand.append(_rel_to_tts_url(row["ref_path"]))
                    try:
                        for c in json.loads(row["candidates"] or "[]"):
                            if isinstance(c, dict):
                                _cand.append(c.get("url") or _rel_to_tts_url(c.get("path")))
                    except Exception:
                        pass
                    _njob += 1
                conn.execute("DELETE FROM jobs WHERE id=?", (jid,))
            conn.commit()
        finally:
            conn.close()

    try:
        r = _mgc.reclaim_urls(_cand)
    except Exception as e:
        return jsonify({"ok": True, "tasksRemoved": _ntask, "historyRemoved": _nhist,
                        "ttsJobsRemoved": _njob, "removed": [], "kept": 0, "bytesFreed": 0,
                        "warning": f"记录已删，但回收失败：{type(e).__name__}: {e}"})
    return jsonify({
        "ok": True,
        "tasksRemoved": _ntask,
        "historyRemoved": _nhist,
        "ttsJobsRemoved": _njob,
        "removed": [{"kind": k, "name": n, "size": s} for k, n, s in r["removed"]],
        "kept": len(r["kept"]),
        "bytesFreed": sum(s for _k, _n, s in r["removed"]),
    })


@app.route("/api/download")
def api_download():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "缺少 url 参数"}), 400
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
    except Exception:
        return jsonify({"error": "无效的 url"}), 400



    if not p.scheme and url.startswith("/assets/"):
        _name = _safe_name(url[len("/assets/"):])
        _full = os.path.join(ASSETS_DIR, _name)
        if not os.path.isfile(_full):
            return jsonify({"error": "本地素材不存在"}), 404
        _ext, _mime = _infer_ext_and_mime(url, None)
        return send_file(_full, mimetype=_mime, as_attachment=True, download_name=_name)
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not any(host == d or host.endswith("." + d) for d in DOWNLOAD_ALLOW_HOSTS):
        return jsonify({"error": "仅允许下载 Agnes 平台（agnes-ai.space）的文件；站内素材请直接使用 /assets/ 路径"}), 403

    import time as _time
    last_err = None
    r = None
    for _attempt in range(3):
        try:
            r = _AGNES_SESSION.get(url, stream=True, timeout=120)
            break
        except Exception as e:
            last_err = e
            _time.sleep(0.8 * (_attempt + 1))
    if r is None:
        return jsonify({"error": "下载失败：" + str(last_err)}), 502
    if r.status_code != 200:
        return jsonify({"error": "源文件不可用（HTTP %s）" % r.status_code}), 502

    from datetime import datetime
    ext, mime = _infer_ext_and_mime(url, r.headers.get("Content-Type"))
    fname = "Agnes_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "." + ext
    headers = {
        "Content-Type": mime,
        "Content-Disposition": 'attachment; filename="%s"' % fname,
    }
    cl = r.headers.get("Content-Length")
    if cl:
        headers["Content-Length"] = cl

    def _gen():
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                yield chunk

    return Response(_gen(), status=200, headers=headers)

@app.route("/api/base_style.css")
def base_style_css():
    f = os.path.join(_ROOT, "src", "base", "css", "base.css")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    return send_file(f, mimetype="text/css", conditional=True)

@app.route("/api/base_ui.js")
def base_ui_js():
    f = os.path.join(_ROOT, "src", "base", "js", "app.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/api/imageedit_ui.js")
def imageedit_ui_js():
    
    f = os.path.join(_ROOT, "src", "base", "js", "imageedit.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp





@app.route("/api/provider", methods=["GET"])
def api_provider_get():
    return jsonify(_provider.config_snapshot(masked=True))

@app.route("/api/provider", methods=["POST"])
def api_provider_save():
    
    data = request.get_json(silent=True) or {}
    try:
        snap = _provider.save(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "config": snap})

@app.route("/api/provider/reset", methods=["POST"])
def api_provider_reset():
    
    return jsonify({"ok": True, "config": _provider.reset()})

@app.route("/api/provider/test", methods=["POST"])
def api_provider_test():
    
    data = request.get_json(silent=True) or {}
    draft_base = (data.get("base_url") or "").strip()
    draft_key = (data.get("api_key") or "").strip()

    if draft_key and "…" in draft_key:
        draft_key = ""
    result = _provider.test_connection(
        base_url=draft_base or None,
        api_key=draft_key or None,
    )
    return jsonify(result)






try:
    _ttsclient.init_audio_db()
except Exception as _e:
    print("[WARN] 音频表(voices/jobs)初始化失败:", _e, flush=True)



@app.route("/api/audio_ui.js")
def audio_ui_js():
    f = os.path.join(_ROOT, "src", "base", "js", "audio.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp





import server.canvas_store as _canvas_store


@app.route("/api/canvas/projects", methods=["GET"])
def api_canvas_projects_list():
    return jsonify({"projects": _canvas_store.list_projects()})


@app.route("/api/canvas/projects", methods=["POST"])
def api_canvas_projects_create():
    data = request.get_json(silent=True) or {}
    doc = _canvas_store.create_project(data.get("name"))
    return jsonify(doc)


@app.route("/api/canvas/projects/<pid>", methods=["GET"])
def api_canvas_project_get(pid):
    doc = _canvas_store.get_project(pid)
    if not doc:
        return jsonify(error="画布项目不存在"), 404
    return jsonify(doc)


@app.route("/api/canvas/projects/<pid>", methods=["PUT"])
def api_canvas_project_save(pid):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="需要 JSON 文档"), 400
    doc = _canvas_store.save_project(pid, data)
    if doc is None:
        return jsonify(error="画布项目已删除，放弃写回"), 404
    return jsonify({"ok": True, "updated_at": doc["updated_at"]})


@app.route("/api/canvas/projects", methods=["DELETE"])
def api_canvas_projects_delete():
    data = request.get_json(silent=True) or {}
    n = _canvas_store.delete_projects(data.get("ids"))
    return jsonify({"deleted": n})


@app.route("/api/canvas_style.css")
def canvas_style_css():
    f = os.path.join(_ROOT, "src", "canvas", "css", "canvas.css")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="text/css"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/canvas_manager.js")
def canvas_manager_js():
    f = os.path.join(_ROOT, "src", "canvas", "js", "manager.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/canvas_stage.js")
def canvas_stage_js():
    f = os.path.join(_ROOT, "src", "canvas", "js", "stage.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/canvas_dagre.js")
def canvas_dagre_js():
    f = os.path.join(_ROOT, "src", "canvas", "js", "vendor", "dagre.min.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/canvas_timeline.js")
def canvas_timeline_js():
    
    f = os.path.join(_ROOT, "src", "canvas", "js", "timeline.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp
















import subprocess as _subprocess
import shutil as _shutil
import tempfile as _tempfile
import json as _json
import array as _array
import media_tools as _mt


def _tl_kind_of(path):
    
    ext = os.path.basename(path).rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
    if ext in IMG_EXTS:
        return "image"
    if ext in VID_EXTS:
        return "video"
    return "audio"


def _tl_local(url):
    
    u = (url or "").strip()
    pb = _public_base()
    name = None
    if u.startswith("/assets/"):
        name = u[len("/assets/"):]
    elif pb and u.startswith(pb + "/assets/"):
        name = u[len(pb) + len("/assets/"):]
    if not name:
        return None
    try:
        name = name.split("?")[0]
    except Exception:
        pass
    return _resolve_asset_file(name)


def _tl_run(cmd, timeout=300):
    return _subprocess.run(cmd, stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, timeout=timeout)


def _tl_ffpath(p):
    
    try:
        if os.name != "nt":
            return str(p)
        s = str(p)
        if s.isascii():
            return s
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(s, buf, 1024)
        return buf.value if n else s
    except Exception:
        return str(p)


def _tl_probe_av(full):
    
    src = _tl_ffpath(full)
    fp = _mt.ffprobe()
    if fp:
        try:
            r = _tl_run([fp, "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
                         "-show_entries", "format=duration", "-of", "json", src], timeout=60)
            j = _json.loads(r.stdout.decode("utf-8", "ignore") or "{}")
            try:
                dur = float((j.get("format") or {}).get("duration") or 0)
            except Exception:
                dur = 0.0
            w = h = 0
            ha = False
            sdur = 0.0
            for s in (j.get("streams") or []):

                try:
                    sdur = max(sdur, float(s.get("duration") or 0))
                except Exception:
                    pass
                if s.get("codec_type") == "video" and not w:
                    try:
                        w = int(s.get("width") or 0)
                        h = int(s.get("height") or 0)
                    except Exception:
                        w = h = 0
                elif s.get("codec_type") == "audio":
                    ha = True
            if dur <= 0:
                dur = sdur
            if dur > 0:
                return (dur, w, h, ha)
        except Exception:
            pass

    ff = _mt.ffmpeg()
    if ff:
        try:
            r = _tl_run([ff, "-v", "info", "-hide_banner", "-i", src, "-f", "null", "-"], timeout=120)
            txt = r.stderr.decode("utf-8", "ignore")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
            if m:
                hh, mm, ss = m.groups()
                return (int(hh) * 3600 + int(mm) * 60 + float(ss), 0, 0, "Audio:" in txt)
        except Exception:
            pass
    return (0.0, 0, 0, False)


def _tl_image_size(full):
    
    try:
        from PIL import Image
        with Image.open(full) as im:
            return (int(im.size[0]), int(im.size[1]))
    except Exception:
        return (0, 0)


@app.route("/api/media/probe", methods=["POST"])
def api_media_probe():
    
    data = request.get_json(silent=True) or {}
    full = _tl_local(data.get("url"))
    if not full:
        return jsonify(error="素材不在站内资产库，无法解析"), 400
    kind = _tl_kind_of(full)
    if kind == "image":
        w, h = _tl_image_size(full)
        return jsonify({"kind": "image", "duration": 0.0, "width": w, "height": h})
    dur, w, h, ha = _tl_probe_av(full)
    if not dur:
        return jsonify(error="该视频源有问题，无法读取时长（未入线）"), 422
    return jsonify({"kind": kind, "duration": round(dur, 3), "width": w, "height": h, "has_audio": ha})


@app.route("/api/media/waveform", methods=["POST"])
def api_media_waveform():
    
    data = request.get_json(silent=True) or {}
    full = _tl_local(data.get("url"))
    if not full:
        return jsonify(error="素材不在站内资产库，无法解析"), 400
    try:
        buckets = int(data.get("buckets") or 600)
    except Exception:
        buckets = 600
    buckets = max(60, min(2000, buckets))
    ff = _mt.ffmpeg()
    if not ff:
        return jsonify(error="未找到 ffmpeg，无法生成波形"), 503
    try:
        r = _tl_run([ff, "-v", "error", "-i", _tl_ffpath(full), "-ac", "1", "-ar", "8000",
                     "-f", "s16le", "-"], timeout=180)
    except Exception as e:
        return jsonify(error="波形解析失败：" + str(e)), 500
    pcm = r.stdout or b""
    if len(pcm) < 4:
        return jsonify(error="该素材没有可解析的音频轨"), 422
    try:
        buf = _array.array("h")
        buf.frombytes(pcm[:len(pcm) // 2 * 2])
    except Exception:
        return jsonify(error="波形解码失败"), 500
    n = len(buf)
    step = max(1, int(n / buckets))
    peaks = []
    for i in range(0, n, step):
        mx = 0
        end = min(n, i + step)
        for j in range(i, end):
            v = buf[j]
            if v < 0:
                v = -v
            if v > mx:
                mx = v
        peaks.append(round(min(1.0, mx / 32768.0), 4))
        if len(peaks) >= buckets:
            break
    if not peaks:
        return jsonify(error="波形为空"), 422
    return jsonify({"peaks": peaks, "buckets": len(peaks), "duration": round(n / 8000.0, 3)})



_TL_VENC_CACHE = {"enc": None}


def _tl_pick_venc():
    
    if _TL_VENC_CACHE["enc"] is not None:
        return _TL_VENC_CACHE["enc"]
    ff = _mt.ffmpeg()
    enc = None
    if ff:
        try:
            r = _tl_run([ff, "-hide_banner", "-encoders"], timeout=60)
            txt = r.stdout.decode("utf-8", "ignore")
            for name in ("libopenh264", "h264_qsv", "mpeg4", "libvpx-vp9", "vp9_qsv"):
                if re.search(r"\b" + re.escape(name) + r"\b", txt):
                    enc = name
                    break
        except Exception:
            enc = None
    _TL_VENC_CACHE["enc"] = enc
    return enc


def _tl_even(v):
    v = int(v or 0)
    if v <= 0:
        return 0
    return v if v % 2 == 0 else v + 1


def _tl_silence_pcm(seconds, path, ar=44100):
    
    nbytes = int(max(0.05, float(seconds)) * ar) * 2
    with open(path, "wb") as f:
        f.write(b"\x00" * min(nbytes, ar * 2))
        left = nbytes - min(nbytes, ar * 2)
        chunk = b"\x00" * (ar * 2)
        while left > 0:
            w = min(left, len(chunk))
            f.write(chunk[:w])
            left -= w
    return path


def _tl_norm_video(seg, out_path, w, h, venc):
    
    ff = _mt.ffmpeg()
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25")
    base = [ff, "-y"]
    src = _tl_ffpath(seg["path"])
    if seg.get("kind") == "image":
        base += ["-loop", "1", "-t", f"{float(seg['dur']):.3f}", "-i", src]
    else:
        base += ["-ss", f"{float(seg.get('start') or 0):.3f}", "-t", f"{float(seg['dur']):.3f}", "-i", src]
    base += ["-an", "-vf", vf, "-r", "25", "-c:v", venc, "-pix_fmt", "yuv420p", out_path]
    r = _tl_run(base, timeout=600)
    return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


def _tl_norm_audio(seg, out_path):
    
    ff = _mt.ffmpeg()
    if seg.get("kind") == "image":
        return False
    dur = f"{float(seg['dur']):.3f}"
    cmd = [ff, "-y", "-ss", f"{float(seg.get('start') or 0):.3f}", "-t", dur, "-i", _tl_ffpath(seg["path"]),
           "-vn", "-ac", "2", "-ar", "44100", "-c:a", "aac", out_path]
    r = _tl_run(cmd, timeout=600)
    if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return True

    sil = os.path.join(os.path.dirname(out_path), "_sil_" + os.path.basename(out_path) + ".pcm")
    try:
        _tl_silence_pcm(float(seg["dur"]) or 0.05, sil)
        r2 = _tl_run([ff, "-y", "-f", "s16le", "-ar", "44100", "-ac", "1", "-i", sil,
                      "-t", dur, "-ac", "2", "-ar", "44100", "-c:a", "aac", out_path], timeout=600)
        ok = r2.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception:
        ok = False
    try:
        if os.path.exists(sil):
            os.remove(sil)
    except Exception:
        pass
    return ok


def _tl_concat_list(paths, list_file):
    with open(list_file, "w", encoding="utf-8") as f:
        for p in paths:
            f.write("file '" + str(p).replace("'", "'\\''") + "'\n")
    return list_file


def _tl_cat(paths, out_path, has_audio_stream):
    
    ff = _mt.ffmpeg()
    lst = out_path + ".txt"
    _tl_concat_list(paths, lst)
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy"]
    if not has_audio_stream:
        cmd += ["-an"]
    cmd += [out_path]
    r = _tl_run(cmd, timeout=600)
    try:
        if os.path.exists(lst):
            os.remove(lst)
    except Exception:
        pass
    return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


@app.route("/api/media/concat", methods=["POST"])
def api_media_concat():
    
    data = request.get_json(silent=True) or {}
    vsegs = [s for s in (data.get("video") or []) if isinstance(s, dict)]
    asegs = [s for s in (data.get("audio") or []) if isinstance(s, dict)]
    if not vsegs and not asegs:
        return jsonify(error="时间线为空，没有可导出的片段"), 400
    ff = _mt.ffmpeg()
    if not ff:
        return jsonify(error="未找到 ffmpeg，无法导出成片（见启动日志的修复指引）"), 503
    venc = _tl_pick_venc()
    if vsegs and not venc:
        return jsonify(error="当前 ffmpeg 没有可用的视频编码器，无法导出画面"), 503


    def _prep(seq):
        out = []
        for s in seq:
            full = _tl_local(s.get("url"))
            if not full:
                continue
            try:
                dur = float(s.get("dur") or 0)
            except Exception:
                dur = 0.0
            if dur <= 0:
                continue
            out.append({"path": full, "kind": (s.get("kind") or _tl_kind_of(full)),
                        "start": float(s.get("start") or 0), "dur": dur})
        return out

    vsegs, asegs = _prep(vsegs), _prep(asegs)
    if not vsegs and not asegs:
        return jsonify(error="没有可用的站内素材片段"), 400


    w = h = 0
    for s in vsegs:
        if s["kind"] == "image":
            iw, ih = _tl_image_size(s["path"])
        else:
            _, iw, ih, _ha = _tl_probe_av(s["path"])
        if iw and ih:
            w, h = _tl_even(iw), _tl_even(ih)
            break
    if not w or not h:
        w, h = 1280, 720
    else:


        k = min(1.0, 1280.0 / w, 720.0 / h)
        w, h = _tl_even(round(w * k)), _tl_even(round(h * k))

    work = _tempfile.mkdtemp(prefix="tl_concat_")
    try:
        vpaths, apaths, vaudio = [], [], []
        for i, s in enumerate(vsegs):
            vp = os.path.join(work, f"v{i}.mp4")
            if not _tl_norm_video(s, vp, w, h, venc):
                return jsonify(error=f"第 {i + 1} 个画面片段处理失败"), 500
            vpaths.append(vp)
            if s["kind"] != "image":
                ap = os.path.join(work, f"va{i}.m4a")
                if _tl_norm_audio(s, ap):
                    vaudio.append(ap)
        for i, s in enumerate(asegs):
            ap = os.path.join(work, f"a{i}.m4a")
            if _tl_norm_audio(s, ap):
                apaths.append(ap)

        vcat = os.path.join(work, "vcat.mp4")
        if vsegs:
            if len(vpaths) == 1:
                _shutil.copyfile(vpaths[0], vcat)
            elif not _tl_cat(vpaths, vcat, False):
                return jsonify(error="画面轨拼接失败"), 500


        atracks = []
        if vaudio:
            t1 = os.path.join(work, "vcat_a.m4a")
            if len(vaudio) == 1:
                _shutil.copyfile(vaudio[0], t1)
            elif _tl_cat(vaudio, t1, True):
                pass
            else:
                t1 = None
            if t1:
                atracks.append(t1)
        if apaths:
            t2 = os.path.join(work, "acat.m4a")
            if len(apaths) == 1:
                _shutil.copyfile(apaths[0], t2)
            elif _tl_cat(apaths, t2, True):
                pass
            else:
                t2 = None
            if t2:
                atracks.append(t2)

        short = uuid.uuid4().hex[:10]
        if vsegs:
            out_name = f"tl_{short}.mp4"
            kind_out = "video"
        else:
            out_name = f"tl_{short}.m4a"
            kind_out = "audio"
        final = os.path.join(ASSETS_DIR, out_name)
        cmd = [ff, "-y"]
        if vsegs:
            cmd += ["-i", vcat]
        for t in atracks:
            cmd += ["-i", t]
        if len(atracks) >= 2:
            fc = "".join(f"[{i + (1 if vsegs else 0)}:a]" for i in range(len(atracks)))
            cmd += ["-filter_complex", f"{fc}amix=inputs={len(atracks)}:duration=longest[a]",
                    "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"]
        elif len(atracks) == 1:
            if vsegs:
                cmd += ["-map", "0:v:0", "-map", f"{1}:a:0", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"]
            else:
                cmd += ["-map", "0:a:0", "-c:a", "copy"]
        else:
            cmd += ["-map", "0:v:0", "-c:v", "copy"]
        cmd += [final]
        r = _tl_run(cmd, timeout=900)
        if r.returncode != 0 or not os.path.exists(final) or os.path.getsize(final) <= 0:
            try:
                if os.path.exists(final):
                    os.remove(final)
            except Exception:
                pass
            return jsonify(error="成片合成失败：" + (r.stderr.decode("utf-8", "ignore")[-300:] or "未知错误")), 500
        url = f"{_public_base()}/assets/{out_name}"
        try:
            _assets_store.register(name=out_name, url=url, type=kind_out,
                                   origin=_assets_store.ORIGIN_CREATED, label="时间线成片")
        except Exception as e:
            print("[WARN] 时间线成片入库失败（不影响成片）:", e, flush=True)
        return jsonify({"url": url, "name": out_name, "kind": kind_out})
    finally:
        try:
            _shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass



@app.route("/api/tts_upload.js")
def tts_upload_js():
    f = os.path.join(_ROOT, "src", "base", "js", "tts_upload.js")
    if not os.path.exists(f):
        return jsonify(error="not found"), 404
    resp = make_response(send_file(f, mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp



@app.route("/api/tts/provider", methods=["GET"])
def api_tts_provider_get():
    return jsonify(_ttsprov.config_snapshot(masked=True))


@app.route("/api/tts/provider", methods=["POST"])
def api_tts_provider_save():
    
    data = request.get_json(silent=True) or {}
    try:
        snap = _ttsprov.save(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "config": snap})


@app.route("/api/tts/provider/test", methods=["POST"])
def api_tts_provider_test():
    
    data = request.get_json(silent=True) or {}
    draft_base = (data.get("base_url") or "").strip()
    draft_key = (data.get("api_key") or "").strip()
    draft_model = (data.get("model") or "").strip()
    if draft_key and "…" in draft_key:
        draft_key = ""
    result = _ttsprov.test_connection(
        base_url=draft_base or None,
        api_key=draft_key or None,
        model=draft_model or None,
    )
    return jsonify(result)



@app.route("/api/ark/provider", methods=["GET"])
def api_ark_provider_get():
    return jsonify(_arkprov.config_snapshot(masked=True))


@app.route("/api/ark/provider", methods=["POST"])
def api_ark_provider_save():
    
    data = request.get_json(silent=True) or {}
    try:
        snap = _arkprov.save(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "config": snap})


@app.route("/api/ark/provider/test", methods=["POST"])
def api_ark_provider_test():
    
    data = request.get_json(silent=True) or {}
    draft_base = (data.get("base_url") or "").strip()
    draft_key = (data.get("api_key") or "").strip()
    draft_model = (data.get("model") or "").strip()
    if draft_key and "…" in draft_key:
        draft_key = ""
    result = _arkprov.test_connection(
        base_url=draft_base or None,
        api_key=draft_key or None,
        model=draft_model or None,
    )
    return jsonify(result)


@app.route("/api/ms/provider", methods=["GET"])
def api_ms_provider_get():
    return jsonify(_msprov.config_snapshot(masked=True))








@app.route("/api/image/provider", methods=["POST"])
def api_image_provider_set():
    
    data = request.get_json(silent=True) or {}
    key = str(data.get("provider") or "").strip().lower()
    if key not in _imgen.IMAGE_PROVIDER_ORDER:
        return jsonify({"error": "未知的生图服务商：%r（可选：%s）"
                                 % (data.get("provider"), " / ".join(_imgen.IMAGE_PROVIDER_ORDER))}), 400
    try:
        _img_apply_exclusive(key)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    st = _img_provider_state()

    warn = ""
    if st["fallback"]:
        warn = st["note"]
    return jsonify({"ok": True, "provider": key, "state": st, "warning": warn,
                    "label": _imgen.IMAGE_PROVIDER_LABELS.get(key, key),
                    "activeLabel": _imgen.IMAGE_PROVIDER_LABELS.get(st["winner"], st["winner"])})


@app.route("/api/ms/provider", methods=["POST"])
def api_ms_provider_save():
    
    data = request.get_json(silent=True) or {}
    try:
        snap = _msprov.save(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


    if data.get("chat_models_assistant_enabled"):
        _customprov.save({"chat_models_assistant_enabled": False})
    if data.get("chat_models_storyboard_enabled"):
        _customprov.save({"chat_models_storyboard_enabled": False})
    return jsonify({"ok": True, "config": snap})


@app.route("/api/ms/provider/test", methods=["POST"])
def api_ms_provider_test():
    
    data = request.get_json(silent=True) or {}
    draft_base = (data.get("base_url") or "").strip()
    draft_key = (data.get("api_key") or "").strip()
    draft_model = (data.get("model") or "").strip()
    if draft_key and "…" in draft_key:
        draft_key = ""
    result = _msprov.test_connection(
        base_url=draft_base or None,
        api_key=draft_key or None,
        model=draft_model or None,
    )
    return jsonify(result)






import server.custom_provider as _customprov


@app.route("/api/custom/provider", methods=["GET"])
def api_custom_provider_get():
    return jsonify(_customprov.config_snapshot(masked=True))


@app.route("/api/custom/provider", methods=["POST"])
def api_custom_provider_save():
    
    data = request.get_json(silent=True) or {}
    try:
        snap = _customprov.save(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "config": snap})


@app.route("/api/custom/provider/test", methods=["POST"])
def api_custom_provider_test():
    
    data = request.get_json(silent=True) or {}
    draft_base = (data.get("base_url") or "").strip()
    draft_key = (data.get("api_key") or "").strip()
    if draft_key and "…" in draft_key:
        draft_key = ""
    return jsonify(_customprov.test_connection(
        base_url=draft_base or None, api_key=draft_key or None))


@app.route("/api/llm/provider", methods=["POST"])
def api_llm_provider_set():
    
    data = request.get_json(silent=True) or {}
    uc = str(data.get("use_case") or "").strip()
    key = str(data.get("provider") or "").strip().lower()
    if uc not in _llm._USE_CASES:
        return jsonify({"error": "未知 LLM 用例：%r" % data.get("use_case")}), 400
    if key not in _llm.LLM_PROVIDER_ORDER:
        return jsonify({"error": "未知的 LLM 后端：%r（可选：%s）"
                                 % (data.get("provider"), " / ".join(_llm.LLM_PROVIDER_ORDER))}), 400
    en_key = "chat_models_%s_enabled" % uc

    _msprov.save({en_key: False} if key != "ms" else {en_key: True})
    if key != "ms":
        _customprov.save({en_key: key == "custom"})
    st = _llm._resolve_now(uc)
    warn = st.get("note") or ""
    if st["fallback"]:
        warn = st["note"]
    return jsonify({"ok": True, "use_case": uc, "provider": key, "resolve": st,
                    "label": _llm.LLM_PROVIDER_LABELS.get(key, key),
                    "activeLabel": _llm.LLM_PROVIDER_LABELS.get(st["winner"], st["winner"]),
                    "warning": warn})



@app.route("/api/tts/generate", methods=["POST"])
def api_tts_generate():
    
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "请输入要合成的文字。"}), 400
    speed = data.get("speed", 1.0)
    try:
        count = int(data.get("count", 2))
    except (TypeError, ValueError):
        count = 2
    count = max(1, min(4, count))


    voice_id = (data.get("voice_id") or "").strip()
    reference_raw = data.get("reference_audio") or ""




    ref_source = (data.get("ref_source") or "original").strip().lower()
    if ref_source not in ("original", "preview"):
        ref_source = "original"
    voice_name = "系统默认音色"
    ref_path = ""
    ref_url = ""
    used_ref_source = ""
    try:
        if voice_id:
            vrow = _ttsclient.get_voice_row(voice_id)
            if not vrow:
                return jsonify({"error": f"音色不存在：{voice_id}"}), 404


            used_ref_source = "preview" if (ref_source == "preview" and vrow.get("preview_path")) else "original"
            ref_path = vrow["preview_path"] if used_ref_source == "preview" else vrow["audio_path"]
            if not ref_path:
                return jsonify({"error": "该音色缺少参考音频文件。"}), 400
            ref_url = f"/api/tts/file/{ref_path}"
            voice_name = vrow.get("name") or voice_name
        elif reference_raw:
            _data, _ext, _ = _ttsclient.parse_audio_payload(reference_raw)

            ref_path = _ttsclient.create_reference(_data, _ext)
            ref_url = f"/api/tts/file/{ref_path}"

            voice_name = (data.get("voice_name") or "").strip() or "参考音色"
            used_ref_source = "original"






        job = _ttsclient.create_job(text, speed=speed, voice_name=voice_name,
                                    ref_path=ref_path, count=count)
        _ttsclient.start_job(job["id"], count=count)
        return jsonify({"ok": True, "job": job, "ref_url": ref_url,
                        "voice_name": voice_name, "ref_source": used_ref_source,
                        "speed": _ttsclient._norm_speed(speed), "text": text})
    except _ttsclient.TtsError as e:
        return jsonify({"error": e.message, "code": e.code}), 400


@app.route("/api/tts/job/<job_id>", methods=["GET"])
def api_tts_job(job_id):
    
    job = _ttsclient.get_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在或已被清理。", "code": "no_job"}), 404
    return jsonify({"ok": True, "job": job})



@app.route("/api/tts/voices", methods=["GET"])
def api_tts_voices_list():
    voices = _ttsclient.list_voices(
        owner=request.args.get("owner") or None,
        gender=request.args.get("gender") or None,
        age=request.args.get("age") or None,
        dialect=request.args.get("dialect") or None,
    )
    return jsonify({"ok": True, "voices": voices,
                    "options": {"gender": list(_ttsclient._GENDER),
                                "age": list(_ttsclient._AGE),
                                "dialect": list(_ttsclient._DIALECT)}})


@app.route("/api/tts/voices", methods=["POST"])
def api_tts_voices_add():
    
    data = request.get_json(silent=True) or {}
    reference_raw = data.get("reference_audio") or ""
    if not reference_raw:
        return jsonify({"error": "请上传参考音频。"}), 400
    try:
        voice, _ = _ttsclient.add_voice(
            reference_raw,
            name=(data.get("name") or "").strip(),
            gender=data.get("gender") or "",
            age=data.get("age") or "",
            dialect=data.get("dialect") or "",
            owner="mine",
            make_preview=False,
        )
    except _ttsclient.TtsError as e:
        return jsonify({"error": e.message, "code": e.code}), 400
    _ttsclient.start_preview_job(voice["id"])
    return jsonify({"ok": True, "voice": voice, "preview_pending": True, "preview_error": ""})


@app.route("/api/tts/voices/<vid>", methods=["PATCH"])
def api_tts_voices_update(vid):
    
    data = request.get_json(silent=True) or {}
    try:
        voice = _ttsclient.update_voice(
            vid,
            name=data.get("name") if "name" in data else None,
            gender=data.get("gender") if "gender" in data else None,
            age=data.get("age") if "age" in data else None,
            dialect=data.get("dialect") if "dialect" in data else None,
        )
    except _ttsclient.TtsError as e:
        return jsonify({"error": e.message, "code": e.code}), 400
    if not voice:
        return jsonify({"error": "音色不存在。"}), 404
    return jsonify({"ok": True, "voice": voice})


@app.route("/api/tts/voices/<vid>", methods=["DELETE"])
def api_tts_voices_delete(vid):
    if not _ttsclient.delete_voice(vid):
        return jsonify({"error": "音色不存在。"}), 404
    return jsonify({"ok": True})


@app.route("/api/tts/file/<path:rel>")
def api_tts_file(rel):
    
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not _ttsclient.is_public_rel(rel):
        return jsonify({"error": "forbidden"}), 403
    p = _ttsclient.abs_path(rel)
    if not p or not os.path.isfile(p):
        return jsonify({"error": "not found"}), 404
    ext = os.path.splitext(p)[1].lstrip(".").lower()
    mime = _ttsclient._MIME_BY_EXT.get(ext, "application/octet-stream")
    resp = make_response(send_file(p, mimetype=mime, conditional=True))
    resp.headers["Accept-Ranges"] = "bytes"
    return resp
