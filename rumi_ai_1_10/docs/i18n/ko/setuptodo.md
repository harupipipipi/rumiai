<!-- docs-i18n-links:start -->
[EN](../../setuptodo.md) | [JP](../ja/setuptodo.md) | [KR](./setuptodo.md) | [CN](../zh-cn/setuptodo.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 설정 및 데스크탑 배포 TODO

> **기존 계획 메모**: 구현 계획의 내역입니다. 현재 정책은 [roadmap.md](./roadmap.md) 및 [docs/README.md](./README.md)을 참조하십시오.

최종 업데이트 날짜: 2026-03-17

패턴 C 아키텍처를 기반으로 한 로드맵입니다. Rust Launcher(thin)는 Kernel 프로세스를 관리하며, 설정 UI, 제어판, Flow Editor 등은 모두 Pack에서 제공하는 Web UI(React)입니다. React UI 구현을 담당합니다.

---

## 1. 디자인 결정

### 1.1 패턴 C 채택

3계층 아키텍처: Rust Launcher + 커널 + 팩.

- **Rust Launcher**: 단 5가지 책임: PBS 구성, 커널 프로세스 관리, 상태 확인, 트레이 아이콘, 브라우저 열기
- **커널**: Python 런타임. Flow 실행, Pack 관리, API 서버
- **Pack**: 모든 UI 기능을 팩으로 제공 (React Web UI)

### 1.2 인증/데이터 저장

- **인증**: Supabase Auth(OAuth 전용: Google/GitHub). 이메일/비밀번호 인증 없음
- **프로필 데이터 저장**: Cloudflare KV(Supabase에 저장하지 않음)
- **로컬 프로필**: user_data/settings/profile.json

### 1.3 IPC

기존 pack_api_server(HTTP localhost:8765)를 사용합니다. 새로운 IPC가 필요하지 않습니다.

### 1.4 UI 정책

- React + TSX로 제작된 모든 웹 UI
- React UI는 사용자의 손에 있습니다. 에이전트는 Python 백엔드 + Flow + API + Rust입니다.
- 런처의 프런트 엔드(제어판)도 React입니다.

### 1.5 아이콘 정책

- 미리 설정된 아이콘만 사용 가능 (사용자 원본 아이콘 업로드는 지원되지 않습니다.)
- 아이콘 필드는 사전 설정된 ID 문자열(예: "cat", "avatar_03")을 저장합니다.
- 이미지 파일은 로컬에 저장됩니다. 사이트로부터 ID를 수신하고 해당 이미지를 표시합니다.

---

## 2. 아키텍처 개요

```
┌──────────────────────────────────────────────────────────┐
│                    Rust ランチャー                         │
│  (PBS構築 / Kernel起動 / ヘルスチェック / トレイ / open)      │
└───────┬──────────────────────────────────┬────────────────┘
        │ spawn                            │ open browser
        ▼                                  ▼
┌──────────────────────┐        ┌──────────────────────┐
│       Kernel         │        │    ブラウザ (Web UI)    │
│  (Python runtime)    │◄──────►│   React SPA           │
│                      │  HTTP  │   localhost:8765      │
│  ┌────────────────┐  │        └──────────────────────┘
│  │ pack_api_server │  │
│  │ :8765           │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Flow Engine    │  │
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Pack Manager   │  │
│  └────────────────┘  │
└──────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                         Packs                             │
│  ┌──────────────┐ ┌──────────────────┐                   │
│  │ core_setup   │ │ core_control_panel│                   │
│  │ (Phase B)    │ │ (Phase C)         │                   │
│  └──────────────┘ └──────────────────┘                   │
└──────────────────────────────────────────────────────────┘
```

---

## 3. profile.json 스키마

```json
{
  "schema_version": 1,
  "initialized_at": "2026-03-17T12:00:00Z",
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer",
  "setup_completed": true
}
```

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| 스키마_버전 | 정수 | 스키마 버전 |
| 초기화_at | 문자열(ISO 8601) | 설정 완료 날짜 및 시간 |
| 사용자 이름 | 문자열 | 사용자 이름 (필수, 최대 100자) |
| 언어 | 문자열 | 언어 코드(ja, en, zh, ko, es, fr, de, pt, ru, ar) |
| 아이콘 | 문자열 또는 null | 사전 설정된 아이콘 ID |
| 직업 | 문자열 또는 null | 직업 |
| 설정 완료 | 부울 | 설정 완료 플래그 |

---

## 4. 진행 상황

### 완료

| 작업 | 내용 |
|--------|------|
| 코드 검토 | C+ 등급. 보안 아키텍처 문제 식별 |
| SEC-1 | secure_executor.py: Docker 이미지 다이제스트 고정 + _sanitize_context 향상 |
| SEC-2 | python_file_executor.py: Docker 이미지 다이제스트 수정됨 |
| 앱-1 | app.py: 허용된 가드 강화(화이트리스트 방법) |
| 조사 1 | Python 패키징: PBS + uv를 사용한 조건부 GO |
| 설문조사 2 | 제어판 + 실행기 + 마켓플레이스 개념 |
| 조사 3 | Pack + Flow로 설정이 가능한가요? → 패턴 C 채택 |
| 단계 B | core_setup Pack Python 백엔드 + 흐름 정의 |
| 페이즈 A | 커널 API 확장: /health, /api/setup/status, /api/setup/complete, 정적 파일 전달 |
| 사이트 배포 | Cloudflare 페이지(rumi-setup.pages.dev) |
| 사이트 인증 | Supabase Auth OAuth(Google/GitHub) 작동 확인 |

### 진행 중

| 작업 | 책임 | 내용 |
|--------|------|------|
| 사이트 마무리 | 사용자 | 더미폼 삭제, 10개 언어로 변경, 직업 추가, KV 스토리지 구현 |
| 앱 협업 승인 화면 | 사용자 | /승인 페이지(설계 완료, 구현 대기 중) |
| 사전 설정 아이콘 생성 | 사용자 | ID 네이밍 + 이미지 생성 |

### 시작되지 않음

| 작업 | 책임 | 내용 |
|--------|------|------|
| R 단계 | 에이전트(Rust) + 사용자(React) | Rust 런처 + 업데이트 메커니즘 |
| 단계 C | 에이전트(Python) + 사용자(React) | core_control_panel 팩 |
| 페이즈 U | 에이전트 | 업데이트 메커니즘 |
| 단계 D/E | 에이전트 + 사용자 | 마켓플레이스(마지막 차례) |
| 페이즈 F | 에이전트 | 팩 개발자 CLI |
| 페이즈 G | 에이전트 | 보안 강화 |

---

## 5. 단계 구성

### R 단계: Rust Launcher(책임자: 에이전트 + 사용자)

Rust로 만든 얇은 런처 바이너리입니다.

**담당 상담원:**

- R-1: 화물 프로젝트 초기화 + 크로스 플랫폼 빌드 설정
- R-2: PBS 다운로드/추출(macOS/Windows/Linux)
- R-3: venv 생성 + uv pip 설치
- R-4: 커널 프로세스 생성 + stdout/stderr 파이프
- R-5: 상태 확인 루프(localhost:8765/health, 시간 제한 30초)
- R-6: 시스템 트레이(트레이 아이콘 크레이트)
- R-7: 브라우저 열기(크레이트 열기)
- R-8: 정상 종료(SIGTERM → 커널 중지 → 프로세스 종료)

**사용자 책임:**

- 없음(런처 자체에는 UI가 없습니다. UI는 core_control_panel React입니다)

### A단계: 커널 API 확장 ★완료

- GET /health — 상태 확인(인증 필요 없음)
- GET /api/setup/status — 설정 상태(인증이 필요하지 않음)
- POST /api/setup/complete — 설정 완료(인증 필요 없음)
- 정적 파일 배포 미들웨어
- AppLifecycleManager

### B단계: core_setup 팩 ★Python 백엔드 완료

**완료:**

- 생태계.json, check_profile.py, save_profile.py, launch_setup_ui.py
- setup_wizard.flow.yaml, 00_startup.flow.yaml 수정

**남은 작업(사용자 책임):**

- B-1: 사이트 마무리(더미폼 제거, 10개 언어 추가, 직업 추가)
- B-2: Cloudflare KV 프로필 스토리지 구현
- B-3: 앱 협력 승인 화면(/authorize)
- B-4: 프리셋 아이콘 생성

### C단계: core_control_panel 팩(담당자: 상담원 + 사용자)

대시보드 + 팩 관리 + 흐름 편집기 + 설정 화면 + 업데이트 확인.

**담당 에이전트(Python 백엔드):**

- C-1: Ecosystem.json 생성
- C-2: 대시보드 API(Pack list, Flow list, 시스템 상태)
- C-3: 팩 관리 API(설치, 제거, 활성화/비활성화)
- C-4: Flow Editor API(Flow CRUD, 단계 편집, 실행)
- C-5: 설정 API(profile.json 편집, 환경 설정)
- C-6: 업데이트 확인 API

**사용자 책임(React UI):**

- C-7: 대시보드 화면
- C-8: 팩 관리 화면(Steam 라이브러리 스타일)
- C-9: Flow Editor 화면(React Flow)
- C-10: 설정 화면
- C-11: 업데이트 화면

### U단계: 업데이트 메커니즘(담당: 상담원)

- U-1: 버전 관리(현재 버전, 최신 버전 받기)
- U-2: 업데이트 확인 API(Cloudflare Workers 또는 R2 버전 파일)
- U-3: Rust 런처 자체 업데이트
- U-4: 커널(Python) 업데이트(소스코드 교체)
- U-5: 팩 업데이트

### D 단계: 마켓플레이스 BE(마지막 턴)

Cloudflare 작업자 + R2 + D1 + Supabase 인증

### E단계: 마켓플레이스 FE(마지막 턴)

Cloudflare Pages + 실행 프로그램 내 통합

### F단계: 개발자 CLI 팩

루미팩 초기화 / 유효성 검사 / 빌드 / 게시 / 테스트

### G단계: 보안 강화

팩 서명 확인, 코드 서명, CSP 헤더

---

## 6. 종속성

```
R Phase ──────┐
              ▼
Phase A ★完了  Phase B ★Python完了（React残り）
  │               │
  ▼               ▼
Phase C ──── Phase U
  │
  ▼
Phase F ──── Phase G
  │
  ▼
Phase D ──── Phase E（最後）
```

---

## 7. MVP 정의

MVP = R 단계 + 단계 A + 단계 B + 단계 C의 최소 구성 + 단계 U(업데이트). 마켓플레이스가 없습니다.

---

## 8. 앱 연동 흐름

### 설정 흐름

1. 데스크탑 앱이 브라우저에서 `https://rumi-setup.pages.dev/authorize?callback=http://localhost:8765/api/setup/complete`을 엽니다.
2. 사이트에 로그인되어 있는지 확인 → 로그인이 되어 있지 않은 경우 /login → 로그인이 되어 있는 경우 승인 화면
3. 승인 화면: “이 앱에 프로필 정보를 보내시겠습니까?”
4. 승인 → localhost:8765/api/setup/complete에 대한 POST(가져오기 완료)
5. 앱측에 profile.json 저장 → 설정 완료

### POST용 JSON /api/setup/complete

```json
{
  "username": "haru",
  "language": "ja",
  "icon": "cat",
  "occupation": "engineer"
}
```

---

## 9. 부팅 순서

### 첫 출시

1. 러스트 런처를 시작하세요
2. PBS 확인 → 그렇지 않은 경우 다운로드, 추출, venv 생성, 종속성 설치
3. 커널 생성 → 상태 확인 → 준비
4. 시작 흐름: setup_check → need_setup: true
5. 브라우저에서 rumi-setup.pages.dev/authorize를 엽니다.
6. 사용자 승인 → localhost:8765에 POST → profile.json 저장
7. 설정 완료 → 제어판 디스플레이

### 정상 시작

1. 러스트 런처를 시작하세요
2. PBS 확인 → 존재 → 건너뛰기
3. 커널 생성 → 상태 확인 → 준비
4. 시작 흐름: setup_check → need_setup: false
5. 브라우저에 제어판 표시

---

## 10. 인프라 구성

| 서비스 | 신청 |
|----------|------|
| Cloudflare 페이지 | 사이트(rumi-setup.pages.dev) |
| 클라우드플레어 KV | 프로필 데이터 저장 |
| Cloudflare 작업자 | 업데이트 확인 API, Future Marketplace API |
| 클라우드플레어 R2 | PBS/uv 유통, 향후 Pack 유통 |
| 클라우드플레어 D1 | 미래마켓플레이스 DB |
| 수파베이스 인증 | 사용자 인증(OAuth:Google/GitHub) |

---

## 11. 배포 구성

### 맥OS

```
RumiAI.app/Contents/
├── MacOS/rumi-launcher
├── Resources/
│   ├── python/          # PBS
│   ├── rumi_ai_1_10/   # ソースコード
│   └── user_data/       # 初回起動時作成
└── Info.plist
```

### 윈도우

```
RumiAI/
├── rumi-launcher.exe
├── python/
├── rumi_ai_1_10/
└── user_data/
```

### 리눅스

```
rumi-ai/
├── rumi-launcher
├── python/
├── rumi_ai_1_10/
└── user_data/
```

---

## 12. 미정사항

- 설정 수집 항목 최종 목록
- 언어팩 배포 방법
- "실행 취소" 기능 설정
- Windows의 user_data 경로
- CI/CD 파이프라인 구축
- Python 버전 고정 정책
- macOS 공동 설계 / 공증
- Windows 코드 서명
- core_control_panel에 대한 웹 UI 전달 방법
- Rust 발사기 상자 선택
- 개발자 CLI 언어 팩
- 버전 파일 형식 및 배포 방법 업데이트
