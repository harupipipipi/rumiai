<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# Rumi ビューア フロントエンド

Rumi AI のコントロール パネルのフロントエンド アプリケーション。
このディレクトリは、`/panel/` UI の正規のソースです。

`npm run build` は Vite アーティファクトを `../../rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web` にコピーします。ビューアとブラウザは両方とも、カーネルによって提供される同じ `/panel/` アーティファクトを使用します。 Tauri の `splash` は、カーネルが起動する前のビューア専用画面であり、パネル フロントエンドとは独立しています。

## テクノロジースタック

- React 19 + TypeScript
- ヴィート
- テイルウィンド CSS v4
- Zustand (国家管理)
- React Flow (フローエディター)

## 開発

### 前提条件

- Node.js 18+
-npm

### セットアップ

```bash
npm install
```

### 開発サーバーを開始します

```bash
npm run dev
```

http://localhost:3000. からアクセスできます。
バックエンド API (`http://localhost:8765`) へのリクエストは、Vite プロキシを通じて自動的に転送されます。

### ビルド

```bash
npm run build
```

### 型チェック

```bash
npm run lint
```

## ディレクトリ構造

```
src/
├── components/    UI コンポーネント
├── hooks/         カスタムフック
├── lib/           ユーティリティ・API クライアント・型定義
├── pages/         ページコンポーネント
├── store.ts       Zustand ストア
└── main.tsx       エントリーポイント
```

## グラフエディターの拡張機能

`Flows` ページのグラフ エディターは、単純な垂直ステップ表示から次の拡張をサポートするようになりました。

- `rumi_start`から始めるグラフ編集
- ノードごとに複数のポート
- 各ポートの`contracts`(独自標準タグ)による接続制約
- `rumi_graph` エディタの状態をメタデータとして YAML に保持
- `basepack`をフローメタデータとして保持

`rumi_graph` は、ランタイム互換性の破壊を避けるための編集者用のメタデータです。ビューアは、既存のランタイムで読み取れる`steps` を出力しながら、ポート/接続情報を復元できます。
