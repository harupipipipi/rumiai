<!-- docs-i18n-links:start -->
[EN](../../roadmap.md) | [JP](../ja/roadmap.md) | [KR](./roadmap.md) | [CN](../zh-cn/roadmap.md)
<!-- docs-i18n-links:end -->

# 루미 AI OS — 로드맵

## 🚀 5단계: Rumi Viewer + Pack Desktop 애플리케이션 [가장 중요/최우선 순위]

> **이 단계는 다른 모든 작업보다 우선합니다.**
> Rumi를 "터미널 없는 데스크톱 앱"으로 배포할 수 있게 하는 가장 중요한 이정표입니다.

### 아키텍처 개요

**설치 프로그램의 내용(사용자에게 배포됨):**

1. **Rumi 콘솔**(rumi-launcher, Rust) - 트레이에 상주합니다. 커널 프로세스 관리. 사용자는 일반적으로 이를 인식하지 못합니다.
2. **Rumi Viewer**(Tauri) — Pack 프런트엔드를 표시하는 범용 WebView 앱입니다. 사용자들이 매일 사용하는 주요 앱입니다.
3. **bundled/uv** — Python 환경 구축용입니다.
4. **app/** (rumi_ai_1_10/) — 커널 소스 코드.**루미 뷰어란 무엇인가요?**
- Tauri로 제작된 범용 WebView 애플리케이션
- `web_mount`에서 Pack이 선언한 프런트엔드(HTML/CSS/JS)를 표시합니다.
- 커널 API(localhost:8765)에만 접속할 수 있습니다. 외부사이트 접속이 안되네요
- Pack은 프런트 엔드 파일을 전달합니다. 호스트 환경(샌드박스 WebView)을 건드리지 마세요.
- 팩 백엔드는 Docker 컨테이너에서 격리되어 실행됩니다.
- "프런트엔드 = 샌드박스 WebView" + "백엔드 = Docker 격리"를 통한 이중 격리

**보안 모델:**
- 뷰어에 무언가를 표시하려면 `viewer:display` 기능이 필요합니다(기능 기반 권한 관리).
- 권한이 있는 한 모든 팩에서 뷰어를 사용할 수 있습니다.
- `core_viewer_capability`는 `core_docker_capability`, `core_communication_capability`와 동일한 포지션을 갖습니다.
- 팩이 자체 데스크톱 앱(Tauri/Electron 등)을 제공할 수 있지만 이는 "위험한 권한"(`desktop_app.execute`)으로 처리되며 명시적인 사용자 승인이 필요합니다.
- 대부분의 팩은 보안 뷰어 경로를 사용해야 합니다.

**사용자 경험:**
1. 사용자가 설치 프로그램(.dmg/.exe)을 사용하여 설치합니다.
2. 루미 뷰어를 더블클릭하세요.
3. 루미 콘솔이 자동으로 시작됩니다. → 커널이 백그라운드에서 시작됩니다.
4. 뷰어에 제어판이 표시됩니다.
5. 팩 설치 → AI 채팅 등 팩의 프런트엔드가 뷰어에 표시됩니다.
6. 단말기를 절대 만지지 마세요

**시작 흐름:**
```
Rumi Viewer 起動
  → Kernel ヘルスチェック（localhost:8765/health）
  → 未起動なら Rumi Console を自動起動
  → Kernel ready を待機
  → Viewer が localhost:8765/panel/ を WebView に表示
  → ユーザーが Pack を選択 → Pack のフロントエンドに遷移
```

**충돌/오류 처리:**
- Rumi Console(트레이 아이콘)을 사용하여 충돌 및 시작 오류를 표시하고 처리할 수 있습니다.
- 뷰어는 표시 전용입니다.

### TODO(구현 순서)

**V-1단계: 새로운 Rumi Viewer(Tauri) 생성** [가장 중요/최우선 순위]
- [ ] `rumi_viewer/` 새로운 Tauri 프로젝트 생성
- [ ] 커널 상태 확인 + 자동 시작(Rumi 콘솔을 통해)
- [ ] WebView에 localhost:8765/panel/ 표시
- [ ] 팩 전환 UI(뷰어 탐색)
- [ ] 커널 API에 대한 요청만 허용(외부 URL 차단)
- [ ] 창 관리(여러 팩을 동시에 열 수 있음)

**V-2단계: core_viewer_capability 신규 생성**
- [ ] `core_runtime/core_pack/core_viewer_capability/` 새로 만들기
- [ ] `viewer:display` 기능 정의
- [ ] 뷰어에 프런트엔드를 표시하기 위한 팩 관리 권한 부여
- [ ] 뷰어용 pack_token 발행 API (`/api/viewer/token`)

**V-3단계: 설치 프로그램 통합**
- [ ] Packager.toml에 Rumi Viewer 추가
- [ ] release.yml 업데이트(뷰어 빌드 추가)
- [ ] 설치 프로그램에 모든 Rumi Console + Rumi Viewer + 번들/uv + 앱/이 포함됩니다.
- [ ] macOS: .dmg에 두 앱 모두 포함
- [ ] Windows : NSIS + 시작메뉴 등록으로 모두 설치

**V-4단계: 데스크톱 앱 호환 가능 팩(선택 사항)**
- [ ] Ecosystem.json에 `desktop_app` 섹션을 추가했습니다.
- [ ] `desktop_app.command`으로 임의의 명령을 선언할 수 있습니다.
- [ ] `desktop_app.execute` 기능(위험한 권한, 명시적인 승인이 필요함)
- [ ] 팩-셸 바이너리(커널 자동 시작 + 토큰 획득 + 명령 실행)
- [ ] .app / .lnk 생성(PackAppRegistrar)

**V-5단계: 문서 + 템플릿**
- [ ] `docs/pack_desktop_app_guide.md` 새로 만들기
- [ ] 타우리 팩 템플릿 프로젝트
- [ ] 샘플 팩(AI 채팅 프론트엔드)

---


최종 업데이트 날짜: 2026-02-24

이는 디자인 컨셉과 과거 계획을 포함하는 완전한 로드맵입니다. 전체 디자인은 [architecture.md](./architecture.md)를 참조하세요.

---

## 0. 북극성(비전)

- **인프라 없는 기반**: 공식 버전에는 도메인 개념(채팅/도구/프롬프트/UI 등)이 없으며 "실행, 승인, 격리, 감사, 권한"과 같은 OS와 유사한 메커니즘만 제공합니다.
- 생태계는 제3자에 의해 생성된 것으로 가정하고(악의적 가정), 핵심은 **승인 필요**,**Docker 격리(엄격 권장)**,**Fail-soft**,**감사 로그**입니다.

---

## 1. 디자인 원칙

### 1.1 편애 금지

공식 코어는 "API 키", "도구", "채팅" 등의 의미를 해석하지 않습니다. 공식적으로 제공되는 일반 메커니즘: 흐름 실행, 인증 게이트(해시 유효성 검사), 격리된 실행(Docker/UDS), 신뢰 + 부여(기능), 감사 로그.

### 1.2 악의 전제(위협 모델)

팩 작성자가 악의적인 의도를 갖고 있을 가능성을 항상 가정하십시오. 팩 실행은 기본적으로 Docker `--network=none`입니다. 외부 통신 및 호스트 권한은 기능(신뢰 + 부여)에 할당됩니다.

### 1.3 페일소프트

한 부분이 고장나도 OS 전체가 멈추지 않습니다. 진단 및 감사를 시각화하고 계속 진행합니다.

### 1.4 호스트 권한을 위한 단일 진입점

호스트에서 위험한 일(외부 통신, 파일 액세스, 업데이트 애플리케이션, 터미널 등)은 Pack에서 직접 수행하는 것이 아니라 기능에 의해 중재되며 허가 없이는 수행할 수 없습니다.

---

## 2. 컨셉 구성

### 2.1 팩 / 주체 / 기능

- **주체**: 권한 결정의 대상입니다. v1은 작업을 단순화하기 위해 pack_id 단위를 기반으로 합니다.
- 기능은 `permission_id`으로 요청하고 Trust(sha256) 및 Grant(Principal × 허가)로 부여됩니다.

### 2.2팩인팩(레이어링)

`parent__child`과 같이 계층 구조는 pack_id로 표현되며, 상위 레벨이 하위 레벨을 제한합니다(상위 레벨이 허용하지 않으면 하위 레벨은 이동하지 않습니다).

목적: 번들 배포, 운영 통합 관리, 상위-하위 권한 제약.

> 참고: 디렉터리 계층 구조 ≠ 보안 경계. 강제력은 '호스트 측 게이트(능력/실행 장치)'에 의해 보장된다.

### 2.3 Store / Unit (공유공간 및 재사용 유닛)

사용자/생태계가 임의로 생성할 수 있는 공유 영역(스토어)과 그 영역 내에서 재사용 가능한 단위(유닛)는 범용 플랫폼으로서 가치가 있습니다. 단위는 `data / python / binary` 등일 수 있습니다. 실행 단위는 팩 승인 + 단위 신뢰(sha256 허용 목록)를 기반으로 합니다.

팩 컨테이너, 호스트 기능, 전용 샌드박스(추후) 등 권한에 따라 실행 모드를 선택(수정하지 않음)할 수 있습니다.

---

## 3. 공식 핵심 기반 목록

### 3.1 종속성(pip) 소개

팩에는 `requirements.lock`가 포함되어 있습니다. 휠 전용이 기본값입니다(sdist는 예외로 승인됨). 빌더 컨테이너에서 다운로드 → 설치(설치는 오프라인임). 런타임 시 RO 마운트 + PYTHONPATH를 사용하여 사이트 패키지를 표시합니다(컨테이너는 네트워크=없음을 유지함).

### 3.2 기능 처리기 후보 소개(승인 작업 흐름)

후보자는 생태계에 포함됩니다. 스캔 → 보류 → 승인/거부 → 차단(3회 거부) 승인 신뢰 등록 + 복사 + 레지스트리 다시 로드. 쿨타임 1시간, 차단된 사람은 차단 해제될 때까지 알림을 받지 않습니다.

### 3.3 비밀(API 키 저장)

`.env`를 피하세요(사고율 감소). `user_data/secrets/`에 저장하고 로그에 값을 출력하지 않습니다. Pack에 비밀 파일을 표시하지 마십시오. 획득은 기본적으로 기능(예: `secrets.get`)을 통해 이루어집니다.

### 3.4 팩 배포 형식

입력 3 형식: 폴더 / `.zip` / `.rumipack`(zip 호환). 권장사항: 상단에 루트 1개 팩. 향후 멀티팩 아카이브(팩인팩)로 확장 가능합니다.

### 3.5 업데이트 적용 (자동 업데이트 금지)

공식 버전은 자동 업데이트되지 않습니다. 가져오기 → 스테이징 → 분리 적용. Apply는 위험하므로 기능(`pack.update`)(v1도 운영 API로 사용할 수 있음)으로 옮기고 싶습니다. 단일 pack_id를 적용하여 시작하세요.

### 3.6 실행(파이썬/바이너리)

Pack의 정상적인 실행은 Docker 격리로 설정되므로 호스트에 Python이 없어도(Docker가 있는 한) 괜찮습니다. 호스트에서 실행되는 것(기능 핸들러 등)의 경우 향후에는 Rumi 자체를 단일 실행 파일(Python 포함)로 만들거나 핸들러를 각 OS에 대한 바이너리로 만드는 것이 필요할 것입니다(둘 다 가능함).

---

## 4. 구현현황

본 로드맵에서는 각 항목이 다음과 같은 상태로 관리됩니다.

| 기호 | 의미 |
|------|------|
| ✅ | 완료(구현/운영) |
| 🟡 | 부분적(기초는 있음/개선 필요) |
| 🧩 | 예정(예정/미시행) |
| 🧪 | 실험적(추후 실험/확정 사양) |

> 참고: 여기에서는 실제 저장소 상태에 대한 자동 확인이 수행되지 않습니다. 필요한 경우 나중에 체크리스트를 만드십시오.

---

## 5. v1 (현재 ~ 최근) : 운영 OS 완성 (공식 코어)

### 5.1 안전한 실행/승인/감사(기반)

- ✅ 팩 승인(해시 검증, 수정된 탐지, 차단)
- ✅ 감사 로그(카테고리별 jsonl)
- ✅ Docker 격리(엄격한 권장, 허용은 경고)

### 5.2 pip 종속성 소개(requirements.lock)

- ✅ 스캔 → 승인 → 빌더로 다운로드/설치
- ✅ 사이트 패키지 RO 마운트 + PYTHONPATH
- 🟡 sdist 예외(allow_sdist) 동작에 대한 감사 설명(지속적인 개선)

### 5.3 기능(신뢰 + 부여 + 후보자 소개)

- ✅ 후보자 소개 흐름(대기/승인/거절/차단/휴지)
- ✅ 신탁 저장소 / 보조금 관리자 / 집행자 / 대리인(UDS)
- ✅ 본인별 보조금 관리(HMAC 서명)
- 🟡 다중 플랫폼 바이너리(신뢰 확장)는 중기적으로 진행됩니다.

### 5.4 비밀(일반 텍스트 OK, 사고율 감소)

- ✅ user_data/secrets(1 키 = 1 파일, 삭제 표시, 저널)
- ✅ API는 목록(마스크)/설정/삭제(재표시 없음)만 가능합니다.
- ✅ 로그에 값을 출력하지 마세요(감사 및 진단 모두)
- ✅ `secrets.get` rate_limit=60 (사고예방)
- ✅ get_secret() 도우미 함수 (rumi_capability.py) — Wave 2 #32
- 🧩 v1.1: OS 키체인(키링/DPAPI 등)이 연기됩니다.

### 5.5 팩 가져오기(폴더/zip/루미팩)

- ✅ 폴더 가져오기/zip/rumipack
- ✅ Zip 구조에는 "상위 단일 디렉터리"가 필요합니다.
- ✅ 지퍼 슬립/크기 제한 등으로부터 보호합니다.
- ✅ 준비 → 적용(백업 포함)
- ✅ pack_identity 불일치 대체 방지(사고 예방)

### 5.6 계층적 권한(호스트 > 상위 > 하위)

- ✅ pack_id `parent__child`를 가정하여 상위 체인을 해결합니다.
- ✅ 아이가 허용되더라도 부모가 허용하지 않으면 거절됩니다.
- ✅ 상위 구성과 하위 구성의 교차점

### 5.7 흐름 실행 정렬

- ✅ 비동기 경로 및 파이프라인 경로에 대한 `kernel:*`의 통합 해결 방법
- ✅ 시작 흐름에서 packs_dir 등의 일관성을 수정했습니다.
- ✅ _eval_condition 파서 개선(값에서 == / != 지원) — Wave 1 #16
- ✅ _resolve_value 재귀 깊이 제한 (MAX_RESOLVE_DEPTH=20) — 웨이브 1 #70
- ✅ 흐름 체인 깊이 제한(MAX_FLOW_CHAIN_DEPTH=10) — 웨이브 1 #58

### 5.8 보안 강화(Wave 1)

- ✅ 암호화 필요(base64 대체 제거) — #1
- ✅ API 서버 바인딩 주소 제한(기본값 127.0.0.1) — #3
- ✅ 호스트 실행 시간 초과(ThreadPoolExecutor, 120초) — #4
- ✅ 통합 pack_id 검증 (^[a-zA-Z0-9_-]{1,64}$) — #9
- ✅ Store root_path 경로 탐색 방지 — #5, #12
- ✅ 컨테이너 이름 UUID(충돌 방지) — #10
- ✅ Docker stdout 크기 제한(4MB) — #14
- ✅ Docker 가용성 캐시(60초 TTL) — #17
- ✅ DNS 리바인딩 완화(egress_proxy) — #13
- ✅ egress_proxy ThreadPool — #33
- ✅ HMAC 서명 논리 통합(HMACigner) — #65
- ✅ HMAC 키 파일 원자 쓰기 — #34
- ✅ 와일드카드 도메인 경고 — #31
- ✅ API 오류 메시지 숨김 — #35
- ✅ 파일 이름 확인(secure_executor) — #57
- ✅ pack_import 경로 탐색 방지 — #30
- ✅ 경로 충돌 해결 삭제 — #59

### 5.9 생태계 인프라 강화(Wave 1)

- ✅ 흐름 수정자 와일드카드 경고/시험 실행 모드 — #7, #40
- ✅ 수정자 단계가 지정되지 않은 경우의 기본 동작 — #8
- ✅ 중복된 pack_id가 감지되었습니다 — #15
- ✅ 연결에는 충족되지 않은 경고가 필요합니다 — #20
- ✅ 와일드카드 수정자 감사 로그 — #61
- ✅ 편애 금지: 데드 코드(initializer.py) 삭제, 독스트링 무력화 — NF1-3

### 5.10 내부 품질/개발 플랫폼(Wave 12-14)

- ✅ 테스트 보강: test_egress_proxy(91+), test_capability_installer(44+), test_flow_modifier_regression(32+), test_pack_api_server(53+), test_store_registry(49+) — 웨이브 12
- ✅ egress_proxy 향상(속도 제한/도메인 제어/세분화된 시간 초과) — Wave 12
- ✅ 유효성 검사.py(공통 유효성 검사 플랫폼) — Wave 12
- ✅logging_utils.py(구조적 로깅: StructuredFormatter, StructuredLogger, CorrelationContext, get_structured_logger,configure_logging) — Wave 12
- ✅ 송신 모듈 구분: egress_ip.py, egress_protocol.py, egress_rate_limiter.py, egress_domain_controller.py — Wave 13
- ✅ 기능/수정자 모듈 구분: Capability_models.py, flow_modifier_models.py, flow_modifier_loader.py — Wave 13
- ✅ health.py (HealthChecker: disk_space / memory / file_writable 프로브) — Wave 13
- ✅metrics.py (MetricsCollector: 카운터 / 게이지 / 히스토그램 / 타이머) — Wave 13
- ✅ error_messages.py (ErrorCode, RumiError, 오류 코드 시스템 RUMI-{CAT}-{NNN}) — Wave 13
- ✅ egress_proxy.py 중복 제거 + 테스트 패치 수정 — Wave 14
- ✅ profiling.py(프로파일러: 컨텍스트 관리자/데코레이터, p50/p95/p99, 메모리 제한) — Wave 14
- ✅ type.py + py.typed(NewType: PackId / FlowId / CapabilityName / HandlerKey / StoreKey, Result Generic, Severity enum, PEP 561) — 웨이브 14
- ✅ pack_scaffold.py(PackScaffold CLI: 4개의 템플릿 최소/능력/흐름/전체, 유효성 검사.py 통합) — Wave 14
- ✅ deprecation.py(더 이상 사용되지 않는 데코레이터, DeprecationRegistry, deprecated_class, RUMI_DEPRECATION_LEVEL 환경 변수) — Wave 14

### 5.11 커널 통합/DI 확장(Wave 15)

- ✅ kernel_core.py: 로깅→get_structured_logger, 더 이상 사용되지 않음 적용, type.py 적용
- ✅ kernel_flow_execution.py: 로깅→get_structured_logger, Profiler를 사용한 흐름 측정, MetricsCollector를 사용한 단계 측정
- ✅ kernel_handlers_system.py: 로깅→get_structured_logger, MetricsCollector 측정 추가
- ✅ kernel_handlers_runtime.py: 로깅→get_structured_logger, MetricsCollector 측정 추가
- ✅ di_container.py: health_checker /metrics_collector / profiler의 공장 등록 (총 32개 서비스)
- ✅ app.py:configure_logging() 호출, --health 플래그 추가

> 새로운 환경 변수: RUMI_LOG_LEVEL, RUMI_LOG_FORMAT, RUMI_DEPRECATION_LEVEL. 새로운 CLI 플래그: --health, --validate.

---

## 6. v1.5 ~ v2(중기): 확장해도 깨지지 않도록 개발

### 6.1 Store / Unit (공유공간 및 재사용 유닛)

- ✅ 매장 등록(여러 매장, 고정 경로 없음) — `core_runtime/store_registry.py` 구현
- ✅ 단위 레지스트리(데이터/파이썬/바이너리) — `core_runtime/unit_registry.py` 구현됨
- ✅ 단위 신뢰 저장소(sha256 허용 목록) — `core_runtime/unit_trust_store.py` 구현됨
- 🟡 유닛 실행 게이트(host_capability 모드만 구현됨. 팩 컨테이너/샌드박스는 구현되지 않음) — `core_runtime/unit_executor.py`
- ✅ 비교 및 교환 저장(store.cas) — fcntl.flock 기반 — Wave 2 #6
- ✅ store.list 페이지 매기기 (한계 / 커서 / 접두사) — Wave 2 #18
- ✅ store.batch_get (최대 100개 키, 900KB 제한) — Wave 2 #19
- ✅ 선언적 저장소 생성(ecosystem.json에 필드 저장) — Wave 2 #62
- ✅ 팩 간 스토어 공유(SharedStoreManager, 수동 승인) — Wave 2 #21
- 🧩 "팩 승인 필요, 유닛 개별 승인은 유닛 설정에 따라 다름(팩 요청 가능)" 운영 유지보수

> 여기서는 "자산"이라는 단어를 사용하지 않습니다. 생태계가 '호환 가능한 재사용을 위한 저장소'를 만들면 확립됩니다.

### 6.2 바이너리 지원 기능 강화 (파이썬 없이 동작 구현)

- 🧩 handler.json은 아티팩트를 지원합니다(OS/아치별).
- 🧩 신뢰 저장소 확장(handler_id → 다중 sha256)
- 🧩 실행기의 직접 바이너리 실행(stdin JSON / stdout JSON)
- 🧩 “Rumi 자체를 단일 실행 파일로 변환”에 대한 비교 연구(UX/운영)

### 6.3 전체 업데이트 적용 기능

- 🧩 `pack.update` 허가 표준화(공식적으로는 의미가 해석되지 않지만 "위험한 작업을 위한 프레임"으로 해석됨)
- 🧩 기능을 통해 작업을 적용하고 API에 대한 직접 접근을 최소화합니다.
- 🧩 버전 기록/롤백(스테이징/백업 표준 작업)

### 6.4 역량 확장(Wave 2)

- ✅ flow.run 기능(동기적 Flow-to-Flow 호출, 주기 감지, 깊이 제한) — Wave 2 #5
- ✅ 배치 기능 부여(최대 50개, 최선의 노력) — Wave 2 #63
- ✅ 스케줄러 시간대 지원(zoneinfo, UTC 대체) — Wave 2 #60

### 6.5 어휘를 사용한 구성요소 출력 키 정규화(팩 호환성 계층)

- 🧩 컴포넌트 유형별 출력 키 자동 정규화
- 🧩 vocab_registry의 동의어 그룹 + 변환기를 Flow 실행 경로에 통합
- 🧩 정규화 타이밍 표준화(ctx 저장 전 vs 참조 시)
- 🧩 Pack 측에서 vocab.txt를 사용하여 동의어 선언에 대한 권장 패턴 개발

#### 배경

타사 팩 개발에서 발견된 문제입니다. kernel_core의 _execute_handler_step_async는 Flow 단계의 반환 값을 ctx[step["output"]]에 그대로 저장합니다. 즉, 기본 Pack에 {"content": "...", "model": "gpt-4"}를 반환하는 구조가 있고 Flow가 ${ctx.ai_response.content}를 참조하는 경우 다른 Pack처럼 {"text": "...", "model_name": "..."}을 반환하는 Pack으로 교체하는 순간 모든 Flow 단계에서 콘텐츠가 null이 되어 중단됩니다.

vocab_registry에는 이미 이 문제를 해결하는 메커니즘이 있지만 "흐름 실행 경로의 자동 적용"이 부족합니다.

#### 제안된 구현 계획

**방법 A(저장 중 정규화 - 권장)**: kernel_core에 ctx를 저장하기 전에 vocab_registry에서 원하는 용어로 변환합니다. 몇 줄만 변경하면 기존 메커니즘을 활용할 수 있습니다.**방법 B(참조에 대한 정규화)**: _resolve_value를 사용한 동의어 대체. 저장된 데이터는 변경되지 않지만 해결 경로가 복잡합니다.**방법 C(옵트인 정규화)**: 정규화: 흐름 단계에서 true 플래그를 지정하거나 구성 요소 매니페스트에서 output_vocab_group을 선언합니다. 기존 제품에는 영향이 없지만 팩 작성자는 이 사실을 알고 있어야 합니다.

### 6.6 내부 리팩토링(P3 보류 중)

- 🟡 글로벌 싱글톤 → DI 컨테이너 마이그레이션(커널 통합/32개 서비스 등록) — Wave 15
- 🧩 SQLite에 백엔드 저장(파일 기반에서 마이그레이션 옵션)
- 🧩 pack_api_server.py의 대규모 핸들러 분할(현재 ~80KB)
- 🧩 Docker 실행 논리 공통성(python_file_executor / secure_executor 통합)

---

## 7. v3(장기): 생태계에서 구현되어야 하는 외부

> v3의 아이템은 공식 코어에 구현되지 않고 생태계(Pack)로 구현됩니다.
> 제3자가 제공해야 합니다. 공식은 이러한 기능을 구현하는 것입니다.
> 이미 범용 메커니즘(API 서버, Store, Capability 등)을 제공하고 있습니다.

### 7.1 관리 UI
- 관리 UI를 팩(pack_api_server API를 호출하는 프런트엔드 팩)으로 구현 가능
- 공식적으로 HTTP API를 제공합니다. UI는 생태계 영역이다

### 7.2 외부인증 연동
- Superbase 등에 대한 인증은 Pack via Secrets + 기능을 통해 달성 가능
- 공무원은 인증 메커니즘을 시행하지 않습니다.

---

## 8. 애드온(구식)

`backend_core/ecosystem/addon_manager.py`에 존재했던 JSON 패치 기반 애드온 메커니즘이 제거되었습니다. Flow Modifier가 그 역할을 대신합니다.

---

## 9. 규칙/작업(런북 핵심 사항)

- 프로덕션에는 엄격을 권장합니다(Docker 필요).
- 비밀은 값을 기록하지 않습니다.
- 역량은 신뢰 + 부여의 2계층 조합입니다.
- pip 종속성은 기본적으로 휠 전용이며 sdist는 예외 승인입니다.
- 업데이트가 자동으로 적용되지 않습니다(사용자 상호작용 필요).
- 감사 + 진단을 통해 건너뛰기/거부 추적

---

## 10. 향후 이슈 (미정사항 명시)

- 공식적으로 매장/유닛(단지 프레임 vs. 조금 두꺼운)의 운영 및 유지 관리를 어느 정도까지 표준화할 예정인가요?
- 단위별 개별 승인 UX(보류 항목이 너무 많아지도록 설계)
- 유닛 실행 게이트의 팩 컨테이너/샌드박스 모드 구현
- Python 없이 배포할 수 있는 최단 경로 (본체 통일 vs. 핸들러 바이너리화)
- 계층적 권한의 상한 설정(교차 정의: 목록은 교차 집합, 포트는 최소 등)
- 어휘를 사용한 출력 키 정규화 범위(모든 단계 vs. 선택 vs. 구성요소 유형만)
- 어휘 동의어 충돌 해결(팩 A는 콘텐츠 = 본문, 팩 B는 콘텐츠 = 전체 HTML)
- 변환기의 실행 보안(임의의 Python이 실행되기 때문에 Trust를 설정해야 합니까?)
- 패턴의 균일성을 제공합니다(스키마는 ^[a-z][a-z0-9_]*$이지만 pack-development.md 예제는 ai.client이고 점으로 구분되어 있습니다. 어느 것이 맞습니까?)
- defaults_pack 통합 (다른 팀에서 진행 중)
- 컴파일 → 애플리케이션(단일 실행파일 배포)
- 문서 유지보수(Wave 16 진행 중)

---

## 부록: 중요한 안티 패턴(하지 마세요)

- 컨테이너에 비밀을 마운트하고 Pack이 읽도록 합니다. (즉시 NG)
- 공무원은 도구/채팅 등 고정된 개념을 갖고 있음(편애금지 위반)
- 자동 업데이트(명시적인 사용자 조작 없이 생태계를 다시 작성)
- 감사 로그에 비밀 값과 해독 가능한 정보를 내보냅니다.
