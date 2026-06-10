<!-- docs-i18n-links:start -->
[EN](../../computer_seat_runtime.md) | [JP](../ja/computer_seat_runtime.md) | [KR](./computer_seat_runtime.md) | [CN](../zh-cn/computer_seat_runtime.md)
<!-- docs-i18n-links:end -->

# ComputerSeat 런타임 – 아키텍처 및 사용

## 개요

ComputerSeat는 AI 에이전트를 제공하는 모듈식 데스크탑 자동화 런타임입니다.
데스크탑 애플리케이션을 관찰하고 상호 작용할 수 있는 능력을 갖추고 있습니다. 그것은 사용한다
여러 전략이 시도되는 **드라이버 체인** 아키텍처
우선순위가 높은 드라이버가 실패할 경우 자동으로 대체되는 우선순위 순서입니다.

주요 설계 목표는 다음과 같습니다.

1. **백그라운드 작업** - 포커스를 빼앗지 않고 앱과 상호작용
2. **우아한 성능 저하** – 사용 가능한 모든 권한으로 작업
3. **감사 추적** – 추적성을 위해 모든 작업이 기록됩니다.
4. **권한 인식** – 위험도가 높은 작업에는 명시적인 승인이 필요합니다.
5. **크로스 플랫폼** – Mac이 완벽하게 구현되고 Windows 뼈대가 준비됨

---

## 아키텍처

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

### 핵심 구성 요소

| 구성요소 | 파일 | 역할 |
|-----------|------|------|
| §루미§0§ | §루미§1§ | 드라이버 체인을 통해 작업 조율 |
| §루미§0§ | §루미§1§ | 운전자 등록 및 체인 주문 관리 |
| §루미§0§ | §루미§1§ | JSON 라인 추가 전용 감사 로그 |
| §루미§0§ | §루미§1§ | 위험 분류 및 승인 확인 |
| §루미§0§ | §루미§1§ | 공유 데이터 클래스(ActionResult, ObserveResult 등) |

### 데이터 모델

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

## 드라이버 목록

### Mac 드라이버

| 드라이버 | 이름 | 우선순위 | 기능 |
|--------|------|----------|--------------|
| Mac접근성드라이버 | §루미§0§ | 1(가장 높음) | AX 트리를 통한 의미적 동작 |
| MacApple이벤트드라이버 | §루미§0§ | 2 | 허용된 AppleScript 작업 |
| MacCGEventPidDriver | §루미§0§ | 3 | CGEventPostToPid를 통한 백그라운드 입력 |
| MacForegroundFallback드라이버 | §루미§0§ | 4(최저) | 앱 + 포그라운드 입력 활성화 |
| MacScreenCapture드라이버 | §루미§0§ | — | 관찰 전용(스크린샷) |

### Windows 드라이버(스켈레톤)

| 드라이버 | 이름 | 우선순위 | 상태 |
|--------|------|----------|--------|
| WindowsUIA드라이버 | §루미§0§ | 1 | 스켈레톤 – NotImplementedError 발생 |
| WindowsPostMessageDriver | §루미§0§ | 2 | 스켈레톤 – NotImplementedError 발생 |

---

## Mac 드라이버 주문

`MAC_DRIVER_ORDER`은 대체 체인을 정의합니다.

```python
MAC_DRIVER_ORDER = [
    "mac_accessibility",    # AX tree – semantic, background, high confidence
    "mac_apple_events",     # AppleScript – allowlisted, background
    "mac_cgevent_pid",      # CGEvent – experimental, background
    "mac_foreground",       # Foreground fallback – always works but steals focus
]
```

작업이 요청되는 경우:
1. 서비스는 레지스트리에서 체인을 가져옵니다(`is_available()` 드라이버만 해당).
2. 각 드라이버를 순서대로 시도합니다.
3. 운전자가 `executed=False`을 반환하거나 예외를 제기하면 다음으로 이동합니다.
4. 모두 실패하면 수집된 오류 메모와 함께 실패 ActionResult를 반환합니다.

---

## Mac 도우미 모듈

### `mac/ax.py` – 접근성 API

AX 트리 작업을 위해 pyobjc `ApplicationServices`을 래핑합니다.

