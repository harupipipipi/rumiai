<!-- docs-i18n-links:start -->
[EN](../../multilang_pack_guide.md) | [JP](../ja/multilang_pack_guide.md) | [KR](../ko/multilang_pack_guide.md) | [CN](./multilang_pack_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 多语言包开发指南

最后更新: 2026-03-23

本文档是使用 Python 以外的语言（Rust、Go、Node.js、C/C++ 等）开发 Rumi AI OS Pack 的指南。包含 stdin/stdout JSON 协议的规范、教程和最佳实践。

---

## 1. 多语言包概述

Rumi AI OS的capability_executor.py实现了两个calling_conventions：`binary`和`command`。两者都使用通用协议：在 stdin 上传递 JSON 并从 stdout 读取 JSON。

这允许您以任何可以在 stdin/stdout 上读取和写入 JSON 的语言来实现 Pack 的函数。

### 二进制与命令

|特点 |二进制|命令|
|------|--------|---------|
|如何跑步 |直接运行编译好的二进制文件 |使用命令列表启动进程 |
|适合的语言 | Rust、Go、C、C++ | Node.js、Ruby、Python（不同版本）、shell 脚本 |
|指定 Ecosystem.json | §鲁米§0§，§鲁米§1§| §鲁米§2§，§鲁米§3§|
|函数输入字段 | §鲁米§0§| `command`（列表[str]）|
|路径遍历验证|是（验证二进制文件是否在 function_dir 中）|取决于命令 |

---

## 2.运行时部分规范

您可以通过向 Ecosystem.json 添加 `runtime` 部分来声明构建和运行多语言包所需的信息。

```json
{
  "pack_id": "my_rust_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Rust Pack",
    "description": "Rust で実装された Pack"
  },
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "target/release/my_binary"
    },
    "binary": "target/release/my_binary"
  }
}
```

### 运行时字段

|领域 |类型 |描述 |
|-----------|-----|------|
|类型 |字符串| §鲁米§0§ / §鲁米§1§ / §鲁米§2§ |
|构建命令 |字符串|构建命令 |
|构建.输出|字符串|构建工件路径 |
|二进制|字符串|要执行的二进制文件的路径（当 type=binary 时） |

---

## 3. stdin/stdout JSON 协议规范

### 3.1 输入（标准输入）

当内核启动该函数时，它将以下 JSON 传递到 stdin。

```json
{
  "context": {
    "principal_id": "user_abc123",
    "pack_id": "my_pack",
    "function_id": "my_function",
    "request_id": "req_xyz789",
    "ts": "2026-03-23T12:00:00Z"
  },
  "args": {
    "key": "value",
    "count": 42
  }
}
```

#### 上下文字段

|领域 |类型 |描述 |
|-----------|-----|------|
|主体 ID |字符串|发出请求的主体 ID（来自 UDS）|
|包ID |字符串|执行的Function所属Pack ID |
|函数 ID |字符串|要执行的函数的 ID |
|请求 ID |字符串|请求的唯一ID |
| ts |字符串|请求时间戳（ISO 8601，UTC）|

#### 参数字段

调用者指定的参数字典。内容因功能而异。遵循`input_schema`中定义的结构。

### 3.2 输出 (stdout) — 成功

函数将处理结果以 JSON 形式输出到 stdout。

```json
{
  "message": "Hello, Pack!",
  "processed_at": "2026-03-23T12:00:01Z"
}
```

输出 JSON 按原样存储在`CapabilityResponse.output`中。如果输出为空（没有写入标准输出），则`output` 变为`null`。

### 3.3 输出 (stderr) — 出错时

如果发生错误，则以非零退出代码退出。写入 stderr 的内容将记录为错误消息（最多前 500 个字符）。

```
# 正常終了: exit code 0 + stdout に JSON
# エラー:  exit code 1 + stderr にメッセージ
```

**重要**：还有一种方法可以将错误信息作为 JSON 输出到 stdout，但内核使用退出代码来确定成功/失败。对于非零退出代码，stdout 被忽略，stderr 被用作错误消息。

### 3.4 超时

|设置|价值|来源 |
|------|-----|--------|
|默认超时 | 30 秒 | §鲁米§0§|
|最大超时| 120 秒 | §鲁米§0§|
|最小超时 | 1 秒 | §鲁米§0§|
|定制|在函数清单的`grant_config.timeout`中指定 |

如果达到超时，进程将被终止，并返回`error_type: "timeout"`的 CapabilityResponse。

### 3.5 响应大小限制

标准输出上的输出必须小于或等于 **1 MB**（`MAX_RESPONSE_SIZE = 1 * 1024 * 1024` 字节）。如果超过，将导致`error_type: "response_too_large"`错误。

---

## 4.calling_convention：二进制详细信息

### 4.1 概述

该方法直接执行编译后的二进制文件。适用于Rust、Go、C、C++等语言。

### 4.2 执行流程

```
Kernel
  │
  ├─ 1. entry.main_binary_path の存在確認
  ├─ 2. パストラバーサル検証
  │     Path(binary_path).resolve().is_relative_to(func_dir)
  ├─ 3. タイムアウト取得
  ├─ 4. context + args の JSON 構築
  ├─ 5. subprocess.run([str(binary_path)],
  │       input=input_json,
  │       capture_output=True,
  │       text=True,
  │       timeout=timeout,
  │       cwd=str(func_dir))
  ├─ 6. exit code チェック
  │     ├─ 非ゼロ → エラー（stderr を使用）
  │     └─ ゼロ → stdout パース
  ├─ 7. stdout サイズチェック（1MB 制限）
  ├─ 8. stdout が空 → output=null
  └─ 9. JSON パース → CapabilityResponse(success=True, output=...)
```

### 4.3 Ecosystem.json配置示例

```json
{
  "pack_id": "my_rust_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Rust Pack",
    "description": "Rust で実装されたサンプル Pack"
  },
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "target/release/my_rust_function"
    }
  }
}
```

函数清单（在函数部分）：
```json
{
  "my_function": {
    "description": "サンプル Function",
    "runtime": "binary",
    "main": "my_binary",
    "calling_convention": "binary",
    "input_schema": {
      "type": "object",
      "properties": {
        "name": { "type": "string" }
      }
    },
    "grant_config": {
      "timeout": 30
    }
  }
}
```

### 4.4 安全

- **路径遍历预防**：验证二进制路径上`resolve()`的结果是否在`function_dir`之下。如果您尝试使用 `../../` 等进入 function_dir 之外，则会出现 `security_violation` 错误。
- **工作目录**：进程的 cwd 设置为`function_dir`。

---

## 5.calling_convention：命令详细信息

### 5.1 概述

此方法使用命令列表启动进程。适合解释型语言（Node.js、Ruby、不同版本的Python等）。

### 5.2 执行流程

使用与`binary`相同的stdin/stdout JSON协议。不同之处在于我们使用`entry.command`(List[str]) 作为处理命令而不是二进制路径。

### 5.3 Ecosystem.json 配置示例

```json
{
  "pack_id": "my_node_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Node.js Pack",
    "description": "Node.js で実装されたサンプル Pack"
  },
  "runtime": {
    "type": "command",
    "build": {
      "command": "npm install"
    }
  }
}
```

功能清单：
```json
{
  "my_function": {
    "description": "サンプル Function",
    "runtime": "command",
    "command": ["node", "index.js"],
    "calling_convention": "command",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": { "type": "string" }
      }
    }
  }
}
```

---

## 6. 安全限制

### 6.1 路径遍历预防（二进制）

`_execute_binary_function` 执行以下验证：

```python
func_dir = Path(entry.function_dir).resolve()
if not Path(binary_path).resolve().is_relative_to(func_dir):
    # security_violation エラー
```

请务必将二进制文件放置在 Pack 的 function_dir 中。通过符号链接或`../` 进行的转义会被检测到。

### 6.2 响应大小限制

如果 stdout 输出超过 1 MB，则响应将被丢弃并发生 `response_too_large` 错误。如果需要返回大量数据，请将其写入文件并返回路径，或者实现分页。

### 6.3 超时

该函数必须在最多 120 秒内完成。当达到超时时，该进程将被终止。对于需要较长执行时间的进程，请考虑异步模式（例如作业队列）。

### 6.4 环境变量

`RUMI_PACK_ID` 和 `RUMI_FUNCTION_ID` 作为环境变量传递给在 Docker 中执行的 Python 函数。这些不会传递给二进制/命令函数。从 stdin 的 `context` 获取必要的信息。

---

## 7. Rust 包教程

### 7.1 先决条件

- 安装 Rust 工具链（`rustup` + `cargo`）
- Rumi AI OS运行环境

### 7.2 项目创建

```bash
mkdir -p my_rust_pack/functions/hello
cd my_rust_pack/functions/hello
cargo init --name hello_pack
```

### 7.3 添加依赖包

§鲁米§0§：
```toml
[package]
name = "hello_pack"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

### 7.4 实施

§鲁米§0§：
```rust
use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Deserialize)]
struct Input {
    context: Context,
    args: serde_json::Value,
}

