<!-- docs-i18n-links:start -->
[EN](../../pack_desktop_app_guide.md) | [JP](../ja/pack_desktop_app_guide.md) | [KR](./pack_desktop_app_guide.md) | [CN](../zh-cn/pack_desktop_app_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — Pack 데스크톱 앱 개발 가이드

최종 업데이트 날짜: 2026-03-28

이 문서는 개발자가 **데스크톱 앱**(별도의 데스크톱 창에서 실행되는 애플리케이션)을 Rumi AI OS 팩에 통합하기 위한 가이드입니다. Ecosystem.json 설정 방법, 팩-셸 바이너리 사용 방법, 보안 모델 및 바로가기 생성 방법을 다룹니다.

---

## 1. 데스크톱 앱 팩이란 무엇인가요?

### 1.1 개요

팩 데스크톱 앱을 사용하면 Rumi AI OS의 **기능 기반 권한 시스템**을 통해 애플리케이션이 별도의 데스크톱 창에서 실행될 수 있습니다.

Rumi Viewer(Tauri 기반 WebView UI) 내부에 프런트엔드를 표시하는 `viewer:display` 기능과 달리 `desktop_app.execute` 기능은 **OS 기본 창**에서 앱을 시작합니다. tkinter, Qt, Electron, Tauri 등과 같은 GUI 프레임워크를 사용할 수 있습니다.

### 1.2 아키텍처

```
ユーザー
  │
  ├── ショートカット / CLI
  │       │
  │       ▼
  │   pack-shell (Rust バイナリ)
  │       │
  │       ├─ 1. Kernel /health チェック
  │       ├─ 2. Kernel 未起動なら自動起動
  │       ├─ 3. POST /api/desktop/token でトークン取得
  │       ├─ 4. 環境変数 (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) を設定
  │       └─ 5. アプリプロセスを起動
  │               │
  │               ▼
  │           デスクトップアプリ (Python, Node.js, etc.)
  │               │
  │               ▼
  │           Kernel API (localhost:8765) と通信
  │
  └── Rumi AI OS Kernel
          │
          ├── CapabilityGrantManager (Grant 検証)
          ├── DesktopAppManager (登録・ショートカット生成)
          └── POST /api/desktop/token (トークン発行)
```

### 1.3 편애 원칙 없음

데스크탑 앱 지원도 다른 기능과 동일한 패턴을 사용하여 구현됩니다. `core_desktop_capability`는 core_pack으로 커널에 포함되어 있으며 `desktop_app.execute` 권한을 관리합니다. 타사 팩은 다른 기능과 마찬가지로 이 기능을 사용하려면 승인이 필요합니다.

---

## 2. 전제 조건

데스크톱 앱 팩을 개발하고 실행하려면 다음이 필요합니다.

- **Rumi AI OS**를 설치하고 시작할 수 있는 환경
- **pack-shell 바이너리**가 빌드되었습니다(아래 빌드 지침 참조).
- **Python 3.11 이상** (샘플 앱용. 앱 자체는 모든 언어로 구현 가능)

---

## 3. Ecosystem.json의 Desktop_app 섹션

팩에 데스크톱 앱 기능을 추가하려면 `ecosystem.json`에 `desktop_app` 섹션을 추가하세요.

### 3.1 설정 예

```json
{
  "pack_id": "my_desktop_pack",
  "version": "1.0.0",
  "metadata": {
    "name": "My Desktop App",
    "description": "デスクトップアプリのサンプル Pack"
  },
  "desktop_app": {
    "command": "python app.py",
    "working_dir": "",
    "env": {},
    "capabilities": ["desktop_app.execute"],
    "window": {
      "title": "My Desktop App",
      "width": 800,
      "height": 600
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

### 3.2 필드 목록

| 필드 | 유형 | 필수 | 설명 |
|-----------|-----|------|------|
| §루미§0§ | 문자열 | ✅ | 명령을 시작합니다. pack-shell의 `--command` 인수로 앱에 전달됨 |
| §루미§0§ | 문자열 | — | 앱의 작업 디렉터리입니다. 빈 문자열인 경우 Pack 디렉터리가 사용됩니다. |
| §루미§0§ | 사전 | — | 앱에 전달할 추가 환경 변수입니다. `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID`는 팩 쉘이 자동으로 구성하므로 필요하지 않습니다 |
| §루미§0§ | 목록 | — | 요청된 기능 목록 |
| §루미§0§ | 사전 | — | 창 설정. `title`(문자열)으로 앱 이름을 지정하고 `width`/`height`(int)로 크기를 지정합니다. 바로가기 이름에도 사용됨 |
| §루미§0§ | 목록 | — | 지원되는 플랫폼. `"darwin"`, `"win32"`, `"linux"`의 조합 |

### 3.3 스키마 유효성 검사

커널의 `PackImporter`는 다음 규칙을 사용하여 `desktop_app` 섹션의 유효성을 검사합니다.

- `desktop_app`이 있는 경우 dict여야 합니다.
- `desktop_app.command`은 필수이며 비어 있지 않은 문자열이어야 합니다.
- `working_dir`은 문자열, `env`은 dict, `capabilities`는 목록, `window`는 dict, `platforms`는 목록이어야 합니다(모두 생략 가능).

유효성 검사에 실패하면 팩을 가져올 때 경고가 인쇄되고 팩이 등록되지 않습니다.

---

## 4. Desktop_app.execute 기능

### 4.1 개요

`desktop_app.execute`은 `core_desktop_capability` Pack에서 제공하는 기능입니다. 데스크톱 앱의 시작, 중지, 상태 확인을 제어합니다.

### 4.2 매니페스트.json

```json
{
  "function_id": "execute",
  "description": "デスクトップアプリケーションを起動・管理する",
  "requires": ["desktop_app.execute"],
  "grant_config": {
    "permission_id": "desktop_app.execute",
    "dangerous": true,
    "allowed_packs": ["my_desktop_pack"],
    "max_token_lifetime": 3600
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "pack_id": {
        "type": "string",
        "description": "Pack ID whose desktop app to execute"
      },
      "action": {
        "type": "string",
        "description": "Action to perform: launch, stop, status",
        "default": "launch",
        "enum": ["launch", "stop", "status"]
      }
    },
    "required": ["pack_id"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "token": { "type": "string" },
      "port": { "type": "integer" },
      "expires_in": { "type": "integer" }
    },
    "required": ["token", "port", "expires_in"]
  },
  "calling_convention": "block"
}
```

### 4.3 위험 플래그

`desktop_app.execute`가 `dangerous: true`으로 설정되었습니다. 이는 데스크톱 앱이 호스트 OS에서 임의의 프로세스를 시작하기 때문에 높은 권한을 갖는다는 것을 의미합니다. Docker 격리된 Python 함수와 달리 데스크톱 앱은 호스트의 파일 시스템 및 네트워크에 직접 액세스할 수 있습니다.

따라서 사용자는 팩을 설치할 때 `desktop_app.execute` 부여를 명시적으로 승인해야 합니다.

### 4.4 액션

| 액션 | 설명 |
|--------|------|
| §루미§0§ | 앱 시작 및 토큰 발행(기본값) |
| §루미§0§ | 앱 실행 중지 |
| §루미§0§ | 앱의 실행 상태를 반환합니다 |

---

## 5. 팩쉘 사용법

### 5.1 빌드

```bash
cd pack-shell
cargo build --release
```

빌드 아티팩트: `target/release/pack-shell`

크로스 컴파일:

```bash
# macOS (Apple Silicon)
cargo build --release --target aarch64-apple-darwin

