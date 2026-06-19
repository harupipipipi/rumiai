
```markdown
# frontend.md — Rumi AI OS フロントエンド設計書

## 1. 概要

defaults のフロントエンドは Tauri（Rust + WebView）で構成されるデスクトップアプリケーションである。

フロントエンドはドメイン知識を持たない。チャットが何か、エージェントが何か、ファイルが何かを知らない。知っているのは「スロットという枠がある」「Asset という UI ブロックを枠に載せられる」「Widget という描画指示を受け取れる」「メッセージが行き来する」の 4 つだけである。

rumiai 本体がドメイン知識を持たない汎用カーネルであるのと同じ構造を、フロントエンドにも適用する。全てのドメイン機能は Asset が持ち込む。defaults は Asset を載せる空の枠（シェル）と、Asset を描画・通信する仕組みだけを提供する。

具体的な UI（チャット画面、エージェント画面、コーディング画面等）は全て user_data 側のパックが Asset として登録する。defaults 自身は一切の具体的 UI を持たない。

現在の defaultspack 実装では、この一般論に加えて `PlacementManifest`
ベースの配置候補と pin 永続化を段階的に導入している。最初の適用先は
right sidebar / settings / composer 周辺で、Tool Manager, Tool Filter Log,
YOLO toggle, Model Manager, Webhook Endpoints などを surface-aware に配置
できる。

defaultspack の template catalog は、この配置モデルを JSON で合成するための
metadata layer である。`settings_field`, `composer_input`, `ai_input`,
`tool_policy`, `composer_command`, `composer_widget` などの piece は catalog
に投影され、既存の安全な renderer / command runtime に接続される。
template renderer は任意の React module を実行する仕組みではなく、
`SettingsFieldRendererHost` や composer が持つ allowlisted builtin renderer
へ metadata を渡す。backend 実行も任意 `handler_ref` ではなく、builtin
template から許可済み `pack_block` / registry entry へ接続する。

RumiTemplate の schema、trust、activation、collision、AI input、tool policy、
test contract、renderer security の詳細は [templates.md](templates.md) に集約している。


## 2. アーキテクチャ

```
Tauri App（1プロセス）
├── Rust コア (src-tauri/)
│     ├── Tauri 本体
│     ├── sidecar 管理: rumiai バイナリの起動・終了
│     └── IPC ブリッジ: stdin/stdout ↔ invoke/event/channel
│
├── WebView (src/)
│     ├── シェル: スロットを定義する空の枠
│     ├── Asset ローダー: Asset の動的読み込みと配置
│     ├── Widget レンダラー: Widget JSON を描画する
│     ├── Layout エンジン: layout.json に従い Asset を配置する
│     └── Theme エンジン: theme.yaml に従い見た目を適用する
│
└── rumiai コンパイル済みバイナリ（別プロセス、sidecar）
      └── ecosystem/defaults/
            └── handlers/frontend.py: 通信ブリッジのみ
