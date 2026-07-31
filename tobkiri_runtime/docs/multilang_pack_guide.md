# Tobkiri — 多言語 Pack 開発ガイド

最終更新: 2026-03-23

本ドキュメントは Tobkiri の Pack を **Python 以外の言語**（Rust, Go, Node.js, C/C++ 等）で開発するためのガイドです。stdin/stdout JSON プロトコルの仕様、チュートリアル、ベストプラクティスを含みます。

---

## 1. 多言語 Pack の概要

Tobkiri の capability_executor.py には `binary` と `command` の 2 つの calling_convention が実装されています。どちらも **stdin に JSON を渡し、stdout から JSON を読み取る** という共通のプロトコルを使用します。

これにより、stdin/stdout で JSON を読み書きできる任意の言語で Pack の Function を実装できます。

### binary vs command

| 特性 | binary | command |
|------|--------|---------|
| 実行方法 | コンパイル済みバイナリを直接実行 | コマンドリストでプロセスを起動 |
| 適した言語 | Rust, Go, C, C++ | Node.js, Ruby, Python (別バージョン), シェルスクリプト |
| ecosystem.json の指定 | `"runtime": "binary"`, `"main": "path/to/binary"` | `"runtime": "command"`, `"command": ["node", "index.js"]` |
| FunctionEntry フィールド | `main_binary_path` | `command` (List[str]) |
| パストラバーサル検証 | あり（バイナリが function_dir 内か検証） | コマンドに依存 |

---

## 2. runtime セクションの仕様

ecosystem.json に `runtime` セクションを追加することで、多言語 Pack のビルドと実行に必要な情報を宣言できます。

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

### runtime フィールド

| フィールド | 型 | 説明 |
|-----------|-----|------|
| type | string | `"binary"` / `"command"` / `"python"` |
| build.command | string | ビルドコマンド |
| build.output | string | ビルド成果物のパス |
| binary | string | 実行するバイナリのパス（type=binary 時） |

---

## 3. stdin/stdout JSON プロトコル仕様

### 3.1 入力（stdin）

Kernel は Function を起動する際、stdin に以下の JSON を渡します。

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

#### context フィールド

| フィールド | 型 | 説明 |
|-----------|-----|------|
| principal_id | string | リクエストを発行した主体の ID（UDS 由来） |
| pack_id | string | 実行される Function が属する Pack の ID |
| function_id | string | 実行される Function の ID |
| request_id | string | リクエストの一意な ID |
| ts | string | リクエストのタイムスタンプ（ISO 8601、UTC） |

#### args フィールド

呼び出し元が指定した引数の辞書です。内容は Function ごとに異なります。`input_schema` で定義した構造に従います。

### 3.2 出力（stdout）— 成功時

Function は処理結果を stdout に JSON として出力します。

```json
{
  "message": "Hello, Pack!",
  "processed_at": "2026-03-23T12:00:01Z"
}
```

出力の JSON はそのまま `CapabilityResponse.output` に格納されます。出力が空（stdout に何も書かない）の場合、`output` は `null` になります。

### 3.3 出力（stderr）— エラー時

エラーが発生した場合は、**非ゼロの exit code** で終了してください。stderr に書かれた内容がエラーメッセージとして記録されます（先頭 500 文字まで）。

```
# 正常終了: exit code 0 + stdout に JSON
# エラー:  exit code 1 + stderr にメッセージ
```

**重要**: エラー情報を stdout に JSON として出力する方法もありますが、Kernel は exit code で成功/失敗を判定します。非ゼロ exit code の場合、stdout は無視され、stderr がエラーメッセージとして使用されます。

### 3.4 タイムアウト

| 設定 | 値 | ソース |
|------|-----|--------|
| デフォルトタイムアウト | 30 秒 | `DEFAULT_FUNCTION_TIMEOUT = 30.0` |
| 最大タイムアウト | 120 秒 | `MAX_TIMEOUT = 120.0` |
| 最小タイムアウト | 1 秒 | `max(t, 1.0)` |
| カスタマイズ | Function マニフェストの `grant_config.timeout` で指定 |

タイムアウトに達すると、プロセスは強制終了され、`error_type: "timeout"` の CapabilityResponse が返されます。

