<!-- docs-i18n-links:start -->
[EN](../../multilang_pack_guide.md) | [JP](../ja/multilang_pack_guide.md) | [KR](./multilang_pack_guide.md) | [CN](../zh-cn/multilang_pack_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 다국어 팩 개발 가이드

최종 업데이트 날짜: 2026-03-23

이 문서는 Python 이외의 언어(Rust, Go, Node.js, C/C++ 등)로 Rumi AI OS 팩을 개발하기 위한 가이드입니다. stdin/stdout JSON 프로토콜에 대한 사양, 튜토리얼 및 모범 사례가 포함되어 있습니다.

---

## 1. 다국어 팩 개요

Rumi AI OS의capability_executor.py는 `binary` 및 `command`의 두 가지 호출 규칙을 구현합니다. 둘 다 공통 프로토콜을 사용합니다. 즉, stdin에서 JSON을 전달하고 stdout에서 JSON을 읽습니다.

이를 통해 stdin/stdout에서 JSON을 읽고 쓸 수 있는 모든 언어로 Pack의 함수를 구현할 수 있습니다.

### 바이너리 대 명령

| 특성 | 바이너리 | 명령 |
|------|--------|---------|
| 실행 방법 | 컴파일된 바이너리를 직접 실행 | 명령 목록으로 프로세스 시작 |
| 적합한 언어 | 러스트, Go, C, C++ | Node.js, Ruby, Python(다른 버전), 쉘 스크립팅 |
| Ecosystem.json 지정 | §루미§0§, §루미§1§ | §루미§2§, §루미§3§ |
| 기능입력 필드 | §루미§0§ | `command` (목록[str]) |
| 경로 순회 검증 | 예(binary가 function_dir에 있는지 확인) | 명령에 따라 다름 |

---

## 2. 런타임 섹션 사양

Ecosystem.json에 `runtime` 섹션을 추가하여 다국어 팩을 빌드하고 실행하는 데 필요한 정보를 선언할 수 있습니다.

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

### 런타임 필드

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| 유형 | 문자열 | §루미§0§ / §루미§1§ / §루미§2§ |
| 빌드.명령 | 문자열 | 빌드 명령 |
| 빌드.출력 | 문자열 | 아티팩트 경로 빌드 |
| 바이너리 | 문자열 | 실행될 바이너리의 경로(type=binary인 경우) |

---

## 3. stdin/stdout JSON 프로토콜 사양

### 3.1 입력(표준 입력)

커널이 함수를 시작하면 다음 JSON을 stdin에 전달합니다.

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

#### 컨텍스트 필드

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| 교장_ID | 문자열 | 요청을 발행한 주체의 ID(UDS에서) |
| 팩_ID | 문자열 | 실행된 Function이 속한 Pack의 ID |
| 함수_ID | 문자열 | 실행될 함수의 ID |
| 요청_ID | 문자열 | 요청의 고유 ID |
| TS | 문자열 | 요청 타임스탬프(ISO 8601, UTC) |

#### 인수 필드

호출자가 지정한 인수 사전입니다. 내용은 기능에 따라 다릅니다. `input_schema`에 정의된 구조를 따릅니다.

### 3.2 출력(stdout) — 성공 시

함수는 처리 결과를 JSON으로 stdout에 출력합니다.

```json
{
  "message": "Hello, Pack!",
  "processed_at": "2026-03-23T12:00:01Z"
}
```

출력 JSON은 `CapabilityResponse.output`에 그대로 저장됩니다. 출력이 비어 있으면(stdout에 아무것도 기록되지 않음) `output`은 `null`가 됩니다.

### 3.3 출력(stderr) - 오류 시

오류가 발생하면 0이 아닌 종료 코드로 종료하십시오. stderr에 기록된 내용은 오류 메시지로 기록됩니다(처음 500자까지).

```
# 正常終了: exit code 0 + stdout に JSON
# エラー:  exit code 1 + stderr にメッセージ
```

**중요**: 오류 정보를 JSON으로 stdout에 출력하는 방법도 있지만 커널은 종료 코드를 사용하여 성공/실패를 결정합니다. 0이 아닌 종료 코드의 경우 stdout이 무시되고 stderr이 오류 메시지로 사용됩니다.

### 3.4 시간 초과

| 설정 | 가치 | 소스 |
|------|-----|--------|
| 기본 시간 초과 | 30초 | §루미§0§ |
| 최대 시간 초과 | 120초 | §루미§0§ |
| 최소 시간 초과 | 1초 | §루미§0§ |
| 맞춤화 | 함수 매니페스트의 `grant_config.timeout`에 지정됨 |

시간 초과에 도달하면 프로세스가 종료되고 `error_type: "timeout"`의 CapabilityResponse가 반환됩니다.

### 3.5 응답 크기 제한

표준 출력의 출력은 **1MB**(`MAX_RESPONSE_SIZE = 1 * 1024 * 1024`바이트)보다 작거나 같아야 합니다. 이를 초과하면 `error_type: "response_too_large"` 오류가 발생합니다.

---

## 4. call_convention: 바이너리 세부정보

### 4.1 개요

이 메서드는 컴파일된 바이너리를 직접 실행합니다. Rust, Go, C, C++ 등의 언어에 적합합니다.

### 4.2 실행 흐름

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

### 4.3 생태계.json 구성 예시

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

함수 매니페스트(함수 섹션):
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

### 4.4 보안

- **경로 순회 방지**: 바이너리 경로에 대한 `resolve()` 결과가 `function_dir` 아래에 있는지 확인합니다. `../../` 등으로 function_dir 외부로 나가려고 하면 `security_violation` 오류가 발생합니다.
- **작업 디렉터리**: 프로세스의 cwd가 `function_dir`으로 설정됩니다.

---

## 5. call_convention: 명령 세부정보

### 5.1 개요

이 방법은 명령 목록을 사용하여 프로세스를 시작합니다. 해석된 언어(Node.js, Ruby, 다른 버전의 Python 등)에 적합합니다.

### 5.2 실행 흐름

`binary`과 동일한 stdin/stdout JSON 프로토콜을 사용합니다. 차이점은 바이너리 경로 대신 `entry.command`(List[str])을 프로세스 명령으로 사용한다는 것입니다.

### 5.3 생태계.json 구성 예시

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

기능 매니페스트:
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

## 6. 보안 제약

### 6.1 경로 탐색 방지(바이너리)

`_execute_binary_function`은 다음 검증을 수행합니다:

```python
func_dir = Path(entry.function_dir).resolve()
if not Path(binary_path).resolve().is_relative_to(func_dir):
    # security_violation エラー
```

팩의 function_dir에 바이너리를 배치해야 합니다. 기호 링크 또는 `../`을 통한 이스케이프가 감지됩니다.

### 6.2 응답 크기 제한

stdout 출력이 1MB를 초과하면 응답이 삭제되고 `response_too_large` 오류가 발생합니다. 많은 양의 데이터를 반환해야 하는 경우 이를 파일에 쓰고 경로를 반환하거나 페이지 매김을 구현하세요.

### 6.3 시간 초과

함수는 최대 120초 이내에 완료되어야 합니다. 시간 초과에 도달하면 프로세스가 종료됩니다. 긴 실행 시간이 필요한 프로세스의 경우 비동기 패턴(예: 작업 큐)을 고려하세요.

### 6.4 환경 변수

`RUMI_PACK_ID` 및 `RUMI_FUNCTION_ID`은 Docker에서 실행되는 Python 함수에 환경 변수로 전달됩니다. 이는 바이너리/명령 함수로 전달되지 않습니다. stdin의 `context`에서 필요한 정보를 얻으세요.

---

## 7. 러스트 팩 튜토리얼

### 7.1 전제 조건

- Rust 툴체인 설치(`rustup` + `cargo`)
- Rumi AI OS가 동작하는 환경

### 7.2 프로젝트 생성

```bash
mkdir -p my_rust_pack/functions/hello
cd my_rust_pack/functions/hello
cargo init --name hello_pack
```

### 7.3 종속 상자 추가하기

§루미§0§:
```toml
[package]
name = "hello_pack"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

### 7.4 구현

§루미§0§:
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

### 7.5 빌드

```bash
cargo build --release
```

### 7.6 테스트

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_rust_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./target/release/hello_pack
```

예상 출력:
```json
{"message":"Hello, Rumi!","greeted_by":"my_rust_pack:hello","principal":"test_user"}
```

### 7.7 생태계.json

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

### 7.8 배치

미리 빌드된 바이너리를 function_dir에 복사하거나 심볼릭 링크하여 Rumi AI OS의 `ecosystem/`에 Pack 디렉터리를 배치합니다.

---

## 8. Go 팩 튜토리얼

### 8.1 전제 조건

- Go 설치(1.21 이상 권장)

### 8.2 프로젝트 생성

```bash
mkdir -p my_go_pack/functions/hello
cd my_go_pack/functions/hello
go mod init hello_pack
```

### 8.3 구현

§루미§0§:
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

### 8.4 빌드 및 테스트

```bash
go build -o hello_pack .
echo '{"context":{"principal_id":"test_user","pack_id":"my_go_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | ./hello_pack
```

---

## 9. Node.js 팩 튜토리얼

### 9.1 전제 조건

- Node.js 설치(18세 이상 권장)

### 9.2 프로젝트 생성

```bash
mkdir -p my_node_pack/functions/hello
cd my_node_pack/functions/hello
npm init -y
```

### 9.3 구현

§루미§0§:
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

### 9.4 테스트

```bash
echo '{"context":{"principal_id":"test_user","pack_id":"my_node_pack","function_id":"hello","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"name":"Rumi"}}' | node index.js
```

### 9.5 생태계.json

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

## 10. 디버깅 방법

### 10.1 명령줄에서 테스트하기

모든 다국어 Pack 기능은 stdin/stdout 프로토콜을 따르므로 명령줄에서 직접 테스트할 수 있습니다.

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

### 10.2 종료 코드 확인

```bash
cat /tmp/test_input.json | ./my_binary
echo "Exit code: $?"
```

### 10.3 표준 오류 확인

```bash
cat /tmp/test_input.json | ./my_binary 2>/tmp/stderr.log
cat /tmp/stderr.log
```

### 10.4 시간 초과 시뮬레이션

```bash
timeout 30 sh -c 'cat /tmp/test_input.json | ./my_binary'
echo "Exit code: $?"
```

### 10.5 응답 크기 확인

```bash
cat /tmp/test_input.json | ./my_binary | wc -c
# 1048576 (1MB) 以下であることを確認
```

---

## 11. 모범 사례

### 11.1 오류 처리

- stdin 읽기가 실패하면 stderr에 메시지를 쓰고 종료 코드 1로 종료합니다.
- 마찬가지로 JSON 파싱 오류가 있는 경우 stderr + 종료 코드 1
- 처리 중 오류에는 stderr + 0이 아닌 종료 코드도 포함됩니다.
- 패닉/충돌 방지(Rust는 `unwrap()` 대신 오류 처리를 권장함)

### 11.2 출력

- 성공하면 유효한 JSON을 한 줄로 stdout에 출력합니다.
- stdout에 추가 줄바꿈이나 로그를 혼합하지 마세요(stderr 사용).
- 디버그 출력을 stdout과 혼합하면 JSON 구문 분석 오류가 발생합니다.
- 출력 크기를 1MB 미만으로 유지하세요.

### 11.3 성능

- 시작 시간 단축(타임아웃에는 시작 시간도 포함됨)
- 대량의 데이터를 스트리밍이 아닌 일괄처리(stdin을 한번에 전달)
- Rust/Go는 정적 링크로 바이너리 크기를 최적화합니다.

### 11.4 보안

- 환경 변수에서 민감한 정보를 읽지 않음(컨텍스트에서 가져옴)
- 파일 액세스는 function_dir로 제한됩니다.
- 외부 네트워크 액세스는 요구 사항에 따라 적절한 권한을 선언합니다.
- 사용자 입력(args)을 신뢰하지 마세요. 검증 수행

### 11.5 크로스 플랫폼

- Rust: `cross` 크레이트에서 크로스 컴파일됨
- 이동: `GOOS` / `GOARCH` 환경 변수를 사용한 크로스 컴파일
- Node.js: 플랫폼 종속 네이티브 모듈에 주의하세요.
- 바이너리 이름에 확장자를 포함하지 마세요(Windows가 아닌 경우 불필요함).

### 11.6 테스트

- CI/CD에서 테스트 입력 JSON을 준비하고 예상 출력과 비교
- 여러 인수 패턴 테스트
- 또한 빈 인수, 잘못된 형식의 JSON 및 대규모 입력과 같은 극단적인 경우도 테스트합니다.
- 종료 코드가 올바른지 확인하세요.

---

## 부록 A: 프로토콜 빠른 참조

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

## 부록 B: CapabilityResponse 필드 대응 표

| 함수 동작 | 역량응답 |
|----------------|-------------------|
| 종료 0 + JSON을 표준 출력으로 | §루미§0§ |
| 종료 0 + 표준 출력 비어 있음 | §루미§0§ |
| 종료 0 + stdout이 잘못된 JSON입니다 | §루미§0§ |
| 종료 0 + 표준 출력 > 1MB | §루미§0§ |
| 0이 아닌 종료 | §루미§0§ |
| 시간 초과 | §루미§0§ |
| 바이너리를 찾을 수 없습니다 | §루미§0§ |
| 경로 탐색 감지 | §루미§0§ |

---

## 관련 문서

- [팩 개발 가이드](./pack-development.md) — 팩 개요
- [샘플 코드: Rust Pack](examples/rust_pack/) — Rust Pack 전체 샘플
- [샘플 코드: 바둑 팩](examples/go_pack/) — 바둑 팩 샘플 완성
- [샘플 코드: Node.js 팩](examples/node_pack/) — Node.js 팩 전체 샘플
