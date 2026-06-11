<!-- docs-i18n-links:start -->
[EN](../../extending.md) | [JP](../ja/extending.md) | [KR](../ko/extending.md) | [CN](./extending.md)
<!-- docs-i18n-links:end -->

# defaults 包扩展指南

解释向默认包添加新功能的过程。

---

## 添加新块的步骤

block是defaults pack的最小执行单元。每个块都放置在`blocks/<category>/<name>.py`中并导出`def run(input_data, context)`函数。

### 1.创建文件

```
blocks/
  <category>/
    __init__.py      # 空ファイル（既存なら不要）
    <name>.py        # 新しい block
```

### 2.编写块代码

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

### 3.命名约定

块文件名是蛇形命名，对应于处理程序名称的最后部分。例如，`defaults.chat.send`处理程序调用`run()`或`blocks/chat/send.py`。

---

## 添加新域模块的步骤

领域模块是Block调用的业务逻辑层。

### 1.创建目录

```
domain/
  <module_name>/
    __init__.py
    <main_class>.py
```

### 2.图案选择

域模块遵循以下模式之一（有关详细信息，请参阅`docs/internals/domain-patterns.md`）：

**单例模式** — 具有状态的全局实例：

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

**存储模式** — 内存中数据管理：

```python
class MyStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
        return cls._instance
```

### 3.导入路径

当使用块中的域模块时，使用来自`sys.path.insert`完成的包根的绝对路径而不是相对路径导入它：

```python
from domain.<module>.<file> import ClassName
```

---

## 如何更新ecosystem.json

如果添加新组件，则需要更新`ecosystem.json`。

### 1.向vocabulary.types添加类型

```json
{
  "vocabulary": {
    "types": ["chat", "agent", ..., "new_type"]
  }
}
```

### 2.为组件添加入口

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

### 3.更新load_order

根据依赖关系按顺序将条目添加到 `load_order` 数组中：

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

`frontend` 始终放在最后。

---

## 如何添加路由到transport/http.py

### 1. 将路由添加到_setup_routes

在`DefaultsHttpServer._setup_routes()`方法中向根数组添加一个新条目：

```python
("POST", "/api/new_module/action", self._handle_new_action),
```

如果需要路径参数，请使用`{param}`格式：

```python
("GET", "/api/new_module/{id}/detail", self._handle_new_detail),
```

### 2.添加处理方法

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

### 3. 当同时添加到 stdio/UDS 传输时

将相同的路由添加到`transport/stdio.py`和`transport/uds.py`的`_ROUTE_MAP`和`_ID_INJECT_MAP`。

---

## 如何测试

### 通过 HTTP 进行测试

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

### 通过 stdio 测试

```bash
echo '{"method":"GET","path":"/api/health"}' | python -m transport.stdio
```

### 块的单元测试

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
