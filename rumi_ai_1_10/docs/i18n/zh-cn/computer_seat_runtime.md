<!-- docs-i18n-links:start -->
[EN](../../computer_seat_runtime.md) | [JP](../ja/computer_seat_runtime.md) | [KR](../ko/computer_seat_runtime.md) | [CN](./computer_seat_runtime.md)
<!-- docs-i18n-links:end -->

# ComputerSeat 运行时 – 架构和使用

## 概述

ComputerSeat 是一个模块化桌面自动化运行时，提供 AI 代理
具有观察桌面应用程序并与之交互的能力。它使用
尝试多种策略的 **驱动链** 架构
优先级顺序，当较高优先级的驱动程序发生故障时自动回退。

主要设计目标是：

1. **后台操作** – 与应用程序交互而不窃取焦点
2. **优雅降级** – 使用任何可用权限
3. **审核跟踪** – 每个操作都会被记录以供追踪
4. **权限意识** – 高风险行为需要明确批准
5. **跨平台** – Mac 完全实现，Windows 框架就绪

---

## 架构

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

### 核心组件

|组件|文件|角色 |
|-----------|------|------|
| `ComputerSeatService`| `service.py` |通过驱动链协调行动 |
| `DriverRegistry`| `registry.py` |管理司机注册和连锁订购 |
| `AuditLogger`| `audit.py` | JSON 行仅附加审核日志 |
| `permissions`| `permissions.py` |风险分类和审批检查|
| `models`| `models.py` |共享数据类（ActionResult、ObserveResult 等）|

### 数据模型

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

## 驱动程序列表

### Mac 驱动程序

|司机 |名称 |优先|能力|
|--------|------|----------|--------------|
| Mac 辅助功能驱动程序 | `mac_accessibility`| 1（最高）|通过 AX 树进行语义操作 |
| MacAppleEvents 驱动程序 | `mac_apple_events`| 2 |列入白名单的 AppleScript 操作 |
| MacCGEventPidDriver | MacCGEventPidDriver | MacCGEventPidDriver `mac_cgevent_pid`| 3 |通过 CGEventPostToPid 后台输入 |
| MacForegroundFallbackDriver | MacForegroundFallbackDriver | MacForegroundFallbackDriver | MacForegroundFallbackDriver `mac_foreground`| 4（最低）|激活应用程序+前台输入 |
| MacScreenCapture 驱动程序 | `mac_screen_capture`| — |仅观察（截图）|

### Windows 驱动程序（骨架）

|司机 |名称 |优先|状态 |
|--------|------|----------|--------|
| WindowsUIA 驱动程序 | `windows_uia`| 1 |骨架 – 引发 NotImplementedError |
| WindowsPostMessageDriver | WindowsPostMessageDriver | `windows_postmessage`| 2 |骨架 – 引发 NotImplementedError |

---

## Mac 驱动程序命令

`MAC_DRIVER_ORDER` 定义了后备链：

```python
MAC_DRIVER_ORDER = [
    "mac_accessibility",    # AX tree – semantic, background, high confidence
    "mac_apple_events",     # AppleScript – allowlisted, background
    "mac_cgevent_pid",      # CGEvent – experimental, background
    "mac_foreground",       # Foreground fallback – always works but steals focus
]
```

当请求执行操作时：
1.服务从注册表获取链（仅限`is_available()`驱动程序）
2. 按顺序尝试每个驱动程序
3. 如果驱动程序返回`executed=False`或提出异常，则转到下一个
4.如果全部失败，则返回失败ActionResult，并带有收集的错误注释

---

## Mac 帮助模块

### `mac/ax.py` – 辅助功能 API

包装 pyobjc `ApplicationServices` 以进行 AX 树操作：

- `ax_is_trusted()` – 检查进程是否具有辅助功能权限
- `ax_prompt_permission()` – 提示用户许可
- `ax_list_windows(pid)` – 列出 PID 的窗口
- `ax_get_tree(pid, app, window_title, window_id)` – 获取完整的 AX 树
- `ax_find_candidates(pid, app, role, title, ...)` – 查找匹配元素
- `ax_press(element_id)` – 在元素上调用 AXPress
- `ax_set_value(pid, app, value, element_id)` – 设置元素值
- `ax_raise(window_id)` – 升起窗户

在非 macOS 上或当 pyobjc 不可用时，所有函数都会返回空结果。

### `mac/cgevent.py` – CGEvent 注入

包装 pyobjc `Quartz` 以直接发布事件：

- `post_click_to_pid(pid, x, y, button)` – 单击坐标
- `post_key_to_pid(pid, text, key_combo)` – 输入文本或组合键
- `post_scroll_to_pid(pid, x, y, direction, clicks)` – 卷轴
- `cgevent_smoke_test()` – 检查 API 可用性

### `mac/screencapture.py` – 窗口捕获

- `capture_window(window_id, pid, app, output_path)` – 捕获屏幕截图
- `screen_capture_kit_available()` – 检查 ScreenCaptureKit
- `list_windows()` – 通过 CGWindowListCopyWindowInfo 列出可见窗口

从 ScreenCaptureKit 回退到 `screencapture -l <window_id>` CLI。

### `mac/applescript.py` – 安全 AppleScript 桥

列入白名单的 AppleScript 执行：

