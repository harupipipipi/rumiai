# Block シグネチャ仕様

defaults Pack のすべての block は `blocks/<category>/<name>.py` に配置され、統一されたシグネチャに従う。

---

## `def run(input_data, context)` のルール

すべての block は以下のシグネチャを持つ `run` 関数をモジュールレベルでエクスポートする:

```python
def run(input_data: dict, context: dict) -> dict:
```

### input_data の構造

`input_data` はクライアントからのリクエストデータを格納する dict である。transport 層が以下の処理を行った後に渡される:

HTTP の場合は JSON Body をパースした dict がそのまま渡される。パスパラメータは transport 層が `input_data` に事前注入する。例えば `/api/chat/conversations/{id}` の場合:

```python
input_data["conversation_id"] = path_params.get("id", "")
```

stdio/UDS の場合はリクエスト JSON の `"data"` フィールドの内容が渡される。パスパラメータの注入は `_ID_INJECT_MAP` に基づいて自動的に行われる。

`input_data` に含まれるフィールドは各 block によって異なる。各 block は自身が必要とするフィールドを `input_data.get()` で取得し、不足時は `error()` を返す。

### context の全フィールド

#### transport 直接呼び出し時のフィールド

各 transport の `_build_context()` が生成するベースフィールド。全ての呼び出しで必ず存在する。

| フィールド | 型 | 説明 |
|---|---|---|
| `flow_id` | `string` | 実行フローの識別子。transport 直接呼び出し時は `"transport_direct"`（HTTP）、`"stdio_direct"`（stdio）、`"uds_direct"`（UDS）のいずれか |
| `step_id` | `string` | ステップの識別子。transport 直接呼び出し時は `"http_request"`（HTTP）、`"stdio_request"`（stdio）、`"uds_request"`（UDS）のいずれか |
| `phase` | `string` | 常に `"execute"` |
| `ts` | `string` | ISO 8601 タイムスタンプ (例: `"2025-01-01T00:00:00Z"`) |
| `owner_pack` | `string` | 常に `"defaults"` |
| `inputs` | `dict` | 追加入力。通常は空 dict |

#### Flow エンジン / カーネル経由で追加されるフィールド

Flow エンジン経由、または `call_handler` 経由で handler が呼び出される場合、カーネルが以下の追加フィールドを context に注入する。transport 直接呼び出し時にはこれらのフィールドは存在しない（handler 側では `context.get()` で安全に取得する必要がある）。

| フィールド | 型 | 説明 |
|---|---|---|
| `call_handler` | `callable \| None` | 他の handler を呼び出す関数。`call_handler(handler_name: str, input_data: dict) -> dict` のシグネチャ。カーネルの InterfaceRegistry を通じて handler 名を解決し、対象の `run()` を呼び出す |
| `emit_event` | `callable \| None` | イベントを発行する関数。`emit_event(event_type: str, data: dict) -> None` のシグネチャ。カーネルの EventBus にイベントを送信する |
| `wait_event` | `callable \| None` | イベントを待機する関数。`wait_event(event_type: str, timeout: int, filter: dict) -> dict \| None` のシグネチャ。指定されたイベントが発火するまでブロックする |
| `emit_widget` | `callable \| None` | Widget を UI に送信する関数。`emit_widget(widget_json: dict) -> None` のシグネチャ。`lib/rumi_widgets/` で定義された Widget 構造を送信する |
| `cancel_check` | `callable \| None` | 現在の実行がキャンセルされたか確認する関数。`cancel_check() -> bool` のシグネチャ。長時間実行のループ内で定期的に呼び出して早期終了に使用する |
| `handler_config` | `dict \| None` | handler の設定情報。`conditions.json` 等で定義された handler 固有の設定がカーネルから注入される |
| `session` | `dict \| None` | セッション情報。`session_id`、`workspace` 等のフィールドを含む。セッションスコープの状態管理に使用される |

#### context フィールドの使用例

```python
def run(input_data, context):
    # transport 直接呼び出し時のベースフィールド（常に存在）
    flow_id = context["flow_id"]
    ts = context["ts"]

    # Flow エンジン経由のフィールド（存在しない場合がある）
    call_handler = context.get("call_handler")
    emit_event = context.get("emit_event")
    emit_widget = context.get("emit_widget")
    cancel_check = context.get("cancel_check")
    session = context.get("session")
    handler_config = context.get("handler_config")

    # call_handler が存在する場合のみ他の handler を呼び出す
    if call_handler is not None:
        result = call_handler("defaults.ai.complete", {
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
        })

    # cancel_check が存在する場合のみキャンセルチェック
    if cancel_check is not None and cancel_check():
        return error("execution cancelled", "CANCELLED")

    return ok({"done": True})
```

---

## 戻り値 — `ok()` / `error()` 形式

すべての block は `blocks/_common.py` の `ok()` または `error()` を使って結果を返す。

### 成功レスポンス

```python
from blocks._common import ok

return ok({"key": "value"})
# → {"status": "ok", "data": {"key": "value"}}

return ok(None)
# → {"status": "ok", "data": null}
```

### エラーレスポンス

```python
from blocks._common import error

return error("conversation_id is required", "INVALID_INPUT")
# → {"status": "error", "error": {"code": "INVALID_INPUT", "message": "conversation_id is required"}}

return error("something went wrong")
# → {"status": "error", "error": {"code": "ERROR", "message": "something went wrong"}}
```

### 未実装スタブ

```python
from blocks._common import not_implemented

return not_implemented("defaults.some.handler")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.some.handler"}
```

### 静的ファイル（transport/http.py 専用）

HTTP transport のみ、静的ファイルを返すための特殊形式がある:

```python
return {"_static": True, "content_type": "text/html; charset=utf-8", "body": "<html>...</html>"}
```

---

## import パスのルール

すべての block ファイルは冒頭で以下のパターンで `sys.path` を設定する:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
```

これにより、パックルートからの絶対パスで import できるようになる:

```python
from blocks._common import ok, error, gen_id, timestamp
from domain.chat.store import ChatStore
from domain.ai_client.client import AIClient
```

`sys.path.insert(0, ...)` はファイルの先頭（他の import より前）に記述する。

---

## `_common.py` の全関数

`blocks/_common.py` は以下の 5 つの関数を提供する:

### `ok(data=None) -> dict`

成功レスポンスを返す。`data` には任意の JSON シリアライズ可能なオブジェクトを渡す。

```python
ok({"id": "abc"})   # → {"status": "ok", "data": {"id": "abc"}}
ok()                 # → {"status": "ok", "data": null}
```

### `error(message, code="ERROR") -> dict`

エラーレスポンスを返す。

```python
error("not found", "NOT_FOUND")  # → {"status": "error", "error": {"code": "NOT_FOUND", "message": "not found"}}
error("fail")                     # → {"status": "error", "error": {"code": "ERROR", "message": "fail"}}
```

### `not_implemented(handler_name) -> dict`

未実装ハンドラのスタブレスポンスを返す。

```python
not_implemented("defaults.foo.bar")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.foo.bar"}
```

### `timestamp() -> str`

ISO 8601 形式の UTC タイムスタンプ文字列を返す。

```python
timestamp()  # → "2025-01-01T00:00:00Z"
```

内部実装: `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`

### `gen_id() -> str`

UUID v4 の文字列を返す。

```python
gen_id()  # → "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

内部実装: `str(uuid.uuid4())`
