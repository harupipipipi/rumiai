<!-- docs-i18n-links:start -->
[EN](../../roadmap.md) | [JP](../ja/roadmap.md) | [KR](./roadmap.md) | [CN](../zh-cn/roadmap.md)
<!-- docs-i18n-links:end -->

# rumiai defaults Pack — 로드맵

최종 업데이트: 2026-03-06
상태 범례: ✅ 완료 / 🔧 수정 필요 / ⬜ 미착수

---

## 0단계: 기초(완료)

모두 완료. 시작 → 브라우저 액세스 → AI 채팅까지 동작 확인 완료.

| ID | 내용 | 상태 |
|----|------|-----------|
| G0-G3 | 해골 ~ Chat/Flow 레이어 | ✅ |
| P0 | 정규화 | ✅ |
| G4 | Agent / Transport / Frontend | ✅ |
| G5 | AI 공급자 (OpenAI, Anthropic, Google, Genspark) + MCP | ✅ |
| G6 | UX 강화 | ✅ |
| G7 | Tool & Prompt 확장 | ✅ |
| G8 | Agent 강화 + 전체 수정 | ✅ |
| G9a/b | 지식 기반 + 흐름 내 자동 검색 | ✅ |
| docs | 문서 24 파일 + 수정 4 번 | ✅ |
| startup/boot-fix | setup.py, ecosystem.json, components/ | ✅ |
Step 0 | Route Registry 패턴 마이그레이션(44→100 루트 분산) | ✅ |

---

## 1단계: 향상된 기능(T1-T17)

17 태스크의 병렬 구현. Route Registry로 http.py를 변경하지 않고 완료.

| ID | 내용 | domain | blocks | 루트 | 상태 |
|----|------|--------|--------|--------|-----------|
| T1 | 다중 대화 세션 관리 | ✅ session_manager.py | 🔧 blocks/chat/session/ 작성되지 않음 |
| T2 | AI로 대화 기록 편집 | ✅ history_editor.py | 🔧 blocks/chat/history/ 작성되지 않음 | 🔧 등록되지 않음 |
| T3 | 런타임 도구 만들기 | ✅ runtime_creator.py | ✅ 기존 blocks에서 지원 | ✅ | ✅ |
| T4 | 면책 동의 tool | ✅ disclaimer_manager.py | ✅ 기존 blocks에서 대응 | ✅ |
| T5 | prompt 고급화 (빌더, 버전 관리) | ✅ builder.py | ✅ blocks/prompt/advanced/ | ✅ 8 루트 | ✅ |
| T6 | tool/prompt 통합 템플릿 | ✅ unified.py | ✅ blocks/prompt/convert.py | ✅ | ✅ |
| T7 | rumi 모델 (자동 라우팅) | ✅ model_router.py | ✅ blocks/ai/routing/ | ✅ 10 루트 | ✅ |
| T8 | 컨텍스트 표시 API | ✅ analyzer.py | 🔧 전용 blocks 없음 | 🔧 루트 미등록 | 🔧 |
| T9 | dev tool 확장 | ✅ usage_tracker.py | ✅ 기존 blocks에서 지원 | ✅ | ✅ |
| T10 | 조직 에이전트 기반 | ✅ org_manager.py | ✅ blocks/agent/org/ (11 파일) | 🔧 루트 미등록 | 🔧 |
| T11 | Slack 바람 AI 채팅 | ✅ channel_manager.py | ✅ blocks/chat/channel/ (10 파일) | ✅ 10 루트 | ✅ |
| T12 | 정기 실행 에이전트 | ✅ scheduler.py | ✅ blocks/agent/scheduler/ (9 파일) | ✅ 9 루트 | ✅ |
| T13 | 작업 중 지시 추가 | ✅ interrupt_manager.py | ✅ blocks/agent/interrupt/ (8 파일) | ✅ 9 루트 | ✅ |
| T14 | Linux 환경 + 좌표 조작 | ✅ container_manager.py | ✅ blocks/tool/container/ (12 파일) | ✅ 13 루트 | ✅ |
| T15 | 권한 관리 | ⬜ 미실장 | ⬜ 미실장 | ⬜ | ⬜ |
| T16 | CLI 완전 분리 | ✅ cli.py | ✅ blocks/cli/entry.py | ✅ 2 루트 | ✅ |
| T17 | 탭 시스템 백엔드 | ⬜ 미실장 | ⬜ 미실장 | ⬜ |

---

## 2단계: 품질 보증 + 잔여 수정

### 2-A: P1 수정(블로커)

