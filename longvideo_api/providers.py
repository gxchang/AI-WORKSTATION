

import json


class _Resp:
    

    __slots__ = ("status_code", "_payload", "text")

    def __init__(self, status_code, payload=None, text=""):
        self.status_code = int(status_code)
        self._payload = payload if payload is not None else {}
        try:
            self.text = text or json.dumps(self._payload, ensure_ascii=False)
        except Exception:
            self.text = str(self._payload)

    def json(self):
        return self._payload


class SegmentSubmitter:
    


    supports_native_multi_segment = False

    max_segments_per_task = None

    label = "?"

    def __init__(self, model):
        self.model = model

    def submit(self, req, attempt=0):
        
        raise NotImplementedError

    def poll(self, video_id, timeout=600, should_stop=None, on_state=None):
        
        raise NotImplementedError


    supports_remote_cancel = False

    def cancel(self, video_id):
        
        return False, "该上游没有取消接口（在飞任务会跑完）"

    def ref_caps(self):
        
        from server.video_caps import ref_caps as _rc
        return _rc(self.model)


class AgnesSubmitter(SegmentSubmitter):
    

    label = "Agnes"

    def submit(self, req, attempt=0):
        from . import _core
        return _core._agnes_create_video(
            req.get("images") or [], req.get("audios") or [], req.get("prompt") or "",
            req.get("seconds") or 5, attempt, req.get("mode") or "reference",
            size=req.get("size") or "720P", aspect_ratio=req.get("aspect_ratio") or "16:9",
            model=self.model)

    def poll(self, video_id, timeout=600, should_stop=None, on_state=None):



        from . import _core
        return _core._agnes_poll(video_id, timeout=timeout, model=self.model,
                                 should_stop=should_stop)


class RhSubmitter(SegmentSubmitter):
    

    label = "RunningHub"
    supports_native_multi_segment = True
    max_segments_per_task = None

    supports_remote_cancel = True

    def __init__(self, model):
        super().__init__(model)


        self.last_cost = None

    def submit(self, req, attempt=0):
        import server.routes as _routes
        data = {
            "model": self.model,
            "mode": req.get("mode") or ("reference" if (req.get("images") or req.get("audios")) else "text"),
            "prompt": req.get("prompt") or "",
            "seconds": req.get("seconds") or 5,
            "size": req.get("size") or "",
            "aspect_ratio": req.get("aspect_ratio") or "",
            "images": req.get("images") or [],
            "audios": req.get("audios") or [],
            "sessionId": req.get("sessionId"),




            "instance": req.get("instance"),
            "accel": req.get("accel"),
            "quality_tier": req.get("quality_tier"),
            "refine": req.get("refine"),
            "face": req.get("face"),


            "selflift": req.get("selflift"),

            "seed": req.get("seed"),
        }
        out, code = _routes._submit_video_to_runninghub(data)
        if code == 200 and isinstance(out, dict) and out.get("video_id"):
            return _Resp(200, out)
        return _Resp(code or 502, out if isinstance(out, dict) else {"error": str(out)[:200]})

    def cancel(self, video_id):
        
        import server.runninghub_provider as _rh
        return _rh.cancel(video_id)

    def poll(self, video_id, timeout=600, should_stop=None, on_state=None):
        
        import time
        import server.runninghub_provider as _rh
        self.last_cost = None
        t0 = time.time()
        while time.time() - t0 < timeout:

            if should_stop and should_stop():
                return "cancelled", ""
            body, err = _rh.poll_status(video_id)
            if not err:
                st = _rh.parse_status(body) or {}
                s = st.get("status") or "processing"

                if on_state and s in ("queued", "processing"):
                    on_state("queued" if s == "queued" else "running")
                if s == "failed":
                    return "failed", ""
                if s in ("done", "completed", "success"):

                    outs, _e = _rh.fetch_outputs(video_id)
                    url = st.get("video_url")
                    if not url:
                        url, _reason = _rh.parse_outputs(outs or {})

                    cost = _rh.parse_usage(outs or {})
                    if cost:
                        _u = (_rh.limits(self.model) or {}).get("usage") or {}
                        cost["coins_unit"] = _u.get("coins_unit") or ""
                        cost["money_unit"] = _u.get("money_unit") or ""
                        self.last_cost = cost
                    return ("completed" if url else "failed"), (url or "")
            time.sleep(8)
        return "processing", ""

    def submit_group(self, segments, common=None):
        
        common = common or {}
        if not segments or len(segments) < 2:
            raise ValueError("submit_group 要求整组一次性提交（≥2 段），实际收到 %d 段" % len(segments or []))

        for i, s in enumerate(segments):
            s = dict(s)
            s["continuity"] = bool(s.get("continuity", i > 0))
            segments[i] = s

        _strip_tail_from_segments(segments, common)





        _anchor_prompt = ""
        for _s in segments:
            _anchor_prompt = str(_s.get("prompt") or "").strip()
            if _anchor_prompt:
                break
        data = {
            "model": self.model,
            "mode": common.get("mode") or "reference",
            "prompt": _anchor_prompt,
            "aspect_ratio": common.get("aspect_ratio") or "",
            "size": common.get("size") or "",
            "sessionId": common.get("sessionId"),
            "instance": common.get("instance"),
            "accel": common.get("accel"),



            "quality_tier": common.get("quality_tier"),
            "refine": common.get("refine") or {},
            "face": common.get("face") or {},
            "selflift": common.get("selflift") or {},
            "seed": common.get("seed"),
            "segments": segments,


            "images": common.get("images") or _aggregate_refs(segments),
            "audios": common.get("audios") or [],
        }

        import server.runninghub_provider as _rh
        tl = _rh.build_timeline_data(data, file_names={})
        _assert_continuity_suite(tl)

        import server.routes as _routes
        out, code = _routes._submit_video_to_runninghub(data)
        if code == 200 and isinstance(out, dict) and out.get("video_id"):
            return _Resp(200, out)
        return _Resp(code or 502, out if isinstance(out, dict) else {"error": str(out)[:200]})


