<!-- docs-i18n-links:start -->
[EN](../../pack_development_guide.md) | [JP](../ja/pack_development_guide.md) | [KR](./pack_development_guide.md) | [CN](../zh-cn/pack_development_guide.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 팩 개발 가이드

> **레거시 문서**: 호환성 참조를 위해 보관됩니다. 새로운 참조는 [pack-development.md](./pack-development.md) 및 [pack-development-guide.md](./pack-development-guide.md)보다 우선해야 합니다.

최종 업데이트 날짜: 2026-03-23

이 문서는 Rumi AI OS 팩 개발을 위한 포괄적인 가이드입니다. 팩 개요, 구조, 수명 주기, 권한 시스템, Docker 격리 및 개발 워크플로를 다룹니다.

---

## 1. 팩이란 무엇인가요?

팩은 Rumi AI OS의 기능 확장 유닛입니다. 팩은 OS 자체(커널)에서 제공하는 핵심 기능 위에 고유한 기능을 추가합니다.

팩에는 다음 요소가 포함될 수 있습니다.

- **기능**: API를 통해 호출할 수 있는 처리 단위(JSON in → JSON out)
- **구성요소**: UI 구성요소 및 데이터 모델
- **경로**: HTTP 엔드포인트 정의
- **흐름**: 여러 기능을 결합한 워크플로

팩은 `ecosystem.json`라는 매니페스트 파일로 정의됩니다. 커널은 이 파일을 읽고 Pack의 함수를 FunctionRegistry에 등록한 다음 실행 가능하게 만듭니다.

---

## 2. 팩 구조

### 2.1 디렉토리 구조

```
my_pack/
├── ecosystem.json          # Pack マニフェスト（必須）
├── functions/
│   ├── my_function/
│   │   ├── main.py         # Python Function のエントリーポイント
│   │   └── ...
│   └── my_binary_function/
│       ├── my_binary        # コンパイル済みバイナリ
│       └── ...
├── components/
│   └── ...
├── routes/
│   └── ...
└── flows/
    └── my_flow.flow.yaml
```

### 2.2 Ecosystem.json의 모든 필드

```json
{
  "pack_id": "my_pack",
  "pack_identity": "vendor:user/pack-name",
  "version": "1.0.0",
  "metadata": {
    "name": "My Pack",
    "description": "Pack の説明",
    "author": "Author Name",
    "license": "MIT",
    "is_core_pack": false
  },
  "vocabulary": {
    "types": []
  },
  "dependencies": {},
  "components": {},
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

| 필드 | 유형 | 필수 | 설명 |
|-----------|-----|------|------|
| 팩_ID | 문자열 | ✅ | 팩 고유 식별자 |
| 팩_신원 | 문자열 | — | 공급업체:사용자/이름 형식의 공식 식별자 |
| 버전 | 문자열 | ✅ | 의미적 버전 관리 |
| 메타데이터.이름 | 문자열 | ✅ | 사람이 읽을 수 있는 팩 이름 |
| 메타데이터.설명 | 문자열 | — | 팩 설명 |
| 메타데이터.작성자 | 문자열 | — | 저자 이름 |
| 메타데이터.라이센스 | 문자열 | — | 라이센스 |
| 메타데이터.is_core_pack | 부울 | — | core_pack입니까(대개 false) |
| 어휘.유형 | 배열 | — | 어휘 유형 정의 |
| 종속성 | 개체 | — | |에 의존하는 기타 팩 |
| 구성요소 | 개체 | — | 구성요소 정의 |
| 런타임 | 개체 | — | 런타임 설정(다국어 팩의 경우 자세한 내용은 multilang_pack_guide.md 참조) |

### 2.3 함수 매니페스트

각 기능은 Ecosystem.json의 `functions` 섹션이나 `functions/<function_id>/` 디렉터리의 매니페스트에 정의되어 있습니다.

함수 매니페스트의 주요 필드:

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| 설명 | 문자열 | 기능 설명 |
| 런타임 | 문자열 | `"python"` / `"binary"` / `"command"` |
| 메인 | 문자열 | 바이너리 상대 경로(런타임=바이너리인 경우) |
| 명령 | 배열[문자열] | 실행 명령(runtime=command인 경우) |
| 진입점 | 문자열 | Python 진입점(예: `"main.py:run"`) |
| 전화 컨벤션 | 문자열 | 실행 방법(후술) |
| 호스트_실행 | 부울 | 호스트에서 직접 실행 |
| 필요하다 | 배열[문자열] | 필수 권한 |
| caller_requires | 배열[문자열] | 발신자로부터 요청된 권한 |
| 입력_스키마 | 개체 | JSON 스키마 입력 |
| 출력_스키마 | 개체 | JSON 스키마 출력 |
| 태그 | 배열[문자열] | 태그 검색 |
| vocab_aliases | 배열[문자열] | 어휘 별칭 |
| 부여_구성 | 개체 | 부여 설정(시간 초과 등) |
| docker_이미지 | 문자열 | 도커 이미지(기본값: python:3.11-slim) |
| 확장 | 개체 | 확장 메타데이터 |

---

## 3. 팩 수명주기

팩은 다음 수명 주기를 통해 관리됩니다.

### 3.1 스캔

커널의 PackImporter는 Pack 디렉터리를 검색하고 `ecosystem.json`을 읽습니다. 각 팩의 구조를 살펴보고 해당 기능을 알아보세요.

### 3.2 승인

ApprovalManager는 팩의 승인 상태를 관리합니다. 승인되지 않은 팩의 기능은 실행할 수 없습니다. core_pack(`pack_id`이 `core_` 접두사로 시작됨)이 자동으로 승인됩니다.

### 3.3 로드

승인된 Pack의 기능은 FunctionRegistry에 등록됩니다. 각 기능에 대해:

1. FunctionEntry 구성(매니페스트에서 필드 읽기)
2. 런타임에 따라 `main_py_path` / `main_binary_path` / `command` 해결
3. 경로 순회 확인(바이너리 경로가 function_dir 내에 맞는가?)
4. FunctionRegistry(qualified_name = `pack_id:function_id`)에 등록합니다.
5. vocab_aliases 등록

### 3.4 실행

CapabilityExecutor는 실행을 담당합니다. 실행 흐름은 다음과 같습니다.

1. **FunctionRegistry 해결**: 허가_ID 또는 자격을 갖춘_이름으로 FunctionEntry 검색
2. **신뢰 확인**: TrustStore에서 sha256 해시 유효성 검사(core_pack은 제외)
3. **그랜트 확인**: GrantManager에서 주체 × 권한을 확인합니다.
4. **calling_convention 분기** : Function의 실행 방법에 따라 적절한 핸들러로 분기합니다.
5. **감사 로깅**: 모든 실행 결과를 감사 로그에 기록합니다.

---

## 4. core_pack 대 에코시스템 팩

### 코어_팩

- `pack_id`는 `core_` 접두사로 시작됩니다.
- 커널에 포함됨
- 신뢰 확인이 단순화되었습니다(sha256은 기록되지만 TrustStore에서의 확인은 생략됨).
- 자동 승인됨
- `core_runtime/core_pack/` 디렉토리에 위치

### 에코시스템 팩

- 제3자 또는 사용자가 개발한 팩
- 신뢰 확인이 필요합니다. (sha256이 TrustStore에 등록되어 있어야 합니다.)
- 명시적인 승인이 필요합니다.
- `ecosystem/` 디렉토리에 위치

---

## 5. 기능, 구성 요소, 경로 및 흐름의 차이점

### 기능

가장 기본적인 처리 장치이다. JSON 입력을 허용하고 JSON 출력을 반환합니다. Python, 컴파일된 바이너리 또는 명령으로 구현할 수 있습니다.

### 구성 요소

UI 구성 요소 및 데이터 모델의 정의. 팩 간에 공유할 수 있는 구조화된 데이터를 제공합니다.

### 경로

HTTP 엔드포인트 정의. pack_api_server에 등록되어 외부에서 접근 가능한 API를 제공합니다.

### 흐름

이는 여러 기능을 결합한 워크플로우입니다. YAML에 정의되고 Flow Engine에 의해 실행됩니다. 여기에는 조건부 분기, 루프 및 오류 처리가 포함될 수 있습니다.

---

## 6. 기능의 작동 방식

Rumi AI OS에는 3단계 권한 시스템이 있습니다.

### 6.1 신뢰

TrustStore는 핸들러 파일의 sha256 해시를 관리합니다. 등록된 해시와 런타임 해시가 일치하지 않으면 실행이 거부됩니다. 파일 변조를 감지합니다.

### 6.2 부여

GrantManager는 누가(principal_id) 무엇을(permission_id) 할 수 있는지 관리합니다. grant_config를 사용하면 시간 초과와 같은 세부적인 제어가 가능합니다.

### 6.3 속도 제한

특정 허가 ID(예: `secrets.get`)에 대한 분당 호출 수를 제한합니다. 기본값은 60회/분/원칙입니다.

### 6.4 역량 흐름

```
リクエスト
  → FunctionRegistry 解決
  → Trust チェック（sha256 検証）
  → Grant チェック（principal × permission）
  → Rate Limit チェック（該当する場合）
  → calling_convention に応じた実行
  → 監査ログ記録
  → CapabilityResponse 返却
```

---

## 7. Calling_convention (실행 방법)

Calling_convention은 함수가 실행되는 방법을 결정합니다.

| 전화 컨벤션 | 설명 | 대상 언어 |
|-------------------|------|---------|
| 커널 | 커널 내부에서 직접 호출 | — |
| 하위 프로세스 | Python 하위 프로세스에서 실행 | 파이썬 |
| 블록 | core_pack용 DI 기반 핸들러 | 파이썬 |
| python_host | 호스트 프로세스에서 Python 실행 | 파이썬 |
| python_docker | Docker 컨테이너 내에서 Python 실행 | 파이썬 |
| 바이너리 | 컴파일된 바이너리 실행(stdin/stdout JSON) | Rust, Go, C/C++ 등 |
| 명령 | 명령 목록(stdin/stdout JSON)을 사용하여 프로세스 시작 | Node.js, Ruby, 임의 |

`binary` 및 `command`는 다국어 팩 개발의 핵심입니다. 자세한 내용은 [다국어 팩 개발 가이드](./multilang_pack_guide.md)를 참조하세요.

---

## 8. Docker 격리 작동 방식

### 8.1 개요

에코시스템 팩(비-core_pack)의 Python 함수는 기본적으로 Docker 컨테이너에서 실행됩니다. 이렇게 하면 호스트 시스템에 미치는 영향을 방지할 수 있습니다.

### 8.2 도커 실행 흐름

1. 입력 JSON을 임시 파일에 작성합니다.
2. DockerRunBuilder를 사용하여 컨테이너 빌드
3. `/function:ro`을 사용하여 function_dir 마운트(읽기 전용)
4. `/input.json:ro`을 사용하여 입력 JSON 파일을 마운트합니다.
5. 환경변수 `RUMI_PACK_ID`, `RUMI_FUNCTION_ID` 설정
6. 컨테이너 내에서 Python 실행기 스크립트를 실행합니다.
7. stdout에서 JSON 읽기
8. 타임아웃이 발생하면 `docker kill`으로 컨테이너를 강제 중지합니다.

### 8.3 Docker를 사용할 수 없는 경우

Docker를 사용할 수 없는 경우 호스트의 하위 프로세스로 대체됩니다(경고 로그가 출력됨).

### 8.4 바이너리/명령어 기능 실행

`binary` 및 `command`에 Calling_convention이 있는 함수는 Docker가 아닌 호스트에서 하위 프로세스로 실행됩니다. 다만, `host_execution=false`, `runtime != "python"`의 경우 보안 위반으로 오류가 발생한다.

---

## 9. 개발 → 테스트 → 배포 워크플로우

### 9.1 개발

1. Pack 디렉토리 생성
2. `ecosystem.json` 생성
3. `functions/` 디렉토리에 기능 구현
4. 필요에 따라 흐름, 구성 요소 및 경로 생성

### 9.2 테스트

함수는 stdin/stdout에 대한 JSON 프로토콜을 따르므로 명령줄에서 직접 테스트할 수 있습니다.

```bash
# Python Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | python main.py

# バイナリ Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | ./my_binary

# コマンド Function
echo '{"context":{"principal_id":"test","pack_id":"my_pack","function_id":"my_func","request_id":"1","ts":"2026-01-01T00:00:00Z"},"args":{"key":"value"}}' | node index.js
```

### 9.3 배포

1. Pack 디렉터리를 zip으로 배포하거나 Git 저장소에 게시합니다.
2. `ecosystem/`에 배치된 사용자
3. 다음 시작 시 커널 스캔 및 등록
4. 향후 시장에 유통될 예정(Phase D/E)

---

## 10. CapabilityResponse

모든 함수 호출의 결과는 CapabilityResponse로 반환됩니다.

```json
{
  "success": true,
  "output": { "任意のデータ": "..." },
  "error": null,
  "error_type": null,
  "latency_ms": 42.5
}
```

| 필드 | 유형 | 설명 |
|-----------|-----|------|
| 성공 | 부울 | 성공적인 실행 |
| 출력 | 어떤 | 출력 데이터(JSON) |
| 오류 | 문자열 / 널 | 오류 메시지 |
| 오류 유형 | 문자열 / 널 | 오류 유형 |
| 대기시간_ms | 플로트 | 실행에 걸린 시간(ms) |

### 오류 유형 목록

| 오류 유형 | 설명 |
|-----------|------|
| 잘못된 요청 | 잘못된 요청 형식 |
| handler_not_found | 핸들러를 찾을 수 없습니다 |
| 신뢰거부 | 신뢰 확인 실패 |
| 승인 거부 | 부여 확인 실패 |
| 속도 제한 | 비율 제한에 도달함 |
| 시간 초과 | 시간 초과 |
| response_too_large | 응답 크기 초과(1MB) |
| 함수_실행_오류 | 함수 실행 중 오류 |
| 잘못된_json_output | stdout이 유효한 JSON이 아닙니다 |
| 바이너리_not_found | 바이너리를 찾을 수 없습니다 |
| 보안 위반 | 보안 위반(경로 순회 등) |
| 초기화_오류 | 초기화 오류 |
| 내부 오류 | 내부 오류 |

---

## 관련 문서

- [다국어 팩 개발 가이드](./multilang_pack_guide.md) — Python 이외의 언어로 팩을 개발하는 방법
- [Pack 데스크톱 앱 개발 가이드](./pack_desktop_app_guide.md) — 데스크톱 앱용 팩 개발 방법
- [로드맵](./roadmap.md) — 루미 AI OS 전체 계획