# macOS (Intel)
cargo build --release --target x86_64-apple-darwin

# Windows
cargo build --release --target x86_64-pc-windows-msvc

# Linux
cargo build --release --target x86_64-unknown-linux-gnu
```

### 5.2 CLI 참조

pack-shell에는 `run` 및 `version` 하위 명령이 있습니다.

#### 실행 하위 명령

```
pack-shell run <PACK_ID> --command <COMMAND> [OPTIONS]
```

| 인수 | 유형 | 필수 | 기본값 | 설명 |
|------|-----|------|-----------|------|
| §루미§0§ | 위치 인수 | ✅ | — | 출시할 팩의 ID |
| §루미§0§ | 문자열 | ✅ | — | 실행할 명령(예: `"python app.py"`) |
| §루미§0§ | 문자열 | ✅ | 환경 변수 `RUMI_API_TOKEN` | 커널 API 인증 토큰 |
| §루미§0§ | u16 | — | §루미§1§ | 커널 API 포트 번호 |
| §루미§0§ | 문자열 | — | §루미§1§ | 커널이 시작되지 않은 경우 시작 명령 |
| §루미§0§ | u64 | — | §루미§1§ | 커널 시작 대기 시간 초과(초) |
| §루미§0§ | 문자열 | — | 없음 | 앱 작업 디렉토리 |

#### 버전 하위 명령

```bash
pack-shell version
# 出力: pack-shell 0.1.0
```

### 5.3 실행 예

```bash
# 基本的な使い方
pack-shell run my_desktop_pack --command "python app.py" --working-dir /path/to/my_desktop_pack --api-token "$TOKEN"

# 全オプション指定
pack-shell run my_desktop_pack \
  --command "python app.py" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --api-token "your-api-token" \
  --timeout 60 \
  --working-dir /path/to/workdir