- `ax_is_trusted()` – 프로세스에 접근성 권한이 있는지 확인
- `ax_prompt_permission()` – 사용자에게 허가를 요청합니다.
- `ax_list_windows(pid)` – PID에 대한 목록 창
- `ax_get_tree(pid, app, window_title, window_id)` – 전체 AX 트리 얻기
- `ax_find_candidates(pid, app, role, title, ...)` – 일치하는 요소 찾기
- `ax_press(element_id)` – 요소에 대해 AXPress 호출
- `ax_set_value(pid, app, value, element_id)` – 요소 값 설정
- `ax_raise(window_id)` – 창 올리기

macOS가 아니거나 pyobjc를 사용할 수 없는 경우 모든 함수는 빈 결과를 반환합니다.

### `mac/cgevent.py` – CGEvent 주입

직접 이벤트 게시를 위해 pyobjc `Quartz`를 래핑합니다.

- `post_click_to_pid(pid, x, y, button)` – 좌표 클릭
- `post_key_to_pid(pid, text, key_combo)` – 텍스트 또는 키 콤보 입력
- `post_scroll_to_pid(pid, x, y, direction, clicks)` – 스크롤
- `cgevent_smoke_test()` – API 가용성 확인

### `mac/screencapture.py` – 창 캡처

- `capture_window(window_id, pid, app, output_path)` – 스크린샷 캡처
- `screen_capture_kit_available()` – ScreenCaptureKit 확인
- `list_windows()` – CGWindowListCopyWindowInfo를 통해 표시되는 창 나열

ScreenCaptureKit에서 `screencapture -l <window_id>` CLI로 대체됩니다.

### `mac/applescript.py` – 안전한 AppleScript 브리지

허용 목록에 있는 AppleScript 실행:

- `send_keystroke(app, text)` – 허용 목록에 있는 앱에 키 입력 보내기
- `send_key_combo(app, key_combo)` – 키 조합 보내기
- `execute_safe_action(app, intent, element)` – 허용 목록에 있는 작업 실행
- `get_app_info(app)` – 시스템 이벤트를 통해 앱 정보 얻기
- `get_safari_current_url()` – Safari의 현재 URL을 가져옵니다.
- `safari_open_url(url)` – Safari에서 URL 열기
- `finder_reveal(path)` – Finder에 파일 공개

`_KEYSTROKE_ALLOWLIST`의 앱과 `_INTENT_ALLOWLIST`의 인텐트만
허용됩니다. 다른 모든 항목은 `executed=False`을 반환합니다.

### `mac/helper.py` – 플랫폼 유틸리티

- `is_macos()` – 플랫폼 확인
- `macos_version()` – 버전 튜플 가져오기
- `tcc_accessibility_granted()` – TCC 접근성 확인
- `tcc_screen_recording_granted()` – TCC 화면 녹화 확인
- `get_frontmost_app()` – 활성 앱 받기
- `activate_app(app, pid)` – 앱을 포그라운드로 가져오기
- `restore_app(previous_app)` – 이전 맨 앞의 앱 복원

---

## 사용 예

### 관찰하다

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

### pid_event (실험적)

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

### 의사

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

`computer_doctor` 기능은 개별 권한 확인을 통해 이를 확장합니다.

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

## 승인 및 감사

### 위험 수준

조치는 세 가지 위험 수준으로 분류됩니다.

| 레벨 | 작업 | 행동 |
|-------|---------|----------|
| §루미§0§ | 관찰, 목록, 스크린샷, ax_tree_read | 승인이 필요하지 않습니다 |
| §루미§0§ | 스크롤 | 승인이 필요하지 않습니다(현재) |
| §루미§0§ | 클릭, type_text, 키, semantic_action, ax_press, ax_set_value, post_to_pid | 승인 필요 |

### 승인 흐름

`requires_approval(action)`가 `True`을 반환하는 경우 런타임은 다음을 수행해야 합니다.
1. 사용자에게 작업 세부정보를 제시합니다.
2. 명시적인 확인을 기다립니다.
3. 그런 다음에만 드라이버 체인을 통해 실행합니다.

