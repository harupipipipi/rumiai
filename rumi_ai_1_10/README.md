```
# Rumi AI OS

**基盤のない基盤 ― AIエコシステムのためのOS**

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🌟 このプロジェクトについて

現在のAI開発は混沌としています：

- APIはプロバイダーごとにバラバラ
- 新機能が毎週のように登場
- 昨日の常識が今日は通用しない
- カスタマイズすると本体更新が困難に

**Rumi AI OS**は、この問題に対する根本的な解決策です。

Minecraftのmodのように、**公式ファイルを一切編集せずに**機能を追加・変更できる。しかしMinecraftと決定的に違うのは、**改造する「本体」が存在しない**ことです。

---

## 💭 思想

### 「基盤のない基盤」とは

Minecraftのmodは「Minecraft」という基盤を改造します。
しかしRumi AI OSには、改造される「本体」がありません。

```
Minecraft の世界:
┌─────────────────────────────────┐
│         Minecraft本体            │  ← これを改造
│  (ブロック、クリーパー、etc.)     │
├─────────────────────────────────┤
│            Mod A                 │
│            Mod B                 │
└─────────────────────────────────┘

Rumi AI OS の世界:
┌─────────────────────────────────┐
│                                 │
│    Component ←→ Component       │
│        ↑           ↓            │  ← 網のように繋がる
│    Component ←→ Component       │
│                                 │
├─────────────────────────────────┤
│     Kernel (実行ルールのみ)       │  ← 「何を」ではなく「どう動くか」だけ
└─────────────────────────────────┘
```

公式が定義するのは**実行ルール**だけです：

- `setup.py` → 起動時に実行される
- `dependency_manager.py` → 環境構築時に実行される
- `runtime_boot.py` → サービス登録時に実行される

**「チャット」「ツール」「プロンプト」「AIクライアント」「フロントエンド」― これらは全て公式の知らない概念です。**

誰かがそういうComponentを作り、他のComponentがそれを見つけて繋がる。それだけです。

---

### 贔屓なし (No Favoritism)

```
❌ 公式が「チャット機能」を実装
❌ 公式が「ツール」の仕様を定義
❌ 公式が「AIクライアント」のインターフェースを決定
❌ 公式が「フロントエンド」のデザインを固定