### 3.5 レスポンスサイズ制限

stdout の出力は **1 MB**（`MAX_RESPONSE_SIZE = 1 * 1024 * 1024` バイト）以下でなければなりません。超過した場合、`error_type: "response_too_large"` のエラーになります。

---

## 4. calling_convention: binary の詳細

### 4.1 概要

コンパイル済みバイナリを直接実行する方式です。Rust, Go, C, C++ などの言語に適しています。

### 4.2 実行フロー

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

### 4.3 ecosystem.json の設定例

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

Function マニフェスト（functions セクション内）:
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

### 4.4 セキュリティ

- **パストラバーサル防止**: バイナリパスを `resolve()` した結果が `function_dir` の配下であることを検証します。`../../` 等で function_dir の外に出ようとすると `security_violation` エラーになります。
- **作業ディレクトリ**: プロセスの cwd は `function_dir` に設定されます。

---

## 5. calling_convention: command の詳細

### 5.1 概要

コマンドリストでプロセスを起動する方式です。インタプリタ言語（Node.js, Ruby, Python の別バージョン等）に適しています。

### 5.2 実行フロー

`binary` と同じ stdin/stdout JSON プロトコルを使用します。違いは、バイナリパスの代わりに `entry.command`（List[str]）をプロセスコマンドとして使用する点です。

### 5.3 ecosystem.json の設定例

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

Function マニフェスト:
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

## 6. セキュリティ制約

### 6.1 パストラバーサル防止（binary）

`_execute_binary_function` は以下の検証を行います:

```python
func_dir = Path(entry.function_dir).resolve()
if not Path(binary_path).resolve().is_relative_to(func_dir):
    # security_violation エラー
```

バイナリは必ず Pack の function_dir 内に配置してください。シンボリックリンクや `../` による脱出は検出されます。

### 6.2 レスポンスサイズ制限

stdout の出力が 1 MB を超えると、レスポンスは破棄され `response_too_large` エラーになります。大量のデータを返す必要がある場合は、ファイルに書き出してパスを返すか、ページネーションを実装してください。

### 6.3 タイムアウト

Function は最大 120 秒以内に完了する必要があります。タイムアウトに達するとプロセスは強制終了されます。長時間実行が必要な処理は、非同期パターン（ジョブキューなど）を検討してください。

### 6.4 環境変数

Docker で実行される Python Function には `RUMI_PACK_ID` と `RUMI_FUNCTION_ID` が環境変数として渡されます。binary/command Function にはこれらは渡されません。必要な情報は stdin の `context` から取得してください。

---

## 7. Rust Pack チュートリアル

### 7.1 前提条件

- Rust ツールチェーンがインストール済み（`rustup` + `cargo`）
- Tobkiri が動作する環境

### 7.2 プロジェクト作成

```bash
mkdir -p my_rust_pack/functions/hello
cd my_rust_pack/functions/hello
cargo init --name hello_pack
```

### 7.3 依存クレートの追加

`Cargo.toml`:
```toml
[package]
name = "hello_pack"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

### 7.4 実装

`src/main.rs`:
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

### 7.5 ビルド

```bash
cargo build --release
```

### 7.6 テスト

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_rust_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./target/release/hello_pack
```

期待される出力:
```json
{"message":"Hello, Rumi!","greeted_by":"my_rust_pack:hello","principal":"test_user"}
```

### 7.7 ecosystem.json

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

### 7.8 配置

ビルド済みバイナリを function_dir 内にコピーまたはシンボリックリンクして、Tobkiri の `ecosystem/` に Pack ディレクトリを配置します。

---

## 8. Go Pack チュートリアル

### 8.1 前提条件

- Go がインストール済み（1.21 以上推奨）

### 8.2 プロジェクト作成

```bash
mkdir -p my_go_pack/functions/hello
cd my_go_pack/functions/hello
go mod init hello_pack
```

### 8.3 実装

`main.go`:
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

### 8.4 ビルドとテスト

```bash
go build -o hello_pack .
echo '{"context":{"principal_id":"test_user","pack_id":"my_go_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./hello_pack
```

---

## 9. Node.js Pack チュートリアル

### 9.1 前提条件

- Node.js がインストール済み（18 以上推奨）

