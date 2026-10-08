#!/usr/bin/env bash

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/server.py" ]; then
  APP="$HERE"
elif [ -f "$HERE/../server.py" ]; then
  APP="$(cd "$HERE/.." && pwd)"
else
  echo "[ERROR] server.py was not found next to this script or one level up."
  exit 1
fi
cd "$APP"
PORT="${PORT:-5000}"
URL="http://127.0.0.1:${PORT}/"
WANT_DL=0
[ "${1:-}" = "--get-ffmpeg" ] && WANT_DL=1

echo "============================================================"
echo "  AI WORKSTATION - launcher"
echo "  project: $APP"
echo "============================================================"

open_browser() {
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  else echo "  Open this URL manually: $URL"; fi
}

if curl -s -o /dev/null --max-time 3 "${URL}api/config" 2>/dev/null; then
  echo "[OK] Service is already running - opening browser."
  open_browser
  exit 0
fi

PROBE=""
try_python() {
  [ -n "$PROBE" ] && return 0
  [ -z "$1" ] && return 0
  command -v "$1" >/dev/null 2>&1 || return 0
  "$1" -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' >/dev/null 2>&1 && PROBE="$1"
  return 0
}
try_python python3
try_python python

if [ -z "$PROBE" ] && [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
  echo "[1/5] No Python found - installing it via Homebrew (one-time step)..."
  brew install python >/dev/null 2>&1 || true
  for d in /opt/homebrew/bin /usr/local/bin; do
    if [ -z "$PROBE" ] && [ -x "$d/python3" ]; then
      "$d/python3" -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' >/dev/null 2>&1 && PROBE="$d/python3"
    fi
  done
fi

if [ -z "$PROBE" ]; then
  echo "[ERROR] No working Python 3.10+ was found on this machine."
  echo "  macOS : brew install python"
  echo "  Linux : sudo apt install python3 python3-venv   (or your distro's equivalent)"
  echo "  Then run this script again - it only needs doing once."
  exit 1
fi

PYTHON=""; FFDIR=""; FFDIR_BAD=""; FFNOTE=""
while IFS='=' read -r k v; do
  case "$k" in
    PYTHON)    PYTHON="$v" ;;
    FFDIR)     FFDIR="$v" ;;
    FFDIR_BAD) FFDIR_BAD="$v" ;;
    FFNOTE)    FFNOTE="$v" ;;
  esac
done < <("$PROBE" "$HERE/env_probe.py" 2>/dev/null || true)

if [ -n "$PYTHON" ]; then
  PYBIN="$PYTHON"
  echo "[1/5] Python OK (using the environment already on this machine)"
  echo "[2/5] Dependencies OK (already installed - nothing to do)"
  echo "[3/5] Dependencies OK"
else
  echo "[1/5] Python: $("$PROBE" -c 'import sys;print(sys.version.split()[0])')"
  PYBIN="$APP/venv/bin/python"
  if [ ! -x "$PYBIN" ]; then
    echo "[2/5] Creating virtual environment (first run only)..."
    "$PROBE" -m venv venv || { echo "[ERROR] venv failed (Debian/Ubuntu: sudo apt install python3-venv)"; exit 1; }
  else
    echo "[2/5] Virtual environment OK"
  fi
  if ! "$PYBIN" -c 'import flask' >/dev/null 2>&1; then
    echo "[3/5] Installing dependencies (first run only, needs network)..."
    "$PYBIN" -m pip install --upgrade pip --quiet
    "$PYBIN" -m pip install -r requirements.txt || {
      echo "[ERROR] pip install failed. Try: $PYBIN -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
      exit 1
    }
  else
    echo "[3/5] Dependencies OK"
  fi
fi

if [ -x "bin/ffmpeg" ]; then
  echo "[4/5] ffmpeg OK (project bin/)"
elif [ -n "$FFDIR" ]; then
  export FFMPEG_PATH="$FFDIR" FFPROBE="$FFDIR/ffprobe"
  echo "[4/5] ffmpeg OK (yours: $FFDIR)"
elif [ -n "$FFDIR_BAD" ] && [ "$WANT_DL" = "0" ]; then
  export FFMPEG_PATH="$FFDIR_BAD" FFPROBE="$FFDIR_BAD/ffprobe"
  echo "[4/5] ffmpeg: using the build already on this machine: $FFDIR_BAD"
  echo "[WARN] Self-test note ($FFNOTE): it cannot handle non-ASCII file names,"
  echo "  so thumbnails / duration probing / rendering of such files may fail."
  echo "  Re-run with --get-ffmpeg to fetch an official build instead."
else
  echo "[4/5] No ffmpeg on this machine - trying to fetch an official build..."
  mkdir -p bin
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg >/dev/null 2>&1 || true
    command -v ffmpeg >/dev/null 2>&1 && echo "[4/5] ffmpeg OK (homebrew)"
  fi
  if [ ! -x "bin/ffmpeg" ] && ! command -v ffmpeg >/dev/null 2>&1; then
    TMP="$(mktemp -d)"
    if curl -fsSL --max-time 600 "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -o "$TMP/ff.tar.xz" \
       && tar -xJf "$TMP/ff.tar.xz" -C "$TMP" 2>/dev/null; then
      find "$TMP" -name ffmpeg -type f -exec cp {} bin/ffmpeg \; 2>/dev/null
      find "$TMP" -name ffprobe -type f -exec cp {} bin/ffprobe \; 2>/dev/null
      chmod +x bin/ffmpeg bin/ffprobe 2>/dev/null
    fi
    rm -rf "$TMP"
  fi
  if [ -x "bin/ffmpeg" ] || command -v ffmpeg >/dev/null 2>&1; then
    echo "[4/5] ffmpeg OK"
  else
    echo "[WARN] ffmpeg still missing. The service starts anyway; only video"
    echo "  composing / frame grabbing will be unavailable. Fix later by putting"
    echo "  ffmpeg + ffprobe into: $APP/bin/   (or set FFMPEG_PATH / FFPROBE)"
  fi
fi

echo "[5/5] Starting service on port ${PORT} ..."
"$PYBIN" server.py &
SRV=$!
for _ in $(seq 1 40); do
  if curl -s -o /dev/null --max-time 2 "${URL}api/config" 2>/dev/null; then
    echo "[OK] Service is up: $URL"
    open_browser
    echo "Press Ctrl+C to stop the service."
    wait "$SRV"
    exit 0
  fi
  sleep 1
done
echo "[WARN] The service did not answer within 40 seconds - check the log above."
exit 1
