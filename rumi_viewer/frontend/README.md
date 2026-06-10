<!-- docs-i18n-links:start -->
[EN](./README.md) | [JP](./i18n/ja/README.md) | [KR](./i18n/ko/README.md) | [CN](./i18n/zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Rumi Viewer Frontend

Front-end application for Rumi AI's control panel.
This directory is the canonical source of the `/panel/` UI.

`npm run build` copies Vite artifacts to `../../rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web`. Both viewer and browser use the same `/panel/` artifact delivered by the kernel. Tauri's `splash` is a viewer-only screen before the kernel starts, and is separate from the panel frontend.

## Technology stack

- React 19 + TypeScript
- Vite
- Tailwind CSS v4
- Zustand (state management)
- React Flow (Flow Editor)

## Development

### Prerequisites

- Node.js 18+
- npm

### Setup

```bash
npm install
```

### Start development server

```bash
npm run dev
```

It can be accessed at http://localhost:3000.
Requests to the backend API (`http://localhost:8765`) are automatically forwarded through the Vite proxy.

### Build

```bash
npm run build
```

### Type checking

```bash
npm run lint
```

## Directory structure

```
src/
├── components/    UI コンポーネント
├── hooks/         カスタムフック
├── lib/           ユーティリティ・API クライアント・型定義
├── pages/         ページコンポーネント
├── store.ts       Zustand ストア
└── main.tsx       エントリーポイント
```

## Graph Editor Extensions

The graph editor on the `Flows` page now supports the following expansions from simple vertical step display.

- Graph editing starting from `rumi_start`
- Multiple ports per node
- Connection constraints by `contracts` (proprietary standard tag) for each port
- `rumi_graph` Keep editor state in YAML as metadata
- Keep `basepack` as flow metadata

`rumi_graph` is metadata for editors to avoid breaking runtime compatibility. The viewer can restore port/connection information while simultaneously outputting `steps` that can be read by the existing runtime.
