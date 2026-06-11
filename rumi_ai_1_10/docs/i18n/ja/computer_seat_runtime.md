<!-- docs-i18n-links:start -->
[EN](../../computer_seat_runtime.md) | [JP](./computer_seat_runtime.md) | [KR](../ko/computer_seat_runtime.md) | [CN](../zh-cn/computer_seat_runtime.md)
<!-- docs-i18n-links:end -->

# ComputerSeat ランタイム – アーキテクチャと使用法

## 概要

ComputerSeat は、AI エージェントを提供するモジュール式デスクトップ オートメーション ランタイムです。
デスクトップ アプリケーションを観察して操作する機能を備えています。使用します
複数の戦略が試行される **ドライバー チェーン** アーキテクチャ
優先順位が高く、優先順位の高いドライバーが失敗した場合は自動フォールバックが行われます。

主な設計目標は次のとおりです。

1. **バックグラウンド操作** – フォーカスを奪うことなくアプリを操作します
2. **正常な劣化** – 利用可能なあらゆる権限で動作します
3. **監査証跡** – トレーサビリティのためにすべてのアクションが記録されます
4. **許可を考慮した** – リスクの高いアクションには明示的な承認が必要です
5. **クロスプラットフォーム** – Mac は完全に実装され、Windows スケルトンは準備完了

---

## アーキテクチャ

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

### コアコンポーネント

|コンポーネント |ファイル |役割 |
|-----------|------|------|
| `ComputerSeatService` | `service.py` |ドライバー チェーンを通じてアクションを調整します。
| `DriverRegistry` | `registry.py` |ドライバーの登録とチェーンの注文を管理 |
| `AuditLogger` | `audit.py` | JSON 行の追加専用監査ログ |
| `permissions` | `permissions.py` |リスクの分類と承認のチェック |
| `models` | `models.py` |共有データクラス (ActionResult、ObserveResult など) |

### データモデル

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

## ドライバーリスト

### Mac ドライバー

|ドライバー |名前 |優先順位 |機能 |
|--------|------|----------|--------------|
| Macアクセシビリティドライバー | `mac_accessibility` | 1 (最高) | AX ツリーを介したセマンティック アクション |
| MacAppleEventsドライバー | `mac_apple_events` | 2 |許可リストに登録された AppleScript アクション |
| MacCGEventPidDriver | `mac_cgevent_pid` | 3 | CGEventPostToPid によるバックグラウンド入力 |
| MacForegroundFallbackDriver | `mac_foreground` | 4 (最低) |アプリ + フォアグラウンド入力をアクティブ化します |
| MacScreenCaptureDriver | `mac_screen_capture` | — |観察のみ（スクリーンショット） |

### Windows ドライバー (スケルトン)

|ドライバー |名前 |優先順位 |ステータス |
|--------|------|----------|--------|
| WindowsUIAドライバー | `windows_uia` | 1 |スケルトン – NotImplementedError を発生させます。
| Windowsポストメッセージドライバー | `windows_postmessage` | 2 |スケルトン – NotImplementedError を発生させます。

---

## Mac ドライバーの注文

`MAC_DRIVER_ORDER` はフォールバック チェーンを定義します。

```python
MAC_DRIVER_ORDER = [
    "mac_accessibility",    # AX tree – semantic, background, high confidence
    "mac_apple_events",     # AppleScript – allowlisted, background
    "mac_cgevent_pid",      # CGEvent – experimental, background
    "mac_foreground",       # Foreground fallback – always works but steals focus
]
```

アクションが要求された場合:
1. サービスはレジストリからチェーンを取得します (`is_available()` ドライバーのみ)
2. 各ドライバーを順番に試します
3. ドライバーが `executed=False` を返すか、例外を発生させた場合は、次のステップに進みます。
4. すべて失敗した場合は、収集されたエラー メモを含む失敗の ActionResult を返します。

---

## Mac ヘルパー モジュール

### `mac/ax.py` – アクセシビリティ API

AX ツリー操作のために pyobjc `ApplicationServices` をラップします。