def _strip_tail_from_segments(segments, common):
    
    _TAIL = ("tail", None)
    for s in segments:
        s["images"] = [x for x in (s.get("images") or []) if x not in _TAIL]
        s["audios"] = [x for x in (s.get("audios") or []) if x not in _TAIL]

    if "images" in common:
        common["images"] = [x for x in (common.get("images") or []) if x not in _TAIL]


def _aggregate_refs(segments):
    
    seen, out = set(), []
    for s in segments:
        for x in (s.get("images") or []):
            if x and x not in seen:
                seen.add(x); out.append(x)
        for x in (s.get("audios") or []):
            if x and x not in seen:
                seen.add(x); out.append(x)
    return out


def _assert_continuity_suite(tl):
    
    out_cfg = (tl.get("output") or {})
    if out_cfg.get("continuityEnabled") is not True:
        raise AssertionError(
            "续接组提交必须启用段间引导(continuityEnabled=True)，实为 %r" % out_cfg.get("continuityEnabled"))
    segs = tl.get("segments") or []
    if not segs:
        raise AssertionError("续接组提交必须带 segments[]，实为空的")
    if segs[0].get("continuityFromPrev") is not False:
        raise AssertionError("段间引导锚点错配：首段 continuityFromPrev 应 False，实为 %r" % segs[0].get("continuityFromPrev"))
    for i, s in enumerate(segs[1:], start=1):
        if s.get("continuityFromPrev") is not True:
            raise AssertionError("段间引导错配：第 %d 段 continuityFromPrev 应 True，实为 %r" % (i, s.get("continuityFromPrev")))

    for k in ("continuityOverlapFrames", "continuityMode", "continuityRedraw", "continuityKeepTail"):
        if k not in out_cfg:
            raise AssertionError("段间引导缺参数 %s" % k)


def get_submitter(model):
    
    m = str(model or "").strip()
    try:
        import server.runninghub_provider as _rh
        if _rh.is_video_model(m):
            return RhSubmitter(m)
    except Exception:
        pass
    return AgnesSubmitter(m)
