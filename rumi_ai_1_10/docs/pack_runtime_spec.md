# Pack Runtime Specification

## 概要

ecosystem.json の `runtime` セクションにより、Pack が自身のランタイム環境を宣言的に指定できます。
これにより、Python 以外の言語（Rust, Go, Node.js 等）で実装された Pack が動作可能になります。

## スキーマ

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

## フィールド定義

### `type` (必須)

実行方式。FunctionEntry の `calling_convention` に対応します。

| 値 | 説明 |
|----|------|
| `python_host` | ホスト上で Python サブプロセスとして実行。`RUMI_ALLOW_HOST_EXECUTION=1` が必要。 |
| `python_docker` | Docker コンテナ内で Python を実行（デフォルト動作と同等）。 |
| `binary` | コンパイル済みバイナリを実行。stdin/stdout JSON プロトコルで通信。 |
| `command` | 任意のコマンドを実行。stdin/stdout JSON プロトコルで通信。 |
| `wasm` | WebAssembly ランタイムで実行（将来拡張用。現時点では未実装）。 |

### `language` (任意)

開発言語。情報用途のみで、実行方式には影響しません。

### `protocol` (任意)

通信プロトコル。現時点では `stdio_json` のみサポートしています。

- `stdio_json`: stdin に JSON を渡し、stdout から JSON を受け取る

### `docker` (任意)

Docker 環境の設定。

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `image` | string | `python:3.11-slim` | Docker イメージ名 |
| `build_command` | string\|null | null | ビルドコマンド（将来拡張用） |
| `network` | boolean | false | コンテナにネットワークアクセスを許可するか |

### `host_requirements` (任意)

ホスト環境の要求。

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `min_memory_mb` | integer\|null | null | 最小メモリ要求 (MB) |
| `gpu` | boolean | false | GPU が必要か |

## 後方互換性

- `runtime` セクションが未指定の場合、既存のロジックで runtime が決定されます:
  - `core_` 接頭辞を持つ Pack → `block` / `kernel`
  - その他 → `subprocess`（Python サブプロセス）
- `runtime.type` のみ指定すれば最小限の構成で動作します。
- **優先順位**: functions/\<func\>/manifest.json の `calling_convention` > ecosystem.json の `runtime.type`

## サンプル

### Rust で実装された binary Pack

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

### Docker イメージを指定した Python Pack

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

### Host 上で直接実行する Python Pack

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

## stdin/stdout JSON プロトコル

binary / command タイプの Pack は、stdin/stdout JSON プロトコルで通信します。

### 入力 (stdin)

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

### 出力 (stdout)

成功時:
```json
{
  "result": "processed: hello world"
}
```

エラー時:
```json
{
  "error": "Invalid input format",
  "error_type": "validation_error"
}
```

## 内部処理フロー

1. `registry.py` の `_load_functions()` が ecosystem.json の `runtime` セクションを読み取る
2. 各 function の manifest に Pack レベルの runtime 情報をデフォルトとして注入:
   - `runtime.type` → `manifest["calling_convention"]`
   - `runtime.docker.image` → `manifest["docker_image"]`
   - `runtime.type == "python_host"` → `manifest["host_execution"] = True`
   - `runtime.type in ("binary", "command")` → `manifest["runtime"] = type`
3. `FunctionRegistry._entry_from_kwargs()` が manifest から FunctionEntry を構築
4. `capability_executor.py` の `_dispatch_by_calling_convention()` が calling_convention で分岐

個別の function manifest で `calling_convention` が指定されている場合は、そちらが優先されます。
