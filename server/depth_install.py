

import glob
import json
import os
import shutil
import subprocess
import sys
import time

from . import depth_env

MB = 1024.0 * 1024.0





PKG_HINT_MB = 126
_PKG_HINT = PKG_HINT_MB * MB













PIP_INDEXES = (
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    None,
)
PIP_INDEX_DEFAULT = PIP_INDEXES[0]
PIP_INDEX_FALLBACK = PIP_INDEXES[-1]


def human(n):
    return f"{n / MB:.1f}MB"


def _noop(*_a, **_k):
    return None



def _verify_ort(target):
    
    code = (
        "import sys, json;"
        f"sys.path.insert(0, {target!r});"
        f"sys.path.append({depth_env.PYLIBS_DIR!r});"
        "import onnxruntime as o;"
        "print(json.dumps({'v': o.__version__, 'p': o.get_available_providers()}))"
    )
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return False, [], f"{type(e).__name__}: {e}"
    if r.returncode != 0:
        return False, [], (r.stderr or b"").decode("utf-8", "replace")[-300:]
    try:
        d = json.loads((r.stdout or b"{}").decode("utf-8", "replace").strip().splitlines()[-1])
    except Exception as e:
        return False, [], f"输出无法解析：{e}"
    return True, list(d.get("p") or []), ""


def _stash_old_ort():
    
    import time as _t

    stamp = _t.strftime("%Y%m%d%H%M%S")
    moved, failed = [], []
    for pat in ("onnxruntime", "onnxruntime-*.dist-info", "onnxruntime_directml-*.dist-info"):
        for p in glob.glob(os.path.join(depth_env.PYLIBS_DIR, pat)):
            dst = p + ".old-" + stamp
            try:
                os.rename(p, dst)
                moved.append(dst)
            except OSError as e:
                failed.append(f"{os.path.basename(p)}：{e}")
    return moved, failed


def _purge(paths):
    
    left = []
    for p in paths:
        try:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        except OSError:
            left.append(os.path.basename(p))
    return left


def install_deps(index=PIP_INDEX_DEFAULT, force=False, log=None):
    
    log = log or _noop
    os.makedirs(depth_env.PYLIBS_DIR, exist_ok=True)
    _purge(glob.glob(os.path.join(depth_env.PYLIBS_DIR, "*.old-*")))

    staging = depth_env.PYLIBS_DIR + ".staging"
    _purge([staging])
    if os.path.exists(staging):



        return False, (f"暂存目录删不掉：{staging}（多半被另一个还在运行的工作台占用）。"
                       f"关掉所有工作台窗口后重试，或手动删掉该目录")
    os.makedirs(staging, exist_ok=True)


    have_deps = os.path.isdir(os.path.join(depth_env.PYLIBS_DIR, "numpy"))

    def _pip(pkgs, what):
        
        cmd = [sys.executable, "-m", "pip", "install",
               "--target", staging, "--no-warn-script-location", "--no-deps"]
        if force:
            cmd.append("--upgrade")
        if index:
            cmd += ["-i", index]
        cmd += list(pkgs)
        log(f"[deps] {what}")
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=1800)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"无法执行 pip：{e}"
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()
            tail = " / ".join(tail.splitlines()[-4:])
            return False, f"pip 退出码 {r.returncode}：{tail[:300]}"
        return True, ""

    t0 = time.time()
    ok, err = _pip(depth_env.PY_PKGS,
                   f"安装 {', '.join(depth_env.PY_PKGS)}（约 {human(_PKG_HINT)}，"
                   f"走{'国内镜像' if index else '官方源'}）")
    if not ok:
        _purge([staging])
        return False, err
    if not have_deps:
        ok, err = _pip(depth_env.PY_DEPS,
                       f"补运行依赖 {', '.join(depth_env.PY_DEPS)}")
        if not ok:
            _purge([staging])
            return False, err



    log(f"[deps] pip 完成（{time.time() - t0:.0f} 秒）")

    ok, provs, err = _verify_ort(staging)
    if not ok:
        _purge([staging])
        return False, f"装完验证失败：{err}"
    log(f"[deps] 验证通过，编译进来的后端：{', '.join(provs) or '?'}")
    if depth_env.EXPECT_ACCEL and not depth_env.has_accel(provs):
        log("[deps] 这份包里没有加速后端，仍走 CPU")

    moved, failed = _stash_old_ort()
    if failed:

        for p in moved:
            try:
                os.rename(p, p.split(".old-")[0])
            except OSError:
                pass
        _purge([staging])
        return False, f"旧包挪不开，放弃替换：{'; '.join(failed)}"

    try:


        skip = {"bin", "Scripts"}
        for name in os.listdir(staging):
            if name in skip:
                continue
            src, dst = os.path.join(staging, name), os.path.join(depth_env.PYLIBS_DIR, name)

            if os.path.exists(dst):
                raise RuntimeError(f"目标已存在：{name}")
            shutil.move(src, dst)
    except Exception as e:
        for p in moved:
            try:
                os.rename(p, p.split(".old-")[0])
            except OSError:
                pass
        _purge([staging])
        depth_env.invalidate()
        return False, f"换入失败：{e}"

    _purge([staging])
    _purge(moved)
    depth_env.invalidate()
    return True, ""