#[derive(Deserialize)]
struct Context {
    principal_id: String,
    pack_id: String,
    function_id: String,
    request_id: String,
    ts: String,
}

#[derive(Serialize)]
struct Output {
    message: String,
    greeted_by: String,
    principal: String,
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap_or_else(|e| {
        eprintln!("Failed to read stdin: {}", e);
        std::process::exit(1);
    });

    let parsed: Input = serde_json::from_str(&input).unwrap_or_else(|e| {
        eprintln!("Failed to parse input JSON: {}", e);
        std::process::exit(1);
    });

    let name = parsed.args.get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("World");

    let output = Output {
        message: format!("Hello, {}!", name),
        greeted_by: format!("{}:{}", parsed.context.pack_id, parsed.context.function_id),
        principal: parsed.context.principal_id,
    };

    println!("{}", serde_json::to_string(&output).unwrap());
}
```

### 7.5 构建

```bash
cargo build --release
```

### 7.6 测试

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_rust_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./target/release/hello_pack
```

预期输出：
```json
{"message":"Hello, Rumi!","greeted_by":"my_rust_pack:hello","principal":"test_user"}
```

### 7.7 生态系统.json

```json
{
  "pack_id": "my_rust_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Rust Pack",
    "description": "Rust で実装された Hello Pack"
  },
  "runtime": {
    "type": "binary",
    "build": {
      "command": "cargo build --release",
      "output": "functions/hello/target/release/hello_pack"
    }
  }
}
```

