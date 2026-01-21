## 🌟 このプロジェクトについて

現在のAI開発は混沌としています：

- APIはプロバイダーごとにバラバラ
- 新機能が毎週のように登場
- 昨日の常識が今日は通用しない
- カスタマイズすると本体更新が困難に

**Rumi AI**は、この問題に対する根本的な解決策です。

Minecraftのmodのように、**公式ファイルを一切編集せずに**機能を追加・変更できる。しかしMinecraftと決定的に違うのは、**改造する「本体」が存在しない**ことです。

---

## 💭 思想

### 「基盤のない基盤」とは

Minecraftのmodは「Minecraft」という基盤を改造します。
しかしRumi AIには、改造される「本体」がありません。

```
Minecraft の世界:
┌─────────────────────────────────────┐
│         Minecraft本体                │  ← これを改造
│  (ブロック、クリーパー、etc.)         │
├─────────────────────────────────────┤
│            Mod A                     │
│            Mod B                     │
└─────────────────────────────────────┘

Rumi AI の世界:
┌─────────────────────────────────────┐
│                                     │
│    Component ←→ Component           │
│        ↑           ↓                │  ← 網のように繋がる
│    Component ←→ Component           │
│                                     │
├─────────────────────────────────────┤
│     Kernel (実行ルールのみ)           │  ← 「何を」ではなく「どう動くか」だけ
└─────────────────────────────────────┘
```

公式が定義するのは**実行の仕組み**だけです：

- Flow YAML（`flow/*.flow.yaml`）に定義されたパイプラインを順次実行
- `component_phase:{phase_name}` ハンドラで任意のPythonファイルを実行可能
- どのフェーズを設けるか、どのファイル名にするかは**YAMLとコミュニティが決める**

例えば、デフォルトのFlow定義では以下の規約を採用しています（公式の強制ではない）：

- `dependency_manager.py` → 依存関係解決フェーズ
- `setup.py` → セットアップフェーズ  
- `runtime_boot.py` → ランタイム起動フェーズ

**「チャット」「ツール」「プロンプト」「AIクライアント」「フロントエンド」― これらは全て公式の知らない概念です。**

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

`ecosystem/default/` にあるComponentも、あなたが作るComponentも、完全に同じルールで動きます。

---

## 🚀 クイックスタート

### 必要条件

- Python 3.9+
- Git

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/your-repo/rumi-ai.git
cd rumi-ai

# セットアップを実行
# Windows:
setup.bat

# Mac/Linux:
chmod +x setup.sh
./setup.sh
```

セットアップウィザードが起動します：

```
╔════════════════════════════════════════════╗
║    🌸 Rumi AI セットアップ                 ║
╠════════════════════════════════════════════╣
║                                            ║
║    1. CLI モード（ターミナル操作）         ║
║    2. Web モード（ブラウザ操作）           ║
║    q. 終了                                 ║
║                                            ║
╚════════════════════════════════════════════╝
```

### アプリケーションの起動

セットアップ完了後：

```bash
# セットアップツールから起動
./setup.sh --cli run

# または直接起動
.venv/bin/python app.py      # Mac/Linux
.venv\Scripts\python app.py  # Windows
```

ブラウザで `http://localhost:5000` を開きます。

---

## 🛠️ セットアップシステム

Rumi AI には統合セットアップシステムが含まれています。

### コマンド一覧

| コマンド | 説明 |
|---------|------|
| `./setup.sh` | 対話モード（CLI/Web選択） |
| `./setup.sh --cli check` | 環境チェック（Python, Git, Docker） |
| `./setup.sh --cli init` | 初期セットアップ |
| `./setup.sh --cli doctor` | システム診断 |
| `./setup.sh --cli recover` | 壊れた設定を修復 |
| `./setup.sh --cli run` | アプリケーション起動 |
| `./setup.sh --web` | Web UI モード |
| `./setup.sh --web --port 9000` | ポート指定 |

### セットアップの流れ

```
setup.bat / setup.sh
    │
    ├── 1. Python チェック（なければガイドを表示）
    ├── 2. Git チェック（なければガイドを表示）
    ├── 3. Docker チェック（任意・警告のみ）
    ├── 4. 仮想環境（.venv）を作成
    ├── 5. pip アップグレード
    ├── 6. requirements.txt インストール
    └── 7. bootstrap.py 実行
            │
            ├── CLI モード → ターミナルで操作
            └── Web モード → ブラウザで操作
```

### Default Pack のインストール

初期セットアップ時に default pack のインストールを選択できます：

```
default pack をインストールしますか？ [Y/n]:
```

