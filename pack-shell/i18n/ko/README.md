<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# 팩쉘

Pack 데스크톱 앱 실행을 위한 도우미 바이너리입니다.

## 개요

pack-shell은 다음 흐름을 자동화합니다.

1. 커널의 /health 엔드포인트를 확인하세요.
2. 커널이 시작되지 않으면 자동으로 시작됩니다.
3. /api/desktop/token에서 인증 토큰을 가져옵니다.
4. 환경변수(RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID) 설정 후 앱 실행

## 빌드

```bash
cd pack-shell
cargo build --release
```

빌드 아티팩트: `target/release/pack-shell`

## 사용방법

```bash
# 基本的な使い方
pack-shell run <PACK_ID> --command "python app.py" --api-token "$TOKEN"

# 全オプション指定
pack-shell run my-pack-123 \
  --command "python app.py" \
  --api-token "your-api-token" \
  --port 8765 \
  --kernel-cmd "python -m rumi_ai" \
  --timeout 60 \
  --working-dir /path/to/workdir

# バージョン表示
pack-shell version
```

## 시작 흐름

```
pack-shell run
    │
    ▼
GET /health ──── OK ───────────────┐
    │                              │
    │ (timeout/error)              │
    ▼                              │
Start Kernel subprocess            │
    │                              │
    ▼                              │
Poll /health (1s interval)         │
    │                              │
    ▼ (healthy)                    │
    ◄──────────────────────────────┘
    │
    ▼
POST /api/desktop/token
    │
    ▼
Set env vars (RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID)
    │
    ▼
Spawn app subprocess (--command)
    │
    ▼
Wait for app exit → return exit code
```

## 환경 변수

### 입력(pack-shell로 읽음)

| 변수 | 설명 | 메모 |
|------|------|------|
| RUMI_API_TOKEN | API 인증 토큰 | --api-token 대안 |

`DesktopAppManager`에서 실행되는 데스크톱 앱은 `RUMI_API_TOKEN`을 환경 변수로 받는 계약입니다.

### 출력(앱으로 전달)

| 변수 | 설명 |
|------|------|
| 루미_토큰 | 데스크톱용 임시 토큰 |
| 루미_포트 | 커널 API 포트 |
| RUMI_PACK_ID | 대상 팩 ID |

## 크로스 빌드

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
