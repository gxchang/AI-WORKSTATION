

import os
import subprocess
import time

import media_tools as _mt

from . import depth_env


_VENC_CACHE = {"enc": None, "probed": False}


_PROBE_CACHE = {}

_FPS_FALLBACK = 24.0



def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def pick_venc():
    
    if _VENC_CACHE["probed"]:
        return _VENC_CACHE["enc"], _VENC_CACHE["ext"]
    enc, ext = None, "mp4"
    ff = _mt.ffmpeg()
    if ff:
        try:
            txt = _run([ff, "-hide_banner", "-encoders"], timeout=60).stdout.decode("utf-8", "ignore")
            for name, e in (("libopenh264", "mp4"), ("h264_qsv", "mp4"),
                            ("mpeg4", "mp4"), ("libvpx-vp9", "webm")):
                if name in txt:
                    enc, ext = name, e
                    break
        except Exception:
            enc = None
    _VENC_CACHE.update({"enc": enc, "ext": ext, "probed": True})
    print(f"[depth] 视频编码器 {enc or '未找到'}（容器 {ext}）", flush=True)
    return enc, ext


def probe_video(path):
    
    try:
        st = os.stat(path)
        key = (os.path.abspath(path), st.st_mtime, st.st_size)
    except OSError:
        key = None
    if key and key in _PROBE_CACHE:
        return dict(_PROBE_CACHE[key])

    fp = _mt.ffprobe()
    if not fp:
        raise RuntimeError("ffprobe 不可用，无法读取视频信息")
    r = _run([fp, "-v", "error", "-show_entries",
              "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,"
              "nb_frames:format=duration", "-of", "json", path], timeout=120)
    import json as _json
    try:
        j = _json.loads(r.stdout.decode("utf-8", "ignore") or "{}")
    except Exception:
        raise RuntimeError(f"ffprobe 输出无法解析：{r.stderr[:200]!r}")

    out = {"w": 0, "h": 0, "fps": _FPS_FALLBACK, "fps_frac": "24/1", "frames": 0,
           "duration": 0.0, "has_audio": False, "acodec": ""}

    def _frac_ok(s):
        
        try:
            num, _, den = str(s or "").partition("/")
            v = float(num) / float(den or 1)
            return v if 0 < v < 240 else None
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    got_rate = False
    for s in (j.get("streams") or []):
        if s.get("codec_type") == "video" and not out["w"]:
            out["w"] = int(s.get("width") or 0)
            out["h"] = int(s.get("height") or 0)




            cand = [s.get("avg_frame_rate"), s.get("r_frame_rate")]
            for c in cand:
                v = _frac_ok(c)
                if v:
                    out["fps"], out["fps_frac"] = v, str(c)
                    got_rate = True
                    break
            nb = s.get("nb_frames")
            out["frames"] = int(nb) if str(nb or "").isdigit() else 0
        elif s.get("codec_type") == "audio":
            out["has_audio"] = True
            out["acodec"] = str(s.get("codec_name") or "")
    try:
        out["duration"] = float((j.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        out["duration"] = 0.0
    if not out["frames"] and out["duration"]:
        out["frames"] = int(round(out["duration"] * out["fps"]))






    if out["frames"] and out["duration"] and not got_rate:
        guess = out["frames"] / out["duration"]
        if 1 < guess < 240:
            out["fps"], out["fps_frac"] = guess, f"{int(round(guess * 1000))}/1000"
    if key:
        _PROBE_CACHE[key] = dict(out)
    return out


def _infer_size(w, h, short):
    
    def _m14(v):
        return max(14, int(round(v / 14.0)) * 14)
    if w >= h:
        return _m14(short * w / float(h)), _m14(short)
    return _m14(short), _m14(short * h / float(w))



def _plan(ort):
    
    out = []
    for p in depth_env.candidates(ort.get_available_providers()):
        if p == "DmlExecutionProvider":
            for dev in (0, 1):
                out.append({"provider": p, "opts": {"device_id": dev},
                            "label": f"{p}#{dev}"})
        else:
            out.append({"provider": p, "opts": None, "label": p})
    out.append({"provider": depth_env.CPU_PROVIDER, "opts": None,
                "label": depth_env.CPU_PROVIDER})
    return out


def _make(ort, entry, threads):
    
    o = ort.SessionOptions()
    o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    prov, opts = entry["provider"], entry["opts"]
    if prov == depth_env.CPU_PROVIDER:

        o.intra_op_num_threads = int(threads or max(2, (os.cpu_count() or 4) - 2))
        providers = [prov]
    else:

        providers = [(prov, opts)] if opts else [prov]
        providers.append(depth_env.CPU_PROVIDER)
    sess = ort.InferenceSession(depth_env.MODEL_PATH, o, providers=providers)
    actual = (sess.get_providers() or [depth_env.CPU_PROVIDER])[0]
    return sess, actual


def _bench(sess, ort, tw, th):
    
    import numpy as np

    inp = sess.get_inputs()[0].name
    x = np.random.default_rng(0).random((1, 3, th, tw), dtype=np.float32)
    for _ in range(depth_env.BENCH_WARMUP):
        sess.run(None, {inp: x})
    ts = []
    for _ in range(depth_env.BENCH_ROUNDS):
        t = time.time()
        sess.run(None, {inp: x})
        ts.append((time.time() - t) * 1000.0)
    ts.sort()
    return ts[len(ts) // 2]


def _session_for(ort, tw, th, threads=None):
    
    import numpy as np

    avail = ort.get_available_providers()
    key = depth_env.device_cache_key(getattr(ort, "__version__", "?"), avail, tw, th)
    force = os.environ.get(depth_env.REBENCH_ENV, "") not in ("", "0", "false")
    cache = None if force else depth_env.read_device_cache()
    plan = _plan(ort)


    if len(plan) == 1:
        sess, actual = _make(ort, plan[0], threads)
        return sess, {"provider": actual, "requested": plan[0]["label"],
                      "ms": None, "from_cache": False, "tried": []}


    if cache and cache.get("key") == key:
        hit = cache.get("chosen") or {}
        entry = next((e for e in plan if e["label"] == hit.get("requested")), None)
        if entry and not force:
            try:
                sess, actual = _make(ort, entry, threads)
                if actual == hit.get("actual"):
                    return sess, {"provider": actual, "requested": entry["label"],
                                  "ms": hit.get("ms"), "from_cache": True, "tried": []}
                print(f"[depth] 缓存的后端给不出来了（要 {hit.get('actual')}，"
                      f"实际 {actual}），重新测一遍", flush=True)
            except Exception as e:
                print(f"[depth] 缓存的后端建不起来，重新测一遍：{type(e).__name__}: {e}",
                      flush=True)


    tried, best = [], None
    for entry in plan:
        try:
            sess, actual = _make(ort, entry, threads)
            ms = _bench(sess, ort, tw, th)
        except Exception as e:
            print(f"[depth]   {entry['label']:32s} 跳过：{type(e).__name__}: "
                  f"{str(e)[:120]}", flush=True)
            continue
        tried.append({"requested": entry["label"], "actual": actual, "ms": round(ms, 1)})
        print(f"[depth]   {entry['label']:32s} -> {actual:26s} {ms:7.1f}ms/帧", flush=True)
        if best is None or ms < best[0]:
            best = (ms, sess, entry, actual)

    if best is None:
        raise RuntimeError("没有任何可用的推理后端（连 CPUExecutionProvider 都建不起来）")

    ms, sess, entry, actual = best
    print(f"[depth] 选中 {entry['label']}（实际 {actual}，{ms:.1f}ms/帧，"
          f"共试 {len(tried)} 个后端）", flush=True)
    depth_env.write_device_cache({
        "key": key,
        "chosen": {"requested": entry["label"], "actual": actual, "ms": round(ms, 1)},
        "tried": tried,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return sess, {"provider": actual, "requested": entry["label"], "ms": round(ms, 1),
                  "from_cache": False, "tried": tried}



def extract_depth(src, out, short=518, alpha=0.2, threads=None, on_progress=None):
    


    st = depth_env.probe()
    if not st["ok"]:
        raise RuntimeError(st["reason"])
    depth_env.ensure_syspath()
    import numpy as np
    import onnxruntime as ort

    ff, fp = _mt.ffmpeg(), _mt.ffprobe()
    if not ff or not fp:
        raise RuntimeError("ffmpeg / ffprobe 不可用")

    info = probe_video(src)
    if not info["w"] or not info["h"]:
        raise RuntimeError("读不到视频分辨率（可能不是视频文件）")
    tw, th = _infer_size(info["w"], info["h"], int(short))
    total = info["frames"] or 0

    sess, chosen = _session_for(ort, tw, th, threads)
    inp = sess.get_inputs()[0]

    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    enc_name, cont = pick_venc()
    if not enc_name:
        raise RuntimeError("这台机器的 ffmpeg 没有可用的视频编码器")

    vid_only = out + (".v.mp4" if cont == "mp4" else ".v.webm")

    dec = subprocess.Popen(
        [ff, "-v", "error", "-i", src, "-vf", f"scale={tw}:{th}",



         "-r", info["fps_frac"],
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    enc_cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray",
               "-s", f"{tw}x{th}", "-r", info["fps_frac"], "-i", "-",
               "-vf", f"scale={info['w']}:{info['h']}:flags=bicubic",
               "-c:v", enc_name, "-b:v", "8M", "-pix_fmt", "yuv420p"]
    if cont == "mp4":
        enc_cmd += ["-movflags", "+faststart"]
    enc = subprocess.Popen(enc_cmd + [vid_only],
                           stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    n, fs = 0, tw * th * 3
    lo_s = hi_s = None
    t0 = t_last = time.time()
    try:
        while True:
            buf = dec.stdout.read(fs)
            if not buf or len(buf) < fs:
                break
            img = np.frombuffer(buf, dtype=np.uint8).reshape(th, tw, 3).astype(np.float32) / 255.0
            x = ((img - mean) / std).transpose(2, 0, 1)[None].astype(np.float32)
            d = np.squeeze(sess.run(None, {inp.name: x})[0]).astype(np.float32)
            lo, hi = float(d.min()), float(d.max())
            if lo_s is None:
                lo_s, hi_s = lo, hi
            else:
                lo_s = alpha * lo + (1 - alpha) * lo_s
                hi_s = alpha * hi + (1 - alpha) * hi_s
            if hi_s - lo_s < 1e-6:
                hi_s = lo_s + 1e-6
            g = ((d - lo_s) / (hi_s - lo_s) * 255.0).clip(0, 255).astype(np.uint8)
            enc.stdin.write(g.tobytes())
            n += 1
            if on_progress and time.time() - t_last >= 5.0:
                t_last = time.time()
                on_progress(n, total)
    finally:
        for p in (dec, enc):
            try:
                p.stdin and p.stdin.close()
            except Exception:
                pass
        try:
            dec.stdout.close()
        except Exception:
            pass
        dec.wait()
        enc.wait()

    if n == 0:
        raise RuntimeError("一帧都没读到（源视频可能损坏或编码不受支持）")


    if info["has_audio"]:



        mux_cmd = [ff, "-y", "-v", "error", "-i", vid_only, "-i", src,
                   "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                   "-c:a", "aac", "-b:a", "128k"]
        if cont == "mp4":
            mux_cmd += ["-movflags", "+faststart"]
        r = _run(mux_cmd + [out], timeout=600)
        if r.returncode == 0:
            try:
                os.remove(vid_only)
            except OSError:
                pass
        else:

            print(f"[depth] 音轨回贴失败，保留无声版：{r.stderr[-200:]!r}", flush=True)
            os.replace(vid_only, out)
    else:
        os.replace(vid_only, out)

    return {"frames": n, "seconds": round(time.time() - t0, 1),
            "w": info["w"], "h": info["h"], "short": int(short),
            "audio": bool(info["has_audio"]),



            "device": "cpu" if chosen["provider"] == depth_env.CPU_PROVIDER else "gpu",
            "provider": chosen["provider"],
            "provider_requested": chosen["requested"],
            "bench_ms": chosen["ms"],
            "device_cached": bool(chosen["from_cache"])}



def _snap_frame(at, fps, total_frames):
    
    fps = float(fps or 0)
    if fps <= 0 or at is None:
        return None, float(at or 0)
    n = int(max(0.0, at) * fps)
    if total_frames:
        n = min(n, int(total_frames) - 1)
    return n, n / fps


def grab_frame(src, out, which="head", at=None):
    
    ff = _mt.ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg 不可用")
    info = probe_video(src)
    frame = None
    if at is not None:
        fps = float(info.get("fps") or 0)



        span = 0.0
        if info.get("frames") and fps > 0:
            span = info["frames"] / fps
        else:
            span = float(info.get("duration") or 0)
        a = max(0.0, float(at))
        if span > 0 and fps > 0:
            a = min(a, max(0.0, span - 1.0 / fps))
        frame, a = _snap_frame(a, fps, info.get("frames"))


        a = max(0.0, float(a) - 0.0001)
        cmd = [ff, "-y", "-v", "error", "-ss", f"{a:.6f}", "-i", src,
               "-frames:v", "1", out]
        which = "at"
    elif which == "tail":
        cmd = [ff, "-y", "-v", "error", "-sseof", "-0.3", "-i", src,
               "-update", "1", "-frames:v", "1", out]
    else:
        cmd = [ff, "-y", "-v", "error", "-i", src, "-frames:v", "1", out]
    r = _run(cmd, timeout=180)
    if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError(f"截帧失败：{(r.stderr or b'')[-200:]!r}")
    out_info = {"which": which, "w": info["w"], "h": info["h"], "frames": 1}
    if frame is not None:
        out_info["at"] = round(frame / float(info["fps"]), 3)
        out_info["frame"] = frame
    return out_info



_AUDIO_EXT = {"aac": "m4a", "mp3": "mp3", "opus": "m4a", "vorbis": "m4a",
              "ac3": "m4a", "eac3": "m4a", "flac": "m4a", "pcm_s16le": "m4a"}


def audio_ext_of(src):
    
    info = probe_video(src)
    if not info["has_audio"]:
        raise RuntimeError("这个视频没有音轨，无法分离音频")
    return _AUDIO_EXT.get((info["acodec"] or "").lower(), "m4a")


def extract_audio(src, out):
    
    ff = _mt.ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg 不可用")
    ext = audio_ext_of(src)
    want_ext = os.path.splitext(out)[1].lstrip(".").lower()
    copyable = (ext == want_ext)
    cmd = [ff, "-y", "-v", "error", "-i", src, "-vn"]
    cmd += ["-c:a", "copy"] if copyable else ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", out] if want_ext == "m4a" else [out]
    r = _run(cmd, timeout=300)
    if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise RuntimeError(f"分离音频失败：{(r.stderr or b'')[-200:]!r}")
    return {"codec": "copy" if copyable else "aac", "ext": want_ext}
