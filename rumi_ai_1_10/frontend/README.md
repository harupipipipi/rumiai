# Rumi AI Frontend

Rumi AI のコントロールパネル用フロントエンドアプリケーション。

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
├── components/    UI コンポーネント
├── hooks/         カスタムフック
├── lib/           ユーティリティ・API クライアント・型定義
├── pages/         ページコンポーネント
├── store.ts       Zustand ストア
└── main.tsx       エントリーポイント
```