✅ 公式は実行の仕組みだけを提供
✅ 全てのComponentは平等
✅ 「公式Component」という概念すら存在しない
```

`ecosystem/default/` にあるComponentも、あなたが作るComponentも、完全に同じルールで動きます。公式が特別扱いすることはありません。

---

### なぜこの設計なのか

AIの世界は変化が速すぎます。

- 今日の最先端は来月の遺物
- 特定のAPIに依存すると、そのAPI廃止で全てが壊れる
- 「正しい設計」は1年後には「古い設計」

だからこそ、**公式は何も決めない**。

コミュニティが自由に作り、自由に繋げ、自由に置き換える。公式はその「場」を提供するだけです。

---

## 🏗️ アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Frontend (ecosystem内)                  │   │
│  │  Sidebar │ ChatView │ Modal │ Toast │ Settings      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Flask (app.py)                          │
│                           │                                  │
│              ┌────────────┴────────────┐                    │
│              ▼                         ▼                    │
│    ┌──────────────────┐    ┌───────────────────────┐       │
│    │ Static Files     │    │ API Routes            │       │
│    │ /frontend/*      │    │ /api/*                │       │
│    └──────────────────┘    └───────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    core_runtime/Kernel                       │
│  ┌───────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │   Flow    │  │ InterfaceRegistry│  │   Diagnostics   │   │
│  │  Runner   │  │ (Service Locator)│  │                 │   │
│  └─────┬─────┘  └────────┬────────┘  └─────────────────┘   │
│        │                 │                                   │
│        └────────┬────────┘                                   │
│                 ▼                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Component Lifecycle Executor               │   │
│  │    dependency → setup → runtime_boot                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ecosystem/default/                        │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ frontend│ │  chats  │ │io_http  │ │ message │          │
│  │         │ │         │ │  _api   │ │  _stub  │          │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘          │
│       └───────────┴───────────┴───────────┘                 │
│                 InterfaceRegistry                            │
│       (service.chats, io.http.binders, ui.shell, ...)       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      user_data/                              │
│    chats/  │  settings/  │  mounts.json  │  cache/          │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 ディレクトリ構造

```
project_root/
│
├── app.py                              # Flaskエントリポイント
├── requirements.txt                    # Python依存関係
│
├── core_runtime/                       # 用途非依存カーネル
│   ├── __init__.py
│   ├── kernel.py                       # Flow駆動カーネル
│   ├── diagnostics.py                  # 診断集約
│   ├── install_journal.py              # 生成物追跡
│   ├── interface_registry.py           # サービス登録箱
│   ├── event_bus.py                    # イベントバス
│   └── component_lifecycle.py          # コンポーネントライフサイクル
│
├── backend_core/                       # エコシステム基盤
│   └── ecosystem/
│       ├── __init__.py
│       ├── mounts.py                   # パス抽象化
│       ├── registry.py                 # Pack/Component読込
│       ├── active_ecosystem.py         # アクティブPack管理
│       ├── compat.py                   # 互換レイヤー
│       └── spec/
│           └── ecosystem_spec.md       # アーキテクチャ仕様
│
├── ecosystem/                          # Pack/Component群
│   └── default/
│       ├── backend/
│       │   ├── ecosystem.json          # Pack定義
│       │   └── components/
│       │       ├── chats/              # チャット管理
│       │       ├── io_http_api/        # HTTP APIバインダー
│       │       ├── services/
│       │       │   └── message_stub/   # メッセージ処理スタブ
│       │       ├── foundation/         # 基盤ユーティリティ
│       │       ├── settings/           # 設定管理
│       │       └── ...
│       │
│       └── frontend/                   # フロントエンドUI
│           ├── manifest.json
│           ├── index.html              # SPAエントリ
│           ├── app.js                  # アプリケーション
│           ├── api.js                  # APIクライアント
│           ├── store.js                # 状態管理
│           ├── router.js               # ルーティング
│           ├── utils.js                # ユーティリティ
│           ├── components/
│           │   ├── Sidebar.js          # サイドバー
│           │   ├── ChatView.js         # チャット表示
│           │   ├── ContextMenu.js      # コンテキストメニュー
│           │   ├── Modal.js            # モーダル
│           │   ├── SettingsModal.js    # 設定
│           │   ├── UIHistoryPanel.js   # 実行ログ
│           │   └── Toast.js            # 通知
│           └── styles/
│               ├── variables.css       # CSS変数
│               ├── main.css            # メインスタイル
│               ├── sidebar.css         # サイドバー
│               ├── chat.css            # チャット
│               └── responsive.css      # レスポンシブ
│
├── user_data/                          # ユーザーデータ
│   ├── mounts.json                     # マウント設定
│   ├── active_ecosystem.json           # アクティブPack
│   ├── chats/                          # チャット履歴
│   └── settings/                       # ユーザー設定
│
└── flow/                               # Flow定義
    └── project.flow.yaml               # パイプライン定義
```

---

## 🚀 クイックスタート

### 必要条件

- Python 3.9+
- pip

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/your-repo/rumi-ai-os.git
cd rumi-ai-os

# 依存関係をインストール
pip install -r requirements.txt

# 起動
python app.py
```

### アクセス

ブラウザで `http://localhost:5000` を開きます。

---

## 📡 API リファレンス

### チャット管理

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/chats` | チャット一覧取得 |
| `POST` | `/api/chats` | 新規チャット作成 |
| `GET` | `/api/chats/<id>` | チャット履歴取得 |
| `PATCH` | `/api/chats/<id>` | メタデータ更新 |
| `DELETE` | `/api/chats/<id>` | チャット削除 |
| `POST` | `/api/chats/<id>/copy` | チャットコピー |

### メッセージ

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `POST` | `/api/message` | メッセージ送信 |
| `POST` | `/api/message/stream` | ストリーミング送信（SSE） |
| `POST` | `/api/stream/abort` | ストリーム中断 |

### フォルダ

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `POST` | `/api/folders` | フォルダ作成 |

### 設定

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/user/settings` | 設定取得 |
| `POST` | `/api/user/settings` | 設定保存 |

