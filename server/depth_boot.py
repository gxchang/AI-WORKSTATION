

import threading
import time

from . import depth_env, depth_install

_LOCK = threading.Lock()
_THREAD = None
_LOGS = []
_LOG_MAX = 8

STATE = {
    "phase": "idle",
    "pct": 0,
    "done": 0,
    "total": 0,
    "message": "",
    "error": "",
    "updated_at": 0.0,
}


def _set(**kw):
    with _LOCK:
        STATE.update(kw)
        STATE["updated_at"] = time.time()


def _log(msg):
    
    print(msg, flush=True)
    with _LOCK:
        _LOGS.append(msg)
        while len(_LOGS) > _LOG_MAX:
            _LOGS.pop(0)


def status():
    
    with _LOCK:
        s = dict(STATE)
        s["log"] = list(_LOGS)
    return s


def _model_hint(total):
    return f"共 {depth_install.human(total)}"


def _run():
    st = depth_env.probe(use_cache=False)
    if st["ok"]:
        _set(phase="ready", pct=100, message="本地深度已就绪")
        return

    errs = []


    if "model" in st["missing"]:
        total = depth_env.pack_bytes("external")
        _set(phase="downloading", pct=0, done=0, total=total,
             message=f"正在下载深度模型（{_model_hint(total)}）", error="")

        def _prog(done, tot):
            pct = int(done * 100 / tot) if tot else 0
            _set(pct=pct, done=done, total=tot,
                 message=f"正在下载深度模型 {pct}%（{depth_install.human(done)}"
                         f" / {depth_install.human(tot)}）")

        ok, err = depth_install.fetch_model(log=_log, progress=_prog)
        if not ok:
            errs.append(f"模型：{err}")




    if "pylibs" in st["missing"]:
        ok, err = False, ""
        for idx in depth_install.PIP_INDEXES:
            host = "pip 官方源" if not idx else idx.split("//")[-1].split("/")[0]
            _set(phase="installing", pct=0,
                 message=f"正在安装推理引擎（约 {depth_install.PKG_HINT_MB}MB，走 {host}）")
            ok, err = depth_install.install_deps(index=idx, log=_log)
            if ok:
                break
            _log(f"[deps] {host} 不通或失败（{err}），换下一个源")
        if not ok:
            errs.append(f"依赖：{err}")

    depth_env.invalidate()
    st2 = depth_env.probe(use_cache=False)
    if st2["ok"]:
        _set(phase="ready", pct=100, message="本地深度已就绪", error="")
        _log(f"[boot] 补齐完成（{st2['reason']}）")
        return
    msg = "；".join(errs) or st2["reason"]
    _set(phase="error", pct=0, message="本地深度不可用", error=msg)
    _log(f"[boot] 补齐未完成：{msg}")


def ensure_started():
    
    global _THREAD
    with _LOCK:
        if _THREAD is not None:
            return False
        _THREAD = threading.Thread(target=_run, name="depth-boot", daemon=True)
        STATE.update(phase="checking", message="正在检查本地深度环境", updated_at=time.time())
    _THREAD.start()
    return True
