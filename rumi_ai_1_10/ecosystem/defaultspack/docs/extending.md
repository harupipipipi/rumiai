<!-- docs-i18n-links:start -->
[EN](./extending.md) | [JP](./i18n/ja/extending.md) | [KR](./i18n/ko/extending.md) | [CN](./i18n/zh-cn/extending.md)
<!-- docs-i18n-links:end -->

#defaults pack extension guide

Explaining the procedure for adding new features to defaults pack.

---

## Steps to add new block

block is the minimum execution unit of defaults pack. Each block is placed in `blocks/<category>/<name>.py` and exports `def run(input_data, context)` functions.

### 1. Create a file

```
blocks/
  <category>/
    __init__.py      # 空ファイル（既存なら不要）
    <name>.py        # 新しい block
```

### 2. Write block code

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

### 3. Naming convention

The block file name is snake case and corresponds to the last part of the handler name. For example, `defaults.chat.send` handler calls `run()` of `blocks/chat/send.py`.

---

## Steps to add new domain module

The domain module is the business logic layer called by block.

### 1. Create a directory

```
domain/
  <module_name>/
    __init__.py
    <main_class>.py
```

### 2. Pattern selection

The domain module follows one of the following patterns (see `docs/internals/domain-patterns.md` for details):

**Singleton pattern** — global instance with state:

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

**Store pattern** — In-memory data management:

```python
class MyStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
        return cls._instance
```

### 3. import path

When using the domain module from block, import it using the absolute path from the `sys.path.insert`-completed pack root instead of the relative path:

```python
from domain.<module>.<file> import ClassName
```

---

## How to update ecosystem.json

If you add new components, you will need to update `ecosystem.json`.

### 1. Add types to vocabulary.types

```json
{
  "vocabulary": {
    "types": ["chat", "agent", ..., "new_type"]
  }
}
```

### 2. Add entry to components

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

### 3. Update load_order

Add entries to the `load_order` array in order according to dependencies:

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

`frontend` is always placed last.

---

## How to add route to transport/http.py

### 1. Add route to _setup_routes

Add a new entry to the root array in the `DefaultsHttpServer._setup_routes()` method:

```python
("POST", "/api/new_module/action", self._handle_new_action),
```

If a path parameter is required, use the `{param}` format:

```python
("GET", "/api/new_module/{id}/detail", self._handle_new_detail),
```

### 2. Add handler method

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

### 3. When also adding to stdio/UDS transport

Add the same route to `_ROUTE_MAP` and `_ID_INJECT_MAP` of `transport/stdio.py` and `transport/uds.py`.

---

## How to test

### Testing over HTTP

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

### Testing via stdio

```bash
echo '{"method":"GET","path":"/api/health"}' | python -m transport.stdio
```

### Unit test for block

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