```

3つの層が存在する。

Rust 層は Tauri のコアであり、2つの通信を橋渡しする。rumiai プロセスとの stdin/stdout と、WebView との Tauri IPC（invoke / event / channel）である。Rust 層自身はメッセージの中身を解釈しない。

WebView 層は描画面である。シェル（空の枠 + スロット定義）、Asset ローダー、Widget レンダラー、Layout エンジン、Theme エンジンで構成される。

rumiai 層はバックエンドである。frontend handler が通信を中継するだけであり、ドメイン処理は行わない。


## 3. 権限

フロントエンドの権限は 12 個のみ。ドメイン権限は一切含まない。

| 権限 | 説明 |
|------|------|
| `frontend.render.mount` | Asset を描画面に載せる |
| `frontend.render.unmount` | 描画面から外す |
| `frontend.render.update` | 描画内容を更新する |
| `frontend.message.send` | バックエンド → 描画面 |
| `frontend.message.receive` | 描画面 → バックエンド |
| `frontend.message.stream` | 連続的にデータを流す |
| `frontend.asset.register` | Asset の登録を受け入れる |
| `frontend.asset.unregister` | Asset の解除 |
| `frontend.asset.list` | 何が登録されているか |
| `frontend.layout.read` | 現在のレイアウト情報を取得 |
| `frontend.layout.write` | レイアウトを変更・保存 |
| `frontend.theme.read` | 現在のテーマ情報を取得 |


## 4. Asset モデル

Asset とはフロントエンドに UI を持ち込む単位である。あらゆるパック、あらゆる tool が Asset を登録できる。フロントエンドは Asset が何者であるかを問わない。

### 4.1 Asset の構成

Asset は以下を持つ。

`asset_id` は ecosystem 内で一意な文字列である。命名規則は `{source}.{category}.{name}`。例えば `defaults.chat.messages` や `my_pack.dashboard.main`。

`entry` はパック内の HTML ファイル（または JS バンドル）の相対パスである。フロントエンドはこのファイルを WebView に読み込ませる。

`handler` はバックエンドでメッセージを処理する Python ファイルの相対パスである。Asset 宛のメッセージがこの handler に転送される。

`permissions` はこの Asset が要求するドメイン権限の配列である。フロントエンド権限（`frontend.*`）とは別に Asset 自身が持つ。

`placement` はこの Asset をどのスロットに載せたいかのヒントである。`slot`（スロット名）と `priority`（数値、大きい方が優先）を持つ。

`category` は UI の分類である。`"chat"`, `"coding"`, `"settings"` 等。自由な文字列。

`tags` は検索・フィルタ用のタグ配列である。

`requires` は他の Asset への依存。指定された Asset が登録されていないとこの Asset は動作しない。

`extensions` はスキーマフリーの拡張フィールドである。対応するかは読む側の責務。

### 4.2 asset.yaml

Asset の定義ファイル。パック内の `assets/` ディレクトリに配置する。

```yaml
asset_id: "my_pack.chat.messages"
name: "Chat Messages"
description: "メッセージ表示エリア"
version: "1.0.0"
source: "my_pack"

entry: "ui/chat/messages.html"
handler: "components/chat_messages.py"

permissions:
  - chat.message.send
  - chat.message.read
  - chat.message.stream
  - ai.completion
  - ai.stream

placement:
  slot: "main"
  priority: 100
  size_hint:
    min_width: 400
    min_height: 300

category: "chat"
tags: ["chat", "messages", "conversation"]

requires: []

on_conflict: "replace"

extensions:
  supports_attachments: true
  supports_voice_input: false
```

### 4.3 Asset の登録

Asset が `frontend.asset.register` を通じて登録されると、フロントエンドは以下を記録する。

```json
{
  "asset_id": "my_pack.chat.messages",
  "entry": "ui/chat/messages.html",
  "source": "my_pack",
  "handler": "components/chat_messages.py",
  "permissions": ["chat.message.send", "chat.message.read", "..."],
  "placement": {
    "slot": "main",
    "priority": 100,
    "size_hint": { "min_width": 400, "min_height": 300 }
  },
  "category": "chat",
  "tags": ["chat", "messages"],
  "requires": [],
  "extensions": {}
}
```

フロントエンドはこの情報を使って WebView にファイルを載せ、layout.json に従って配置する。Asset が何をするかは知らない。

### 4.4 同一 ID での上書き

既に登録済みの asset_id と同じ ID で `asset.register` が呼ばれた場合、後からの登録が前の登録を置き換える。これにより別のパックが任意の Asset を差し替えられる。

### 4.5 tool が Asset を追加する仕組み

tool はツール実行結果の Widget 出力に加えて、Asset を持てる。ツールディレクトリ内に `assets/` を配置し、`*.asset.yaml` と HTML ファイルを置く。ツールのインストール時にその Asset が「未配置」状態で登録され、ユーザーが Layout エディタで配置する。

```
user_data/shared/tools/browser_navigate/
├── tool.json
├── handler.py
└── assets/
    ├── browser_view.asset.yaml
    └── ui/
        └── browser_view.html