### 9.2 プロジェクト作成

```bash
mkdir -p my_node_pack/functions/hello
cd my_node_pack/functions/hello
npm init -y
```

### 9.3 実装

`index.js`:
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

### 9.4 テスト

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_node_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | node index.js
```

### 9.5 ecosystem.json

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

## 10. デバッグ方法

### 10.1 コマンドラインでのテスト

全ての多言語 Pack Function は stdin/stdout プロトコルに従うため、コマンドラインで直接テストできます:

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

### 10.2 exit code の確認

```bash
cat /tmp/test_input.json | ./my_binary
echo "Exit code: $?"
```

### 10.3 stderr の確認

```bash
cat /tmp/test_input.json | ./my_binary 2>/tmp/stderr.log
cat /tmp/stderr.log
```

### 10.4 タイムアウトのシミュレーション

```bash
timeout 30 sh -c 'cat /tmp/test_input.json | ./my_binary'
echo "Exit code: $?"
```

### 10.5 レスポンスサイズの確認

```bash
cat /tmp/test_input.json | ./my_binary | wc -c
# 1048576 (1MB) 以下であることを確認
```

---

## 11. ベストプラクティス

### 11.1 エラーハンドリング

- stdin の読み取り失敗時は stderr にメッセージを書いて exit code 1 で終了する
- JSON パースエラー時も同様に stderr + exit code 1
- 処理中のエラーも stderr + 非ゼロ exit code
- パニック/クラッシュは避ける（Rust では `unwrap()` の代わりにエラーハンドリングを推奨）

### 11.2 出力

- 成功時は stdout に有効な JSON を 1 行で出力する
- 余計な改行やログを stdout に混ぜない（stderr を使う）
- stdout にデバッグ出力を混ぜると JSON パースエラーになる
- 出力サイズを 1 MB 以下に抑える

### 11.3 パフォーマンス

- 起動時間を短くする（タイムアウトには起動時間も含まれる）
- 大量のデータ処理はストリーミングではなく一括処理（stdin は一度に全て渡される）
- Rust/Go はスタティックリンクでバイナリサイズを最適化

### 11.4 セキュリティ

- 環境変数から機密情報を読み取らない（context から取得する）
- ファイルアクセスは function_dir 内に限定する
- 外部ネットワークアクセスは requires で適切なパーミッションを宣言する
- ユーザー入力（args）を信頼しない。バリデーションを行う

### 11.5 クロスプラットフォーム

- Rust: `cross` クレートでクロスコンパイル
- Go: `GOOS` / `GOARCH` 環境変数でクロスコンパイル
- Node.js: プラットフォーム依存のネイティブモジュールに注意
- バイナリ名に拡張子を含めない（Windows 以外では不要）

### 11.6 テスト

- CI/CD でテスト入力 JSON を用意し、期待出力と比較する
- 複数の args パターンをテストする
- 空の args、不正な JSON、巨大な入力などのエッジケースもテストする
- exit code が正しいことを確認する

---

## 付録 A: プロトコル早見表

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

## 付録 B: CapabilityResponse フィールド対応表

| Function の動作 | CapabilityResponse |
|----------------|-------------------|
| exit 0 + stdout に JSON | `success=true, output=<parsed JSON>` |
| exit 0 + stdout 空 | `success=true, output=null` |
| exit 0 + stdout が不正な JSON | `success=false, error_type="invalid_json_output"` |
| exit 0 + stdout > 1MB | `success=false, error_type="response_too_large"` |
| exit 非ゼロ | `success=false, error_type="function_execution_error"` |
| タイムアウト | `success=false, error_type="timeout"` |
| バイナリ未発見 | `success=false, error_type="binary_not_found"` |
| パストラバーサル検出 | `success=false, error_type="security_violation"` |

---

## 関連ドキュメント

- [Pack 開発ガイド](pack-development.md) — Pack の全体像
- [サンプルコード: Rust Pack](examples/rust_pack/) — Rust Pack の完全なサンプル
- [サンプルコード: Go Pack](examples/go_pack/) — Go Pack の完全なサンプル
- [サンプルコード: Node.js Pack](examples/node_pack/) — Node.js Pack の完全なサンプル
