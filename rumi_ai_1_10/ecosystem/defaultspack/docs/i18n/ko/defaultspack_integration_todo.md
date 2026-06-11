<!-- docs-i18n-links:start -->
[EN](../../defaultspack_integration_todo.md) | [JP](../ja/defaultspack_integration_todo.md) | [KR](./defaultspack_integration_todo.md) | [CN](../zh-cn/defaultspack_integration_todo.md)
<!-- docs-i18n-links:end -->

# defaultspack 통합 TODO

## 목표

defaultspack은 Rumi에서 제공하는 팩 데스크톱 앱입니다. 프런트엔드는 백엔드 구성요소의 하드와이어 소유자가 아닌 교체 가능한 셸로 유지되어야 합니다.

## 원칙

- 부품은 데이터로 선언됩니다. 프런트엔드는 부분 계약을 받고 이해한 내용을 렌더링합니다.
- 구성 요소는 모든 새 구성 요소에 대해 React를 편집하는 것이 아니라 매니페스트/구성을 제공하여 부품 사용 방법을 결정합니다.
- 백엔드 기능/구성 요소 이름은 `/api/ui/*` 계약 뒤에 유지됩니다.
- 사용자 오버레이는 `user_data/shared/frontend_extensions/*.ui.json`를 통해 기본 부품을 교체하거나 확장할 수 있습니다.
- UI는 나중에 폐기될 수 있습니다. 계약, 매니페스트, 경로 및 아이콘 자산 경로는 재작성 후에도 유지되어야 합니다.

## 현재 슬라이스

- [x] Rumi 파비콘을 defaultspack 소유 자산으로 이동합니다.
- [x] React에서 하드코딩하는 대신 UI 표면 구성을 통해 아이콘을 노출합니다.
- [x] `ecosystem.json`에 defaultspack `desktop_app` 메타데이터를 추가합니다.
- [x] defaultspack HTTP 표면을 여는 작은 데스크탑 실행 프로그램을 추가합니다.
- [x] `/api/ui/catalog`, `/api/ui/settings` 및 `/api/ui/conversations/{id}/preview`를 등록합니다.
- [x] 독립형 모드에 대한 대체 HTTP 경로를 추가합니다.
- [x] 부품 및 구성 요소 바인딩을 위한 UI 표면 구성 슬롯을 추가합니다.
- [x] 입력된 API 계약을 통해 프런트엔드 액세스를 유지합니다.
- [x] UI 카탈로그에 셸 레이아웃/셸 렌더러 계약을 추가합니다.
- [x] `user_data/shared/frontend_shell.json`가 React를 편집하지 않고 쉘 레이아웃을 재정의하도록 합니다.
- [x] 앱 크롬, 기록, 채팅, 미리보기, 사이드바 및 설정에 대한 스키마 포함 부분을 추가합니다.
- [x] 셸 레이아웃 계약을 통해 표시되는 React 영역을 게이트로 이동합니다.
- [x] 눈에 보이는 각 React 영역을 `webapp/src/renderers/` 아래의 자체 작은 렌더러 모듈로 분할합니다.
- [x] 오류 경계 및 폴백 렌더러와 함께 신뢰할 수 있는 로컬 번들에 대한 지연 사용자 정의 렌더러 로딩을 추가합니다.
- [x] 잘못된 `parts`, `component_bindings`, `shell_layout` 및 `shell_renderers`에 대한 검증 진단을 추가합니다.
- [x] 미리 보기 계약의 도구 타임라인, 계획 단계, 승인, 첨부 파일 및 오디오 페이로드에 대한 명시적 스키마를 추가합니다.
- [x] DI, 권한 구성, 토큰 발급 및 커널 데스크톱 처리기를 통해 부여 흐름을 `desktop_app.execute`에 연결합니다.
- [x] `RUMI_DEFAULTSPACK_SURFACE=webview`를 통해 기본 webview 래퍼 옵션을 추가합니다.

## 제품 후속 조치 참고사항

- 제품 UI 방향이 설정된 후 임시 내장 렌더러 비주얼을 교체합니다.
- 기본 WebView가 기본값이 되는 경우에만 패키지 `pywebview`; 현재 기본값은 브라우저 대체 상태로 유지됩니다.
- 뷰어 UI가 데스크톱 앱이 실행되는 위치를 선택하면 엔드투엔드 뷰어 클릭 경로를 추가합니다.