```

### 5.4 실행 흐름

pack-shell은 다음과 같이 데스크톱 앱을 시작합니다.

1. `GET /health`으로 커널의 동작상태를 확인한다
2. 커널이 응답하지 않으면 `--kernel-cmd`로 커널을 시작하고 상태 점검을 폴링합니다(1초 간격, 최대 `--timeout`).
3. `POST /api/desktop/token`에서 임시 토큰을 받으세요.
4. 환경 변수 `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID`를 설정하고 앱 프로세스를 시작합니다.
5. 앱 프로세스가 끝날 때까지 기다렸다가 종료 코드를 반환합니다.

### 5.5 환경 변수

pack-shell이 읽는 환경 변수:

| 변수 | 설명 |
|------|------|
| §루미§0§ | `--api-token` 대체. CLI 인수가 우선 적용됩니다 |

`DesktopAppManager`를 통한 실행은 `RUMI_API_TOKEN`을 환경 변수로 제공하는 계약으로 고정됩니다.

pack-shell이 앱에 전달하는 환경 변수:

| 변수 | 설명 |
|------|------|
| §루미§0§ | 커널에서 발행한 임시 토큰 |
| §루미§0§ | 커널 API 포트 번호 |
| §루미§0§ | 대상 팩 ID |

---

## 6. API 참조

### 6.1 POST /api/desktop/token

데스크톱 앱용 임시 토큰을 발행합니다. `core_desktop_capability` Pack에서 제공하는 API 경로입니다.

#### 요청

```json
{
  "pack_id": "my_desktop_pack"
}
```

| 필드 | 유형 | 필수 | 설명 |
|-----------|-----|------|------|
| §루미§0§ | 문자열 | ✅ | 토큰이 발급된 팩 ID |

#### 응답(성공)

```json
{
  "token": "abc-123-xyz",
  "port": 8765,
  "expires_in": 3600
}
```

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| §루미§0§ | 문자열 | 단기 액세스 토큰 |
| §루미§0§ | 정수 | 커널 API 포트 번호(기본값: 8765) |
| §루미§0§ | 정수 | 토큰 만료 시간(초, 기본값: 3600) |

#### 응답(오류)

```json
{
  "error": "desktop_app.execute not granted for pack: my_desktop_pack",
  "status_code": 403
}
```

| 상태_코드 | 설명 |
|------------|------|
| 400 | `pack_id` 지정되지 않았거나 유효하지 않음 |
| 403 | `desktop_app.execute`에 대한 보조금 없음 |
| 500 | 내부 오류 |
| 503 | 데스크탑 기능 핸들러를 사용할 수 없음 |

---

## 7. 바로가기 생성

### 7.1 데스크탑앱매니저

`desktop_app_manager.py`의 `DesktopAppManager` 클래스는 Pack 데스크톱 앱의 수명 주기를 관리합니다.

#### 주요 메소드

| 방법 | 설명 |
|--------|------|
| §루미§0§ | Pack 데스크톱 앱 등록 및 플랫폼별 바로가기 생성 |
| §루미§0§ | 바로가기 구독 취소 및 삭제 |
| §루미§0§ | 등록된 앱 시작 |
| §루미§0§ | SIGTERM |
| §루미§0§ | 등록된 앱 목록 반환 |

#### Register_app의 반환 값

```json
{
  "success": true,
  "shortcut_path": "/Users/user/Applications/MyApp.app"
}
```

### 7.2 플랫폼 단축키

`register_app`은 플랫폼별 바로가기를 자동으로 생성합니다.

| 플랫폼 | 형식 | 위치 |
|---------------|------|--------|
| macOS(`darwin`) | `.app` 번들(Info.plist + 실행 스크립트) | §루미§2§ |
| 윈도우(`win32`) | `.lnk` 바로가기(PowerShell로 생성됨) | §루미§2§ |
| 리눅스 | §루미§0§ 파일 | §루미§1§ |

단축키 `AppName`는 `desktop_app.window.title`(또는 지정되지 않은 경우 `pack_id`)에서 가져옵니다.

### 7.3 팩-쉘 바이너리 검색

`DesktopAppManager`은 다음 순서로 팩-쉘 바이너리를 검색합니다:

1. 환경 변수 `RUMI_PACK_SHELL_PATH`에 지정된 경로
2. 시스템 내 `PATH`에서 `pack-shell`를 검색하세요.

찾을 수 없는 경우 `register_app`는 오류를 반환합니다.

---

## 8. 보안

### 8.1 왜 위험한가요?

`desktop_app.execute`는 다음과 같은 이유로 `dangerous: true`로 설정됩니다.

- 데스크톱 앱은 호스트 OS에서 직접 실행됩니다(Docker 격리 없음).
- 파일 시스템, 네트워크, 기타 프로세스에 접근 가능
- `command` 필드에 지정된 모든 명령이 실행됩니다.

### 8.2 사용자 승인의 중요성

팩은 악의적인 의도로 설계되었습니다. 사용자는 보조금을 승인하기 전에 데스크탑 앱 `command`이 실행하는 프로그램을 확인해야 합니다.

### 8.3 토큰 만료 시간

`POST /api/desktop/token`으로 발행된 토큰은 짧은 시간(기본값 3600초 = 1시간) 후에 만료됩니다. `max_token_lifetime`은 `grant_config`에 의해 제어됩니다.

`allowed_packs`은 실패 시 닫힙니다. 빈 배열 `[]`, 지정되지 않음 또는 불법 유형은 어떤 팩에서도 허용되지 않습니다. 모든 팩을 명시적으로 허용해야 하는 경우 유효성 검사 목적으로 `["*"]`를 지정할 수 있지만 일반적으로 실행하려는 팩 ID를 나열해야 합니다.

### 8.4 권장 사항

- 신뢰할 수 있는 출처의 팩만 설치
- 승인 승인 전 `desktop_app.command`의 내용을 확인하세요.
- 더 이상 필요하지 않은 팩의 경우 `unregister_app`으로 단축키를 삭제하세요.
- 특정 팩에만 부여를 허용하도록 `allowed_packs`를 설정합니다.

---

## 9. 개발 흐름

### 9.1 단계별

1. **앱 개발**: tkinter, Qt, Electron 등과 같은 프레임워크를 사용하여 데스크톱 앱을 만듭니다.
2. **환경 변수 지원**: `RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID`를 읽고 ​​앱 내에서 Kernel API와 통신하는 코드를 구현합니다.
3. **팩쉘로 테스트**: `pack-shell run <PACK_ID> --command "python app.py" --working-dir <DIR> --api-token <TOKEN>`으로 작동을 확인합니다.
4. **ecosystem.json에 Desktop_app 추가**: `command`, `window`, `platforms` 등을 설정합니다.
5. **팩 설치**: `ecosystem/`에 배치하거나 PackImporter로 가져오기
6. **승인 승인**: GrantManager에서 `desktop_app.execute`에 대한 보조금을 설정합니다.
7. **바로가기 생성**: DesktopAppManager의 `register_app`을 사용하여 플랫폼별 바로가기를 자동으로 생성합니다.

### 9.2 로컬 개발 팁

또한 pack-shell을 사용하지 않고 환경 변수를 수동으로 설정하고 앱을 직접 시작할 수도 있습니다.

```bash
export RUMI_TOKEN="dev-token-for-testing"
export RUMI_PORT="8765"
export RUMI_PACK_ID="my_desktop_pack"
python app.py
```

커널이 실행되면 `GET /health`으로 연결을 확인할 수 있습니다:

```bash
curl http://localhost:8765/health
# {"status": "ok"}
```

---

## 10. 문제 해결

### pack-shell이 커널에 연결할 수 없습니다.

- 커널이 실행 중인지 확인: `curl http://localhost:8765/health`
- 포트 번호가 올바른지 확인하세요. 기본값은 `8765`입니다.
- `--kernel-cmd`에 올바른 커널 시작 명령이 지정되어 있는지 확인하십시오.

