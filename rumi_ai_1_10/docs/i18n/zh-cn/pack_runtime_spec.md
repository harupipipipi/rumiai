<!-- docs-i18n-links:start -->
[EN](../../pack_runtime_spec.md) | [JP](../ja/pack_runtime_spec.md) | [KR](../ko/pack_runtime_spec.md) | [CN](./pack_runtime_spec.md)
<!-- docs-i18n-links:end -->

# 打包运行时规范

## 概述

Ecosystem.json 的 `runtime` 部分允许 Pack 以声明方式指定其运行时环境。
这使得使用 Python 以外的语言（Rust、Go、Node.js 等）实现的 Pack 也可以工作。

## 架构

```json
{
  "runtime": {
    "type": "python_host | python_docker | binary | command | wasm",
    "language": "python | rust | go | nodejs | c | cpp | ...",
    "protocol": "stdio_json",
    "docker": {
      "image": "python:3.11-slim",
      "build_command": null,
      "network": false
    },
    "host_requirements": {
      "min_memory_mb": null,
      "gpu": false
    }
  }
}
```

## 字段定义

### `type`（必填）

执行方法。对应于 FunctionEntry 的`calling_convention`。

|价值|描述 |
|----|------|
| `python_host`|作为主机上的 Python 子进程运行。需要`RUMI_ALLOW_HOST_EXECUTION=1`。 |
| `python_docker`|在 Docker 容器内运行 Python（相当于默认行为）。 |
| `binary`|运行编译的二进制文件。通过 stdin/stdout JSON 协议进行通信。 |
| `command`|执行任意命令。通过 stdin/stdout JSON 协议进行通信。 |
| `wasm`|在 WebAssembly 运行时上运行（用于将来的扩展，目前未实现）。 |

### `language`（可选）

开发语言。仅供参考，不影响执行方法。

### `protocol`（可选）

通信协议。目前仅支持`stdio_json`。

- `stdio_json`：将 JSON 传递到 stdin 并从 stdout 接收 JSON

### `docker`（可选）

设置 Docker 环境。

|领域|类型 |默认|描述 |
|-----------|-----|-----------|------|
| `image`|字符串| `python:3.11-slim` | Docker 镜像名称 |
| `build_command`|字符串\|空|空 |构建命令（用于将来的扩展）|
| `network`|布尔 |假 |允许网络访问容器 |

### `host_requirements`（可选）

主机环境要求。

|领域|类型 |默认|描述 |
|-----------|-----|-----------|------|
| `min_memory_mb`|整数\|null |空 |最小内存请求 (MB) |
| `gpu`|布尔 |假 |需要 GPU |

## 向后兼容性

- 如果未指定`runtime`部分，则运行时间由现有逻辑确定：
  - 带有`core_`前缀的包 → `block` / `kernel`
  - 其他 → `subprocess`（Python 子进程）
- 如果仅指定`runtime.type`，它将以最小的配置工作。
- **优先级**：functions/\<func\>/manifest.json 中的`calling_convention` > Ecosystem.json 中的`runtime.type`

## 示例

### 用 Rust 实现的二进制包

```json
{
  "pack_id": "my_rust_pack",
  "pack_identity": "github:myorg/my-rust-pack",
  "version": "1.0.0",
  "vocabulary": { "types": [] },
  "runtime": {
    "type": "binary",
    "language": "rust",
    "protocol": "stdio_json"
  }
}
```

### 带 Docker 镜像的 Python 包

```json
{
  "pack_id": "my_ml_pack",
  "pack_identity": "github:myorg/my-ml-pack",
  "version": "1.0.0",
  "vocabulary": { "types": [] },
  "runtime": {
    "type": "python_docker",
    "language": "python",
    "docker": {
      "image": "pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime",
      "network": false
    },
    "host_requirements": {
      "gpu": true
    }
  }
}
```

### Python Pack 直接在主机上运行

```json
{
  "pack_id": "my_host_pack",
  "pack_identity": "github:myorg/my-host-pack",
  "version": "1.0.0",
  "vocabulary": { "types": [] },
  "runtime": {
    "type": "python_host",
    "language": "python"
  }
}
```

## 标准输入/标准输出 JSON 协议

二进制/命令类型的包使用 stdin/stdout JSON 协议进行通信。

### 输入（标准输入）

```json
{
  "context": {
    "principal_id": "pack:caller_pack_id",
    "pack_id": "my_rust_pack",
    "function_id": "process_data",
    "request_id": "req-abc123",
    "ts": "2025-01-15T10:30:00Z"
  },
  "args": {
    "input_data": "hello world"
  }
}
```

### 输出（标准输出）

关于成功：
```json
{
  "result": "processed: hello world"
}
```

出错时：
```json
{
  "error": "Invalid input format",
  "error_type": "validation_error"
}
```

## 内部处理流程

1. `registry.py`的`_load_functions()`读取ecosystem.json的`runtime`部分
2. 默认情况下将包级运行时信息注入到每个函数的清单中：
   - `runtime.type` → `manifest["calling_convention"]`
   - `runtime.docker.image` → `manifest["docker_image"]`
   - `runtime.type == "python_host"` → `manifest["host_execution"] = True`
   - `runtime.type in ("binary", "command")` → `manifest["runtime"] = type`
3.`FunctionRegistry._entry_from_kwargs()`从清单构造FunctionEntry
4.calling_convention 处的 `_dispatch_by_calling_convention()` 或 `capability_executor.py` 分支

如果在单个函数清单中指定了`calling_convention`，则优先。