현재 구현에서는 감사 로그에 `approval_required`을 기록합니다.
실제 승인 게이트는 서비스 위의 API/UI 레이어에 구현됩니다.

### 감사 로그

모든 작업(성공 또는 실패)은 `~/.rumi/computer_seat_audit.jsonl`에 기록됩니다.

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

## 함수 매니페스트

4개의 함수 엔드포인트는 ComputerSeat를 AI 런타임에 노출합니다.

| 기능 | 설명 |
|----------|-------------|
| §루미§0§ | 목표 관찰 – 스크린샷 + AX ​​트리 + 기능 |
| §루미§0§ | 의미적 동작 실행(버튼 누르기, 값 설정) |
| §루미§0§ | 직접 CGEvent 주입(실험적) |
| §루미§0§ | 플랫폼 기능 및 권한 진단 |

각 함수는 표준 매니페스트 형식을 따릅니다.
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

## 윈도우 스켈레톤

Windows 구현은 동일한 드라이버 인터페이스를 제공하지만
아직 기능적입니다. 그것은 다음을 위해 존재합니다:

1. Windows 지원을 위한 대상 아키텍처 정의
2. 인터페이스 계약을 확인하기 위한 테스트 허용
3. Windows 도우미를 동시에 개발할 수 있습니다.

### Windows 도우미 모듈

| 모듈 | 목적 |
|--------|---------|
| §루미§0§ | UI 자동화 트리 작업(스텁) |
| §루미§0§ | 창 핸들 열거(스텁) |
| §루미§0§ | PrintWindow 스크린샷 캡처(스텁) |

### Windows 드라이버 주문

```python
WINDOWS_DRIVER_ORDER = [
    "windows_uia",          # UIA tree – semantic, background
    "windows_postmessage",  # PostMessage – background input injection
]
```

현재 모든 Windows 드라이버 방법은 `NotImplementedError`을 발생시킵니다.
`is_available()` 메서드는 `sys.platform == "win32"`에 대해서만 `True`을 반환합니다.

---

## 우아한 저하

모든 도우미 모듈은 동일한 패턴을 따릅니다:

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

이를 통해 다음이 보장됩니다.
- 어떤 플랫폼에도 `ImportError`가 없습니다.
- 함수는 안전한 기본값을 반환합니다(거짓, 빈 목록, 빈 사전).
- 드라이버 체인은 사용할 수 없는 드라이버를 자연스럽게 건너뜁니다.
- OS별 종속성 없이 모든 플랫폼에서 테스트를 실행할 수 있습니다.

---

## 디렉토리 구조

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

## 테스트

테스트는 `rumi_ai_1_10/tests/`에 있으며 모의 드라이버를 사용하여 모든 플랫폼에서 실행됩니다.

| 테스트 파일 | 적용범위 |
|-----------|----------|
| §루미§0§ | 서비스 관찰/클릭/모의 텍스트 입력 |
| §루미§0§ | 레지스트리 순서 및 필터링 |
| §루미§0§ | 대체 체인 동작 |
| §루미§0§ | 기존 컴퓨터 사용 연기 테스트 |
| §루미§0§ | Windows 드라이버 인터페이스 계약 |
| §루미§0§ | Mac AX 드라이버 인스턴스화 |
| §루미§0§ | CGEvent 드라이버 PID 요구 사항 |

모든 테스트를 실행합니다.
```bash
cd rumi_ai_1_10
python -m pytest tests/test_computer_*.py tests/test_mac_*.py tests/test_windows_*.py tests/test_browser_computer_compat.py -v
```

---

## 미래의 일

- [ ] comtypes/pywinauto를 사용하여 Windows UIA 드라이버 구현
- [ ] Windows PrintWindow 캡처 구현
- [ ] ScreenCaptureKit 기본 캡처 추가(현재 CLI 전용)
- [ ] API 레이어에 승인 게이트 미들웨어 추가
- [ ] 반복되는 의미 작업을 위한 요소 캐싱 추가
- [ ] 창/화면 공간 간의 좌표 정규화 추가
- [ ] Mac 포그라운드 드라이버에 대한 다중 모니터 지원 추가