| ID | 내용 | 상세 |
|----|------|------|
| P1-1 | 시스템 루트 404 수정 | /api/health, /, /api/context, /static/* 를 io.http.route 에 등록. Registry 모드에서도 액세스 가능하게 |
| P1-2 | T15 권한 관리 구현 | domain/permission/manager.py, user_store.py, role_store.py, auth.py, audit.py + blocks/permission/ + setup.py 루트 등록 |
| P1-3 | T17 탭 시스템 구현 | domain/frontend/tab_manager.py, tab_presets.py + blocks/frontend/tabs/ + setup.py 루트 등록 |

### 2-B: P2 수정(기능 보완)

| ID | 내용 | 상세 |
|----|------|------|
| P2-1 | T10 조직 에이전트의 루트 등록 | blocks/agent/setup.py
| P2-2 | T1 세션 관리 blocks + 루트 | blocks/chat/session/ 생성 + chat/setup.py 에 8 루트 추가 |
| P2-3 | T2 기록 편집의 blocks + 루트 | blocks/chat/history/ 작성 + chat/setup.py 에 4 루트 추가 |
| P2-4 | T8 컨텍스트 API의 루트 | /api/context/conversation/{id}, /api/context/system 등록 |
| P2-5 | ecosystem.json의 provides 업데이트 | T10/T12/T13/T14의 새로운 핸들러 반영 |

### 2-C: 파일 검사

| ID | 내용 | 상세 |
|----|------|------|
| FC-1 | 모든 블록 def run 서명 확인 | def run(input_data, context): 가 통합되어 있는지 |
| FC-2 | import 스타일 통일 확인 | sys.path.insert(0, pack_root) + from blocks._common import ... |
| FC-3 | pass / TODO / NotImplementedError 잔여 확인 | 금지된 구현되지 않은 함수가 있습니까?
| FC-4 | setup.py 루트 수와 실제 블록 수 일치 | 등록 된 루트 대상 모듈이 모두 존재합니까?
| FC-5 | 불필요한 파일 삭제 | transport/uds.py, blocks/frontend/stop.py 등 |

### 2-D: rumiai 커널 규칙 적합성 검사

| ID | 내용 | 상세 |
|----|------|------|
| RC-1 | ecosystem.json 스키마 준수 | 커널 W26의 ecosystem.schema.json을 준수합니까?
| RC-2 | components/manifest.json 존재 확인 |
| RC-3 | setup.py context 사용의 유효성 | context["interface_registry"] 등의 사용이 커널 사양을 준수하는가 |
| RC-4 | KernelFacade API 제한 준수 | get_interface, list_interfaces, emit 이외를 호출하지 않습니까 |
| RC-5 | Pack 승인 흐름 호환성 | 파일 변경 → modified 상태 → 재승인이 올바르게 작동하는지 |

### 2-E: defaults로 중립성 검사

| ID | 내용 | 상세 |
|----|------|------|
| NC-1 | AI 공급자의 희생 없음 | 특정 공급자가 하드 코딩되지 않았습니까? stub/default가 폴백인가 |
| NC-2 | 모형의 최선 없음 | rumi 모형 라우팅이 공정한가? 특정 모델을 부당하게 우선하지 않습니까?
| NC-3 | 스토리지 중립성 |
| NC-4 | 외부 종속 최소화 | 표준 라이브러리 이외의 필수 종속성이 없는지 (Docker SDK는 선택 사항입니까?) |
| NC-5 | 설정 재정의 가능성 | 모든 거동이 환경 변수 or API 로 변경 가능한가. 하드 코드 설정이 없습니까?

---

## 3단계: 확장성 검증

### 3-A: user_data 확장성

| ID | 내용 | 상세 |
|----|------|------|
| UX-1 | 다른 팩의 user_data 액세스 | 다른 팩에는 자체 user_data 서브 디렉토리가 있습니까?
| UX-2 | 데이터 마이그레이션 | user_data 스키마 변경시 마이그레이션 수단이 있습니까 |
| UX-3 | 백업/복원 | user_data의 일괄 내보내기/가져오기 가능 |
| UX-4 | 스토리지 플러그인 | JSON 파일 이외의 스토리지 백엔드 (SQLite 등)로 교체 가능 |
| UX-5 | 동시 액세스 안전성 | 다중 쓰레드/프로세스로부터의 user_data 기입이 안전인가(락 기구) |

### 3-B: Pack 간 확장성

| ID | 내용 | 상세 |
|----|------|------|
| PX-1 | 다른 팩에서 루트 추가 테스트 |
| PX-2 | 다른 팩에서 domain 교체 |
| PX-3 | 이벤트 후크 | EventBus에서 defaults Pack 동작에 후크 할 수 있습니까?
| PX-4 | 프로바이더 플러그인 | 새로운 AI 프로바이더를 다른 팩으로부터 추가할 수 있을까(Genspark 방식의 재현) |

---

## 4단계: 프로덕션 준비

### 4-A: 권한 시스템 완성

| ID | 내용 | 상세 |
|----|------|------|
| AUTH-1 | T15의 완전 구현 | 2 단계 A P1-2의 기반 구현. 여기서 통합 테스트 + 에지 케이스 지원 |
| AUTH-2 | 루트 당 권한 정의 | 모든 100+ 루트에 필요한 권한 정의 |
| AUTH-3 | 인증 미들웨어 통합 |
| AUTH-4 | 기본 사용자 + 초기 설정 흐름 | 처음 시작할 때 admin 사용자 작성 |

### 4-B: tool / prompt의 한가지 방법

| ID | 내용 | 상세 |
|----|------|------|
| TP-1 | 내장 도구 세트 | web_search, calculator, code_exec, file_read, file_write, http_request |
| TP-2 | 내장 prompt 템플릿 | general_assistant, coder, analyst, translator, summarizer, creative_writer |
| TP-3 | 도구 / 프롬프트 설명서 | 각 도구 / 프롬프트 사용, 매개 변수 및 예 |
| TP-4 | tool/prompt 테스트 | 각 도구/프롬프트 동작 확인 |

### 4-C: 프런트 엔드 세트(사용자 담당)

| ID | 내용 | 상세 | 담당 |
|----|------|------|------|
| FE-1 | shell.html의 대규모 분할 | 배경, 사이드바, 입력바, 제목, chattab, setting으로 분할 | 사용자 |
| FE-2 | 탭 UI | 브라우저 스타일 탭 (normal, work, coding, agent, max, monitor) | 사용자 |
| FE-3 | 세션 UI | 대화 탭의 병렬 표시 (이력 1 / 이력 2 / 이력 3) | 사용자 |
| FE-4 | 채널 UI | Slack 바람 채널 목록 + 메시지 표시 | 사용자 |
| FE-5 | 컨텍스트 패널 | 현재 컨텍스트 정보를 실시간으로 표시 | 사용자 |
| FE-6 | Dev 패널 | 프롬프트 사용, 실시간 편집 | 사용자 |
| FE-7 | 권한 관리 UI | 사용자 / 역할 / 권한 관리 화면 | 사용자 |
| FE-8 | 면책 팝업 | 동의 tool 팝업 표시 | 사용자 |
| FE-9 | 컨테이너 조작 UI | Linux 환경의 조작 화면 + 스크린 샷 표시 | 사용자 |

---

## 5단계: 데스크톱 앱화

| ID | 내용 | 상세 |
|----|------|------|
DA-1 | Electron or Tauri 래퍼 | shell.html을 데스크톱 앱으로 패키징 |
| DA-2 | 네이티브 통지 | OS 통지 연계 (정기 실행 agent의 결과 통지 등) |
| DA-3 | 트레이 아이콘 | 배경 동작 + 트레이 아이콘 |
| DA-4 | 자동 부팅 설정 | OS 부팅시 자동으로 커널 + defaults Pack 시작 |
| DA-5 | 업데이터 | git pull 기반 자동 업데이트(or GitHub Releases) |

---

## 6단계: 컴파일 + 릴리스

| ID | 내용 | 상세 |
|----|------|------|
| CP-1 | Python 번들 | PyInstaller or Nuitka에서 커널 + defaults Pack을 단일 바이너리화 |
| CP-2 | 프런트 엔드 최적화 | shell.html minify + 자산 번들 |
| CP-3 | 크로스 플랫폼 빌드 | macOS, Linux, Windows 용 빌드 |
| CP-4 | 설치 프로그램 | macOS: .dmg, Linux: .AppImage/.deb, Windows: .msi |
| CP-5 | CI/CD 파이프라인 | GitHub Actions에서 빌드 + 테스트 + 릴리스 자동화 |
| CP-6 | 릴리스 노트 | 모든 기능의 릴리스 노트 작성 |

---

## 7단계: 최종 구성

| ID | 내용 | 상세 |
|----|------|------|
| CL-1 | 불필요한 파일 삭제 | transport/uds.py, transport/stdio.py (CLI 마이그레이션 후), blocks/frontend/stop.py |
| CL-2 | docs 최종 동기화 | 24 문서를 모든 기능에 맞게 업데이트 |
| CL-3 | README.md 업데이트 | 설치 절차, 기능 목록, 스크린 샷 |
| CL-4 | CHANGELOG.md 작성 | 전체 릴리스 이력 |
| CL-5 | LICENSE 확인 | 라이센스 파일의 최종 확인 |
| CL-6 | feature/genspark-provider 브랜치 삭제 | 병합된 브랜치 정리 |

---

## 통계

| 항목 | 수량 |
|------|------|
| 총 단계 수 | 8 (0-7) |
| 총 작업 수 | 약 80 |
| 완료된 작업 | 약 45 |
| 나머지 작업 | 약 35 |
| 등록 경로 수 | 100+ |
| 블록 수 | 100+ |
| domain 모듈 수 | 30+ |
| 문서 | 24 파일 |