```


## 5. スロット

スロットは Asset が表示される位置の枠である。シェル（shell.html）がスロットを定義する。

### 5.1 スロットモデル

```
┌─────────────────────────────────────────────────┐
│  header                                         │
├──────────┬──────────────────────────┬───────────┤
│ sidebar  │         main             │ sidebar   │
│ .left    │                          │ .right    │
│ [stack]  │  [tabs or split]         │ [stack]   │
│          ├──────────────────────────┤           │
│          │     panel.bottom         │           │
│          │     [tabs]               │           │
├──────────┴──────────────────────────┴───────────┤
│  statusbar                                      │
├─────────────────────────────────────────────────┤
│  floating（モーダル/フローティングウィンドウ）      │
└─────────────────────────────────────────────────┘
```

### 5.2 スロットのレンダリングモード

| スロット | モード | 説明 |
|----------|--------|------|
| `header` | single | 横一列に並べる |
| `sidebar.left` | stack | 縦に積む、各 Asset のサイズ変更可能 |
| `sidebar.right` | stack | 縦に積む |
| `main` | tabs | タブ切り替え、分割も可能 |
| `panel.bottom` | tabs | タブ切り替え |
| `statusbar` | single | 横一列に並べる |
| `floating` | float | 必要時にオーバーレイ表示 |

Asset は未知のスロット名を指定できる。シェルがそのスロットを認識しない場合、`floating` にフォールバックする。

### 5.3 配置の競合解決

同じスロットに複数の Asset が配置される場合のルール。placement.priority が高い方が優先（数値が大きい方）。同一 priority なら後から登録された方が勝つ。ユーザーが layout.json で明示的に配置した場合それが最優先。場所を失った Asset は「未配置」状態になる。


## 6. Layout

### 6.1 layout.json

Asset の画面上の配置を定義する。`user_data/layout/` に保存される。

```json
{
  "layout_id": "default",
  "name": "Default Layout",
  "slots": {
    "header": {
      "visible": true,
      "height": 48,
      "assets": ["my_pack.ai.model_selector"]
    },
    "sidebar.left": {
      "visible": true,
      "width": 280,
      "assets": [
        { "id": "my_pack.chat.sidebar", "height": "1fr" }
      ]
    },
    "main": {
      "mode": "tabs",
      "active_tab": "my_pack.chat.messages",
      "assets": ["my_pack.chat.messages"],
      "bottom": {
        "asset": "my_pack.chat.input",
        "height": "auto"
      }
    },
    "panel.bottom": {
      "visible": false,
      "height": 250,
      "assets": []
    },
    "statusbar": {
      "visible": true,
      "height": 28,
      "assets": []
    }
  },
  "unplaced": []
}
```

defaults はこのファイルの形式を定義する。具体的にどの Asset がどこに置かれるかは user_data 側で決まる。

### 6.2 ユーザーによるレイアウト編集

通常モードでは Asset の境界をドラッグしてリサイズ。編集モードでは Asset をスロット間でドラッグ移動、「未配置」パネルから Asset をドラッグして追加、Asset を閉じて未配置に戻す操作が可能。複数のレイアウトプリセットを保存・切り替え可能。

これらの仕組みはシェル（shell.html）に組み込まれる。


## 7. Widget レンダリング

### 7.1 概要

Widget はバックエンドが「このデータをこう表示してほしい」と宣言するための JSON である。tool の handler、prompt、agent、ai_client、あらゆるバックエンドコードが Widget を emit できる。フロントエンドの Widget レンダラーがこの JSON を受け取り、テーマに従って描画する。

Widget は純粋なデータ（JSON）であり、UI ライブラリではない。描画の責任はフロントエンド側にある。

### 7.2 Widget JSON 形式

全ての Widget は以下の基底プロパティを持つ。

```json
{
  "type": "widget_type",
  "id": "optional_id",
  "style_hint": {},
  "meta": {}
}
```

`type` は Widget の種類を示す文字列。`id` は任意の識別子。`style_hint` はテーマへのヒント（フロントエンドが解釈してもしなくてもよい）。`meta` は任意のメタデータ（フロントエンドは無視してよい）。

### 7.3 Widget 型一覧

**表示系（14種）**

| type | 説明 | 主要プロパティ |
|------|------|---------------|
| `text` | テキスト | text |
| `code_block` | コード | language, content, filename, line_start |
| `diff` | 差分 | old_content, new_content, filename |
| `image` | 画像 | src, alt, width, height |
| `screenshot` | スクリーンショット | src, url, title |
| `progress` | 進捗 | label, current, total, state |
| `terminal` | ターミナル出力 | command, output, exit_code |
| `table` | テーブル | headers, rows |
| `chart` | グラフ | chart_type, data, labels |
| `file_tree` | ファイルツリー | tree |
| `markdown` | Markdown | content |
| `audio` | 音声 | src, duration |
| `video` | 動画 | src, duration |
| `map` | 地図 | lat, lng, zoom |

**コントロール系（6種）**

| type | 説明 | 主要プロパティ |
|------|------|---------------|
| `input` | テキスト入力 | placeholder, value, multiline |
| `button` | ボタン | label, action, variant |
| `select` | 選択 | options, value, multiple |
| `toggle` | トグル | label, value |
| `slider` | スライダー | min, max, value, step |
| `checkbox` | チェックボックス | label, checked |

**レイアウト系（6種）**

| type | 説明 | 主要プロパティ |
|------|------|---------------|
| `container` | 汎用コンテナ | children |
| `row` | 横並び | children, gap |
| `column` | 縦並び | children, gap |
| `tabs` | タブ切り替え | tabs |
| `collapsible` | 折りたたみ | label, default_open, children |
| `card` | カード | header, body, footer |

**ストリーミング系（2種）**

| type | 説明 | 主要プロパティ |
|------|------|---------------|
| `stream` | 状態ベースストリーム | states |
| `indicator` | 状態インジケータ | label, state, animation |

**カスタム（1種）**

| type | 説明 | 主要プロパティ |
|------|------|---------------|
| `custom` | 定義外 Widget | custom_type, fallback, data |

### 7.4 Widget レンダラーの責務

シェルに組み込まれた Widget レンダラーは以下を行う。

Widget JSON を受け取り、`type` に応じた描画関数を呼び出す。描画はテーマ（theme.yaml）の `widgets` セクションに定義されたスタイルに従う。未知の `type` はテキストにフォールバックする。`custom` 型は `custom_type` のレンダラーが登録されていれば専用描画を行い、なければ `fallback` Widget を描画する。

Widget レンダラーはシェルの一部であり、全ての Asset が共有する。Asset 内の JS は Widget JSON を Widget レンダラーに渡して描画を委譲できる。

### 7.5 Custom Widget レンダラー

`user_data/widget_renderers/` にカスタムレンダラーを配置できる。

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js
│   └── renderer.yaml
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml にメタデータ（custom_type、バージョン等）を定義し、renderer.js に描画ロジックを実装する。シェルの Widget レンダラーが custom_type を検出した時にこの JS を動的にロードして呼び出す。


## 8. Theme

### 8.1 概要

テーマは全レイヤーの見た目を制御する。色、フォント、アニメーション、Widget の描画スタイルを定義する。`user_data/themes/` に `.theme.yaml` として配置される。テーマの詳細仕様は `docs/theme.md` に定義する。

### 8.2 テーマの適用

シェルの Theme エンジンが `user_data/config.json` の `theme_id` を読み、対応する `theme.yaml` をロードする。テーマの `tokens`（色、フォント、スペーシング等）を CSS 変数として WebView に注入する。Widget レンダラーはこの CSS 変数を参照して描画する。Asset 内の HTML/JS もこの CSS 変数を使用できる。

テーマの切り替えは config.json の `theme_id` を変更するだけで行われ、Asset やバックエンドに影響しない。


## 9. 通信プロトコル

全ての通信は 3 つの層を通過する。

```
WebView ←→ Rust ←→ rumiai
        IPC      stdin/stdout
