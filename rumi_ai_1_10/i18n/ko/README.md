<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# 루미 AI OS

**"토대 없는 기초"** — 수정할 "본체"가 없는 모듈식 AI 프레임워크

---

## 목적이 있는 가이드

모든 코드를 따라갈 필요 없이 진입점을 찾을 수 있도록 목적별로 읽을 대상을 먼저 배치하세요.

| 내가 하고 싶은 것 | 먼저 읽을 곳 | 나는 얼마나 이해할 수 있는가 |
|---|---|---|
| 목적별로 문서를 추적하고 싶어요 | [`docs/README.md`](./docs/README.md) | "하고 싶은 일 → 어떤 문서"를 한 페이지에서 추적할 수 있습니다 |
| 용어의 의미를 정렬하고 싶습니다 | [`docs/terminology.md`](./docs/terminology.md) | `rule`, `skill`, `team workspace`, `delegation`의 사용법을 확인할 수 있습니다 |
| 먼저 시작하고 싶어요 | 루트 [`README.md`](../README.md) | 최단 시작 명령 및 Repo 입구 |
| 먼저 해보고 싶어요 | [`docs/tutorials/runtime-quickstart.md`](./docs/tutorials/runtime-quickstart.md) | `--health`에서 `/panel/`까지의 가장 짧은 튜토리얼 |
| 코드를 읽지 않고 런타임 메커니즘을 이해하고 싶습니다 | [`docs/concepts/system-mechanism.md`](./docs/concepts/system-mechanism.md) | 스타트업, 플로우, 승인, 부여, 시청자 협업 실행경로 |
| `rumi_viewer`의 시작 절차와 작동이 어떻게 중단되는지 보고 싶습니다 | [`docs/rumi_viewer_start.md`](./docs/rumi_viewer_start.md) | `401`, 검은색 화면, 패널과 defaultspack의 관계 |
| defaultspack의 프런트엔드를 확장하고 싶습니다 | [`ecosystem/defaultspack/docs/frontend_extensions.md`](./ecosystem/defaultspack/docs/frontend_extensions.md) | 오른쪽 막대, 설정, 채팅 렌더러 및 미리보기 피드를 늘리는 방법 |
| 이 런타임의 아이디어를 알고 싶습니다 | 이 README의 `Thoughts` | 흐름 중심, Pack 전제, Fail-Soft 아이디어 |
| 디렉토리의 역할을 알고 싶습니다 | `Project structure`의 역할 | 이 추가 정보의 `core_runtime/`, `ecosystem/`, `user_data/` |
| 팩 생성/수리 | [`docs/pack-development.md`](./docs/pack-development.md) | `ecosystem.json`, `routes.json`, `permissions.json`, 비밀 사용 |
| defaultspack의 채팅/ai를 팔로우하고 싶어요 | [`ecosystem/defaultspack/README.md`](./ecosystem/defaultspack/README.md) | defaultspack의 구현 측면 |
| defaultspack 프론트엔드의 향후 작업을 보고 싶습니다 | [`ecosystem/defaultspack/docs/frontend_todo.md`](./ecosystem/defaultspack/docs/frontend_todo.md) | 레지스트리 진행 및 차기작 |
| API 키와 비밀을 설정하고 싶습니다 | [`docs/operations.md`](./docs/operations.md)의 비밀 섹션 | `user_data/secrets/` 및 API 경로 |
| 뷰어를 통해 부팅 경로를 수정하고 싶습니다 | [`../rumi_viewer/src-tauri/src/config.rs`](../rumi_viewer/src-tauri/src/config.rs) 및 [`../rumi_viewer/src-tauri/src/kernel_manager.rs`](../rumi_viewer/src-tauri/src/kernel_manager.rs) | 뷰어가 시작해야 하는 커널과 통과해야 하는 환경은 무엇입니까 |
| 설치 팩 / 인증을 보고 싶습니다 | [`core_runtime/setup_pack.py`](./core_runtime/setup_pack.py) 및 [`core_runtime/approval_manager.py`](./core_runtime/approval_manager.py) | 설치 팩 선택, all-ok 부여, 재인증 |
| 운영 및 감사에 대해 알고 싶습니다 | [`docs/operations.md`](./docs/operations.md) 및 [`docs/roadmap.md`](./docs/roadmap.md) | 운영 API, 비밀, 향후 정책 |

## 최단 평면도

1. `app.py`이 커널을 시작합니다.
2. `core_runtime/`에는 Flow, Pack, Approval, Execution 인프라가 있습니다.
3. `ecosystem/<pack_id>/`는 주요 기능을 제공합니다.
4. `user_data/`에는 인증 상태, 비밀, 저장, 감사가 있습니다.
5. `rumi_viewer/`은 커널을 시작하고 패널에 연결하는 쉘이 됩니다.