- `send_keystroke(app, text)` – 将击键发送到列入白名单的应用程序
- `send_key_combo(app, key_combo)` – 发送组合键
- `execute_safe_action(app, intent, element)` – 执行列入许可名单的操作
- `get_app_info(app)` – 通过系统事件获取应用程序信息
- `get_safari_current_url()` – 获取 Safari 的当前 URL
- `safari_open_url(url)` – 在 Safari 中打开 URL
- `finder_reveal(path)` – 在 Finder 中显示文件

仅`_KEYSTROKE_ALLOWLIST`中的应用程序和`_INTENT_ALLOWLIST`中的意图
允许的。所有其他人返回`executed=False`。

### `mac/helper.py` – 平台实用程序

- `is_macos()` – 平台检查
- `macos_version()` – 获取版本元组
- `tcc_accessibility_granted()` – 检查 TCC 辅助功能
- `tcc_screen_recording_granted()` – 检查 TCC 屏幕录制
- `get_frontmost_app()` – 获取活跃的应用程序
- `activate_app(app, pid)` – 将应用程序带到前台
- `restore_app(previous_app)` – 恢复之前最前面的应用程序

---

## 用法示例

### 观察

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

### 语义动作

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

### pid_event（实验）

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

### 医生

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

`computer_doctor` 函数通过单独的权限检查扩展了此功能：

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

## 批准与审核

### 风险级别

操作分为三个风险级别：

|水平|行动|行为 |
|-------|---------|----------|
| `low`|观察、列表、屏幕截图、ax_tree_read |无需批准 |
| `medium`|滚动|无需批准（目前）|
| `high`|单击、type_text、key、semantic_action、ax_press、ax_set_value、post_to_pid |需要批准 |

### 审批流程

当`requires_approval(action)`返回`True`时，运行时应该：
1. 向用户呈现操作细节
2.等待明确确认
3.然后通过驱动链执行

当前的实现在审核日志中记录`approval_required`。
实际的批准门是在服务之上的 API/UI 层实现的。

### 审核日志

每个操作（成功或失败）都会记录到`~/.rumi/computer_seat_audit.jsonl`：

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

## 函数清单

四个函数端点将 ComputerSeat 暴露给 AI 运行时：

|功能|描述 |
|----------|-------------|
| `computer_observe`|观察目标——截图+AX树+能力|
| `computer_semantic_action`|执行语义动作（按下按钮，设置值）|
| `computer_pid_event`|直接CGEvent注入（实验性）|
| `computer_doctor`|诊断平台能力和权限 |

每个函数都遵循标准清单格式：
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

## Windows 骨架

Windows 实现提供了相同的驱动程序接口，但不是
但功能齐全。它的存在是为了：

1. 定义Windows支持的目标架构
2.允许测试来验证接口契约
3. 启用 Windows 助手的并行开发

### Windows 帮助程序模块

|模块|目的|
|--------|---------|
| `windows/uia.py`| UI 自动化树操作（存根）|
| `windows/hwnd.py`|窗口句柄枚举（存根）|
| `windows/printwindow.py`| PrintWindow 屏幕截图捕获（存根）|

### Windows 驱动程序顺序

```python
WINDOWS_DRIVER_ORDER = [
    "windows_uia",          # UIA tree – semantic, background
    "windows_postmessage",  # PostMessage – background input injection
]
```

当前所有 Windows 驱动程序方法都会引发`NotImplementedError`。
`is_available()` 方法仅在`sys.platform == "win32"` 上返回`True`。

---

## 优雅降级

所有辅助模块都遵循相同的模式：

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

这可以确保：
- 任何平台上均无`ImportError`
- 函数返回安全默认值（False、空列表、空字典）
- 驱动程序链自然地跳过不可用的驱动程序
- 测试可以在任何平台上运行，无需特定于操作系统的依赖性

---

## 目录结构

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

## 测试

测试在`rumi_ai_1_10/tests/`中进行，并使用模拟驱动程序在任何平台上运行：

|测试文件|覆盖范围|
|-----------|----------|
| `test_computer_seat_service.py`|使用模拟服务观察/点击/输入文本 |
| `test_computer_driver_registry.py`|注册表排序和过滤|
| `test_computer_fallback_order.py`|后备链行为 |
| `test_browser_computer_compat.py`|现有电脑_使用冒烟测试|
| `test_windows_driver_skeleton.py`| Windows驱动接口合约|
| `test_mac_accessibility_driver.py`| Mac AX 驱动程序实例化 |
| `test_mac_cgevent_pid_driver.py`| CGEvent 驱动程序 PID 要求 |

运行所有测试：
```bash
cd rumi_ai_1_10
python -m pytest tests/test_computer_*.py tests/test_mac_*.py tests/test_windows_*.py tests/test_browser_computer_compat.py -v
```

---

## 未来的工作

- [ ] 使用 comtypes/pywinauto 实现 Windows UIA 驱动程序
- [ ] 实现 Windows PrintWindow 捕获
- [ ] 添加 ScreenCaptureKit 本机捕获（当前仅限 CLI）
- [ ] API层添加审批门中间件
- [ ] 为重复的语义动作添加元素缓存
- [ ] 添加窗口/屏幕空间之间的坐标标准化
- [ ] 添加Mac前台驱动的多显示器支持
