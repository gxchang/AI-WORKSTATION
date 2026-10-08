



import base64
import glob
import os
import shutil
import subprocess
import sys
import tempfile

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PROBE_NAME = "启动器实测-中文名.png"

def emit(key, value):
    print("%s=%s" % (key, value), flush=True)


def find_python():
    
    cands = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_py = os.path.join(root, "venv", "Scripts" if IS_WIN else "bin", "python" + EXE)
    if os.path.exists(venv_py):
        cands.append(venv_py)
    for name in (["python", "python3"] if not IS_WIN else ["python", "py"]):
        p = shutil.which(name)
        if p:
            cands.append(p)

    if IS_WIN:
        try:
            out = subprocess.run(["where", "python"], capture_output=True, text=True).stdout
            cands += [l.strip() for l in out.splitlines() if l.strip()]
        except Exception:
            pass

        home = os.environ.get("USERPROFILE", "")
        globs = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python3*", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Python3*", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Python3*", "python.exe"),
            os.path.join(home, "miniconda3", "python.exe"),
            os.path.join(home, "anaconda3", "python.exe"),
            os.path.join(home, ".conda", "envs", "*", "python.exe"),
            os.path.join(home, ".workbuddy", "binaries", "python", "envs", "*", "Scripts", "python.exe"),
            os.path.join(home, ".workbuddy", "binaries", "python", "versions", "*", "python.exe"),
        ]
        for g in globs:
            cands += sorted(glob.glob(g))
    seen = set()
    for c in cands:
        c = os.path.normpath(c)
        if c.lower() in seen or not os.path.exists(c):
            continue
        seen.add(c.lower())
        try:
            r = subprocess.run([c, "-c", "import flask, requests, PIL"],
                               capture_output=True, timeout=20)
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return None


def candidate_dirs():
    
    out, seen = [], set()

    def add(p):
        if not p:
            return
        p = os.path.normpath(os.path.expandvars(os.path.expanduser(p)))
        if os.path.isdir(p) and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)


    env = (os.environ.get("FFMPEG_PATH") or "").strip()
    if env:
        add(os.path.dirname(env) if env.lower().endswith(EXE) else env)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    add(os.path.join(root, "bin"))


    w = shutil.which("ffmpeg")
    if w:
        add(os.path.dirname(w))

    if IS_WIN:
        pf = [os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
              os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramData", "")]
        vendor_globs = [
            r"Krita*\bin", r"JianyingPro*\*", r"CapCut*\*", r"OBS Studio\bin\64bit",
            r"Shotcut\*", r"HandBrake\*", r"ffmpeg*\bin", r"Wondershare*\*",
            r"Programs\*\bin", r"Microsoft\WinGet\Links", r"chocolatey\bin",
        ]
        for base in filter(None, pf):
            for g in vendor_globs:
                for hit in glob.glob(os.path.join(base, g)):
                    add(hit)
        for extra in (r"scoop\shims", r"scoop\apps\ffmpeg\current\bin",
                      r"miniconda3\Library\bin", r"anaconda3\Library\bin",
                      r"miniconda3\Scripts", r"anaconda3\Scripts"):
            add(os.path.join(os.environ.get("USERPROFILE", ""), extra))
    else:
        for d in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/snap/bin", "/opt/local/bin"):
            add(d)

    return out

def probe(d):
    
    ff = os.path.join(d, "ffmpeg" + EXE)
    fp = os.path.join(d, "ffprobe" + EXE)
    if not os.path.exists(ff):
        return False, "no-ffmpeg"
    if not os.path.exists(fp):
        return False, "no-ffprobe"
    tmp = tempfile.mkdtemp(prefix="ffcheck_")
    try:
        src = os.path.join(tmp, PROBE_NAME)
        dst = os.path.join(tmp, "输出-中文名.jpg")
        with open(src, "wb") as f:
            f.write(PNG_1PX)
        r1 = subprocess.run([ff, "-v", "error", "-y", "-i", src, dst],
                            capture_output=True, timeout=60)
        if r1.returncode != 0 or not os.path.exists(dst):
            return False, "cannot-open-non-ascii-name"
        r2 = subprocess.run([fp, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width", "-of", "csv=p=0", src],
                            capture_output=True, timeout=60)
        if r2.returncode != 0:
            return False, "ffprobe-failed"
        return True, "ok"
    except Exception as e:
        return False, "error:%s" % type(e).__name__
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    py = find_python()
    if py:
        emit("PYTHON", py)
        emit("PYDIR", os.path.dirname(py))

    bad_dir, bad_note = None, None
    for d in candidate_dirs():
        ok, note = probe(d)
        if ok:
            emit("FFDIR", d)
            emit("FFNOTE", "probe-passed")
            return 0
        if bad_dir is None and note in ("cannot-open-non-ascii-name", "ffprobe-failed", "no-ffprobe"):
            bad_dir, bad_note = d, note
    if bad_dir:
        emit("FFDIR_BAD", bad_dir)
        emit("FFNOTE", bad_note)
    else:
        emit("FFNOTE", "not-found")
    return 1

if __name__ == "__main__":
    sys.exit(main())
