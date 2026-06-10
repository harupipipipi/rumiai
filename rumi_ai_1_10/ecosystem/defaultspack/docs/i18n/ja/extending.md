<!-- docs-i18n-links:start -->
[EN](../../extending.md) | [JP](./extending.md) | [KR](../ko/extending.md) | [CN](../zh-cn/extending.md)
<!-- docs-i18n-links:end -->

#defaults パック拡張ガイド

デフォルトパックに新機能を追加する手順を説明します。

---

## 新しいブロックを追加する手順

ブロックは、デフォルト パックの最小実行単位です。各ブロックは `blocks/<category>/<name>.py` に配置され、`def run(input_data, context)` の関数をエクスポートします。

### 1. ファイルを作成します

```
blocks/
  <category>/
    __init__.py      # 空ファイル（既存なら不要）
    <name>.py        # 新しい block
```

### 2. ブロックコードを書く

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp


def run(input_data, context):
    """
    input_data: dict — クライアントからのリクエストデータ
    context: dict — 実行コンテキスト
    """
    # パラメータの検証
    param = input_data.get("param")
    if not param:
        return error("param is required", "INVALID_INPUT")

    # ドメインロジックの呼び出し
    from domain.<module>.<class> import SomeClass
    instance = SomeClass()
    result = instance.some_method(param)

    # 結果を返す
    return ok(result)
```

### 3. 命名規則

ブロック ファイル名はスネークケースで、ハンドラー名の最後の部分に対応します。たとえば、`defaults.chat.send` ハンドラは、`blocks/chat/send.py` の `run()` を呼び出します。

---

## 新しいドメイン モジュールを追加する手順

ドメインモジュールは、ブロックによって呼び出されるビジネスロジック層です。

### 1. ディレクトリを作成します。

```
domain/
  <module_name>/
    __init__.py
    <main_class>.py
```

### 2. パターンの選択

ドメイン モジュールは、次のいずれかのパターンに従います (詳細については、`docs/internals/domain-patterns.md` を参照)。

**シングルトン パターン** — 状態を持つグローバル インスタンス:

```python
class MyService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 初期化処理
```

**ストア パターン** — インメモリ データ管理:

```python
class MyStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
        return cls._instance
```

### 3. インポートパス

ブロックからドメイン モジュールを使用する場合は、相対パスの代わりに、`sys.path.insert`-completed パック ルートからの絶対パスを使用してインポートします。

```python
from domain.<module>.<file> import ClassName
```

---

## エコシステム.json を更新する方法

新しいコンポーネントを追加する場合は、`ecosystem.json`を更新する必要があります。

### 1. タイプをvocabulary.typesに追加します。

```json
{
  "vocabulary": {
    "types": ["chat", "agent", ..., "new_type"]
  }
}
```

### 2. コンポーネントにエントリを追加します

```json
{
  "components": {
    "new_module": {
      "type": "new_type",
      "id": "new_module",
      "path": "blocks/new_module",
      "connectivity": {
        "provides": [
          "defaults.new_module.action1",
          "defaults.new_module.action2"
        ]
      }
    }
  }
}
```

### 3.load_order を更新する

依存関係に従って順番に `load_order` 配列にエントリを追加します。

```json
{
  "load_order": [
    "memory:memory",
    ...,
    "new_type:new_module",
    "frontend:frontend"
  ]
}
```

`frontend` は常に最後に配置されます。

---

## Transport/http.py にルートを追加する方法

### 1. ルートを _setup_routes に追加します

`DefaultsHttpServer._setup_routes()` メソッドのルート配列に新しいエントリを追加します。

```python
("POST", "/api/new_module/action", self._handle_new_action),
```

パス パラメーターが必要な場合は、`{param}` 形式を使用します。

```python
("GET", "/api/new_module/{id}/detail", self._handle_new_detail),
```

### 2. ハンドラーメソッドの追加

```python
def _handle_new_action(self, request_data, path_params):
    from blocks.new_module.action import run as handler_run
    context = self._build_context()
    return handler_run(request_data, context)

def _handle_new_detail(self, request_data, path_params):
    from blocks.new_module.detail import run as handler_run
    context = self._build_context()
    request_data["item_id"] = path_params.get("id", "")
    return handler_run(request_data, context)
```

### 3. stdio/UDS トランスポートにも追加する場合

`transport/stdio.py`と`transport/uds.py`の`_ROUTE_MAP`と`_ID_INJECT_MAP`にも同じルートを追加します。

---

## テスト方法

### HTTP 経由のテスト

```bash
# ヘルスチェック
curl http://127.0.0.1:8766/api/health

# 会話作成
curl -X POST http://127.0.0.1:8766/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"model": "stub/default"}'

# メッセージ送信
curl -X POST http://127.0.0.1:8766/api/chat/conversations/{id}/messages \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "content": "Hello"}}'
```

### 標準入出力経由でのテスト

```bash
echo '{"method":"GET","path":"/api/health"}' | python -m transport.stdio
```

### ブロックの単体テスト

```python
from blocks.new_module.action import run

context = {
    "flow_id": "test",
    "step_id": "test",
    "phase": "execute",
    "ts": "2025-01-01T00:00:00Z",
    "owner_pack": "defaults",
    "inputs": {},
}

result = run({"param": "value"}, context)
assert result["status"] == "ok"
```