## 자주 이용하는 출입구

### 시작 확인

```bash
python -m rumi_ai --health
python -m rumi_ai
```

### 뷰어 개발 시작

```bash
cd ../rumi_viewer/src-tauri
cargo tauri dev
```

### 일반적인 테스트

```bash
python -m pytest tests/test_defaultspack_google_provider.py
python -m pytest tests/test_defaultspack_modules.py
```

---

## 생각

### 편애 금지

Rumi AI의 공식 코드는 "채팅", "도구", "프롬프트", "AI 클라이언트", "프론트엔드"와 같은 도메인 개념에 대해 전혀 알지 못합니다. 이 모든 것은 생태계 내의 팩으로 정의됩니다. 공식은 **실행 메커니즘**만 제공합니다.

### 기초 없는 기초

마인크래프트 모드는 '마인크래프트'의 기초를 수정하는 것입니다. 그러나 루미 AI에는 수정 가능한 '몸'이 없습니다. 모든 애플리케이션 기능은 팩으로 구현되고 흐름을 사용하여 연결됩니다.

### 흐름 중심 아키텍처

Flow를 사용하여 팩 간의 연결, 순서 및 설치 후를 정의합니다. 기존 팩을 수정하지 않고도 새로운 기능을 추가할 수 있습니다.

```
          +---------------------------+
          |       Flow Definition     |
          +---------------------------+
                      |
          +---------------------------+
          |    python_file_call       |
          +---------------------------+
            /         |         \
    +--------+  +--------+  +--------+
    | Pack A |  | Pack B |  | Pack C |
    +--------+  +--------+  +--------+
            \         |         /
          +---------------------------+
          |         Kernel            |
          +---------------------------+
```

> **흐름 가져오기 소스**: `flows/`, `user_data/shared/flows/`, `ecosystem/<pack_id>/backend/flows/`

### 페일소프트

오류가 발생해도 시스템은 멈추지 않습니다. 계속하려면 실패한 구성 요소가 비활성화되고 진단 정보에 기록됩니다.

### 악성팩 기반 보안

생태계는 제3자에 의해 생성될 수 있다는 점과 악의적인 작성자도 있을 수 있다는 점을 전제로 설계되었습니다.

- **승인 필요**: 승인되지 않은 팩의 코드는 실행되지 않습니다.
- **해시 검증**: 승인 후 파일 수정 시 자동 무효화(재승인 필요)
- **Docker 격리**: 승인된 팩이 컨테이너에서 실행됩니다(엄격 모드).
- **송신 프록시**: 외부 통신은 UDS 소켓을 통한 프록시에서만 허용됩니다.
- **기능(신뢰 + 부여)**: 2단계 승인으로 호스트 권한을 제어합니다.

기존 환경에서 HMAC 서명 없이 구성 파일에 다시 서명하려면 다음 안내를 따르세요.

```bash
python -m rumi_ai migrate-hmac
```

---

## 프로젝트 구조

<details>
<summary>디렉토리 트리(확대하려면 클릭)</summary>

