<!-- docs-i18n-links:start -->
[EN](../../../internals/block-signature.md) | [JP](./block-signature.md) | [KR](../../ko/internals/block-signature.md) | [CN](../../zh-cn/internals/block-signature.md)
<!-- docs-i18n-links:end -->

# ブロック署名の仕様

デフォルト パック内のすべてのブロックは `blocks/<category>/<name>.py` に配置され、統一された署名に従います。

---

## `def run(input_data, context)` のルール

すべてのブロックは、モジュール レベルで次の署名を持つ `run` 関数をエクスポートします。

```python
def run(input_data: dict, context: dict) -> dict:
```

### input_data の構造

`input_data`はクライアントからのリクエストデータを格納する辞書です。トランスポート層が以下を実行した後に渡されます。

HTTPの場合は、解析されたJSON Bodyであるdictがそのまま渡されます。パス パラメーターは、トランスポート層によって `input_data` に事前に挿入されます。たとえば、`/api/chat/conversations/{id}` の場合:

```python
input_data["conversation_id"] = path_params.get("id", "")
```

stdio/UDSの場合、リクエストJSONの`"data"`フィールドの内容が渡されます。パスパラメータの挿入は`_ID_INJECT_MAP`に基づいて自動的に行われます。

`input_data`に含まれるフィールドはブロックごとに異なります。各ブロックは `input_data.get()` を使用して必要なフィールドを取得し、不十分な場合は `error()` を返します。

### コンテキストのすべてのフィールド

#### Transport 直接呼び出す場合のフィールド

`_build_context()` によってトランスポートごとに生成される基本フィールド。すべての通話に同席する必要があります。

|フィールド |タイプ |説明 |
|---|---|---|
| `flow_id` | `string` |実行フローの識別子。 Transport 直接呼び出す場合は、`"transport_direct"` (HTTP)、`"stdio_direct"` (stdio)、または `"uds_direct"` (UDS) のいずれかを呼び出します。
| `step_id` | `string` |ステップの識別子。 Transport 直接呼び出す場合は、`"http_request"` (HTTP)、`"stdio_request"` (stdio)、または `"uds_request"` (UDS) のいずれかを呼び出します。
| `phase` | `string` |いつも`"execute"` |
| `ts` | `string` | ISO 8601 タイムスタンプ (例: `"2025-01-01T00:00:00Z"`) |
| `owner_pack` | `string` |いつも`"defaults"` |
| `inputs` | `dict` |追加入力。通常は空の辞書 |

#### フロー エンジン/カーネル経由で追加されたフィールド

ハンドラーがフロー エンジンまたは `call_handler` を介して呼び出される場合、カーネルは次の追加フィールドをコンテキストに挿入します。 これらのフィールドは、トランスポートを直接呼び出す場合には存在しません (ハンドラーは `context.get()` を使用して安全にフィールドを取得する必要があります)。

|フィールド |タイプ |説明 |
|---|---|---|
| `call_handler` | `callable \| None` |他のハンドラーを呼び出す関数。 `call_handler(handler_name: str, input_data: dict) -> dict`の署名。カーネルの InterfaceRegistry を通じてハンドラー名を解決し、ターゲット `run()` | を呼び出します。
| `emit_event` | `callable \| None` |イベントを発生させる関数。 `emit_event(event_type: str, data: dict) -> None`の署名。イベントをカーネルの EventBus に送信します。
| `wait_event` | `callable \| None` |イベントを待つ関数。 `wait_event(event_type: str, timeout: int, filter: dict) -> dict \| None`の署名。指定されたイベントが発生するまでブロックします。
| `emit_widget` | `callable \| None` | WidgetをUIに送信する関数。 `emit_widget(widget_json: dict) -> None`の署名。 `lib/rumi_widgets/`で定義されたウィジェット構造を送信します。
| `cancel_check` | `callable \| None` |現在の実行がキャンセルされたかどうかを確認する関数。 `cancel_check() -> bool`の署名。長時間実行ループ内で定期的に呼び出して、早期終了に使用します。
| `handler_config` | `dict \| None` |ハンドラー構成情報。 `conditions.json` などで定義されたハンドラ固有の設定はカーネルから注入されます。
| `session` | `dict \| None` |セッション情報。 `session_id`、`workspace`などのフィールドが含まれます。セッション スコープの状態管理に使用されます。

#### コンテキストフィールドの使用例

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

すべてのブロックは、`blocks/_common.py`、`ok()`、または `error()`を使用して結果を返します。

### 応答成功

```python
from blocks._common import ok

return ok({"key": "value"})
# → {"status": "ok", "data": {"key": "value"}}

return ok(None)
# → {"status": "ok", "data": null}
```

### エラー応答

```python
from blocks._common import error

return error("conversation_id is required", "INVALID_INPUT")
# → {"status": "error", "error": {"code": "INVALID_INPUT", "message": "conversation_id is required"}}

return error("something went wrong")
# → {"status": "error", "error": {"code": "ERROR", "message": "something went wrong"}}
```

### 未実装のスタブ

```python
from blocks._common import not_implemented

return not_implemented("defaults.some.handler")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.some.handler"}
```

### 静的ファイル (transport/http.py のみ)

HTTP トランスポートのみが静的ファイルを返すための特別な形式を持っています。

```python
return {"_static": True, "content_type": "text/html; charset=utf-8", "body": "<html>...</html>"}
```

---

## インポートパスルール

すべてのブロック ファイルは、次のパターンで先頭に `sys.path` を設定します。

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
```

これにより、パック ルートからの絶対パスを使用してインポートできるようになります。

```python
from blocks._common import ok, error, gen_id, timestamp
from domain.chat.store import ChatStore
from domain.ai_client.client import AIClient
```

`sys.path.insert(0, ...)` はファイルの先頭 (他のインポートの前) に記述する必要があります。

---

## `_common.py`の全機能

`blocks/_common.py`は以下の5つの機能を提供します。

### `ok(data=None) -> dict`

成功応答を返します。任意の JSON シリアル化可能オブジェクトを `data` に渡します。

```python
ok({"id": "abc"})   # → {"status": "ok", "data": {"id": "abc"}}
ok()                 # → {"status": "ok", "data": null}
```

### `error(message, code="ERROR") -> dict`

エラー応答を返します。

```python
error("not found", "NOT_FOUND")  # → {"status": "error", "error": {"code": "NOT_FOUND", "message": "not found"}}
error("fail")                     # → {"status": "error", "error": {"code": "ERROR", "message": "fail"}}
```

### `not_implemented(handler_name) -> dict`

未実装のハンドラーのスタブ応答を返します。

```python
not_implemented("defaults.foo.bar")
# → {"status": "ok", "data": null, "_stub": true, "_handler": "defaults.foo.bar"}
```

### `timestamp() -> str`

ISO 8601 形式の UTC タイムスタンプ文字列を返します。

```python
timestamp()  # → "2025-01-01T00:00:00Z"
```

内部実装: `time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())`

### `gen_id() -> str`

UUID v4 文字列を返します。

```python
gen_id()  # → "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

内部実装: `str(uuid.uuid4())`
