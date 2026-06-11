<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# 루미 AI

Rumi AI는 모듈식 AI 런타임 및 도구 작업 공간입니다.

저장소는 `rumi_ai_1_10/`에서 런타임 구현을 유지하는 반면, `rumi_ai/`은 버전이 안정적인 Python 진입점을 제공합니다. 정식 제어판 프런트엔드 소스는 `rumi_viewer/frontend`에 있습니다. 커널은 `/panel/`에서 빌드된 아티팩트를 제공합니다.

## 이럴 때 읽어보세요...

| 내가 하고 싶은 것 | 먼저 읽을 곳 | 보충제 |
|---|---|---|
| 목적에 맞게 문서를 따라가고 싶어요 | [`rumi_ai_1_10/docs/README.md`](./rumi_ai_1_10/docs/README.md) | "하고 싶은 것"부터 읽는 순서대로 안내해 드립니다 |
| 용어의 의미를 정렬하고 싶습니다 | [`rumi_ai_1_10/docs/terminology.md`](./rumi_ai_1_10/docs/terminology.md) | `rule`, `skill`, `team workspace`, `subagent` 호환되는 이름 정리 |
| 어차피 시작하고 싶어 | [`README.md`](./README.md)의 `Start` | 가장 짧은 시작 명령만 나열됩니다. |
| 런타임/커널의 전체적인 그림을 알고 싶습니다 | [`rumi_ai_1_10/README.md`](./rumi_ai_1_10/README.md) | 아키텍처와 주요 디렉터리에 대한 설명이 있습니다. |
| 코드를 읽지 않고 메커니즘을 이해하고 싶습니다 | [`rumi_ai_1_10/docs/concepts/system-mechanism.md`](./rumi_ai_1_10/docs/concepts/system-mechanism.md) | 시작, 흐름, 승인, 승인의 흐름을 텍스트 |
| 먼저 동작을 확인하고 싶습니다(튜토리얼) | [`rumi_ai_1_10/docs/tutorials/runtime-quickstart.md`](./rumi_ai_1_10/docs/tutorials/runtime-quickstart.md) | `--health`에서 `/panel/`까지의 최단 단계 |
| 시작하고 싶어요 `rumi_viewer` / 시청자가 어떻게 막히는지 보고 싶어요 | [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md) | 시작 절차 요약, `401`, 검은색 화면 및 `defaultspack`과의 관계 |
| 뷰어 측을 수정하고 싶습니다 | [`rumi_viewer/src-tauri/src/config.rs`](./rumi_viewer/src-tauri/src/config.rs) 및 [`rumi_viewer/src-tauri/src/kernel_manager.rs`](./rumi_viewer/src-tauri/src/kernel_manager.rs) | 뷰어는 Tauri 쉘이고 Rust 측은 커널 |
| pack / defaultspack을 사용하고 싶습니다 | [`rumi_ai_1_10/ecosystem/defaultspack/README.md`](./rumi_ai_1_10/ecosystem/defaultspack/README.md) | 이것은 chat, ai_client, 도구 등의 팩 측 구현입니다. |
| defaultspack의 프런트엔드를 확장하는 방법을 알고 싶습니다 | [`rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md`](./rumi_ai_1_10/ecosystem/defaultspack/docs/frontend_extensions.md) | 오른쪽 막대 추가, 설정 추가, 채팅 렌더러 확장 및 미리보기 피드 추가를 위한 게이트웨이입니다.
| API 키와 비밀을 처리하는 방법을 알고 싶습니다 | [`rumi_ai_1_10/docs/operations.md`](./rumi_ai_1_10/docs/operations.md)의 비밀 섹션 | `user_data/secrets/` 및 API 경로에 대한 설명이 있습니다 |
| 팩을 만드는 방법을 알고 싶습니다 | [`rumi_ai_1_10/docs/pack-development.md`](./rumi_ai_1_10/docs/pack-development.md) | Ecosystem.json의 매너, 경로, 권한을 정리했습니다 |
| 운영 및 감사의 개념을 알고 싶습니다 | [`rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`](./rumi_ai_1_10/docs/quality_pack/philosophy_memo.md) | 지속적인 발전과 회귀확인을 위한 가정을 정리하고 있습니다 |

