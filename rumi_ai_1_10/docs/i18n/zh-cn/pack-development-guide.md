<!-- docs-i18n-links:start -->
[EN](../../pack-development-guide.md) | [JP](../ja/pack-development-guide.md) | [KR](../ko/pack-development-guide.md) | [CN](./pack-development-guide.md)
<!-- docs-i18n-links:end -->

# Pack 开发快速入门指南

> 有关详细 API 参考，请参阅[pack-development.md](./pack-development.md)。

本指南介绍了使用scaffold（模板生成工具）创建第一个Pack、从Flow中调用它并检查其操作的步骤。

---

## 先决条件

- Python 3.10 或更高版本
- Rumi AI OS存储库的克隆环境
- 在存储库根目录中工作（`rumi_ai_1_10/`目录必须存在）

---

## 步骤1：使用模板生成包

`pack_scaffold` 使用 CLI 生成 Pack 模板。

```bash
python -m core_runtime.pack_scaffold my_pack --template minimal --output ecosystem/
```

将生成以下目录结构。

```
ecosystem/my_pack/
├── ecosystem.json
└── __init__.py
```

### 模板类型

| Template | Contents |
|-------------|------|
| `minimal` | Minimum configuration (`ecosystem.json` + `__init__.py`) |
| `capability` | minimal + `capability_handler.py` |
| `flow` | minimal + `flows/sample_flow.yaml` |
| `full` | All included (all of the above + `tests/` + `README.md`) |

### CLI 选项

| Options | Description |
|-----------|------|
| `--template`, `-t` | Template type (default: `minimal`) |
| `--output`, `-o` | Parent directory of output destination (default: current directory) |
| `--force`, `-f` | Allow overwriting of existing directories |

> 如果这是您第一次，我们建议您从 `minimal` 模板开始，并根据需要添加文件。

---

## 步骤2：编辑ecosystem.json

编辑脚手架生成的`ecosystem.json`。脚手架输出不包含 `pack_identity`，因此请手动添加。

### 由脚手架生成的 Ecosystem.json

```json
{
  "pack_id": "my_pack",
  "version": "0.1.0",
  "description": "my_pack - A Rumi AI OS Pack",
  "capabilities": [],
  "flows": [],
  "connectivity": [],
  "trust": {
    "level": "sandboxed",
    "permissions": []
  }
}
```

### 编辑后（添加`pack_identity`）

```json
{
  "pack_id": "my_pack",
  "pack_identity": "github:your-username/my_pack",
  "version": "0.1.0",
  "description": "My first Rumi AI OS Pack",
  "capabilities": [],
  "flows": [],
  "connectivity": [],
  "trust": {
    "level": "sandboxed",
    "permissions": []
  }
}
```

### 必填字段

| Field | Description |
|-----------|------|
| `pack_id` | Pack identifier. Match directory name. Follow the pattern of `[a-zA-Z0-9_-]{1,64}` |
| `pack_identity` | Identifier indicating the distribution source (e.g. `github:author/repo`). If this value changes during Pack update, apply will be rejected |

