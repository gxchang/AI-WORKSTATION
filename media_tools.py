

import os
import shutil

_ROOT = os.path.dirname(os.path.abspath(__file__))

_EXE = {"ffmpeg": "ffmpeg.exe", "ffprobe": "ffprobe.exe"}
_CACHE = {}
_STARTUP_LOGGED = False


def _iter_candidates(tool, exe):
    
    key = "FFMPEG_PATH" if tool == "ffmpeg" else "FFPROBE"
    env = (os.environ.get(key) or "").strip()
    if env:

        yield os.path.join(env, exe) if os.path.isdir(env) else env

    yield os.path.join(_ROOT, "bin", exe)
    found = shutil.which(tool)
    if found:
        yield found


def _usable(path):
    
    if not path:
        return None
    p = path if os.path.isabs(path) else shutil.which(path)
    return p if p and os.path.exists(p) else None


def resolve(tool):
    
    if tool in _CACHE:
        return _CACHE[tool]
    exe = _EXE.get(tool)
    hit = None
    if exe:
        for cand in _iter_candidates(tool, exe):
            hit = _usable(cand)
            if hit:
                break
        if not hit and tool == "ffprobe":

            ff = resolve("ffmpeg")
            if ff:
                hit = _usable(os.path.join(os.path.dirname(ff), exe))
    _CACHE[tool] = hit
    return hit


def ffmpeg():
    return resolve("ffmpeg")


def ffprobe():
    return resolve("ffprobe")


def log_status():
    
    global _STARTUP_LOGGED
    if _STARTUP_LOGGED:
        return
    _STARTUP_LOGGED = True
    ff, fp = resolve("ffmpeg"), resolve("ffprobe")
    if ff:
        print(f"[INFO] ffmpeg 已就绪: {ff}", flush=True)
    else:
        print("[WARN] 未找到 ffmpeg：缩略图抽取与成片拼接(final.mp4)将不可用。"
              "修复二选一：① 安装 ffmpeg 并加入系统 PATH；"
              "② 设置环境变量 FFMPEG_PATH 指向 ffmpeg 可执行文件或其所在目录。"
              "改完需重启服务。", flush=True)
    if fp:
        print(f"[INFO] ffprobe 已就绪: {fp}", flush=True)
    else:
        print("[WARN] 未找到 ffprobe：音视频时长探测将退化为字数估算（播放条时长可能不准）。"
              "修复：安装 ffmpeg（自带 ffprobe）或设置环境变量 FFPROBE 指向 ffprobe 可执行文件。"
              "改完需重启服务。", flush=True)