def verify_pack(name=None, log=None):
    
    log = log or _noop
    name = name or depth_env.installed_pack()
    pack = depth_env.pack_of(name)
    if not pack:
        return False
    for fn, size, sha in pack["files"]:
        fp = os.path.join(depth_env.MODEL_DIR, fn)
        try:
            n = os.path.getsize(fp)
        except OSError:
            log(f"[model] 缺 {fn}")
            return False
        if n != size:
            log(f"[model] {fn} 大小不符（{n} != {size}）")
            return False
        if depth_env.sha256_of(fp) != sha:
            log(f"[model] {fn} 校验失败")
            return False
    return True


def _fetch_file(url, dest, expect_size, expect_sha, on_bytes, log):
    
    tmp = dest + ".part"
    try:
        import requests
    except ImportError:
        log("[model] 缺少 requests，无法自动下载")
        return False

    have = os.path.getsize(tmp) if os.path.isfile(tmp) else 0
    if have > expect_size:
        _purge([tmp])
        have = 0
    headers = {"User-Agent": "Mozilla/5.0"}
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        r = requests.get(url, stream=True, timeout=(20, 180), headers=headers)
    except Exception as e:
        log(f"[model]   连接失败 {type(e).__name__}: {str(e)[:120]}")
        return False

    with r:
        if have and r.status_code == 206:
            mode = "ab"
            log(f"[model]   续传（已有 {human(have)}）")
        elif r.status_code == 200:
            mode, have = "wb", 0
        else:
            log(f"[model]   HTTP {r.status_code}，换下一个源")
            return False
        got = have
        try:
            with open(tmp, mode) as f:
                for chunk in r.iter_content(1 << 20):
                    if not chunk:
                        continue
                    f.write(chunk)
                    got += len(chunk)
                    on_bytes(len(chunk))
        except Exception as e:
            log(f"[model]   中断于 {human(got)}：{type(e).__name__}: {str(e)[:100]}")
            return False

    n = os.path.getsize(tmp)
    if n != expect_size:
        log(f"[model]   大小不符（{n} != {expect_size}），丢弃重下")
        _purge([tmp])
        return False
    if depth_env.sha256_of(tmp) != expect_sha:
        log("[model]   校验失败，丢弃重下")
        _purge([tmp])
        return False
    return True


def fetch_model(force=False, log=None, progress=None):
    
    log = log or _noop
    progress = progress or _noop

    if not force and verify_pack(log=log):
        log(f"[model] 已有可用权重（{depth_env.installed_pack()}），跳过下载")
        return True, ""

    os.makedirs(depth_env.MODEL_DIR, exist_ok=True)
    errs = []
    for src in depth_env.MODEL_SOURCES:
        pack = depth_env.pack_of(src["pack"])
        if not pack:
            continue
        total = sum(sz for _, sz, _ in pack["files"])
        done = 0
        log(f"[model] 源 {src['name']}（{src['pack']}，共 {human(total)}）")
        progress(0, total)
        staged, failed = [], ""
        for fn, size, sha in pack["files"]:
            url = src["base"] + fn
            dest = os.path.join(depth_env.MODEL_DIR, fn)
            base = done
            if not _fetch_file(url, dest, size, sha,
                               lambda d, b=base: progress(b + d, total), log):
                failed = fn
                break
            done += size
            staged.append((dest + ".part", dest))
            progress(done, total)
        if failed:
            errs.append(f"{src['name']}：{failed} 下载失败")
            continue


        for tmp, dest in staged:
            os.replace(tmp, dest)
        if verify_pack(pack["name"], log):
            log(f"[model] 完成 {human(total)}（{src['name']} / {pack['name']}）")
            depth_env.invalidate()
            return True, ""
        errs.append(f"{src['name']}：落地校验未通过")
        for _, dest in staged:
            _purge([dest])

    msg = "；".join(errs) or "没有可用的下载源"
    log(f"[model] 全部源都失败（{msg}）")
    log(f"[model] 可手动下载后放到 {depth_env.MODEL_DIR}，任选其一：")
    for src in depth_env.MODEL_SOURCES:
        for fn, _size, _sha in depth_env.pack_of(src["pack"])["files"]:
            log(f"[model]   {src['base']}{fn}")
    return False, msg
