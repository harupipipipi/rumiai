<!-- docs-i18n-links:start -->
[EN](./computer_seat_runtime.md) | [JP](./i18n/ja/computer_seat_runtime.md) | [KR](./i18n/ko/computer_seat_runtime.md) | [CN](./i18n/zh-cn/computer_seat_runtime.md)
<!-- docs-i18n-links:end -->

# ComputerSeat Runtime – Architecture & Usage

## Overview

ComputerSeat is a modular desktop automation runtime that provides AI agents
with the ability to observe and interact with desktop applications. It uses
a **driver chain** architecture where multiple strategies are tried in
priority order, with automatic fallback when a higher-priority driver fails.

The key design goals are:

1. **Background operation** – interact with apps without stealing focus
2. **Graceful degradation** – work with whatever permissions are available
3. **Audit trail** – every action is logged for traceability
4. **Permission-aware** – high-risk actions require explicit approval
5. **Cross-platform** – Mac fully implemented, Windows skeleton ready

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ComputerSeatService                     │
│  (orchestrator: observe / click / type / key / scroll)   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    DriverRegistry                         │
│  (ordered chain per platform, filters by is_available)   │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────────┐
          ▼              ▼                  ▼
   ┌────────────┐ ┌────────────┐    ┌────────────┐
   │  Driver 1  │ │  Driver 2  │    │  Driver N  │
   │ (highest   │ │ (fallback) │    │ (lowest    │
   │  priority) │ │            │    │  priority) │
   └────────────┘ └────────────┘    └────────────┘
```

### Core Components

| Component | File | Role |
|-----------|------|------|
| `ComputerSeatService` | `service.py` | Orchestrates actions through the driver chain |
| `DriverRegistry` | `registry.py` | Manages driver registration and chain ordering |
| `AuditLogger` | `audit.py` | JSON-lines append-only audit log |
| `permissions` | `permissions.py` | Risk classification and approval checks |
| `models` | `models.py` | Shared dataclasses (ActionResult, ObserveResult, etc.) |

### Data Models

```python
@dataclass
class ComputerTarget:
    app: str | None = None
    pid: int | None = None
    window_id: int | None = None
    window_title: str | None = None

@dataclass
class ActionResult:
    action: str = ""
    driver: str = ""
    executed: bool = False
    confidence: str = "best_effort"
    is_fallback: bool = False
    can_parallel_user_work: bool = False
    notes: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

@dataclass
class ObserveResult:
    platform: str = ""
    target_window: dict = field(default_factory=dict)
    screenshot: dict = field(default_factory=dict)
    ax_tree: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
    recommended_next_actions: list = field(default_factory=list)
    fallback_available: bool = True
```

---

## Driver List

### Mac Drivers

| Driver | Name | Priority | Capabilities |
|--------|------|----------|--------------|
| MacAccessibilityDriver | `mac_accessibility` | 1 (highest) | Semantic actions via AX tree |
| MacAppleEventsDriver | `mac_apple_events` | 2 | Allowlisted AppleScript actions |
| MacCGEventPidDriver | `mac_cgevent_pid` | 3 | Background input via CGEventPostToPid |
| MacForegroundFallbackDriver | `mac_foreground` | 4 (lowest) | Activates app + foreground input |
| MacScreenCaptureDriver | `mac_screen_capture` | — | Observation only (screenshot) |

### Windows Drivers (Skeleton)

| Driver | Name | Priority | Status |
|--------|------|----------|--------|
| WindowsUIADriver | `windows_uia` | 1 | Skeleton – raises NotImplementedError |
| WindowsPostMessageDriver | `windows_postmessage` | 2 | Skeleton – raises NotImplementedError |

---

## Mac Driver Order

The `MAC_DRIVER_ORDER` defines the fallback chain:

```python
MAC_DRIVER_ORDER = [
    "mac_accessibility",    # AX tree – semantic, background, high confidence
    "mac_apple_events",     # AppleScript – allowlisted, background
    "mac_cgevent_pid",      # CGEvent – experimental, background
    "mac_foreground",       # Foreground fallback – always works but steals focus
]
```

When an action is requested:
1. The service gets the chain from the registry (only `is_available()` drivers)
2. Tries each driver in order
3. If a driver returns `executed=False` or raises an exception, moves to next
4. If all fail, returns a failure ActionResult with collected error notes

---

## Mac Helper Modules

### `mac/ax.py` – Accessibility API

Wraps pyobjc `ApplicationServices` for AX tree operations:

- `ax_is_trusted()` – Check if process has Accessibility permission
- `ax_prompt_permission()` – Prompt user for permission
- `ax_list_windows(pid)` – List windows for a PID
- `ax_get_tree(pid, app, window_title, window_id)` – Get full AX tree
- `ax_find_candidates(pid, app, role, title, ...)` – Find matching elements
- `ax_press(element_id)` – Invoke AXPress on an element
- `ax_set_value(pid, app, value, element_id)` – Set element value
- `ax_raise(window_id)` – Raise a window

All functions return empty results on non-macOS or when pyobjc is unavailable.

### `mac/cgevent.py` – CGEvent Injection

Wraps pyobjc `Quartz` for direct event posting:

- `post_click_to_pid(pid, x, y, button)` – Click at coordinates
- `post_key_to_pid(pid, text, key_combo)` – Type text or key combo
- `post_scroll_to_pid(pid, x, y, direction, clicks)` – Scroll
- `cgevent_smoke_test()` – Check API availability

### `mac/screencapture.py` – Window Capture

- `capture_window(window_id, pid, app, output_path)` – Capture screenshot
- `screen_capture_kit_available()` – Check ScreenCaptureKit
- `list_windows()` – List visible windows via CGWindowListCopyWindowInfo

Falls back from ScreenCaptureKit to `screencapture -l <window_id>` CLI.

### `mac/applescript.py` – Safe AppleScript Bridge

Allowlisted AppleScript execution:

- `send_keystroke(app, text)` – Send keystroke to allowlisted app
- `send_key_combo(app, key_combo)` – Send key combination
- `execute_safe_action(app, intent, element)` – Execute allowlisted action
- `get_app_info(app)` – Get app info via System Events
- `get_safari_current_url()` – Get Safari's current URL
- `safari_open_url(url)` – Open URL in Safari
- `finder_reveal(path)` – Reveal file in Finder

Only apps in `_KEYSTROKE_ALLOWLIST` and intents in `_INTENT_ALLOWLIST` are
permitted. All others return `executed=False`.

### `mac/helper.py` – Platform Utilities

- `is_macos()` – Platform check
- `macos_version()` – Get version tuple
- `tcc_accessibility_granted()` – Check TCC Accessibility
- `tcc_screen_recording_granted()` – Check TCC Screen Recording
- `get_frontmost_app()` – Get active app
- `activate_app(app, pid)` – Bring app to foreground
- `restore_app(previous_app)` – Restore previous frontmost app

---

## Usage Examples

### observe

```python
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer import (
    ComputerSeatService, DriverRegistry
)