- **Y**: `rumi_setup/defaults/default/` を `ecosystem/default/` にコピー
- **n**: スキップ（空のecosystemで開始）

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
│  │    任意フェーズの汎用実行器（ファイル名はYAMLで指定）   │   │
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
```

---

## 📁 ディレクトリ構造

```
project_root/
│
├── setup.bat                           # Windows セットアップ
├── setup.sh                            # Mac/Linux セットアップ
├── bootstrap.py                        # セットアップエントリポイント
├── requirements.txt                    # Python依存関係
├── app.py                              # Flaskエントリポイント
│
├── rumi_setup/                         # セットアップシステム
│   ├── guide/                          # インストールガイド(HTML)
│   │   ├── index.html
│   │   ├── python.html
│   │   ├── git.html
│   │   └── docker.html
│   ├── defaults/                       # Default Pack テンプレート
│   │   └── default/
│   ├── core/                           # 共通ロジック
│   │   ├── checker.py
│   │   ├── initializer.py
│   │   ├── recovery.py
│   │   ├── installer.py
│   │   ├── runner.py
│   │   └── state.py
│   ├── cli/                            # CLIインターフェース
│   └── web/                            # Webインターフェース
│
├── core_runtime/                       # 用途非依存カーネル
│   ├── kernel.py                       # Flow駆動カーネル
│   ├── diagnostics.py                  # 診断集約
│   ├── install_journal.py              # 生成物追跡
│   ├── interface_registry.py           # サービス登録箱
│   ├── event_bus.py                    # イベントバス
│   └── component_lifecycle.py          # コンポーネントライフサイクル
│
├── backend_core/                       # エコシステム基盤
│   └── ecosystem/
│       ├── mounts.py                   # パス抽象化
│       ├── registry.py                 # Pack/Component読込
│       ├── active_ecosystem.py         # アクティブPack管理
│       └── compat.py                   # 互換レイヤー
│
├── ecosystem/                          # Pack/Component群
│   └── default/
│       ├── backend/
│       │   ├── ecosystem.json
│       │   └── components/
│       └── frontend/
│
├── flow/                               # Flow定義
│   ├── 00_core.flow.yaml
│   ├── 10_components.flow.yaml
│   ├── 20_services.flow.yaml
│   └── 50_message.flow.yaml
│
├── user_data/                          # ユーザーデータ
│   ├── mounts.json
│   ├── active_ecosystem.json
│   ├── chats/
│   └── settings/
│
└── docs/                               # ドキュメント
    └── setup.txt
```

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

### システム

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| `GET` | `/api/diagnostics` | 診断情報 |
| `GET` | `/api/ecosystem/status` | エコシステム状態 |

---

## 🔧 開発

### 新しいコンポーネントの作成

```
ecosystem/my_pack/backend/components/my_component/
├── manifest.json
└── setup.py          # ファイル名はFlowで定義（慣例としてsetup.py）
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

### ライフサイクルファイルの規約（デフォルトFlow準拠）

| ファイル名 | フェーズ | 用途 |
|-----------|---------|------|
| `dependency_manager.py` | dependency | pip install等の環境構築 |
| `setup.py` | setup | InterfaceRegistryへの登録 |
| `runtime_boot.py` | runtime_boot | サービス起動処理 |

※これらはデフォルトFlowの規約であり、カスタムFlowでは任意のファイル名・フェーズ名を使用可能

### Fail-Soft設計

全ての層でエラー許容：

```python
# コンポーネントのsetup.pyで例外が発生しても
# システムは停止せず、診断情報に記録して継続
```

---

## 📐 設計原則

1. **公式ファイルの編集を必要としない** ― 全ては `ecosystem/` 内で完結
2. **Fail-soft** ― エラーでもシステムは動き続ける
3. **診断可能** ― 何が起きているか常に見える
4. **贔屓なし** ― 公式Componentは存在しない
5. **用途非依存** ― Kernelは「AI」を知らない
6. **ハードコードしない** ― フェーズ名、ファイル名、インターフェース名は全てYAMLまたはコミュニティが定義

---

## 🤝 コントリビューション

このプロジェクトは**コミュニティ主導**を目指しています。

### 参加方法

1. **Componentを作る** ― 好きな機能を実装
2. **Packを作る** ― 複数のComponentをまとめて配布
3. **繋がりを作る** ― 他のComponentと連携
4. **置き換える** ― 既存のComponentをより良いもので置換

### ガイドライン

- 公式ファイルの編集は最小限に
- 新機能は `ecosystem/` 内にComponentとして実装
- Fail-softを心がける（エラーでも動き続ける）
- 診断情報を適切に出力する

---

## ❓ トラブルシューティング

### Python/Git が見つからない

セットアップ実行時に自動的にインストールガイドが開きます。

### ポートが使用中

```bash
./setup.sh --web --port 9000
```

### 仮想環境の問題

```bash
rm -rf .venv
./setup.sh
```

### 詳細なトラブルシューティング

`docs/setup.txt` を参照してください。

---

## 📜 ライセンス

MIT License

---

## 🔗 リンク

- [セットアップドキュメント](docs/setup.txt)
- [エコシステム仕様書](backend_core/ecosystem/spec/ecosystem_spec.md)

---

*「基盤がないからこそ、何でも作れる」*
```