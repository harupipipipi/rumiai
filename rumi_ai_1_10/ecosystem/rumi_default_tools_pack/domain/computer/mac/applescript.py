"""Safe AppleScript bridge for macOS.

All actions are allowlisted. Only permitted app/intent combinations
are executed. Uses subprocess with timeout to prevent hangs.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

# Allowlisted apps for keystroke/key_combo
_KEYSTROKE_ALLOWLIST: set[str] = {
    "Safari",
    "Google Chrome",
    "Firefox",
    "Terminal",
    "TextEdit",
    "Notes",
    "Finder",
    "Mail",
    "Messages",
    "Slack",
    "Visual Studio Code",
    "Code",
    "Xcode",
}

# Allowlisted intents for execute_safe_action
_INTENT_ALLOWLIST: dict[str, set[str]] = {
    "Safari": {"get_url", "open_url", "get_tab_list", "switch_tab"},
    "Google Chrome": {"get_url", "open_url", "get_tab_list", "switch_tab"},
    "Firefox": {"get_url", "open_url"},
    "Finder": {"reveal", "get_selection", "open_folder"},
    "Terminal": {"run_command"},
    "TextEdit": {"get_text", "set_text"},
    "Notes": {"get_text"},
    "Mail": {"get_selected_message"},
}


def send_keystroke(app: str, text: str) -> bool:
    """Insert text into an app via paste to avoid keyboard layout drift."""
    if sys.platform != "darwin":
        return False
    if app not in _KEYSTROKE_ALLOWLIST:
        return False
    script = f"""
on run argv
set rumiPasteText to item 1 of argv
set rumiOriginalClipboard to missing value
set rumiHadClipboard to false
tell application "{_escape(app)}" to activate
try
  set rumiOriginalClipboard to the clipboard
  set rumiHadClipboard to true
end try
try
  set the clipboard to rumiPasteText
  delay 0.05
  tell application "System Events" to keystroke "v" using {{command down}}
  delay 0.05
on error pasteErrorMessage number pasteErrorNumber
  if rumiHadClipboard then
    set the clipboard to rumiOriginalClipboard
  else
    set the clipboard to ""
  end if
  error pasteErrorMessage number pasteErrorNumber
end try
if rumiHadClipboard then
  set the clipboard to rumiOriginalClipboard
else
  set the clipboard to ""
end if
end run
"""
    return _run_osascript(script, [text])


def send_key_combo(app: str, key_combo: str) -> bool:
    """Send a key combination to an app via AppleScript."""
    if sys.platform != "darwin":
        return False
    if app not in _KEYSTROKE_ALLOWLIST:
        return False
    parts = [p.strip() for p in key_combo.split("+")]
    key = parts[-1] if parts else ""
    modifiers = parts[:-1] if len(parts) > 1 else []
    modifier_map = {
        "cmd": "command down",
        "command": "command down",
        "ctrl": "control down",
        "control": "control down",
        "alt": "option down",
        "option": "option down",
        "shift": "shift down",
    }
    using = ", ".join(modifier_map.get(m.lower(), "") for m in modifiers if m.lower() in modifier_map)
    script = f'tell application "{app}" to activate\n'
    if using:
        script += f'tell application "System Events" to key code {_key_code(key)} using {{{using}}}'
    else:
        script += f'tell application "System Events" to keystroke "{_escape(key)}"'
    return _run_osascript(script)


def execute_safe_action(
    app: str, intent: str, element: dict | None = None
) -> dict:
    """Execute an allowlisted action on an app."""
    if sys.platform != "darwin":
        return {"executed": False, "error": "Not macOS"}
    allowed = _INTENT_ALLOWLIST.get(app, set())
    if intent not in allowed:
        return {"executed": False, "error": f"Intent '{intent}' not allowed for '{app}'"}

    if app == "Safari" and intent == "get_url":
        url = get_safari_current_url()
        return {"executed": True, "result": url}
    if app == "Safari" and intent == "open_url":
        url = (element or {}).get("url", "")
        ok = safari_open_url(url)
        return {"executed": ok, "result": url}
    if app == "Finder" and intent == "reveal":
        path = (element or {}).get("path", "")
        ok = finder_reveal(path)
        return {"executed": ok, "result": path}

    return {"executed": False, "error": f"Intent '{intent}' handler not implemented"}


def get_app_info(app: str) -> dict:
    """Get basic info about a running app."""
    if sys.platform != "darwin":
        return {}
    script = f"""
tell application "System Events"
    if exists (application process "{app}") then
        set p to application process "{app}"
        return {{name of p, frontmost of p, count of windows of p}}
    end if
end tell
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return {"app": app, "raw": result.stdout.strip()}
        return {"app": app, "error": result.stderr.strip()}
    except Exception as e:
        return {"app": app, "error": str(e)}


def get_safari_current_url() -> str | None:
    """Get the current URL from Safari."""
    if sys.platform != "darwin":
        return None
    script = 'tell application "Safari" to return URL of current tab of front window'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except Exception:
        return None


def safari_open_url(url: str) -> bool:
    """Open a URL in Safari."""
    if sys.platform != "darwin":
        return False
    if not url:
        return False
    script = f'tell application "Safari" to open location "{_escape(url)}"'
    return _run_osascript(script)


def finder_reveal(path: str) -> bool:
    """Reveal a file/folder in Finder."""
    if sys.platform != "darwin":
        return False
    if not path:
        return False
    script = f'tell application "Finder" to reveal POSIX file "{_escape(path)}"'
    return _run_osascript(script)


# --- internal helpers ---


def _run_osascript(script: str, args: list[str] | None = None) -> bool:
    """Run an osascript and return success."""
    command = ["osascript", "-e", script]
    if args:
        command.extend(["--", *args])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _escape(s: str) -> str:
    """Escape a string for AppleScript."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _key_code(key: str) -> str:
    """Map a key name to an AppleScript key code number."""
    codes: dict[str, int] = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "delete": 51, "escape": 53, "esc": 53,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3,
        "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37,
        "m": 46, "n": 45, "o": 31, "p": 35, "q": 12, "r": 15,
        "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7,
        "y": 16, "z": 6,
    }
    return str(codes.get(key.lower(), 0))
