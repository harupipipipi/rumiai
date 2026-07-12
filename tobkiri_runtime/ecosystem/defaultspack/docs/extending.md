# defaults Pack 拡張ガイド

defaults Pack に新機能を追加する手順を解説する。

設定 UI、AI input、tool/context policy、composer command、function/route
binding、permission metadata、backend service metadata、test contract を組み合わせる
機能は、まず [templates.md](templates.md) の RumiTemplate として宣言する。
block や domain module は実行権限を持つ builtin runtime 側に残し、template は
その安全な runtime への metadata binding を担当する。

---

## 新しい block の追加手順

block は defaults Pack の最小実行単位である。各 block は `blocks/<category>/<name>.py` に配置され、`def run(input_data, context)` 関数をエクスポートする。

### 1. ファイルを作成する

```
blocks/
  <category>/
    __init__.py      # 空ファイル（既存なら不要）
    <name>.py        # 新しい block
```

### 2. block のコードを書く

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

block ファイル名はスネークケースで、handler 名の最後の部分に対応する。例えば `defaults.chat.send` handler は `blocks/chat/send.py` の `run()` を呼び出す。

---

## 新しい domain モジュールの追加手順

domain モジュールは block から呼び出されるビジネスロジック層である。

### 1. ディレクトリを作成する

```
domain/
  <module_name>/
    __init__.py
    <main_class>.py
```

### 2. パターンの選択

domain モジュールは以下のパターンのいずれかに従う（詳細は `docs/internals/domain-patterns.md` を参照）:

**シングルトンパターン** — 状態を持つグローバルインスタンス:

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

**ストアパターン** — インメモリデータ管理:

```python
class MyStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
        return cls._instance
```

### 3. import パス

domain モジュールを block から利用する場合は相対パスではなく、`sys.path.insert` 済みのパックルートからの絶対パスでインポートする:

```python
from domain.<module>.<file> import ClassName
```

---

## ecosystem.json の更新方法

新しいコンポーネントを追加した場合、`ecosystem.json` を更新する必要がある。

### 1. vocabulary.types にタイプを追加

```json
{
  "vocabulary": {
    "types": ["chat", "agent", ..., "new_type"]
  }
}
```

### 2. components にエントリを追加

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

### 3. load_order を更新

依存関係に応じた順序で `load_order` 配列にエントリを追加する:

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

`frontend` は常に最後に配置する。

---

## transport/http.py へのルート追加方法

### 1. _setup_routes にルートを追加

`DefaultsHttpServer._setup_routes()` メソッド内のルート配列に新しいエントリを追加する:

```python
("POST", "/api/new_module/action", self._handle_new_action),
```

パスパラメータが必要な場合は `{param}` 形式を使用する:

```python
("GET", "/api/new_module/{id}/detail", self._handle_new_detail),
```

### 2. ハンドラメソッドを追加

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

### 3. stdio/UDS transport にも追加する場合

`transport/stdio.py` と `transport/uds.py` の `_ROUTE_MAP` と `_ID_INJECT_MAP` に同じルートを追加する。

---

## テストの方法

### HTTP 経由でのテスト

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

### stdio 経由でのテスト

```bash
echo '{"method":"GET","path":"/api/health"}' | python -m transport.stdio
```

### block の単体テスト

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