> 有关各个字段的详细信息，请参阅[the ecosystem.json section of pack-development.md](./pack-development.md#生态系统json)。

---

## 第 3 步：实施该块

Pack的实际处理是按块编写的。创建 `backend/blocks/` 目录并将 Python 文件放置在其中。

```
ecosystem/my_pack/
├── ecosystem.json
├── __init__.py
└── backend/
    └── blocks/
        └── hello.py
```

### 最小块实现

```python
# ecosystem/my_pack/backend/blocks/hello.py

def run(input_data, context=None):
    """
    Args:
        input_data: Flow から渡される入力データ（dict）
        context: 実行コンテキスト（dict）
    Returns:
        JSON 互換の dict
    """
    name = input_data.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

### run() 函数签名

`run()` 函数接受以下三种模式之一。

```python
# パターン1: 入力データとコンテキストの両方（推奨）
def run(input_data: dict, context: dict) -> dict | None:
    ...

# パターン2: 入力データのみ
def run(input_data: dict) -> dict | None:
    ...

# パターン3: 引数なし
def run() -> dict | None:
    ...
```

### 重要提示

**返回值必须与 JSON 兼容**：返回 `dict`、`list`、`str`、`int`、`float`、`bool`、`None` 之一。**不要使用带有 `_` 前缀的键**：如果在返回的字典中包含以 `_` 前缀（例如 `_internal`）开头的键，内核将自动排除它。

```python
# NG: _ プレフィックスは除外される
def run(input_data, context=None):
    return {"_internal": "removed", "result": "kept"}
    # ctx に格納されるのは {"result": "kept"} のみ

# OK
def run(input_data, context=None):
    return {"result": "kept", "metadata": {"source": "my_pack"}}
```

**验证输入数据**：由于 `input_data` 来自外部源，因此请务必执行类型和存在性检查。

```python
def run(input_data: dict, context: dict) -> dict:
    if not isinstance(input_data, dict):
        return {"error": "input_data must be a dict"}

    name = input_data.get("name")
    if not name or not isinstance(name, str):
        return {"error": "missing or invalid field: name"}

    return {"message": f"Hello, {name}!"}
```

> 详细的块规格请参考[the blocks section of pack-development.md](./pack-development.md#块)。

---

## 步骤 4：验证

使用验证工具验证包设置是否正确。

```bash
python app.py --validate
```

验证检查以下内容：

| Check items | Explanation |
|-------------|------|
| JSON parse | Is `ecosystem.json` valid JSON? |
| `pack_id` Match | Does the directory name match `pack_id` in `ecosystem.json` |
| `connectivity` Declaration | `connectivity` Is the field declared |
| `${ctx.*}` Referential integrity | Are `${ctx.PACK_ID.*}` references in the Flow contained in `connectivity` |

### 程序验证

```python
from core_runtime.pack_validator import validate_packs

report = validate_packs(ecosystem_dir="ecosystem/")
print(f"Pack 数: {report.pack_count}, 有効: {report.valid_count}")

for w in report.warnings:
    print(f"  WARNING: {w}")
for e in report.errors:
    print(f"  ERROR: {e}")
```

---

## 步骤 5：测试

### 手动测试

您可以直接运行流程来查看正在运行的块。在`user_data/shared/flows/`中创建测试流程文件。

```yaml
# user_data/shared/flows/test_hello.flow.yaml

flow_id: test_hello
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "Alice"
    output: greeting
```

### Python 单元测试

该块的`run()`函数是一个简单的Python函数，您可以直接调用和测试。

```python
# tests/test_hello.py

import sys
sys.path.insert(0, "ecosystem/my_pack/backend")

from blocks.hello import run

def test_hello_basic():
    result = run({"name": "Alice"})
    assert result == {"message": "Hello, Alice!"}

def test_hello_default():
    result = run({})
    assert result == {"message": "Hello, World!"}
```

---

## 步骤 6：从 Flow 调用

Pack 块是从 Flow 定义中调用的。

### 流文件放置

| Path | Purpose |
|------|------|
| `user_data/shared/flows/` | Share Flow. Used for wiring across multiple packs |
| `ecosystem/<pack_id>/backend/flows/` | Pack-specific Flow |

### 流定义示例

```yaml
# user_data/shared/flows/greet.flow.yaml

flow_id: greet
inputs:
  name: string
outputs:
  greeting: object

phases:
  - main

steps:
  - id: call_hello
    phase: main
    priority: 50
    type: python_file_call
    owner_pack: my_pack
    file: blocks/hello.py
    input:
      name: "${ctx.name}"
    output: greeting
```

### 步骤的关键字段

| Field | Required | Description |
|-----------|------|------|
| `id` | ✅ | Step ID (unique within the Flow) |
| `phase` | ✅ | Affiliation phase |
| `priority` | Optional | Execution priority (ascending order; default 100) |
| `type` | ✅ | `python_file_call` |
| `owner_pack` | Optional | Owned Pack ID |
| `file` | ✅ | Relative path of executable file |
| `input` | Optional | Input data (variable expansion possible with `${ctx.key}`) |
| `output` | Optional | Output destination context key |
| `timeout_seconds` | Optional | Timeout seconds (default 60, maximum 120) |

### 变量扩展

您可以使用 `${ctx.key}` 引用上下文中的值。嵌套引用 (`${ctx.user.id}`) 也是可能的。如果引用不存在，则为 `null`。

> 有关 Flow 定义的详细信息，请参阅[Flow definition section of pack-development.md](./pack-development.md#流程定义)。

---

## 基础模块的利用

Rumi AI OS的核心运行时提供了Pack开发常用的基础模块。下面我们将介绍各个模块的基本用法。

### 结构化日志

`core_runtime.logging_utils`模块支持JSON格式的结构化日志输出。

```python
from core_runtime.logging_utils import get_structured_logger, CorrelationContext

logger = get_structured_logger("rumi.pack.my_pack")

def run(input_data, context=None):
    logger.info("Processing request", pack_id="my_pack", flow_id=context.get("flow_id"))

    # correlation_id でリクエスト追跡
    with CorrelationContext(correlation_id=context.get("flow_id", "unknown")):
        logger.info("Step started")
        # ... 処理 ...
        logger.info("Step completed")

    return {"status": "ok"}
```

`get_structured_logger()` 是一个缓存工厂函数，它返回相同名称的相同实例。您可以使用 `bind()` 方法创建具有固定公共上下文的记录器。

```python
ctx_logger = logger.bind(pack_id="my_pack", flow_id="main_flow")
ctx_logger.info("Step 1")  # pack_id, flow_id が自動付与
ctx_logger.info("Step 2")  # pack_id, flow_id が自動付与
```

输出格式可以通过环境变量`RUMI_LOG_FORMAT`（`json`或`text`）控制。

> 详情请参阅[the structured log settings section of operations.md](./operations.md#structured-log-settings)。

### 统一错误

`core_runtime.error_messages`模块提供统一的错误编码方案(`RUMI-{CATEGORY}-{NUMBER}`)。

```python
from core_runtime.error_messages import format_error, RumiError
from core_runtime.error_messages import VAL_EMPTY_VALUE, PACK_ID_INVALID

def run(input_data, context=None):
    name = input_data.get("name")
    if not name:
        raise format_error(VAL_EMPTY_VALUE, field_name="name")
        # => RumiError: RUMI-VAL-001: name must not be empty

    return {"message": f"Hello, {name}!"}
```

`format_error()` 将参数嵌入到 `ErrorCode` 常量模板中并返回 `RumiError` 实例。 `RumiError` 具有 `.code`、`.message`、`.suggestion`、`.details` 属性，并且可以使用 `.to_dict()` 转换为 JSON 可序列化字典。

主要错误代码类别：`AUTH`（身份验证）、`NET`（网络）、`FLOW`（流程）、`PACK`（包管理）、`CAP`（能力）、`VAL`（验证）、`SYS`（系统）。

> 详情请参阅[the error code reference section of operations.md](./operations.md#error-code-reference)。

### 类型注释

`core_runtime.types`模块提供`NewType`来指定类型级别ID字符串的使用。

```python
from core_runtime.types import PackId, FlowId, JsonDict, Result

def process_pack(pack_id: PackId, flow_id: FlowId) -> JsonDict:
    return {"pack_id": pack_id, "flow_id": flow_id}

# Result[T] で成功/失敗を表現
def load_data(key: str) -> Result[JsonDict]:
    try:
        data = fetch(key)
        return Result(success=True, value=data)
    except Exception as e:
        return Result(success=False, error=str(e))
```

可用类型：`PackId`、`FlowId`、`CapabilityName`、`HandlerKey`、`StoreKey`（NewType）、`JsonValue`、`JsonDict`（类型别名）、`Result[T]`（通用结果类型）、`Severity`（日志严重性枚举类型）。

> 详情请参阅[the type hints/validation section of pack-development.md](./pack-development.md#类型提示验证)。

### 已弃用的 API 管理

`core_runtime.deprecation`模块中的`deprecated`装饰器允许您系统地管理已弃用的API。

```python
from core_runtime.deprecation import deprecated

@deprecated(since="1.0", removed_in="2.0", alternative="new_handler")
def old_handler(input_data, context=None):
    """この関数は非推奨です。"""
    return new_handler(input_data, context)
```

当给定装饰器时，调用函数时会发出 `DeprecationWarning`，并自动在 `DeprecationRegistry` 中注册。还支持`async def`。

警告行为可以通过环境变量`RUMI_DEPRECATION_LEVEL` (`warn` / `error` / `silent` / `log`) 来控制。

> 详情请参阅[the deprecation warning level control section of operations.md](./operations.md#deprecation-warning-level-control)。

---

## 后续步骤

本指南解释了创建最小包的步骤。有关更多高级功能，请参阅下面的 pack-development.md 部分。

- **功能处理程序的实现** → [pack-development.md“包括功能处理程序”](./pack-development.md#includes-capability-handler)
- **创建流量修改器** → [pack-development.md "流量修改器"](./pack-development.md#流量调节剂)
- **网络访问设置** → [pack-development.md "网络访问"](./pack-development.md#网络接入)
- **Inter Pack 合作** → [pack-development.md "Inter Pack 合作模式"](./pack-development.md#跨包装合作模式)
- **使用 Secrets** → [pack-development.md“使用 Secrets（来自 Pack）”](./pack-development.md#使用秘密（来自包）)
- **商店 API** → [pack-development.md“商店 API（通过功能）”](./pack-development.md#存储-api（通过功能）)
- **原始端点的定义** → [pack-development.md“包特定端点”](./pack-development.md#特定于包的端点-routesjson)
- **计划执行** → [pack-development.md“流程定义”](./pack-development.md#流程定义)中的计划执行部分
- **错误处理** → [pack-development.md“错误处理最佳实践”](./pack-development.md#错误处理最佳实践)