### 7.8 安置

通过将预构建的二进制文件复制或符号链接到 function_dir 中，将 Pack 目录放置在 Rumi AI OS 的`ecosystem/`中。

---

## 8. 打包教程

### 8.1 先决条件

- Go 安装（推荐 1.21 或更高版本）

### 8.2 项目创建

```bash
mkdir -p my_go_pack/functions/hello
cd my_go_pack/functions/hello
go mod init hello_pack
```

### 8.3 实施

§鲁米§0§：
```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "os"
)

type Context struct {
    PrincipalID string `json:"principal_id"`
    PackID      string `json:"pack_id"`
    FunctionID  string `json:"function_id"`
    RequestID   string `json:"request_id"`
    Ts          string `json:"ts"`
}

type Input struct {
    Context Context                `json:"context"`
    Args    map[string]interface{} `json:"args"`
}

type Output struct {
    Message   string `json:"message"`
    GreetedBy string `json:"greeted_by"`
    Principal string `json:"principal"`
}

func main() {
    data, err := io.ReadAll(os.Stdin)
    if err != nil {
        fmt.Fprintf(os.Stderr, "Failed to read stdin: %v", err)
        os.Exit(1)
    }

    var input Input
    if err := json.Unmarshal(data, &input); err != nil {
        fmt.Fprintf(os.Stderr, "Failed to parse input JSON: %v", err)
        os.Exit(1)
    }

    name := "World"
    if v, ok := input.Args["name"]; ok {
        if s, ok := v.(string); ok {
            name = s
        }
    }

    output := Output{
        Message:   fmt.Sprintf("Hello, %s!", name),
        GreetedBy: fmt.Sprintf("%s:%s", input.Context.PackID, input.Context.FunctionID),
        Principal: input.Context.PrincipalID,
    }

    enc := json.NewEncoder(os.Stdout)
    if err := enc.Encode(output); err != nil {
        fmt.Fprintf(os.Stderr, "Failed to encode output: %v", err)
        os.Exit(1)
    }
}
```

