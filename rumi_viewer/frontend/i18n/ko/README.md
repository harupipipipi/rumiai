<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# 루미 뷰어 프론트엔드

Rumi AI 제어판용 프런트엔드 애플리케이션입니다.
이 디렉터리는 `/panel/` UI의 정식 소스입니다.

`npm run build`는 Vite 아티팩트를 `../../rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web`에 복사합니다. 뷰어와 브라우저 모두 커널이 제공하는 동일한 `/panel/` 아티팩트를 사용합니다. Tauri의 `splash`은 커널이 시작되기 전의 뷰어 전용 화면이며 패널 프런트엔드와 별개입니다.

## 기술 스택

- 리액트 19 + 타입스크립트
- 비테
- 순풍 CSS v4
- Zustand (상태 관리)
- React Flow(흐름 편집기)

## 개발

### 전제조건

- Node.js 18+
- npm

### 설정

```bash
npm install
```

### 개발 서버 시작

```bash
npm run dev
```

http://localhost:3000.에서 접속하실 수 있습니다.
백엔드 API(`http://localhost:8765`)에 대한 요청은 Vite 프록시를 통해 자동으로 전달됩니다.

### 빌드

```bash
npm run build
```

### 유형 검사

```bash
npm run lint
```

## 디렉토리 구조

```
src/
├── components/    UI コンポーネント
├── hooks/         カスタムフック
├── lib/           ユーティリティ・API クライアント・型定義
├── pages/         ページコンポーネント
├── store.ts       Zustand ストア
└── main.tsx       エントリーポイント
```

## 그래프 편집기 확장

`Flows` 페이지의 그래프 편집기는 이제 간단한 수직 단계 표시에서 다음 확장을 지원합니다.

- `rumi_start`부터 그래프 편집 시작
- 노드당 여러 포트
- 각 포트에 대한 `contracts`(고유 표준 태그)에 의한 연결 제한
- `rumi_graph` 편집자 상태를 YAML에 메타데이터로 유지
- `basepack`를 흐름 메타데이터로 유지

`rumi_graph`은 편집자가 런타임 호환성 손상을 방지하기 위한 메타데이터입니다. 뷰어는 포트/연결 정보를 복원하는 동시에 기존 런타임에서 읽을 수 있는 `steps`을 출력할 수 있습니다.