<pre><code>
프로젝트_루트/
├── app.py
├── bootstrap.py
├── 요구사항.txt
├── 요구사항-dev.txt
│
├── 흐름/
│ └── 00_startup.flow.yaml
│
├── 코어_런타임/
│ ├── kernel.py
│ ├── kernel_core.py
│ ├── kernel_handlers_system.py
│ ├── kernel_handlers_runtime.py
│ ├── paths.py
│ ├── 진단.py
│ ├── 인터페이스_registry.py
│ ├── event_bus.py
│ ├── audit_logger.py
│ ├── install_journal.py
│ ├── 승인_manager.py
│ ├── network_grant_manager.py
│ ├── egress_proxy.py
│ ├── rumi_syscall.py
│ ├── syscall.py
│ ├──capability_proxy.py
│ ├──capability_executor.py
│ ├──capability_trust_store.py
│ ├──capability_grant_manager.py
│ ├──capability_installer.py
│ ├── rumi_capability.py
│ ├── python_file_executor.py
│ ├── secure_executor.py
│ ├── 컨테이너_오케스트레이터.py
│ ├── component_lifecycle.py
│ ├── host_privilege_manager.py
│ ├── pack_api_server.py
│ ├── flow_loader.py
│ ├── flow_modifier.py
│ ├── flow_composer.py
│ ├── flow_scheduler.py
│ ├── function_alias.py
│ ├── vocab_registry.py
│ ├── shared_dict/
│ │ ├── snapshot.py
│ │ ├── 저널.py
│ │ └── resolver.py
│ ├── core_pack/
│ │ ├── core_store_capability/
│ │ ├── core_secrets_capability/
│ │ ├── core_flow_capability/
│ │ ├── core_communication_capability/
│ │ └── core_docker_capability/
│ ├── function_registry.py
│ ├── crypto_utils.py
│ ├── lib_executor.py
│ ├── pip_installer.py
│ ├── pack_importer.py
│ ├── pack_applier.py
│ ├── secrets_store.py
│ ├── store_registry.py
│ ├── 단위_registry.py
│ ├──unit_executor.py
│ ├──unit_trust_store.py
│ ├── hierarchical_grant.py
│ ├── lang.py
│ └── 허가_관리자.py
│
├── 백엔드_코어/
│ └── 생태계/
│ ├── compat.py
│ ├── mounts.py
│ ├── Registry.py
│ ├── active_ecosystem.py
│ ├── 초기화.py
│ ├── uuid_utils.py
│ └── json_patch.py
│
├── 생태계/
│ ├── <pack_id>/
│ │ └── 백엔드/
│ │ ├── 생태계.json
│ │ ├── 허가.json
│ │ ├── 요구 사항.잠금
│ │ ├── Routes.json
│ │ ├── 블록/
│ │ ├── 흐름/
│ │ ├── 구성요소/
│ │ ├── lib/
│ │ ├── 공유/
│ │ ├── vocab.txt
│ │ └── 변환기/
│ └── 팩/
│ └── <pack_id>/...
│
├── 사용자_데이터/
│ ├── 감사/
│ ├── 권한/
│ │ ├── 승인/
│ │ ├── 네트워크/
│ │ ├── 기능/
│ │ └── .secret_key
│ ├── 비밀/
│ ├── 팩/
│ ├── 기능/
│ │ ├── 핸들러/
│ │ ├── 신뢰/
│ │ └── 요청/
│ ├── pip/
│ ├── pack_staging/
│ ├── pack_backups/
│ ├── 공유됨/
│ │ └── 흐름/
│ │ └── 수식어/
│ ├── 보류 중/
│ │ └── 요약.json
│ ├── 매장/
│ └── 설정/
│ ├── shared_dict/
│ └── lib_execution_records.json
│
├── rumi_setup/
│ ├── 코어/
│ ├── cli/
│ ├── 웹/
│ ├── 안내/
│ └── 기본값/
│
├── 랭/
│ ├── ko.txt
│ └── ja.txt
│
├── 테스트/
│ ├── test_capability_installer.py
│ ├── test_capability_system.py
│ ├── test_ecosystem_phase1.py
│ ├── test_ecosystem_phase2.py
│ ├── test_ecosystem_phase3.py
│ ├── test_ecosystem_phase4.py
│ ├── test_ecosystem_phase5.py
│ ├── test_ecosystem_phase6.py
│ ├── test_egress_audit.py
│ ├── test_flow_solution.py
│ ├── test_inbox_and_patches.py
│ ├── test_pip_installer.py
│ ├── test_secure_execution.py
│ └── test_shared_dict.py
│
└── 문서/
    ├── 건축.md
    ├── 팩-개발.md
    ├── Operations.md
    └── 로드맵.md
</code></pre>

</details>

### 메인 디렉토리

| 디렉토리 | 역할 |
|---|---|
| `core_runtime/` | 커널 — 흐름 실행 엔진, 보안 및 권한 관리 |
| `core_runtime/shared_dict/` | 공유사전시스템(스냅샷저널) |
| `core_runtime/core_pack/` | 공식 기능 구현(Store, Secrets, Flow, Communication, Docker) |
| `backend_core/ecosystem/` | 생태계 기반 — 팩/컴포넌트 로딩/초기화 |
| `ecosystem/` | 팩 보관(외장용품) |
| `user_data/` | 런타임 영구 데이터(감사 로그, 승인, 비밀, 저장) |
| `rumi_setup/` | 설정 지원(CLI/웹/가이드) |
| `flows/` | 공식 흐름(스타트업/베이스) |
| `lang/` | 다국어 메시지 |
| `tests/` | 테스트 |
| `docs/` | 문서 |

### 주요 파일

| 파일 | 역할 |
|---|---|
| `app.py` | OS 진입점 |
| `bootstrap.py` | 설정 진입점 |
| `kernel.py` | 믹스인 어셈블리/핸들러 등록 |
| `kernel_core.py` | 흐름 실행 엔진 본체 |
| `python_file_executor.py` | `python_file_call` 실행 |
| `secure_executor.py` | Docker 격리 실행 |
| `approval_manager.py` | 팩 승인 관리 |
| `capability_proxy.py` | 기능 프록시 서버(UDS) |
| `egress_proxy.py` | 외부 통신 프록시(UDS) |
| `flow_loader.py` | 흐름 YAML 로더 |
| `flow_modifier.py` | 흐름 수정자 적용 |
| `pack_importer.py` | 팩 가져오기(zip/폴더 → 준비) |
| `pack_applier.py` | 팩 적용(스테이징 → 생태계) |