### 8.4 构建和测试

```bash
go build -o hello_pack .
echo '{"context":{"principal_id":"test_user","pack_id":"my_go_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./hello_pack
```

---

## 9. Node.js 包教程

### 9.1 先决条件

- 安装 Node.js（推荐 18+）

### 9.2 项目创建

```bash
mkdir -p my_node_pack/functions/hello
cd my_node_pack/functions/hello
npm init -y
```

### 9.3 实施

§鲁米§0§：
```javascript
'use strict';

process.stdin.setEncoding('utf8');

let inputData = '';

process.stdin.on('data', (chunk) => {
    inputData += chunk;
});

process.stdin.on('end', () => {
    try {
        const input = JSON.parse(inputData);
        const context = input.context || {};
        const args = input.args || {};

        const name = args.name || 'World';

        const output = {
            message: 'Hello, ' + name + '!',
            greeted_by: context.pack_id + ':' + context.function_id,
            principal: context.principal_id,
        };

        process.stdout.write(JSON.stringify(output));
    } catch (e) {
        process.stderr.write('Error: ' + e.message);
        process.exit(1);
    }
});
```

### 9.4 测试

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_node_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | node index.js
```

### 9.5 生态系统.json

```json
{
  "pack_id": "my_node_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Node.js Pack",
    "description": "Node.js で実装された Hello Pack"
  },
  "runtime": {
    "type": "command",
    "build": {
      "command": "npm install"
    }
  }
}
```

---

## 10.调试方法

### 10.1 命令行测试

所有多语言 Pack Functions 都遵循 stdin/stdout 协议，因此您可以直接在命令行上测试它们：

```bash
# テスト入力 JSON を作成
cat > /tmp/test_input.json << 'TESTEOF'
{
  "context": {
    "principal_id": "debug_user",
    "pack_id": "my_pack",
    "function_id": "my_func",
    "request_id": "debug_001",
    "ts": "2026-03-23T00:00:00Z"
  },
  "args": {
    "name": "Debug"
  }
}
TESTEOF

# バイナリ Function をテスト
cat /tmp/test_input.json | ./my_binary

# コマンド Function をテスト
cat /tmp/test_input.json | node index.js