- `ax_is_trusted()` – プロセスにアクセシビリティ権限があるかどうかを確認します
- `ax_prompt_permission()` – ユーザーに許可を求めるプロンプトを表示
- `ax_list_windows(pid)` – PID のリスト ウィンドウ
- `ax_get_tree(pid, app, window_title, window_id)` – 完全な AX ツリーを取得する
- `ax_find_candidates(pid, app, role, title, ...)` – 一致する要素の検索
- `ax_press(element_id)` – 要素に対して AXPress を呼び出す
- `ax_set_value(pid, app, value, element_id)` – 要素の値を設定します
- `ax_raise(window_id)` – 窓を上げる

macOS 以外の場合、または pyobjc が使用できない場合、すべての関数は空の結果を返します。

### `mac/cgevent.py` – CGEvent インジェクション

直接イベントを投稿するために pyobjc `Quartz` をラップします。

- `post_click_to_pid(pid, x, y, button)` – 座標をクリックします
- `post_key_to_pid(pid, text, key_combo)` – テキストまたはキーの組み合わせを入力します
- `post_scroll_to_pid(pid, x, y, direction, clicks)` – スクロール
- `cgevent_smoke_test()` – API の利用可能性を確認する

### `mac/screencapture.py` – ウィンドウ キャプチャ

- `capture_window(window_id, pid, app, output_path)` – スクリーンショットをキャプチャする
- `screen_capture_kit_available()` – ScreenCaptureKit を確認する
- `list_windows()` – CGWindowListCopyWindowInfo を介して表示可能なウィンドウをリストする

ScreenCaptureKit から `screencapture -l <window_id>` CLI にフォールバックします。

### `mac/applescript.py` – 安全な AppleScript ブリッジ

ホワイトリストに登録された AppleScript の実行:

- `send_keystroke(app, text)` – 許可リストに登録されたアプリにキーストロークを送信します
- `send_key_combo(app, key_combo)` – キーの組み合わせを送信します
- `execute_safe_action(app, intent, element)` – 許可リストに登録されたアクションを実行する
- `get_app_info(app)` – システムイベント経由でアプリ情報を取得します
- `get_safari_current_url()` – Safari の現在の URL を取得する
- `safari_open_url(url)` – SafariでURLを開く
- `finder_reveal(path)` – Finder でファイルを表示

`_KEYSTROKE_ALLOWLIST` のアプリと `_INTENT_ALLOWLIST` のインテントのみが対象となります。
許可されています。他のすべては`executed=False`を返します。

### `mac/helper.py` – プラットフォーム ユーティリティ

- `is_macos()` – プラットフォームチェック
- `macos_version()` – バージョンタプルの取得
- `tcc_accessibility_granted()` – TCC アクセシビリティを確認する
- `tcc_screen_recording_granted()` – TCC 画面記録を確認する
- `get_frontmost_app()` – アクティブなアプリを取得
- `activate_app(app, pid)` – アプリをフォアグラウンドに移動します
- `restore_app(previous_app)` – 前の最前面のアプリを復元します

---

## 使用例

### 観察してください

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

### セマンティックアクション

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

### pid_event (実験的)

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

### 医師

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

`computer_doctor` 関数は、これを個別の権限チェックで拡張します。

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

## 承認と監査

### リスクレベル

アクションは 3 つのリスク レベルに分類されます。

|レベル |アクション |行動 |
|-------|---------|----------|
| `low` |観察、リスト、スクリーンショット、ax_tree_read |承認は必要ありません |
| `medium` |スクロール |承認は必要ありません (現時点では) |
| `high` | click、type_text、key、semantic_action、ax_press、ax_set_value、post_to_pid |承認が必要です |

### 承認フロー

`requires_approval(action)` が `True` を返す場合、ランタイムは次のことを行う必要があります。
1. アクションの詳細をユーザーに提示する
2. 明示的な確認を待ちます
3. その後、ドライバー チェーンを通じてのみ実行されます。