registry = DriverRegistry()
# Register drivers...
service = ComputerSeatService(registry)

result = service.observe({"app": "Safari"})
# Returns: {
#   "platform": "darwin",
#   "target_window": {"app": "Safari", "pid": 1234},
#   "screenshot": {"path": "...", "data_url": "..."},
#   "ax_tree": {"role": "AXApplication", "children": [...]},
#   "capabilities": {"can_semantic_action": True, ...},
#   "fallback_available": True
# }
```

### semantic_action

```python
result = service.semantic_action(
    {"app": "Safari"},
    intent="press the Downloads button",
)
# Returns: {
#   "action": "semantic_action",
#   "driver": "mac_accessibility",
#   "executed": True,
#   "confidence": "high",
#   "is_fallback": False,
#   "can_parallel_user_work": True,
#   "data": {"element": {...}, "intent": "press the Downloads button"}
# }
```

### pid_event (experimental)

```python
result = service.click(
    {"pid": 1234},
    x=100, y=200
)
# If mac_accessibility can't find an element at (100, 200),
# falls through to mac_cgevent_pid:
# Returns: {
#   "action": "click",
#   "driver": "mac_cgevent_pid",
#   "executed": True,
#   "confidence": "experimental",
#   "is_fallback": True,
#   "notes": ["⚠️ EXPERIMENTAL: CGEventPostToPid click"]
# }
```

### doctor

```python
result = service.doctor()
# Returns: {
#   "platform": "darwin",
#   "available_drivers": [
#     {"name": "mac_accessibility", "available": True, "capabilities": {...}},
#     ...
#   ],
#   "unavailable_drivers": [...],
#   "driver_chain_order": ["mac_accessibility", "mac_apple_events", ...]
# }
```

The `computer_doctor` function extends this with individual permission checks:

```python
# From computer_doctor/main.py:
# Returns: {
#   "platform": "darwin",
#   "checks": [
#     {"name": "accessibility_trusted", "status": "pass", "reason": "..."},
#     {"name": "screen_recording", "status": "warn", "reason": "..."},
#     {"name": "cgevent", "status": "pass", "reason": "..."},
#     {"name": "screen_capture_kit", "status": "warn", "reason": "..."}
#   ],
#   "available_drivers": [...],
#   ...
# }
```

---

## Approval & Audit

### Risk Levels

Actions are classified into three risk levels:

| Level | Actions | Behavior |
|-------|---------|----------|
| `low` | observe, list, screenshot, ax_tree_read | No approval needed |
| `medium` | scroll | No approval needed (currently) |
| `high` | click, type_text, key, semantic_action, ax_press, ax_set_value, post_to_pid | Requires approval |

### Approval Flow

When `requires_approval(action)` returns `True`, the runtime should:
1. Present the action details to the user
2. Wait for explicit confirmation
3. Only then execute through the driver chain

The current implementation records `approval_required` in the audit log.
The actual approval gate is implemented at the API/UI layer above the service.

### Audit Log

Every action (successful or failed) is recorded to `~/.rumi/computer_seat_audit.jsonl`:

```json
{
  "timestamp": 1715000000.0,
  "action": "click",
  "driver": "mac_accessibility",
  "target_app": "Safari",
  "target_pid": 1234,
  "intent": "",
  "selected_element": "",
  "approval_required": true,
  "result": {"action": "click", "driver": "mac_accessibility", "executed": true, ...}
}
```

---

## Function Manifests

Four function endpoints expose ComputerSeat to the AI runtime:

| Function | Description |
|----------|-------------|
| `computer_observe` | Observe target – screenshot + AX tree + capabilities |
| `computer_semantic_action` | Execute semantic action (press button, set value) |
| `computer_pid_event` | Direct CGEvent injection (experimental) |
| `computer_doctor` | Diagnose platform capabilities and permissions |

Each function follows the standard manifest format:
```json
{
  "function_id": "computer_observe",
  "description": "...",
  "calling_convention": "subprocess",
  "host_execution": false,
  "input_schema": {...}
}
```

---

## Windows Skeleton

The Windows implementation provides the same driver interface but is not
yet functional. It exists to:

1. Define the target architecture for Windows support
2. Allow tests to verify the interface contract
3. Enable development of the Windows helpers in parallel

### Windows Helper Modules

| Module | Purpose |
|--------|---------|
| `windows/uia.py` | UI Automation tree operations (stub) |
| `windows/hwnd.py` | Window handle enumeration (stub) |
| `windows/printwindow.py` | PrintWindow screenshot capture (stub) |

### Windows Driver Order

```python
WINDOWS_DRIVER_ORDER = [
    "windows_uia",          # UIA tree – semantic, background
    "windows_postmessage",  # PostMessage – background input injection
]
```

All Windows driver methods currently raise `NotImplementedError`.
The `is_available()` method returns `True` only on `sys.platform == "win32"`.

---

## Graceful Degradation

All helper modules follow the same pattern:

```python
import sys

