# Rumi Viewer Frontend

Rumi AI のコントロールパネル用フロントエンドアプリケーション。
このディレクトリが `/panel/` UI の canonical source です。

`npm run build` は Vite の成果物を `../../rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web` にコピーします。viewer と browser はどちらも kernel が配信する同じ `/panel/` artifact を使用します。Tauri の `splash` は kernel 起動前の viewer 専用画面で、panel frontend とは別です。

## 技術スタック

- React 19 + TypeScript
- Vite
- Tailwind CSS v4
- Zustand (状態管理)
- React Flow (フローエディタ)

## 開発

### 前提条件

- Node.js 18+
- npm

### セットアップ

```bash
npm install
```

### 開発サーバー起動

```bash
npm run dev
```

http://localhost:3000 でアクセスできます。
バックエンド API（http://localhost:8765）へのリクエストは Vite proxy で自動転送されます。

### ビルド

```bash
npm run build
```

### 型チェック

```bash
npm run lint
```

## ディレクトリ構成

```
src/
├── app/           App 起動処理・ルーティング
├── components/    UI コンポーネント
├── hooks/         カスタムフック
├── lib/           ユーティリティ・API クライアント・型定義
├── pages/         ページコンポーネント
├── store/         Zustand ストアの型・初期値・変換
├── store.ts       Zustand ストア本体
└── main.tsx       エントリーポイント
```

## Graph Editor Extensions

`Flows` ページの graph editor は、単純な縦並び step 表示から次の拡張に対応しました。

- `rumi_start` を起点にした graph 編集
- ノードごとの複数ポート
- ポートごとの `contracts`（独自規格タグ）による接続制約
- `rumi_graph` メタデータとして YAML 内へ editor 状態を保持
- `basepack` を flow メタデータとして保持

`rumi_graph` はランタイム互換を壊さないための editor 向けメタデータです。既存ランタイムが読める `steps` も同時に出力しつつ、viewer ではポート/接続情報を復元できます。
