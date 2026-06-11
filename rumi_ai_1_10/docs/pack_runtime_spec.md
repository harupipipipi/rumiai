<!-- docs-i18n-links:start -->
[EN](./pack_runtime_spec.md) | [JP](./i18n/ja/pack_runtime_spec.md) | [KR](./i18n/ko/pack_runtime_spec.md) | [CN](./i18n/zh-cn/pack_runtime_spec.md)
<!-- docs-i18n-links:end -->

# Pack Runtime Specification

## Overview

The `runtime` section of ecosystem.json allows Packs to declaratively specify their runtime environment.
This allows Packs implemented in languages other than Python (Rust, Go, Node.js, etc.) to work.

## Schema

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

## Field definition

### `type` (required)

Execution method. Corresponds to `calling_convention` of FunctionEntry.

| Value | Description |
|----|------|
| `python_host` | Runs as a Python subprocess on the host. `RUMI_ALLOW_HOST_EXECUTION=1` required. |
| `python_docker` | Run Python inside a Docker container (equivalent to default behavior). |
| `binary` | Run compiled binary. Communication via stdin/stdout JSON protocol. |
| `command` | Execute any command. Communication via stdin/stdout JSON protocol. |
| `wasm` | Runs on WebAssembly runtime (for future expansion, not implemented at this time). |

### `language` (optional)

development language. It is for informational purposes only and does not affect the execution method.

### `protocol` (optional)

communication protocol. Currently only `stdio_json` is supported.

- `stdio_json`: Pass JSON to stdin and receive JSON from stdout

### `docker` (optional)

Setting up the Docker environment.

| Field | Type | Default | Description |
|-----------|-----|-----------|------|
| `image` | string | `python:3.11-slim` | Docker image name |
| `build_command` | string\|null | null | Build command (for future expansion) |
| `network` | boolean | false | Allow network access to container |

### `host_requirements` (optional)

Host environment requirements.

| Field | Type | Default | Description |
|-----------|-----|-----------|------|
| `min_memory_mb` | integer\|null | null | Minimum memory request (MB) |
| `gpu` | boolean | false | GPU required |

## Backward compatibility

- If the `runtime` section is unspecified, the runtime is determined by existing logic:
  - Pack with `core_` prefix → `block` / `kernel`
  - Others → `subprocess` (Python subprocess)
- If only `runtime.type` is specified, it will work with minimal configuration.
- **Priority**: `calling_convention` in functions/\<func\>/manifest.json > `runtime.type` in ecosystem.json

## Sample

### binary Pack implemented in Rust

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

### Python Pack with Docker image

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

### Python Pack running directly on the host

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

## stdin/stdout JSON protocol

Packs of type binary / command communicate using the stdin/stdout JSON protocol.

### Input (stdin)

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

### Output (stdout)

On success:
```json
{
  "result": "processed: hello world"
}
```

On error:
```json
{
  "error": "Invalid input format",
  "error_type": "validation_error"
}
```

## Internal processing flow

1. `_load_functions()` of `registry.py` reads the `runtime` section of ecosystem.json
2. Inject pack-level runtime information into each function's manifest as default:
   - `runtime.type` → `manifest["calling_convention"]`
   - `runtime.docker.image` → `manifest["docker_image"]`
   - `runtime.type == "python_host"` → `manifest["host_execution"] = True`
   - `runtime.type in ("binary", "command")` → `manifest["runtime"] = type`
3. `FunctionRegistry._entry_from_kwargs()` constructs FunctionEntry from manifest
4. `_dispatch_by_calling_convention()` of `capability_executor.py` branches at calling_convention

If `calling_convention` is specified in an individual function manifest, that takes precedence.