## 뷰어 그래프 편집기

제어판의 정식 프런트엔드 소스는 `../rumi_viewer/frontend`에 있습니다.
`core_runtime/core_pack/core_control_panel/web`에는 `/panel/`에서 커널이 제공하는 구축된 정적 아티팩트가 포함되어 있습니다.

신속한 행동은 `ecosystem/defaultspack/domain/prompt/` 및 `ecosystem/defaultspack/blocks/prompt/`에 있습니다. 도구 동작은 `ecosystem/defaultspack/domain/tool/` 및 `ecosystem/defaultspack/blocks/tool/`에 있습니다. 이전 최상위 `prompt/`, `tool/` 및 `supporter/` 가져오기 심이 제거되었습니다. 새로운 서포터와 유사한 동작은 defaultspack 기능, 에이전트, 프롬프트, 메모리 또는 확장으로 구현되어야 합니다.

`../rumi_viewer/frontend/src/pages/Flows.tsx`의 그래프 편집기는 팩에 특화된 고정 UI가 아닌 확장 가능한 그래프 메타데이터가 있는 편집기로 취급됩니다.

- 시작 노드는 `rumi_start`입니다.
- 노드는 여러 포트를 가질 수 있습니다
- 포트는 여러 개의 `contracts`를 수용할 수 있습니다.
- `contracts`과 일치하지 않는 포트는 서로 연결할 수 없습니다.
- `rumi_graph`을 YAML에 저장하고 뷰어 측에서 구조를 복원합니다.

이 설계를 사용하면 변환 전용 특수 기능을 추가하지 않고도 Pack 측에서 다양한 입력/출력 계약으로 노드를 정의하여 변환 역할을 표현할 수 있습니다.

## 베이스팩

Rumi AI가 그래프 우선의 기본 실행 프로필로 `basepack`을 선택할 수 있도록 `ecosystem/setup_pack/basepack/pack.json`을 추가했습니다. 현재 우리는 기존 `defaultspack`를 얇은 부트스트랩 프로필로 간주하여 출시하고, 대규모 중복 팩을 늘리지 않고 안전하게 배포하고 있습니다.

---

## 빠른 시작

### 요구 사항

- 파이썬 3.10+
- Docker(프로덕션 환경에 필요)
- 힘내

### 설치

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10
python bootstrap.py --cli init
```

### 시작

```bash
# 本番（Docker 必須）
python app.py

# 開発（Docker 不要）
python app.py --permissive
```

### 팩 승인

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 문서

| 문서 | 내용 |
|---|---|
| [docs/architecture.md](./docs/architecture.md) | 디자인 및 메커니즘의 전체 그림 |
| [docs/pack-development.md](./docs/pack-development.md) | 팩 개발 가이드 |
| [docs/pack-development-guide.md](./docs/pack-development-guide.md) | 팩 개발 빠른 시작 |
| [docs/operations.md](./docs/operations.md) | 운영안내 |
| [docs/roadmap.md](./docs/roadmap.md) | 로드맵 |
| [docs/quality_pack/philosophy_memo.md](docs/quality_pack/philosophy_memo.md) | 개발 결정에 사용되는 생각 노트 |
| [docs/quality_pack/claude_desktop_quality_pack.md](./docs/quality_pack/claude_desktop_quality_pack.md) | 품질 보증/감사/회귀 검증 팩 |

---

## 라이선스

MIT 라이센스
자세한 내용은 저장소 루트의 LICENSE를 참조하세요.
## defaultspack 진실의 소스

이 저장소의 정식 defaultspack 구현은 다음과 같습니다.
`ecosystem/defaultspack/`. 이전 `ecosystem/defaults/` 경로와 별도의 경로
`harupipipipi/rumiai_defaults` 저장소는 호환성 또는 스냅샷 소스입니다.
새로운 로컬 우선 런타임 동작은 레거시와 함께 defaultspack에 포함되어야 합니다.
필요한 경우 별칭을 다시 위임합니다.

defaultspack 런타임은 클라우드 API 키나 외부 없이 시작되도록 설계되었습니다.
네트워크 액세스. 보장된 기본 모델은 `stub/default`입니다. 클라우드 제공업체
선택 사항이므로 명시적으로 선택/구성해야 합니다. 로컬 파일, 터미널,
git 돌연변이는 로컬 요청 가드로 보호되며 일회성 서명됩니다.
승인 토큰 및 수정된 감사 기록.