_AVAILABLE = False
if sys.platform == "darwin":
    try:
        from SomeFramework import SomeAPI
        _AVAILABLE = True
    except ImportError:
        pass

def some_function() -> bool:
    if sys.platform != "darwin" or not _AVAILABLE:
        return False
    # ... actual implementation ...
```

This ensures:
- No `ImportError` on any platform
- Functions return safe defaults (False, empty list, empty dict)
- The driver chain naturally skips unavailable drivers
- Tests can run on any platform without OS-specific dependencies

---

## Directory Structure

```
domain/computer/
├── __init__.py              # Public API exports
├── models.py                # Shared dataclasses
├── service.py               # ComputerSeatService orchestrator
├── registry.py              # DriverRegistry + platform orders
├── audit.py                 # AuditLogger (JSON-lines)
├── permissions.py           # Risk levels + approval checks
├── drivers/
│   ├── __init__.py          # Driver exports
│   ├── base.py              # ComputerDriver ABC
│   ├── mac_accessibility.py # AX tree driver
│   ├── mac_apple_events.py  # AppleScript driver
│   ├── mac_cgevent_pid.py   # CGEvent injection driver
│   ├── mac_foreground.py    # Foreground fallback driver
│   ├── mac_screen_capture.py# Screenshot-only driver
│   ├── local_visible.py     # Local visible desktop driver
│   ├── windows_uia.py       # Windows UIA skeleton
│   └── windows_postmessage.py # Windows PostMessage skeleton
├── mac/
│   ├── __init__.py          # Mac helpers docstring
│   ├── helper.py            # Platform utils (TCC, app mgmt)
│   ├── ax.py                # Accessibility API wrappers
│   ├── cgevent.py           # CGEvent wrappers
│   ├── screencapture.py     # ScreenCaptureKit + CLI
│   └── applescript.py       # Safe AppleScript bridge
└── windows/
    ├── __init__.py          # Windows helpers docstring
    ├── uia.py               # UIA stubs
    ├── hwnd.py              # HWND stubs
    └── printwindow.py       # PrintWindow stub
```

---

## Testing

Tests are in `rumi_ai_1_10/tests/` and use mock drivers to run on any platform:

| Test File | Coverage |
|-----------|----------|
| `test_computer_seat_service.py` | Service observe/click/type_text with mocks |
| `test_computer_driver_registry.py` | Registry ordering and filtering |
| `test_computer_fallback_order.py` | Fallback chain behavior |
| `test_browser_computer_compat.py` | Existing computer_use smoke test |
| `test_windows_driver_skeleton.py` | Windows driver interface contract |
| `test_mac_accessibility_driver.py` | Mac AX driver instantiation |
| `test_mac_cgevent_pid_driver.py` | CGEvent driver PID requirement |

Run all tests:
```bash
cd rumi_ai_1_10
python -m pytest tests/test_computer_*.py tests/test_mac_*.py tests/test_windows_*.py tests/test_browser_computer_compat.py -v
```

---

## Future Work

- [ ] Implement Windows UIA driver with comtypes/pywinauto
- [ ] Implement Windows PrintWindow capture
- [ ] Add ScreenCaptureKit native capture (currently CLI-only)
- [ ] Add approval gate middleware in the API layer
- [ ] Add element caching for repeated semantic actions
- [ ] Add coordinate normalization between window/screen space
- [ ] Add multi-monitor support for Mac foreground driver
