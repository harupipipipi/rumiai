<!-- docs-i18n-links:start -->
[EN](../../../concepts/system-mechanism.md) | [JP](../../ja/concepts/system-mechanism.md) | [KR](./system-mechanism.md) | [CN](../../zh-cn/concepts/system-mechanism.md)
<!-- docs-i18n-links:end -->

# Runtime Mechanism (코드 불필요한 버전)

이 문서는 "Rumi AI가 어떻게 작동하는지"를 코드를 읽지 않아도 추적하도록 정리한 것입니다.

## 1. 부팅시 무슨 일이 일어나는가?

1. `python -m rumi_ai`가 `rumi_ai_1_10/app.py`을 시작합니다.
2. `flows/00_startup.flow.yaml`의 순서로 Kernel 핸들러가 실행된다.
3. 보안 초기화, 팩 스캔, API 서버 초기화가 완료되면 `system.ready`가 발행됩니다.

시작 흐름은 `init -> security -> ecosystem -> finalize`의 4단계입니다.

## 2. Flow 및 Modifier 로드 순서

Flow는 다음 순서로 읽혀집니다 (위보다 우선).

1. `flows/`(공식)
2. `user_data/shared/flows/`(공유)
3. `ecosystem/<pack_id>/.../flows/`(Pack 제공)
4. `ecosystem/flows/`(호환 legacy)

Modifier도 마찬가지로로드되고 대상 Flow에 `inject_before / inject_after / append / replace / remove`를 적용합니다.

## 3. Pack 실행이 허용되는 조건

팩 실행에는 다음 세 단계가 필요합니다.

1. **Approve**: 팩이 승인됨
2. **Trust**: 승인 시 해시와 현재 해시가 일치함
3. **Grant**: capability 실행 권한이 principal 에 부여되어 있는 것

어느 하나라도 누락되면 실행되지 않습니다. 파일 변경이 포함된 팩은 `modified`를 취급하고 다시 승인해야 합니다.

## 4. API 서버 위치 지정

- Kernel은 `127.0.0.1:8765`에서 API를 게시합니다.
- Pack 관리, Flow 실행, secrets, grant, desktop token 등은 이 API가 입구입니다.
- 루트는 코어 API 외에도 Pack 측 `api_routes`을 로드하여 확장됩니다.

## 5. 뷰어와 런타임 간의 관계

`rumi_viewer`는 "Kernel을 시작하여 panel에 연결하는 shell"입니다.

1. 뷰어가 Python / venv / runtime 경로 해결
2. `python -m app`에서 Kernel 시작
3. `/panel/`에 bootstrap하여 UI 표시

`defaultspack`의 독립 frontend(`8766`)와 panel(`8765/panel`)은 별 도선입니다.

## 6. Pack 배포 실행 경로(Import/Apply)

1. PackImporter 가 zip/folder 를 staging 전개(Zip Slip·폭탄 대책)
2. ecosystem.json 검증
3. PackApplier가 backup을 만들어 `ecosystem/<pack_id>/`에 반영
4. 반영 후에는 `modified` 취급이 되기 때문에 재승인 플로우에

## 7. 어디를 읽으면 깊은 파는가?

- 전체 설계: [../architecture.md](../architecture.md)
- 운영/API: [../operations.md](../operations.md)
- 뷰어 시작 경로: [../rumi_viewer_start.md](../rumi_viewer_start.md)
- Pack 개발: [../pack-development.md](../pack-development.md)
