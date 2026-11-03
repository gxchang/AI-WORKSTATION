

import hashlib
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYLIBS_DIR = os.path.join(ROOT, "bin", "pylibs")
MODEL_DIR = os.path.join(ROOT, "bin", "models", "depth")
MODEL_PATH = os.path.join(MODEL_DIR, "model.onnx")















MODEL_PACKS = (
    {
        "name": "external",
        "files": (
            ("model.onnx", 127382,
             "345f249eda90f33e0548890f2fe1e89662c1dbb5a8b7c10a50492558f65e85a3"),
            ("model.onnx_data", 98798080,
             "c4fba31e921953367d8c5348b92296b2bf41f9cef9745ffaca01e2b1653e6d08"),
        ),
    },
    {
        "name": "single",
        "files": (
            ("model.onnx", 99060839,
             "afb6a5c28f3b6bf1618c6e43f02073ef9dfdc70e937502d51603e57b0a1df10c"),
        ),
    },
)




MODEL_SOURCES = (
    {"name": "魔搭",
     "pack": "external",
     "base": "https://modelscope.cn/models/onnx-community/"
             "depth-anything-v2-small-ONNX/resolve/master/onnx/"},
    {"name": "hf-mirror",
     "pack": "single",
     "base": "https://hf-mirror.com/onnx-community/"
             "depth-anything-v2-small/resolve/main/onnx/"},
    {"name": "huggingface",
     "pack": "single",
     "base": "https://huggingface.co/onnx-community/"
             "depth-anything-v2-small/resolve/main/onnx/"},
)





















_PLATFORM_WIN = sys.platform.startswith("win")
PY_PKGS = ("onnxruntime-directml" if _PLATFORM_WIN else "onnxruntime",)












PY_DEPS = ("numpy", "packaging", "flatbuffers", "protobuf")


EXPECT_ACCEL = _PLATFORM_WIN

CPU_PROVIDER = "CPUExecutionProvider"


PROVIDER_PRIORITY = (
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "MIGraphXExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
    "OpenVINOExecutionProvider",
    "VitisAIExecutionProvider",
)



DEVICE_CACHE_PATH = os.path.join(ROOT, "bin", "depth_device.json")
BENCH_WARMUP = 1
BENCH_ROUNDS = 3
REBENCH_ENV = "WB_DEPTH_REBENCH"


def candidates(available=None):
    
    if available is None:
        return list(PROVIDER_PRIORITY)
    have = set(available or ())
    return [p for p in PROVIDER_PRIORITY if p in have]


def has_accel(available=None):
    
    return bool(candidates(available))


def setup_providers(available=None):
    
    cands = candidates(available)
    return cands + [CPU_PROVIDER]


def pack_of(name):
    
    for p in MODEL_PACKS:
        if p["name"] == name:
            return p
    return None


def pack_bytes(name):
    
    p = pack_of(name)
    return sum(sz for _, sz, _ in p["files"]) if p else 0


def installed_pack():
    
    for p in MODEL_PACKS:
        ok = True
        for fn, size, _ in p["files"]:
            fp = os.path.join(MODEL_DIR, fn)
            try:
                if os.path.getsize(fp) != size:
                    ok = False
                    break
            except OSError:
                ok = False
                break
        if ok:
            return p["name"]
    return ""


def device_cache_key(ort_version, available, tw, th):
    
    return "|".join([
        sys.platform,
        str(ort_version or "?"),
        ",".join(sorted(available or ())),
        f"{int(tw)}x{int(th)}",
        installed_pack() or "-",
    ])


def read_device_cache():
    
    try:
        with open(DEVICE_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_device_cache(obj):
    
    try:
        os.makedirs(os.path.dirname(DEVICE_CACHE_PATH), exist_ok=True)
        tmp = DEVICE_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DEVICE_CACHE_PATH)
        return True
    except OSError:
        return False


SETUP_CMD = "python scripts/depth_setup.py"



_CACHE = None


def ensure_syspath():
    
    if not os.path.isdir(PYLIBS_DIR):
        return False
    if PYLIBS_DIR in sys.path[:1]:
        return True
    if PYLIBS_DIR in sys.path:
        sys.path.remove(PYLIBS_DIR)
    sys.path.insert(0, PYLIBS_DIR)
    importlib.invalidate_caches()
    return True


def sha256_of(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def probe(use_cache=True):
    
    global _CACHE
    if use_cache and _CACHE is not None:
        return _CACHE

    missing = []
    out = {
        "ok": False,
        "missing": missing,
        "py": None,
        "py_error": None,
        "providers": [],
        "candidates": [],
        "accel": False,
        "pack": "",
        "model_bytes": 0,
        "hash_ok": False,
        "model_path": MODEL_PATH,
        "pylibs_dir": PYLIBS_DIR,
        "setup_cmd": SETUP_CMD,
        "reason": "",
    }


    ensure_syspath()
    try:
        ort = importlib.import_module("onnxruntime")
        out["py"] = getattr(ort, "__version__", "?")
        try:
            out["providers"] = list(ort.get_available_providers())
        except Exception:
            out["providers"] = []
        out["accel"] = has_accel(out["providers"])
        out["candidates"] = candidates(out["providers"])
    except Exception as e:
        out["missing"].append("pylibs")
        out["py_error"] = f"{type(e).__name__}: {e}"



    pack = installed_pack()
    out["pack"] = pack
    if not pack:
        missing.append("model")
        out["reason"] = f"深度模型缺失（{SETUP_CMD} 或启动时自动补齐）"
    else:
        files = pack_of(pack)["files"]
        out["model_bytes"] = sum(sz for _, sz, _ in files)
        for fn, size, sha in files:
            fp = os.path.join(MODEL_DIR, fn)
            try:
                n = os.path.getsize(fp)
            except OSError as e:
                missing.append("model")
                out["reason"] = f"读取深度模型失败：{e}"
                break
            if n != size:
                missing.append("model")
                out["reason"] = (f"深度模型大小不符（{fn} {n} != {size}，疑为下载中断；"
                                 f"{SETUP_CMD} 会自动重下）")
                break
            try:
                if sha256_of(fp) != sha:
                    missing.append("model")
                    out["reason"] = f"深度模型校验失败（{fn}；{SETUP_CMD} 会自动重下）"
                    break
            except OSError as e:
                missing.append("model")
                out["py_error"] = out["py_error"] or f"读取模型失败：{e}"
                out["reason"] = f"读取深度模型失败：{e}"
                break
        else:
            out["hash_ok"] = True

    if "pylibs" in missing and not out["reason"]:
        out["reason"] = (f"缺少可选依赖 onnxruntime（{SETUP_CMD}"
                         f"{'：' + out['py_error'] if out['py_error'] else ''}）")

    out["ok"] = not missing
    if out["ok"]:

        tail = f"可加速：{', '.join(out['candidates'])}" if out["candidates"] else "仅 CPU"
        out["reason"] = f"本机可用（onnxruntime {out['py']}，{tail}）"
    _CACHE = out
    return out


def invalidate():
    
    global _CACHE
    _CACHE = None
