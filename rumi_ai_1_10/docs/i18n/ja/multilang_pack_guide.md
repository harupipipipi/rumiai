<!-- docs-i18n-links:start -->
[EN](../../multilang_pack_guide.md) | [JP](./multilang_pack_guide.md) | [KR](../ko/multilang_pack_guide.md) | [CN](../zh-cn/multilang_pack_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 多言語パック開発ガイド

最終更新日: 2026-03-23

このドキュメントは、Python 以外の言語 (Rust、Go、Node.js、C/C++ など) で Rumi AI OS パックを開発するためのガイドです。 stdin/stdout JSON プロトコルの仕様、チュートリアル、ベスト プラクティスが含まれています。

---

## 1. 多言語パックの概要

Rumi AI OS のcapability_executor.py は、`binary` と `command` という 2 つの call_conventions を実装しています。どちらも共通のプロトコルを使用します。標準入力で JSON を渡し、標準出力から JSON を読み取ります。

これにより、stdin/stdout で JSON を読み書きできる任意の言語で Pack の関数を実装できます。

### バイナリとコマンド

|特徴 |バイナリ |コマンド |
|------|--------|---------|
|走り方 |コンパイルされたバイナリを直接実行します。コマンド リストを使用してプロセスを開始します。
|適切な言語 | Rust、Go、C、C++ | Node.js、Ruby、Python (さまざまなバージョン)、シェル スクリプト |
|エコシステム.json の指定 | `"runtime": "binary"`、`"main": "path/to/binary"` | `"runtime": "command"`、`"command": ["node", "index.js"]` |
| FunctionEntry フィールド | `main_binary_path` | `command` (リスト[str]) |
|パストラバーサルの検証 |はい (バイナリが function_dir にあるかどうかを検証します) |コマンドに応じて |

---

## 2. 実行時セクションの仕様

`runtime` セクションを Ecosystem.json に追加することで、多言語パックの構築と実行に必要な情報を宣言できます。

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

### ランタイムフィールド

|フィールド |タイプ |説明 |
|-----------|-----|------|
|タイプ |文字列 | `"binary"` / `"command"` / `"python"` |
|ビルド.コマンド |文字列 |ビルドコマンド |
|ビルド.出力 |文字列 |ビルド アーティファクト パス |
|バイナリ |文字列 |実行するバイナリのパス (type=binary の場合) |

---

## 3. stdin/stdout JSON プロトコル仕様

### 3.1 入力 (標準入力)

カーネルは関数を開始すると、次の JSON を標準入力に渡します。

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

#### コンテキストフィールド

|フィールド |タイプ |説明 |
|-----------|-----|------|
|プリンシパル ID |文字列 |リクエストを発行したプリンシパルの ID (UDS から) |
|パックID |文字列 |実行された関数が属するパックの ID |
|関数 ID |文字列 |実行する関数のID |
|リクエストID |文字列 |リクエストの一意の ID |
| ts |文字列 |リクエストのタイムスタンプ (ISO 8601、UTC) |

#### 引数フィールド

呼び出し元によって指定された引数の辞書。機能により内容が異なります。 `input_schema` で定義された構造に従います。

### 3.2 出力 (stdout) — 成功時

処理結果をJSONとしてstdoutに出力する関数です。

```json
{
  "message": "Hello, Pack!",
  "processed_at": "2026-03-23T12:00:01Z"
}
```

出力された JSON はそのまま `CapabilityResponse.output` に格納されます。出力が空の場合 (標準出力に何も書き込まれない)、`output` は `null` になります。

### 3.3 出力 (stderr) — エラー時

エラーが発生した場合は、ゼロ以外の終了コードで終了します。標準エラー出力に書き込まれた内容はエラーメッセージとして記録されます（最初の500文字まで）。

```
# 正常終了: exit code 0 + stdout に JSON
# エラー:  exit code 1 + stderr にメッセージ
```

**重要**: エラー情報を JSON として stdout に出力する方法もありますが、カーネルは終了コードを使用して成功/失敗を判断します。ゼロ以外の終了コードの場合、stdout は無視され、stderr がエラー メッセージとして使用されます。

### 3.4 タイムアウト

|設定 |値 |出典 |
|------|-----|--------|
|デフォルトのタイムアウト | 30秒 | `DEFAULT_FUNCTION_TIMEOUT = 30.0` |
|最大タイムアウト | 120秒 | `MAX_TIMEOUT = 120.0` |
|最小タイムアウト | 1秒 | `max(t, 1.0)` |
|カスタマイズ |関数マニフェストの `grant_config.timeout` で指定 |

タイムアウトに達すると、プロセスは強制終了され、CapabilityResponse `error_type: "timeout"` が返されます。

### 3.5 応答サイズの制限

標準出力の出力は **1 MB** (`MAX_RESPONSE_SIZE = 1 * 1024 * 1024` バイト) 以下である必要があります。それを超えると`error_type: "response_too_large"`エラーとなります。

---

## 4. call_convention: バイナリの詳細

### 4.1 概要

このメソッドは、コンパイルされたバイナリを直接実行します。 Rust、Go、C、C++などの言語に適しています。

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

### 4.3 エコシステム.json の設定例

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

関数マニフェスト (関数セクション内):
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

- **パス トラバーサル防止**: バイナリ パス上の `resolve()` の結果が `function_dir` の下にあることを検証します。 `../../`などでfunction_dirの外に出ようとすると、`security_violation`のエラーが発生します。
- **作業ディレクトリ**: プロセスの cwd は `function_dir` に設定されます。

---

## 5. call_convention: コマンドの詳細

### 5.1 概要

このメソッドは、コマンドリストを使用してプロセスを開始します。インタープリタ型言語 (Node.js、Ruby、Python のさまざまなバージョンなど) に適しています。

### 5.2 実行フロー

`binary` と同じ stdin/stdout JSON プロトコルを使用します。違いは、プロセス コマンドとしてバイナリ パスの代わりに `entry.command`(List[str]) を使用することです。

### 5.3 エコシステム.json の設定例

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

関数マニフェスト:
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

## 6. セキュリティ上の制約

### 6.1 パストラバーサルの防止 (バイナリ)

`_execute_binary_function` は次の検証を実行します。

```python
func_dir = Path(entry.function_dir).resolve()
if not Path(binary_path).resolve().is_relative_to(func_dir):
    # security_violation エラー
```

必ずバイナリをパックの function_dir に配置してください。シンボリック リンクまたは `../` によるエスケープが検出されます。

### 6.2 応答サイズの制限

標準出力出力が 1 MB を超える場合、応答は破棄され、`response_too_large` エラーが発生します。大量のデータを返す必要がある場合は、データをファイルに書き出してパスを返すか、ページネーションを実装します。

### 6.3 タイムアウト

関数は最大 120 秒以内に完了する必要があります。タイムアウトに達するとプロセスは強制終了されます。長い実行時間を必要とするプロセスについては、非同期パターン (ジョブ キューなど) を検討してください。

### 6.4 環境変数

`RUMI_PACK_ID` と `RUMI_FUNCTION_ID` は、Docker で実行される Python 関数に環境変数として渡されます。これらはバイナリ/コマンド関数には渡されません。標準入力の `context` から必要な情報を取得します。

---

## 7. Rust パックのチュートリアル

### 7.1 前提条件

- Rust ツールチェーンがインストールされました (`rustup` + `cargo`)
・Rumi AI OSが動作する環境

### 7.2 プロジェクトの作成

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

### 7.7 エコシステム.json

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

ビルド済みバイナリを function_dir にコピーまたはシンボリック リンクして、Rumi AI OS の `ecosystem/` に Pack ディレクトリを配置します。

---

## 8. Go Pack チュートリアル

### 8.1 前提条件

- インストールしてください (1.21 以降を推奨)

### 8.2 プロジェクトの作成

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

## 9. Node.js パックのチュートリアル

### 9.1 前提条件

- Node.js がインストールされています (18 歳以上推奨)

### 9.2 プロジェクトの作成

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

### 9.5 エコシステム.json

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

すべての多言語パック関数は stdin/stdout プロトコルに従っているため、コマンド ラインで直接テストできます。

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

### 10.2 終了コードの確認

```bash
cat /tmp/test_input.json | ./my_binary
echo "Exit code: $?"
```

### 10.3 標準エラー出力の確認

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

### 11.1 エラー処理

- stdin の読み取りに失敗した場合は、メッセージを stderr に書き込み、終了コード 1 で終了します。
- 同様にJSON解析エラーが発生した場合、stderr + 終了コード1
- 処理中のエラーには、stderr + ゼロ以外の終了コードも含まれます
- パニック/クラッシュを回避します (Rust では `unwrap()` の代わりにエラー処理を推奨します)

### 11.2 出力

- 成功した場合、有効な JSON を 1 行で stdout に出力します。
- 余分な改行やログを stdout に混在させないでください (stderr を使用してください)。
- デバッグ出力と標準出力を混合すると、JSON 解析エラーが発生します
- 出力サイズを 1 MB 未満に保つ

### 11.3 パフォーマンス

- 起動時間の短縮（タイムアウトには起動時間を含みます）
- 大量のデータはストリーミングではなくバッチで処理されます (stdin は一度に渡されます)。
- Rust/Go は静的リンクを使用してバイナリ サイズを最適化します。

### 11.4 セキュリティ

- 機密情報を環境変数から読み取らない（コンテキストから取得する）
- ファイルへのアクセスは function_dir に制限されます
- 外部ネットワーク アクセスは、require を使用して適切な権限を宣言します。
- ユーザー入力 (引数) を信頼しないでください。検証を実行する

### 11.5 クロスプラットフォーム

- Rust: `cross` クレート内でクロスコンパイル
- Go: `GOOS` / `GOARCH` 環境変数を使用したクロスコンパイル
- Node.js: プラットフォームに依存するネイティブ モジュールに注意してください
- バイナリ名に拡張子を含めないでください（Windows 以外では不要）

### 11.6 テスト

- CI/CD でテスト入力 JSON を準備し、予想される出力と比較します
- 複数の引数パターンをテストする
- 空の引数、不正な形式の JSON、大きな入力などのエッジ ケースもテストします
- 終了コードが正しいことを確認してください

---

## 付録 A: プロトコルのクイックリファレンス

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

|関数の動作 |能力応答 |
|----------------|-------------------|
| exit 0 + JSON を標準出力に出力 | `success=true, output=<parsed JSON>` |
|出口 0 + 空の標準出力 | `success=true, output=null` |
| exit 0 + stdout は無効な JSON | `success=false, error_type="invalid_json_output"` |
|出口 0 + 標準出力 > 1MB | `success=false, error_type="response_too_large"` |
|ゼロ以外の値を終了する | `success=false, error_type="function_execution_error"` |
|タイムアウト | `success=false, error_type="timeout"` |
|バイナリが見つかりません | `success=false, error_type="binary_not_found"` |
|パストラバーサルの検出 | `success=false, error_type="security_violation"` |

---

## 関連ドキュメント

- [パック開発ガイド](./pack-development.md) — パックの概要
- [サンプルコード: Rust Pack](examples/rust_pack/) — Rust Packの完全なサンプル
- [サンプル コード: Go Pack](examples/go_pack/) — Go Pack の完全なサンプル
- [サンプル コード: Node.js パック](examples/node_pack/) — Node.js パックの完全なサンプル