### 토큰을 가져올 때 403 오류가 발생했습니다.

- `desktop_app.execute`의 Grant가 설정되어 있는지 확인하세요.
- `pack_id`이 올바른지 확인하세요.
- API 토큰(`--api-token` 또는 `RUMI_API_TOKEN`)이 유효한지 확인하세요.

### 바로가기가 생성되지 않았습니다.

- pack-shell 바이너리가 있는지 확인하십시오. `RUMI_PACK_SHELL_PATH`을 설정하거나 `PATH`에 추가하십시오.
- `register_app`의 반환 값을 확인하세요. `{"success": false, "error": "..."}`에 오류 메시지가 포함되어 있습니다.

### 앱이 시작되지 않습니다

- `desktop_app.command`이 올바른 명령인지 확인하십시오. 쉘에서 직접 실행해 보십시오.
- `working_dir`이 올바른 디렉터리를 가리키는지 확인하세요.
- 필요한 종속 라이브러리가 설치되어 있는지 확인

### macOS에서 .app을 열 수 없습니다.

- 게이트키퍼에 의해 차단된 경우: "시스템 환경설정 > 보안 및 개인정보 보호"에서 허용
- 실행 스크립트에 실행 권한이 있는지 확인: `chmod +x ~/Applications/MyApp.app/Contents/MacOS/launch`

---

## 관련 문서

- [팩 개발 가이드](./pack-development.md) — 팩 개요
- [다국어 팩 개발 가이드](./multilang_pack_guide.md) — Python 이외의 언어로 팩을 개발하는 방법
- [샘플 코드: 데스크톱 앱 팩](examples/desktop_app_pack/) — 데스크톱 앱 팩 템플릿
- [pack-shell README](../../../../pack-shell/i18n/ko/README.md) — 팩-셸 바이너리 세부정보