# 出力を jq で整形
cat /tmp/test_input.json | ./my_binary | jq .
```

### 10.2 检查退出代码

```bash
cat /tmp/test_input.json | ./my_binary
echo "Exit code: $?"
```

### 10.3 检查标准错误

```bash
cat /tmp/test_input.json | ./my_binary 2>/tmp/stderr.log
cat /tmp/stderr.log
```

### 10.4 模拟超时

```bash
timeout 30 sh -c 'cat /tmp/test_input.json | ./my_binary'
echo "Exit code: $?"
```

### 10.5 检查响应大小

```bash
cat /tmp/test_input.json | ./my_binary | wc -c
# 1048576 (1MB) 以下であることを確認
```

---

## 11. 最佳实践

### 11.1 错误处理

- 当读取 stdin 失败时，将消息写入 stderr 并以退出代码 1 退出。
- 同样，当出现 JSON 解析错误时，stderr + 退出代码 1
- 处理期间的错误还包括 stderr + 非零退出代码
- 避免恐慌/崩溃（Rust 建议错误处理而不是`unwrap()`）

### 11.2 输出

- 如果成功，将有效的 JSON 一行输出到 stdout
- 不要将额外的换行符或日志混合到标准输出中（使用标准错误）
- 将调试输出与标准输出混合会导致 JSON 解析错误
- 保持输出大小低于 1 MB

### 11.3 性能

- 缩短启动时间（超时包括启动时间）
- 大量数据以批量方式处理，而不是流式处理（stdin 一次性全部传递）
- Rust/Go 通过静态链接优化二进制大小

### 11.4 安全

- 不要从环境变量中读取敏感信息（从上下文中获取）
- 文件访问仅限于 function_dir
- 外部网络访问声明适当的权限并要求
- 不要相信用户输入（args）。执行验证

### 11.5 跨平台

- Rust：`cross` 在板条箱中交叉编译
- Go：`GOOS` / `GOARCH` 使用环境变量进行交叉编译
- Node.js：注意平台相关的本机模块
- 不要在二进制名称中包含扩展名（在非 Windows 上不需要）

### 11.6 测试

- 在 CI/CD 中准备测试输入 JSON 并将其与预期输出进行比较
- 测试多个参数模式
- 还测试边缘情况，例如空参数、格式错误的 JSON 和大输入
- 确保退出代码正确

---

## 附录 A：协议快速参考

```
┌─────────────────────────────────────────────────┐
│                    Kernel                        │
│                                                  │
│  1. FunctionEntry を取得                          │
│  2. Trust/Grant 検証                              │
│  3. input_json = {"context": {...}, "args": {...}}│
│  4. subprocess.run(                              │
│       [binary_path] or command,                  │
│       input=input_json,                          │
│       timeout=30~120s,                           │
│       cwd=function_dir                           │
│     )                                            │
│  5. exit code → 0: 成功 / 非0: エラー             │
│  6. stdout (≤1MB) → JSON parse → output          │
│  7. stderr → エラーメッセージ (先頭500文字)         │
│                                                  │
└──────────┬──────────────────────────┬─────────────┘
           │ stdin (JSON)             │ stdout (JSON)
           ▼                         │
┌─────────────────────────────────────────────────┐
│              Function (任意の言語)                 │
│                                                  │
│  1. stdin から全文読み取り                         │
│  2. JSON パース → context, args                   │
│  3. 処理実行                                      │
│  4. 結果を JSON で stdout に出力                   │
│  5. exit code 0 で終了                            │
│                                                  │
│  エラー時:                                        │
│  1. stderr にメッセージ                            │
│  2. 非ゼロ exit code で終了                        │
└─────────────────────────────────────────────────┘
```

---

## 附录B：CapabilityResponse字段对应表

|函数行为 |能力响应 |
|----------------|-------------------|
|退出 0 + JSON 到标准输出 | §鲁米§0§|
|退出 0 + 标准输出为空 | §鲁米§0§|
| exit 0 + stdout 无效 JSON | §鲁米§0§|
|退出 0 + 标准输出 > 1MB | §鲁米§0§|
|退出非零 | §鲁米§0§|
|超时 | §鲁米§0§|
|找不到二进制文件 | §鲁米§0§|
|路径遍历检测| §鲁米§0§|

---

## 相关文档

- [包开发指南](./pack-development.md) — 包概述
- [示例代码：Rust Pack](examples/rust_pack/) — Rust Pack 的完整示例
- [示例代码：Go Pack](examples/go_pack/) — 完整的 Go Pack 示例
- [示例代码：Node.js Pack](examples/node_pack/) — Node.js Pack 的完整示例
