#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"

Xvfb "${DISPLAY}" -screen 0 1440x900x24 >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
fluxbox >/tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!
x11vnc -display "${DISPLAY}" -nopw -forever -shared >/tmp/x11vnc.log 2>&1 &
X11VNC_PID=$!

cleanup() {
  kill "${X11VNC_PID}" "${FLUXBOX_PID}" "${XVFB_PID}" >/dev/null 2>&1 || true
}

trap cleanup EXIT

if [[ -n "${START_URL:-}" ]]; then
  python3 - <<'PY'
import os
import subprocess
from pathlib import Path

home = Path.home()
browser_state = home / ".mimo-worker-browser"
browser_state.mkdir(parents=True, exist_ok=True)
subprocess.Popen(
    [
        "python3",
        "-m",
        "playwright",
        "open",
        os.environ["START_URL"],
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
PY
fi

while true; do
  sleep 3600
done