```

### 9.1 メッセージ形式

rumiai と Rust の間は JSON Lines（1行1メッセージ）で通信する。

```json
{
  "type": "メッセージタイプ",
  "data": {}
}
```

`type` はフロントエンド権限に対応する操作名である。`data` は不透明なペイロードであり、フロントエンドと Rust はドメイン固有の中身を解釈しない。ただし Asset の宛先特定に必要なフィールド（`asset_id` 等）はフロントエンドが読む。

### 9.2 メッセージタイプ

#### asset.register

Asset の登録。rumiai → Rust 方向。

```json
{
  "type": "asset.register",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "entry": "ui/chat/messages.html",
    "source": "my_pack",
    "handler": "components/chat_messages.py",
    "permissions": ["chat.message.send", "chat.message.read"],
    "placement": {
      "slot": "main",
      "priority": 100
    },
    "category": "chat",
    "tags": ["chat", "messages"],
    "requires": [],
    "extensions": {}
  }
}
```

#### asset.unregister

Asset の解除。rumiai → Rust 方向。

```json
{
  "type": "asset.unregister",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### render.mount

Asset の描画開始。rumiai → Rust 方向。

```json
{
  "type": "render.mount",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "slot": "main"
  }
}
```

#### render.unmount

Asset の描画終了。rumiai → Rust 方向。

```json
{
  "type": "render.unmount",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### render.update

描画内容の更新。rumiai → Rust 方向。

```json
{
  "type": "render.update",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "payload": {
      "unread_count": 3
    }
  }
}
```

`payload` の中身は Asset が決める。フロントエンドは asset_id で宛先を特定し、該当する Asset にデータをそのまま渡す。

#### message.send

バックエンド → WebView 方向の単発メッセージ。rumiai → Rust 方向。

```json
{
  "type": "message.send",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "payload": {
      "action": "new_message",
      "message_id": "abc123",
      "content": "応答テキスト",
      "widget": {
        "type": "text",
        "text": "応答テキスト"
      }
    }
  }
}
```

`payload` 内に `widget` フィールドがあれば Widget JSON として Widget レンダラーに渡すことができる。これは Asset 側の JS が判断する。フロントエンドは `payload` の中身を解釈しない。

#### message.receive

WebView → バックエンド方向の単発メッセージ。Rust → rumiai 方向。

```json
{
  "type": "message.receive",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "payload": {
      "action": "send",
      "conversation_id": "conv-1",
      "content": "こんにちは"
    }
  }
}
```

#### message.stream.start

ストリーミングの開始。rumiai → Rust 方向。

```json
{
  "type": "message.stream.start",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### message.stream.data

ストリーミングのデータ片。rumiai → Rust 方向。

```json
{
  "type": "message.stream.data",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1",
    "payload": {
      "chunk": "こん"
    }
  }
}
```

`payload` には Widget JSON を含めることもできる。ストリーミング中の進捗表示等に使う。

```json
{
  "type": "message.stream.data",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1",
    "payload": {
      "widget": {
        "type": "indicator",
        "label": "Thinking...",
        "state": "running",
        "animation": "wave_dots"
      }
    }
  }
}
```

#### message.stream.end

ストリーミングの終了。rumiai → Rust 方向。

```json
{
  "type": "message.stream.end",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### layout.update

レイアウト変更通知。双方向。

```json
{
  "type": "layout.update",
  "data": {
    "layout": { "...layout.json の内容..." }
  }
}
```

#### layout.save

レイアウト保存。WebView → rumiai 方向。

```json
{
  "type": "layout.save",
  "data": {
    "layout_id": "my_layout",
    "layout": { "..." }
  }
}
```

#### theme.change

テーマ切り替え。双方向。

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "dark_default"
  }
}
```

#### event.broadcast

汎用イベントのブロードキャスト。双方向。バックエンドの `emit_event` がこのメッセージになる。

```json
{
  "type": "event.broadcast",
  "data": {
    "event_type": "ui.popup.show",
    "payload": {
      "popup_id": "consent_1",
      "title": "確認",
      "message": "この操作を実行しますか？",
      "buttons": ["OK", "キャンセル"]
    }
  }
}
```

Asset の JS がこのイベントを受信してポップアップを描画し、ユーザーの応答を `event.broadcast` で返送する。特定の Asset 宛ではなく、全 Asset がイベントを受信できる。asset_id を含めれば特定 Asset 宛にもできるが、それはフロントエンドの振り分けではなく Asset 自身のフィルタリングに任せる。


## 10. Rust 層の責務

Rust 層は以下だけを行う。ドメイン知識を一切持たない。

### 10.1 sidecar 管理

Tauri 起動時に rumiai コンパイル済みバイナリを sidecar として起動する。`ecosystem/` ディレクトリのパスを起動引数で渡す。sidecar プロセスの stdin/stdout パイプを保持する。アプリ終了時に sidecar を停止する。

### 10.2 stdin/stdout ブリッジ

rumiai の stdout から JSON Lines を1行ずつ読み取り、`type` フィールドに応じて WebView に転送する。`render.*`、`message.send`、`message.stream.*`、`event.broadcast` は WebView への Tauri Event/Channel に変換する。`asset.*` は WebView の Asset ローダーにイベントとして通知する。`layout.*` は WebView の Layout エンジンに通知する。`theme.*` は WebView の Theme エンジンに通知する。

WebView からの `invoke` を受け取り、`message.receive`、`layout.save`、`event.broadcast` 形式に変換して rumiai の stdin に書き込む。

### 10.3 メッセージの不解釈

Rust は `type` と `data` 内の `asset_id` / `stream_id` / `event_type` だけを見る。`payload` の中身は一切解釈しない。


## 11. WebView 層の責務

### 11.1 シェル

WebView のエントリポイントはシェルである。シェルはスロット（`header`, `sidebar.left`, `main`, `panel.bottom`, `sidebar.right`, `statusbar`, `floating`）を定義する空の枠を描画する。スロットの配置とサイズは layout.json に従う。

シェルは以下を含む。

Asset ローダー: `asset.register` イベントを受け取り、Asset の HTML ファイルを iframe で読み込んでスロットに配置する。

Widget レンダラー: Widget JSON を受け取り、テーマに従って DOM に描画する関数群。Asset の JS がこの関数を呼び出す。

Layout エンジン: layout.json を読み込み、スロットのサイズと Asset の配置を管理する。ドラッグ&ドロップによるレイアウト編集を提供する。

Theme エンジン: theme.yaml の tokens を CSS 変数に変換し、WebView に適用する。

イベントディスパッチャー: `event.broadcast` を受信し、全 Asset（iframe）に postMessage で転送する。

### 11.2 Asset ローダー

`asset.register` を受け取ると、ローダーが Asset の HTML ファイルを読み込む。

iframe 方式（デフォルト）: 各 Asset を iframe で読み込む。Asset 間の隔離性が高い。iframe と親ウィンドウの間は `postMessage` で通信する。

Asset の HTML から親ウィンドウの Widget レンダラーを呼び出す場合は、postMessage で Widget JSON を送信し、親がレンダリング結果を返す。または Asset 自身が Widget レンダラーの JS を読み込んで自分で描画する（シェルが提供する `widget-renderer.js` を Asset が `<script>` で取り込む方式）。

### 11.3 メッセージディスパッチ

Rust から Tauri Event で到着した `message.send` や `message.stream.*` を `data.asset_id` で振り分け、該当する iframe に転送する。

ユーザー操作で iframe 内から `postMessage` が来たら、`message.receive` として Rust に渡す。

### 11.4 イベントディスパッチ

`event.broadcast` は全ての iframe に転送する。各 Asset の JS は `event_type` を見て自分に関係あるイベントだけを処理する。


## 12. ファイル構成

### 12.1 defaults 側

```
ecosystem/defaults/
├── handlers/
│     └── frontend.py          # 通信ブリッジのみ
├── ui/
│     └── shell.html           # 空の枠 + スロット + Widget レンダラー
│                                + Layout エンジン + Theme エンジン
│                                + Asset ローダー + イベントディスパッチャー
└── lib/
      └── rumi_widgets/        # Widget Python ヘルパー（バックエンド用）
            ├── __init__.py
            ├── display.py
            ├── controls.py
            ├── layout.py
            ├── stream.py
            └── custom.py
```

defaults が持つ UI ファイルは shell.html のみ。チャット、エージェント、コーディング等の具体的な UI ファイルは一切持たない。

### 12.2 Tauri 側

```
rumiai-desktop/
├── src/
│     ├── main.tsx             # エントリポイント
│     ├── Shell.tsx            # スロット定義
│     ├── AssetLoader.ts       # Asset の動的読み込み
│     ├── WidgetRenderer.tsx   # Widget JSON → 描画
│     ├── LayoutEngine.ts      # layout.json の管理
│     ├── ThemeEngine.ts       # theme.yaml の適用
│     └── EventDispatcher.ts   # イベント振り分け
├── src-tauri/
│     ├── src/
│     │     ├── lib.rs
│     │     ├── sidecar.rs
│     │     └── bridge.rs
│     ├── binaries/
│     │     └── rumiai-{target}
│     └── capabilities/
│           └── default.json
└── ecosystem/
      └── defaults/
```

### 12.3 user_data 側（Asset の例）

```
user_data/packs/my_chat_pack/
├── pack.json
├── assets/
│     ├── chat_messages.asset.yaml
│     ├── chat_input.asset.yaml
│     └── chat_sidebar.asset.yaml
├── ui/
│     ├── chat/
│     │     ├── messages.html
│     │     ├── input.html
│     │     └── sidebar.html
│     └── shared/
│           └── styles.css
└── components/
      ├── chat_messages.py
      ├── chat_input.py
      └── chat_sidebar.py
```


## 13. 起動フロー

```
1. ユーザーが Tauri アプリを起動

2. Rust
   ├── rumiai バイナリを sidecar として起動
   ├── stdin/stdout パイプを確立
   └── WebView を起動（シェルが空のスロットを描画）

3. rumiai
   ├── ecosystem/defaults を読み込み
   └── defaults の frontend handler を実行（通信確立のみ）

4. rumiai がインストール済みパックを走査
   ├── 各パックの assets/ ディレクトリを走査
   ├── *.asset.yaml を読み込み
   └── asset.register メッセージを stdout に送出

5. stdout → Rust → WebView
   ├── Asset ローダーが asset.register を受信
   ├── layout.json を読み込み（なければ各 Asset の placement から自動生成）
   ├── 各 Asset の HTML ファイルを iframe で読み込み
   └── スロットに Asset を配置

6. 画面が完成
   └── ユーザーの操作でレイアウト変更可能
```


## 14. ユーザー操作フロー

```
1. ユーザーが Asset 内で操作する（例: メッセージを入力して送信）

2. Asset の iframe 内 JS
   └── postMessage({ action: "send", content: "こんにちは" })

3. シェル
   └── postMessage を受信、asset_id を付与
   └── invoke("message_receive", { asset_id: "...", payload: {...} })

4. Rust
   └── stdin に書き込み
       {"type":"message.receive","data":{"asset_id":"...","payload":{...}}}

5. rumiai
   └── frontend handler が受信
   └── asset_id に対応する Asset の handler（components/chat_messages.py）に転送

6. Asset の handler（バックエンド）
   └── ドメイン処理（権限チェック → handler 呼び出し → AI リクエスト等）
   └── 結果を message.send または message.stream で返す

7. stdout → Rust → WebView
   └── Asset の iframe に postMessage で転送
   └── Asset の JS が受け取って UI 更新
   └── Widget JSON があれば Widget レンダラーで描画
```


## 15. 別のパックが参加する方法

### 15.1 手順

パックが `assets/` ディレクトリに `*.asset.yaml` と HTML ファイルを置く。rumiai の承認プロセス（SHA-256 ハッシュ検証 + ユーザー承認）を通過する。以上。defaults 側の変更はゼロ。

### 15.2 必要な権限

```yaml
requires:
  # フロントエンドの枠を使う
  - frontend.asset.register
  - frontend.render.mount
  - frontend.render.update
  - frontend.message.send
  - frontend.message.receive

  # 自分のドメイン権限
  - whatever.domain.permission
```

### 15.3 具体例: 天気ウィジェットパック

```
user_data/packs/weather_widget/
├── pack.json
├── assets/
│     └── weather.asset.yaml
├── ui/
│     └── weather.html
└── components/
      └── weather.py
```

```yaml
# weather.asset.yaml
asset_id: "weather.main"
name: "Weather Widget"
entry: "ui/weather.html"
handler: "components/weather.py"
permissions:
  - net.http.request
placement:
  slot: "sidebar.right"
  priority: 50
category: "utility"
tags: ["weather", "widget"]
```

```python
# components/weather.py
def on_message(context, data):
    city = data["payload"].get("city")
    weather = context["call_handler"]("defaults.net.http_get", {
        "url": f"https://api.weather.com/{city}"
    })
    return {
        "type": "message.send",
        "data": {
            "asset_id": "weather.main",
            "payload": {
                "widget": {
                    "type": "card",
                    "header": {"type": "text", "text": city},
                    "body": {"type": "text", "text": weather["temperature"]}
                }
            }
        }
    }
```

### 15.4 具体例: 既存 Asset の差し替え

```yaml
# better_chat.asset.yaml
asset_id: "my_pack.chat.messages"    # 同じ ID で上書き
entry: "ui/better_chat.html"
handler: "components/better_chat.py"
placement:
  slot: "main"
  priority: 200                       # 元より高い priority
```


## 16. セキュリティ

### 16.1 パックの承認

全てのパックは rumiai の承認プロセスを経る。SHA-256 ハッシュ検証により、承認時のコードと実行時のコードが同一であることが保証される。

### 16.2 権限の分離

フロントエンド権限（`frontend.*`）は Asset の登録・描画・メッセージングのみを許可する。ドメイン操作は Asset の handler が持つドメイン権限で行う。

### 16.3 iframe 隔離

各 Asset の UI は別の iframe で実行される。Asset 間の直接的な DOM アクセスは不可能。通信は全て `postMessage` 経由でシェルが中継する。

### 16.4 data の不透明性

Rust 層とフロントエンドはメッセージの `payload` を解釈しない。中間層がデータを改ざんする余地を最小化する。

### 16.5 イベントのフィルタリング

`event.broadcast` は全 Asset に転送される。機密データをイベントに含める場合は Asset 側の JS で `event_type` や `asset_id` によるフィルタリングを行う。フロントエンド側でのフィルタリングは信頼境界ではないため、バックエンド側で権限チェックを行った上でイベントを発行すること。


## 17. Asset 間通信

Asset 間の直接通信は定義していない。Asset A が Asset B に情報を送りたい場合、2つの方法がある。

第一に、バックエンド経由。Asset A が message.receive でバックエンドに送信し、バックエンドの handler が処理して Asset B に message.send を送る。

第二に、イベント経由。Asset A が event.broadcast でイベントを発行し、Asset B がそのイベントを受信する。この場合もバックエンドを経由する（Asset → Rust → rumiai → emit_event → Rust → 全 Asset）。

いずれの場合もフロントエンド内で Asset 間が直接通信することはなく、必ず rumiai バックエンドを経由する。


## 18. 設計上の制約と注意

### 18.1 UI ファイルの配信

Asset の HTML ファイルを WebView に読み込ませる方法は Tauri のアセットプロトコル（`asset://` または `tauri://`）を使用する。パックディレクトリのパスを Tauri のアセットスコープに追加する必要がある。

### 18.2 レイアウトの柔軟性

スロットの種類と配置はシェル（shell.html）が定義する。シェル自体も別のパックが差し替え可能（`ui/shell.html` を上書きする Asset を登録する方式）。

### 18.3 オフライン動作

全ての UI ファイルはローカルの `ecosystem/` または `user_data/` にあるため、インターネット接続なしで UI が描画される。ドメイン処理がネットワークを必要とするかは Asset 側の責務。

### 18.4 CLI との共存

同じバックエンド（rumiai + handlers）に対して、Tauri フロントエンドと CLI の両方からアクセスできる。CLI の場合は transport が stdio になり、Widget JSON はテキストにフォールバック表示される。フロントエンドの有無はバックエンドの動作に影響しない。
```