現在の実装では、監査ログに `approval_required` が記録されます。
実際の承認ゲートは、サービスの上の API/UI レイヤーに実装されます。

### 監査ログ

すべてのアクション (成功または失敗) は `~/.rumi/computer_seat_audit.jsonl` に記録されます。

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

## 関数マニフェスト

4 つの機能エンドポイントは、ComputerSeat を AI ランタイムに公開します。

|機能 |説明 |
|----------|-------------|
| `computer_observe` |ターゲットの観察 – スクリーンショット + AX ツリー + 機能 |
| `computer_semantic_action` |セマンティックアクションを実行 (ボタンを押し、値を設定) |
| `computer_pid_event` |直接 CGEvent インジェクション (実験的) |
| `computer_doctor` |プラットフォームの機能と権限を診断する |

各関数は標準のマニフェスト形式に従います。
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

## Windows スケルトン

Windows 実装では同じドライバー インターフェイスが提供されますが、
それでいて機能的。それは次の目的で存在します。

1. Windows サポートのターゲット アーキテクチャを定義する
2. テストでインターフェイスコントラクトを検証できるようにする
3. Windows ヘルパーの並行開発を可能にする

### Windows ヘルパー モジュール

|モジュール |目的 |
|--------|---------|
| `windows/uia.py` | UI オートメーション ツリーの操作 (スタブ) |
| `windows/hwnd.py` |ウィンドウ ハンドルの列挙 (スタブ) |
| `windows/printwindow.py` | PrintWindow スクリーンショット キャプチャ (スタブ) |

### Windows ドライバーの順序

```python
WINDOWS_DRIVER_ORDER = [
    "windows_uia",          # UIA tree – semantic, background
    "windows_postmessage",  # PostMessage – background input injection
]
```

現在、すべての Windows ドライバー メソッドで `NotImplementedError` が発生します。
`is_available()` メソッドは、`sys.platform == "win32"` に対してのみ `True` を返します。

---

## グレースフル デグラデーション

すべてのヘルパー モジュールは同じパターンに従います。

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

これにより、次のことが保証されます。
- どのプラットフォームでも`ImportError`はありません
- 関数は安全なデフォルト (False、空のリスト、空の辞書) を返します。
- ドライバー チェーンは、使用できないドライバーを自然にスキップします。
- テストは、OS 固有の依存関係なしで任意のプラットフォームで実行できます。

---

## ディレクトリ構造

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

## テスト

テストは`rumi_ai_1_10/tests/` にあり、モック ドライバーを使用して任意のプラットフォームで実行します。

|テストファイル |取材範囲 |
|-----------|----------|
| `test_computer_seat_service.py` |モックを使用したサービスの観察/クリック/タイプテキスト |
| `test_computer_driver_registry.py` |レジストリの順序付けとフィルタリング |
| `test_computer_fallback_order.py` |フォールバック チェーンの動作 |
| `test_browser_computer_compat.py` |既存のコンピュータ_使用煙テスト |
| `test_windows_driver_skeleton.py` | Windows ドライバー インターフェイス契約 |
| `test_mac_accessibility_driver.py` | Mac AX ドライバーのインスタンス化 |
| `test_mac_cgevent_pid_driver.py` | CGEvent ドライバーの PID 要件 |

すべてのテストを実行します。
```bash
cd rumi_ai_1_10
python -m pytest tests/test_computer_*.py tests/test_mac_*.py tests/test_windows_*.py tests/test_browser_computer_compat.py -v
```

---

## 今後の取り組み

- [ ] comtypes/pywinauto を使用して Windows UIA ドライバーを実装する
- [ ] Windows PrintWindow キャプチャを実装する
- [ ] ScreenCaptureKit ネイティブ キャプチャを追加します (現在 CLI のみ)
- [ ] API レイヤーに承認ゲート ミドルウェアを追加します
- [ ] セマンティックアクションを繰り返すための要素キャッシュを追加します。
- [ ] ウィンドウ/スクリーン空間間の座標正規化を追加します
- [ ] Mac フォアグラウンド ドライバーのマルチモニター サポートを追加
