<!-- docs-i18n-links:start -->
[EN](../../../../examples/viewer_pack/README.md) | [JP](../../../ja/examples/viewer_pack/README.md) | [KR](./README.md) | [CN](../../../zh-cn/examples/viewer_pack/README.md)
<!-- docs-i18n-links:end -->

# 뷰어 예제 팩

Rumi Viewer에 프런트엔드를 표시하기 위해 `viewer:display` 기능을 사용하는 팩의 최소 예입니다.

## 개요

이 팩은 다음을 보여줍니다:

- `viewer.display` 능력 선언 방법(`manifest.json`, `requires` 및 `vocab_aliases`)
- `grant_config`에 의한 부여 설정
- `web_mount`를 사용한 프런트엔드 제공
- `calling_convention: "block"`에 대한 함수 스텁

## 디렉토리 구조

```
viewer_pack/
├── ecosystem.json                    # Pack 定義（web_mount, functions）
├── functions/
│   └── request_display/
│       ├── manifest.json             # viewer.display capability 宣言
│       └── main.py                   # Function スタブ（block）
├── web/
│   ├── index.html                    # Pack フロントエンド
│   └── style.css                     # スタイル
└── README.md                         # このファイル
```

## 각 파일의 역할

### 생태계.json

팩의 매니페스트. `pack_id`, `metadata`, `web_mount`, `functions`을 정의합니다.
`web_mount` 필드는 루미 뷰어 내 `web/` 디렉토리의 내용을 전달합니다.

### 함수/request_display/manifest.json

`viewer.display` 능력의 상세한 선언. 다음 필드가 중요합니다.

- **`requires`**: `["viewer.display"]` — 이 기능에 필요한 기능
- **`vocab_aliases`**: `["viewer.display"]` — FunctionRegistry의 별칭 확인에 사용됩니다.
- **`grant_config`**: 부여 설정(`allowed_packs`, `max_token_lifetime`)
- **`calling_convention`**: `"block"` — 커널의 DI 핸들러를 통해 실행됩니다.

### 함수/request_display/main.py

이것은 `calling_convention: "block"`에 대한 스텁입니다. 런타임 시 커널 DI 핸들러
(`handle_display`)이므로 이 파일은 직접 실행되지 않습니다.
팩 구조의 무결성을 위해 존재합니다.

### 웹/index.html, 웹/스타일.css

이것은 Pack의 프런트 엔드입니다. Rumi Viewer의 샌드박스 WebView 내부에 로드됩니다.
저는 CDN을 사용하지 않고 일반 HTML/CSS로 작성합니다.

## 뷰어:디스플레이 기능 작동 방식

1. 팩 요청 `viewer.display` 기능
2. `capability_executor`는 `FunctionRegistry.resolve_by_alias("viewer.display")`에 의해 해결되었습니다.
3. `grant_config`이 설정된 경우 `capability_grant_manager`에서 Grant를 확인합니다.
4. `calling_convention: "block"` → 커널 DI 핸들러(`handle_display`) 실행
5. 토큰과 `web_mount_url`이 반환됩니다.
6. Rumi Viewer는 `web_mount_url`를 샌드박스 WebView에 로드합니다.

## 보조금 받기

이 팩은 `viewer.display` 기능을 사용하려면 보조금이 필요합니다.
보조금은 `capability_grant_manager`에 의해 관리됩니다.

- **`allowed_packs`**: 빈 배열 `[]`인 경우 모든 팩의 요청을 허용합니다.
- **`max_token_lifetime`**: 최대 토큰 만료 시간(초)

보조금 작동 방식에 대한 자세한 내용은 [팩 개발 가이드 섹션 6](../../pack-development.md)을 참조하세요.

## 관련 문서

- [팩 개발 가이드](../../pack-development.md) — 팩 구조, 수명 주기 및 기능에 대한 세부 정보
- [다국어 팩 개발 가이드](../../multilang_pack_guide.md) — Python 이외의 언어로 팩을 개발하는 방법
