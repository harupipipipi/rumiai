<!-- docs-i18n-links:start -->
[EN](../../pack_runtime_spec.md) | [JP](../ja/pack_runtime_spec.md) | [KR](./pack_runtime_spec.md) | [CN](../zh-cn/pack_runtime_spec.md)
<!-- docs-i18n-links:end -->

# Pack Runtime Specification

## 개요

ecosystem.json의 `runtime` 섹션을 사용하면 Pack이 자체 런타임 환경을 선언적으로 지정할 수 있습니다.
이렇게하면 Python 이외의 언어 (Rust, Go, Node.js 등)로 구현 된 팩이 작동 할 수 있습니다.

## 스키마

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

## 필드 정의

### `type` (필수)

실행 방식. FunctionEntry의 `calling_convention`에 해당합니다.

| 값 | 설명 |
|----|------|
| `python_host` | 호스트에서 Python 서브 프로세스로 실행. `RUMI_ALLOW_HOST_EXECUTION=1` 필요. |
| `python_docker` | Docker 컨테이너에서 Python을 실행합니다(기본 동작과 동일). |
| `binary` | 컴파일된 바이너리를 실행. stdin/stdout JSON 프로토콜로 통신. |
| `command` | 모든 명령을 실행합니다. stdin/stdout JSON 프로토콜로 통신. |
| `wasm` | WebAssembly 런타임에서 실행(향후 확장용. 현재는 구현되지 않음). |

### `language` (선택 사항)

개발 언어. 정보 용도만으로 실행 방식에는 영향을 주지 않습니다.

### `protocol` (선택 사항)

통신 프로토콜. 현재는 `stdio_json`만 지원합니다.

- `stdio_json`: stdin에 JSON을 전달하고 stdout에서 JSON을 받습니다.

### `docker` (선택 사항)

Docker 환경 설정.

| 필드 | 유형 | 기본 | 설명 |
|-----------|-----|-----------|------|
| `image` | 문자열 | `python:3.11-slim` | Docker 이미지 이름 |
| `build_command` | string\|null | null | 빌드 명령(향후 확장용) |
| `network` | boolean | false | 컨테이너에 네트워크 액세스를 허용할지 |

### `host_requirements` (선택 사항)

호스트 환경의 요청.

| 필드 | 유형 | 기본 | 설명 |
|-----------|-----|-----------|------|
| `min_memory_mb` | integer\|null | null | 최소 메모리 요청(MB) |
| `gpu` | boolean | false | GPU 필요 |

## 후방 호환성

- `runtime` 섹션이 지정되지 않으면 기존 로직에서 런타임이 결정됩니다.
  - `core_` 접두사가 있는 Pack → `block` / `kernel`
  - 기타 → `subprocess`(Python 서브프로세스)
- `runtime.type`만 지정하면 최소한의 구성으로 동작합니다.
- **우선순위**: functions/\<func\>/manifest.json의 `calling_convention` > ecosystem.json의 `runtime.type`

## 샘플

### Rust로 구현 된 binary Pack

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

### Docker 이미지가있는 Python Pack

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

### Host에서 직접 실행 Python Pack

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

## stdin/stdout JSON 프로토콜

binary / command 유형의 팩은 stdin / stdout JSON 프로토콜을 통해 통신합니다.

### 입력 (stdin)

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

### 출력 (stdout)

성공시:
```json
{
  "result": "processed: hello world"
}
```

오류시:
```json
{
  "error": "Invalid input format",
  "error_type": "validation_error"
}
```

## 내부 처리 흐름

1. `registry.py`의 `_load_functions()`이 ecosystem.json의 `runtime` 섹션을 읽습니다.
2. 각 function 의 manifest 에 Pack 레벨의 런타임 정보를 디폴트로 주입:
   - `runtime.type` → `manifest["calling_convention"]`
   - `runtime.docker.image` → `manifest["docker_image"]`
   - `runtime.type == "python_host"` → `manifest["host_execution"] = True`
   - `runtime.type in ("binary", "command")` → `manifest["runtime"] = type`
3. `FunctionRegistry._entry_from_kwargs()` 가 manifest 로부터 FunctionEntry 를 구축
4. `capability_executor.py`의 `_dispatch_by_calling_convention()`이 calling_convention으로 분기

개별 function manifest에서 `calling_convention`를 지정하면 그 쪽이 우선합니다.
