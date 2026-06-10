<!-- docs-i18n-links:start -->
[EN](../../rumi_viewer_start.md) | [JP](../ja/rumi_viewer_start.md) | [KR](./rumi_viewer_start.md) | [CN](../zh-cn/rumi_viewer_start.md)
<!-- docs-i18n-links:end -->

#rumi_viewer Start Guide

`rumi_viewer`는 Tauri의 desktop shell입니다. 개발 시작은 repo에서 `rumi_ai_1_10/`을 자동 감지하고 Python kernel을 시작하여 panel UI에 연결합니다.
control panel frontend의 source는 `rumi_viewer/frontend`이 소유하고 kernel은 build 된 artifact를 `rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web`에서 `/panel/`로 전달합니다.

## 이것을 읽는 타이밍

- 뷰어를 최단으로 시작하고 싶습니다.
- 뷰어가 커널을 찾지 못하고 멈 춥니 다.
- panel은 열리지만 화면 전환이 무너집니다.
- `defaultspack`의 frontend / panel 주위의 기동 경로를 쫓고 싶다

## 최단 시작 절차

repo 루트에서 다음을 수행합니다.

```bash
cd rumi_viewer/frontend
npm install
cd ..
cargo tauri dev
```

2번째 이후, `rumi_viewer/frontend/node_modules`가 남아 있는 경우는 다음만으로 기동할 수 있습니다.

```bash
cd rumi_viewer
cargo tauri dev
```

개발 기동에서는 viewer 가 다음을 자동으로 실시합니다.

1. repo에서 `rumi_ai_1_10/` 감지
2. `~/Library/Application Support/dev.rumiai.app/venv` 준비
3. `python -m app`에서 커널을 시작합니다.
4. `http://127.0.0.1:8765/panel/`로 bootstrap
5. 뷰어에서 `Open Defaultspack`를 누르면 `defaultspack`의 독립 UI가 열립니다.

## 개발시 승인 흐름

- repo checkout을 감지해도 팩 자동 승인은 활성화되지 않습니다.
- 개발 환경으로 kernel에 `RUMI_ENVIRONMENT=development`는 배달됩니다
- `RUMI_AUTO_APPROVE_LOCAL=true`를 명시하고 뷰어를 시작할 때만 개발 자동 승인이 활성화됩니다.

예:

```bash
cd rumi_viewer
RUMI_AUTO_APPROVE_LOCAL=true cargo tauri dev
```

이 opt-in 을 붙이지 않는 통상의 개발 기동에서는, modified pack 는 재승인 대기 상태인 채입니다.

## 시작할 때 보는 방법

- 정상적으로 시작하면 Tauri window가 열립니다.
- 초기 상태에서는 `/health`가 `needs_setup: true`를 반환할 수 있으며, 이 경우 setup 화면에서 시작됩니다.
- setup 완료 후 panel UI로 전환합니다.
- panel 홈에서 `Open Defaultspack`를 누르면 뷰어가 `defaultspack`의 브라우저 UI를 시작합니다.

## defaultspack과의 관계

- 뷰어가 직접 열리는 것은 kernel의 control panel (`/panel/`)입니다
- frontend source는 뷰어 측에 있지만 배달 경로는 kernel의 `/panel/`로 유지됩니다.
- `defaultspack` 자체는 커널에서 component로 읽습니다.
- `defaultspack`의 독립 HTTP frontend는 `DEFAULTS_HTTP_PORT` 기본값 `8766`이지만 뷰어의 초기 리드와는 별도입니다.
- 개발 기동 (`cargo tauri dev`) 에서는 repo 동고의 `rumi_ai_1_10/ecosystem/defaultspack/` 를 우선해 엽니다
- 배포판 / bundle 기동에서는 `rumi_home/user_data/packs/defaultspack/current.json` 를 보고, 마이그레이션 호환으로서 `app_data_dir/user_data/packs/defaultspack/current.json` 도 참조합니다
- 그러므로 setup/업데이트된 `Defaultspack v2` 가 managed pack 으로 바뀌고 있으면 배포판 viewer 로부터 그 실체를 엽니다

## 자주 걸리는 방법

### `Kernel directory not found`

뷰어가 bundle의 `app/` 만 보거나 repo checkout을 찾을 수 없습니다. 개발 기동은 repo 루트 아래에서 실시해 주세요.

### `panel bootstrap returned 401 Unauthorized`

bootstrap secret가 잘못되었거나 오래된 커널이 `8765` 포트를 잡았을 수 있습니다. 아래에서 점유를 확인합니다.

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

### Home 등을 누르면 어두워집니다.

panel frontend는 `basename="/panel"` 전제입니다. 링크나 `navigate()`에서 `/panel/...`를 이중으로 붙이면 `/panel/panel`로 날아 루트 불일치가 됩니다. frontend 측의 루트는 `/`, `/packs`, `/flows`, `/settings`와 같이 basename 상대로 갖게 해 주십시오.

## 확인 명령

커널이 실행 중인지 확인 :

```bash
curl http://127.0.0.1:8765/health
```

defaultspack 독립 frontend가 시작되었는지 확인 :

```bash
curl http://127.0.0.1:8766/api/health
```

## 관련 파일

- `rumi_viewer/src-tauri/src/config.rs`
- `rumi_viewer/src-tauri/src/kernel_manager.rs`
- `rumi_viewer/src-tauri/src/lib.rs`
- `rumi_viewer/frontend/src/App.tsx`
- `rumi_viewer/frontend/src/lib/routes.ts`