## 저장소 레이아웃

- `rumi_ai_1_10/`: 커널/런타임/API/백엔드 소스 트리
- `rumi_ai/`: 버전이 안정적인 Python 진입점 패키지
- `pack-shell/`: 데스크탑 팩 실행기
- `rumi_viewer/`: 데스크톱 셸 및 제어판 프런트엔드 소스
- `rumi_mobile/`: 신뢰할 수 있는 LAN 기본 팩 액세스를 위한 Flutter iOS/Android 앱
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/`: defaultspack과 함께 번들로 제공되는 브라우저 동반 자산

## 설정

### 전제조건

- 파이썬 3.10+
- Node.js 18+
- npm
- 녹/화물(`rumi_viewer` 접촉 시)
- Flutter SDK(`rumi_mobile` 사용 시)

### 복제 및 설치

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r rumi_ai_1_10/requirements.txt -r rumi_ai_1_10/requirements-dev.txt
pip install -e ./rumi_ai_1_10

cd rumi_viewer/frontend
npm install
cd ../..
```

## 시작

```bash
source .venv/bin/activate
python -m rumi_ai --health
python -m rumi_ai
```

`--health`은 시스템 볼륨 사용량도 확인합니다. `disk` 프로브가 `DEGRADED` / `DOWN`인 경우 코드 문제보다는 여유 공간 부족이 원인일 수 있습니다.

## 일반적인 작업

### 바로가기

`just`을 설치한 경우 저장소 루트에서 일반 검사를 사용할 수 있습니다.

```bash
just -l
just tooling-test
just integrity
```

### 백엔드 상태 점검

```bash
python -m rumi_ai --health
```

### 런타임 시작

```bash
python -m rumi_ai
```

### 뷰어 개발

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

두 번째부터 `rumi_viewer/frontend/node_modules`이 남아 있으면 다음을 수행하여 시작할 수 있습니다.

```bash
cd rumi_viewer
cargo tauri dev
```

개발 뷰어는 저장소에서 `rumi_ai_1_10/`을 자동으로 감지하고 커널을 시작합니다.
`Open Defaultspack`은 개발 시작 시 저장소에 포함된 `defaultspack`보다 우선적으로 열립니다.
시작 시 멈추는 방법을 포함한 가이드는 [`rumi_ai_1_10/docs/rumi_viewer_start.md`](./rumi_ai_1_10/docs/rumi_viewer_start.md)을 참조하세요.

## 개발

```bash
source .venv/bin/activate
cd rumi_ai_1_10
python -m pytest tests/test_capability_trust_store.py
```

## 품질 팩

지속적인 개발, 감사 및 회귀 확인을 위한 운영 팩은 아래를 참조하세요.

- `rumi_ai_1_10/docs/quality_pack/philosophy_memo.md`
- `rumi_ai_1_10/docs/quality_pack/claude_desktop_quality_pack.md`
- `rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh`

## HMAC 마이그레이션

```bash
python -m rumi_ai migrate-hmac
```

## 구성요소

- `rumi_ai`: 안정적인 CLI 및 모듈 진입점
- `rumi_ai_1_10`: 커널, 런타임, API, 백엔드 및 문서
- `pack-shell`: 데스크탑 팩 및 브로커 토큰/부트스트랩 흐름 시작
- `rumi_viewer`: 뷰어측 애플리케이션 셸 및 표준 패널 프런트엔드 소스
- `rumi_mobile`: 베어러 인증 커널 팩 API용 모바일 원격 클라이언트
- `rumi_ai_1_10/ecosystem/defaultspack/browser_extensions/rumi_browser_companion`: defaultspack `browser_companion` 도구용 압축이 풀린 Chromium 확장

아키텍처 및 런타임에 대한 자세한 내용은 [rumi_ai_1_10/README.md](./rumi_ai_1_10/README.md)을 참조하세요.

Codex OSS에서 영감을 받은 코딩 도구 규칙에 대해서는 [AGENTS.md](./AGENTS.md) 및
[rumi_ai_1_10/docs/codex_oss_reference.md](./rumi_ai_1_10/docs/codex_oss_reference.md).