### システム

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/diagnostics` | 診断情報 |
| `GET` | `/api/ecosystem/status` | エコシステム状態 |

---

## 🎨 フロントエンド

### 機能

- **チャット管理**: 作成、削除、コピー、名前変更
- **フォルダ整理**: フォルダ作成、チャット移動、折りたたみ
- **ピン留め**: 重要なチャットを上部に固定
- **ストリーミング**: リアルタイム応答表示
- **設定**: テーマ切替（ダーク/ライト）、各種設定
- **実行ログ**: ツール実行履歴の表示

### レスポンシブ対応

| 画面サイズ | 動作 |
|-----------|------|
| デスクトップ (>1024px) | フルレイアウト |
| タブレット (768-1024px) | 狭めのサイドバー |
| モバイル (<768px) | オーバーレイサイドバー、ハンバーガーメニュー |

### キーボードショートカット

| キー | 動作 |
|-----|------|
| `Ctrl/Cmd + K` | 新規チャット |
| `Ctrl/Cmd + B` | サイドバー切替（モバイル） |
| `Escape` | モーダル/サイドバーを閉じる |
| `Enter` | メッセージ送信 |
| `Shift + Enter` | 改行 |

### アクセシビリティ

- ARIA属性対応
- キーボードナビゲーション
- フォーカス表示
- スキップリンク
- 動き軽減対応 (`prefers-reduced-motion`)

---

## 🔧 バックエンドコンポーネント

### 標準コンポーネント（default Pack）

| コンポーネント | 提供サービス | 説明 |
|--------------|-------------|------|
| `chats` | `service.chats`, `service.relationships` | チャット履歴管理 |
| `io_http_api` | `io.http.binders` | HTTP APIルート登録 |
| `message_stub` | `message.handle`, `message.handle_stream` | メッセージ処理スタブ |
| `foundation` | `foundation.safe_add_url_rule` | 基盤ユーティリティ |
| `settings` | `service.settings_manager` | ユーザー設定管理 |

### InterfaceRegistry

コンポーネント間の疎結合を実現するサービスロケーター：

```python
# サービス登録
ir.register("service.chats", ChatManager())

# サービス取得
chats = ir.get("service.chats", strategy="last")

# 全て取得
binders = ir.get("io.http.binders", strategy="all")
```

---

## ⚙️ 設定

### user_data/mounts.json

データ保存先のカスタマイズ：

```json
{
  "version": "1.0",
  "mounts": {
    "data.chats": "./user_data/chats",
    "data.settings": "./user_data/settings",
    "data.cache": "./user_data/cache"
  }
}
```

### user_data/active_ecosystem.json

アクティブなPackとオーバーライド：

```json
{
  "active_pack_identity": "github:haru/default-pack",
  "overrides": {
    "chats": "chats_v1"
  },
  "disabled_components": [],
  "disabled_addons": []
}
```

### flow/project.flow.yaml

パイプライン定義（自動生成される場合あり）：

```yaml
flow_version: "1.0"
project:
  id: "rumi_ai"
  title: "Rumi AI OS"

pipelines:
  startup:
    - id: "startup.mounts"
      run:
        handler: "kernel:mounts.init"
    - id: "startup.registry"
      run:
        handler: "kernel:registry.load"
    # ...

  message:
    - id: "message.handle"
      run:
        handler: "kernel:delegate.call"
        args:
          interface_key: "message.handle"
```

---

## 🛠️ 開発

### 新しいコンポーネントの作成

```
ecosystem/my_pack/backend/components/my_component/
├── manifest.json
└── setup.py
```

**manifest.json**:
```json
{
  "type": "my_type",
  "id": "my_component_v1",
  "version": "1.0.0",
  "connectivity": {
    "provides": ["my.service"],
    "requires": []
  }
}
```

**setup.py**:
```python
def run(context):
    ir = context.get("interface_registry")
    ir.register("my.service", MyServiceImplementation())
```

### Fail-Soft設計

全ての層でエラー許容：

```python
# コンポーネントのsetup.pyで例外が発生しても
# システムは停止せず、診断情報に記録して継続
```

### 診断

`/api/diagnostics` で全ステップの実行状況を確認：

```json
{
  "records": [
    {
      "ts": "2024-01-01T00:00:00Z",
      "phase": "startup",
      "step_id": "startup.mounts",
      "status": "success"
    }
  ]
}
```

---

## 🤝 コントリビューション

このプロジェクトは**コミュニティ主導**を目指しています。

### 参加方法

1. **Componentを作る** ― 好きな機能を実装
2. **Packを作る** ― 複数のComponentをまとめて配布
3. **繋がりを作る** ― 他のComponentと連携
4. **置き換える** ― 既存のComponentをより良いもので置換

公式の許可は不要です。作って、公開して、使ってもらう。それだけです。

### ガイドライン

- 公式ファイル（`app.py`, `core_runtime/`, `backend_core/`）の編集は最小限に
- 新機能は `ecosystem/` 内にComponentとして実装
- Fail-softを心がける（エラーでも動き続ける）
- 診断情報を適切に出力する

---

## 📐 設計原則

1. **公式ファイルの編集を必要としない** ― 全ては `ecosystem/` 内で完結
2. **Fail-soft** ― エラーでもシステムは動き続ける
3. **診断可能** ― 何が起きているか常に見える
4. **贔屓なし** ― 公式Componentは存在しない
5. **用途非依存** ― Kernelは「AI」を知らない

---

## 📜 ライセンス

MIT License

---

## 🔗 リンク

- [エコシステム仕様書](backend_core/ecosystem/spec/ecosystem_spec.md)
- [API ドキュメント](#-api-リファレンス)

---

*「基盤がないからこそ、何でも作れる」*
```