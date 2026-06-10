<!-- docs-i18n-links:start -->
[EN](../../../../examples/viewer_hello_pack/README.md) | [JP](../../../ja/examples/viewer_hello_pack/README.md) | [KR](./README.md) | [CN](../../../zh-cn/examples/viewer_hello_pack/README.md)
<!-- docs-i18n-links:end -->

# 시청자 헬로우 팩

루미 AI OS의 **뷰어:디스플레이** 기능을 활용한 샘플팩입니다.
루미 뷰어 내에 Hello World 프런트엔드를 표시합니다.

Pack은 개발자가 복사하고 수정할 수 있는 템플릿 역할도 합니다.

---

## 디렉토리 구조

```
viewer_hello_pack/
├── ecosystem.json   # Pack マニフェスト
├── web/
│   ├── index.html   # フロントエンド（Hello World ページ）
│   └── app.js       # Kernel API 通信サンプル
└── README.md        # このファイル
```

---

## 뷰어:디스플레이 기능이란 무엇입니까?

`viewer:display`은 Rumi AI OS의 핵심 기능 중 하나이며 Pack이 Rumi Viewer(Tauri 기반 데스크톱 UI)에서 프런트 엔드를 표시할 수 있는 권한입니다.

이 기능을 갖춘 팩:

1. `web_mount`에 지정된 디렉터리의 정적 파일이 뷰어에서 배포됩니다.
2. 커널은 단기 토큰을 발행하고 뷰어는 해당 토큰으로 인증합니다.
3. 커널 API(`localhost:8765`)를 프런트 엔드에서 호출할 수 있습니다.

능력의 정의는 `core_runtime/core_pack/core_viewer_capability/`에 있습니다.

---

## 사용방법

### 1. 팩을 올려놓는다

이 디렉토리를 `ecosystem/`에 복사하세요:

```bash
cp -r docs/examples/viewer_hello_pack/ ecosystem/viewer_hello_pack/
```

### 2. 커널 시작

```bash
python -m rumi_ai
```

커널이 시작되면 자동으로 `ecosystem/viewer_hello_pack/ecosystem.json`을 검사합니다.

### 3. 팩 승인

에코시스템 팩은 처음 승인이 필요합니다(core_packs와 달리 자동으로 승인되지 않음).
Kernel API 또는 관리 화면에서 팩을 승인해주세요.

### 4. 보조금 받기

`viewer.display` 권한 부여가 필요합니다.
다음과 같이 권한 부여를 구성합니다.

- 커널 GrantManager에 `viewer.display` 부여를 `viewer_hello_pack`에 추가했습니다.
- 권한이 설정되면 뷰어:디스플레이 기능을 통해 프런트엔드가 표시됩니다.

### 5. 뷰어로 표시

루미 뷰어를 시작하면 승인/허용된 팩의 프런트 엔드가 표시됩니다.
`web/index.html`은 뷰어에서 렌더링되며 커널 API를 사용한 통신 데모가 작동합니다.

---

## Ecosystem.json 설명

```json
{
  "pack_id": "viewer_hello_pack",
  "capabilities": ["viewer.display"],
  "web_mount": "web"
}
```

| 필드 | 설명 |
|-----------|------|
| §루미§0§ | 요청된 기능 목록입니다. `viewer.display`을 지정하면 뷰어 표시가 가능합니다 |
| §루미§0§ | 정적 파일을 제공할 디렉터리입니다. 팩 루트에 상대적인 경로 |

---

## 커널 API 통신

`web/app.js`에는 커널 API에 대한 가져오기 샘플이 포함되어 있습니다.

```javascript
fetch("http://localhost:8765/api/health", {
  method: "GET",
  headers: { "Accept": "application/json" }
})
  .then(response => response.json())
  .then(data => console.log(data));
```

커널 API의 기본 포트는 `8765`입니다.

---

## 맞춤 설정 팁

- **UI 변경**: `web/index.html`의 HTML/CSS를 편집합니다. 외부 CSS 프레임워크를 추가하는 것도 가능합니다.
- **API 호출 추가**: `web/app.js`에 새로운 가져오기 호출을 추가합니다.
- **함수 추가**: `ecosystem.json`의 `functions` 섹션과 `functions/` 디렉터리에 함수를 추가하여 백엔드 처리를 구현할 수도 있습니다.
- **다중 페이지**: `web/` 디렉토리에 페이지를 추가하고 SPA 라우팅 및 다중 HTML 파일로 지원
- **팩명 변경** : `ecosystem.json`의 `pack_id`, `pack_identity`을 변경해주세요.

---

## 관련 문서

- [팩 개발 가이드](../../pack-development.md)
- [다국어 팩 개발 가이드](../../multilang_pack_guide.md)
- [core_viewer_capability](../../../core_runtime/core_pack/core_viewer_capability/)
