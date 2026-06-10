<!-- docs-i18n-links:start -->
[EN](../../pack_development_guide.md) | [JP](../ja/pack_development_guide.md) | [KR](../ko/pack_development_guide.md) | [CN](./pack_development_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Pack 开发指南

> **旧文档**：保留以供兼容性参考。新参考文献应优先于[pack-development.md](./pack-development.md)和[pack-development-guide.md](./pack-development-guide.md)。

最后更新: 2026-03-23

本文档是开发 Rumi AI OS Pack 的综合指南。我们涵盖 Pack 概述、结构、生命周期、权限系统、Docker 隔离和开发工作流程。

---

## 1.什么是Pack？

Pack是Rumi AI OS的功能扩展单元。包在操作系统本身（内核）提供的核心功能之上添加了独特的功能。

一个包可以包含以下元素：

- **函数**：可以通过API调用的处理单元（JSON输入→JSON输出）
- **组件**：UI组件和数据模型
- **路由**：HTTP 端点定义
- **流程**：结合多种功能的工作流程

包由名为`ecosystem.json`的清单文件定义。内核读取该文件，将 Pack 中的函数注册到 FunctionRegistry，并使它们可执行。

---

## 2.包结构

### 2.1 目录结构

```
my_pack/
├── ecosystem.json          # Pack マニフェスト（必須）
├── functions/
│   ├── my_function/
│   │   ├── main.py         # Python Function のエントリーポイント
│   │   └── ...
│   └── my_binary_function/
│       ├── my_binary        # コンパイル済みバイナリ
│       └── ...
├── components/
│   └── ...
├── routes/
│   └── ...
└── flows/
    └── my_flow.flow.yaml
```

### 2.2 Ecosystem.json 中的所有字段

```json
{
  "pack_id": "my_pack",
  "pack_identity": "vendor:user/pack-name",
  "version": "1.0.0",
  "metadata": {
    "name": "My Pack",
    "description": "Pack の説明",
    "author": "Author Name",
    "license": "MIT",
    "is_core_pack": false
  },
  "vocabulary": {
    "types": []
  },
  "dependencies": {},
  "components": {},
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

|领域 |类型 |必填 |描述 |
|-----------|-----|------|------|
|包ID |字符串| ✅ |包唯一标识符|
|包身份 |字符串| — |供应商的正式标识符：用户/名称格式 |
|版本 |字符串| ✅ |语义版本控制 |
|元数据.名称 |字符串| ✅ |人类可读的包名称 |
|元数据.描述 |字符串| — |包说明 |
|元数据.作者 |字符串| — |作者姓名 |
|元数据.许可证 |字符串| — |许可证|
|元数据.is_core_pack |布尔 | — |是 core_pack （通常为 false） |
|词汇.类型 |数组| — |词汇类型定义 |
|依赖关系 |对象| — |其他依赖于 | 的包
|组件|对象| — |组件定义|
|运行时|对象| — |运行时设置（对于多语言包，请参阅 multilang_pack_guide.md 了解详细信息）|

### 2.3 函数清单

每个函数都在 Ecosystem.json 的 `functions` 部分或 `functions/<function_id>/` 目录中的清单中定义。

函数清单中的关键字段：

|领域 |类型 |描述 |
|-----------|-----|------|
|描述 |字符串|功能说明|
|运行时|字符串| §鲁米§0§ / §鲁米§1§ / §鲁米§2§ |
|主要|字符串|二进制相对路径（当运行时=二进制时）|
|命令|数组[字符串] |执行命令（当runtime=command时）|
|入口点 |字符串| Python 入口点（例如`"main.py:run"`）|
|调用约定 |字符串|执行方法（后述）|
|主机执行 |布尔 |直接在主机上执行 |
|需要 |数组[字符串] |所需权限|
|来电者要求 |数组[字符串] |请求调用者的权限 |
|输入模式 |对象|输入 JSON 架构 |
|输出模式 |对象|输出 JSON 架构 |
|标签 |数组[字符串] |搜索标签 |
|词汇别名 |数组[字符串] |词汇别名 |
|授予配置|对象|授予设置（超时等）|
| docker_image |字符串| Docker 镜像（默认：python:3.11-slim）|
|扩展 |对象|扩展元数据 |

---

## 3. 包生命周期

包通过以下生命周期进行管理：

### 3.1 扫描

内核的 PackImporter 扫描 Pack 目录并读取`ecosystem.json`。检查每个包的结构并发现其功能。

### 3.2 批准

ApprovalManager 管理 Pack 的批准状态。无法执行未经批准的包中的功能。 core_pack（其中`pack_id`以`core_`前缀开头）会自动获得批准。

### 3.3 加载

批准的 Pack 的功能将在 FunctionRegistry 中注册。对于每个函数：

1.构造FunctionEntry（从manifest中读取字段）
2. 根据运行时间求解`main_py_path` / `main_binary_path` / `command`
3. 路径遍历验证（二进制路径是否适合function_dir？）
4. 向 FunctionRegistry 注册（qualified_name = `pack_id:function_id`）
5. 注册vocab_aliases

### 3.4 执行

CapabilityExecutor 负责执行。执行流程如下：

1. **FunctionRegistry解析**：通过permission_id或qualified_name搜索FunctionEntry
2. **信任检查**：验证 TrustStore 中的 sha256 哈希（core_pack 除外）
3. **Grant check**：验证GrantManager中的主体×权限
4. **calling_convention分支**：根据Function的执行方法分支到合适的handler
5. **审计日志**：将所有执行结果记录在审计日志中

---

## 4. core_pack 与生态系统包

### 核心包

- `pack_id` 以`core_` 前缀开头
- 包含在内核中
- 简化信任检查（记录 sha256，但省略 TrustStore 中的验证）
- 自动批准
- 放置在`core_runtime/core_pack/`目录中

### 生态系统包

- 由第三方或用户开发的包
- 需要信任检查（sha256必须在TrustStore中注册）
- 需要明确批准
- 放置在`ecosystem/`目录中

---

## 5. 功能、组件、路由和流程之间的区别

### 函数

它是最基本的处理单元。接受 JSON 输入并返回 JSON 输出。可以用 Python、编译的二进制文件或命令来实现。

### 组件

UI 组件和数据模型的定义。提供可在 Pack 之间共享的结构化数据。

### 路线

HTTP 端点定义。它注册到 pack_api_server 并提供外部可访问的 API。

### 流量

这是一个结合了多种功能的工作流程。在 YAML 中定义并由 Flow Engine 执行。它可以包括条件分支、循环和错误处理。

---

## 6. 能力如何发挥作用

Rumi AI OS具有三层权限系统：

### 6.1 信任

TrustStore 管理处理程序文件的 sha256 哈希值。如果注册的哈希值和运行时哈希值不匹配，则执行将被拒绝。这可以检测文件篡改。

### 6.2 格兰特

GrantManager 管理谁 (principal_id) 和 (permission_id) 可以做什么。 grant_config 允许细粒度控制，例如超时。

### 6.3 速率限制

限制特定permission_id（例如`secrets.get`）每分钟的调用次数。默认为 60 次/分钟/本金。

### 6.4 能力流程

```
リクエスト
  → FunctionRegistry 解決
  → Trust チェック（sha256 検証）
  → Grant チェック（principal × permission）
  → Rate Limit チェック（該当する場合）
  → calling_convention に応じた実行
  → 監査ログ記録
  → CapabilityResponse 返却
```

---

## 7.calling_convention（执行方法）

Calling_Convention 决定了 Function 的执行方式。

|调用约定 |描述 |目标语言 |
|-------------------|------|---------|
|内核|直接从内核内部调用 | — |
|子流程|在Python子进程中运行 |蟒蛇 |
|块| core_pack | 基于 DI 的处理程序蟒蛇 |
| python_主机 |在主机进程上运行Python |蟒蛇 |
| python_docker |在 Docker 容器内运行 Python |蟒蛇 |
|二进制|运行已编译的二进制文件（stdin/stdout JSON）| Rust、Go、C/C++ 等 |
|命令|使用命令列表启动进程（stdin/stdout JSON）| Node.js、Ruby、任意 |

`binary`和`command`是多语言包开发的核心。详情请参考【多语言包开发指南】(./multilang_pack_guide.md)。

---

## 8. Docker 隔离如何工作

### 8.1 概述

默认情况下，生态系统包（非 core_pack）中的 Python 函数在 Docker 容器中运行。这可以防止对主机系统产生任何影响。

### 8.2 Docker执行流程

1.将输入JSON写出到临时文件
2.使用DockerRunBuilder构建容器
3. 使用`/function:ro`挂载function_dir（只读）
4. 使用`/input.json:ro`挂载输入JSON文件
5. 设置环境变量`RUMI_PACK_ID`、`RUMI_FUNCTION_ID`
6. 在容器内运行Python运行器脚本
7. 从标准输出读取 JSON
8.超时时用`docker kill`强行停止容器

### 8.3 如果 Docker 不可用

如果Docker不可用，它将回退到主机上的子进程（将输出警告日志）。

### 8.4 二进制/命令函数执行

`binary`和`command`中带有calling_convention的函数作为子进程在主机上运行，而不是在Docker中运行。但是，在`host_execution=false`和`runtime != "python"`的情况下，将会发生作为安全违规的错误。

---

## 9. 开发→测试→分发工作流程

### 9.1 开发

1.创建Pack目录
2. 创建`ecosystem.json`
3. 实现`functions/`目录下的函数
4. 根据需要创建流、组件和路由

### 9.2 测试

函数遵循 stdin/stdout 的 JSON 协议，因此您可以直接在命令行上测试它：

```bash
# Python Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | python main.py

# バイナリ Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | ./my_binary

# コマンド Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | node index.js
```

### 9.3 分布

1. 将 Pack 目录作为 zip 分发或发布到 Git 存储库中
2. 用户被置于`ecosystem/`中
3.下次启动时内核扫描并注册
4. 未来将在市场上发行（D/E阶段）

---

## 10. 能力响应

每个函数调用的结果都作为 CapabilityResponse 返回。

```json
{
  "success": true,
  "output": { "任意のデータ": "..." },
  "error": null,
  "error_type": null,
  "latency_ms": 42.5
}
```

|领域 |类型 |描述 |
|-----------|-----|------|
|成功|布尔 |执行成功 |
|输出|任何|输出数据（JSON）|
|错误 |字符串/空 |错误信息 |
|错误类型 |字符串/空 |错误类型 |
|延迟毫秒 |浮动|执行所需的时间（毫秒）|

### 错误类型列表

|错误类型 |描述 |
|-----------|------|
|无效请求 |请求格式无效 |
|未找到处理程序 |未找到处理程序 |
|信任被拒绝 |信任检查失败 |
|授予拒绝 |授权检查失败 |
|速率限制 |已达到速率限制 |
|超时|超时|
|响应太大 |响应大小超出 (1MB) |
|函数执行错误 |函数执行期间出错 |
|无效的 json 输出 | stdout 不是有效的 JSON |
|未找到二进制文件 |找不到二进制文件 |
|安全违规 |安全违规（路径遍历等）|
|初始化错误 |初始化错误 |
|内部错误 |内部错误 |

---

## 相关文档

- [多语言包开发指南](./multilang_pack_guide.md) — 如何用Python以外的语言开发包
- [Pack 桌面应用程序开发指南](./pack_desktop_app_guide.md) — 如何开发桌面应用程序包
- [路线图](./roadmap.md) — Rumi AI OS整体规划
