<!-- docs-i18n-links:start -->
[EN](../../frontend.md) | [JP](./frontend.md) | [KR](../ko/frontend.md) | [CN](../zh-cn/frontend.md)
<!-- docs-i18n-links:end -->

# frontend.md — Rumi AI OS フロントエンド設計ドキュメント

## 1. 概要

デフォルトのフロントエンドは、Tauri (Rust + WebView) で構成されるデスクトップ アプリケーションです。

フロントエンドにはドメインの知識がありません。チャットが何なのか、エージェントが何なのか、ファイルが何なのかがわかりません。私が知っていることは次の 4 つだけです。「`There is a frame called a slot,'' ``UI blocks called Assets can be placed in the frame,'' ``Widgets can receive drawing instructions,'' and `「メッセージは送受信される」。

rumiai自体がドメイン知識を持たない汎用カーネルであるのと同じ構造がフロントエンドにも適用されます。すべてのドメイン機能は Asset によって取り込まれます。デフォルトでは、アセットを配置する空のフレーム (シェル) と、アセットを描画して通信するメカニズムのみが提供されます。

特定の UI (チャット画面、エージェント画面、コーディング画面など) はすべて user_data 側のパックによって Asset として登録されます。デフォルト自体には具体的な UI がありません。


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

3つの層があります。

Rust 層は Tauri の中核であり、2 つの間の通信の橋渡しをします。 rumiai プロセスを使用した stdin/stdout および WebView を使用した Tauri IPC (invoke/event/channel)。 Rust 層自体はメッセージの内容を解釈しません。

WebView レイヤーは描画面です。これは、シェル (空のフレーム + スロット定義)、アセット ローダー、ウィジェット レンダラー、レイアウト エンジン、およびテーマ エンジンで構成されます。

rumiai レイヤーはバックエンドです。フロントエンド ハンドラーは通信を中継するだけであり、ドメイン処理は実行しません。


## 3. 権限

フロントエンドには 12 個の権限しかありません。ドメイン権限は含まれません。

|権限 |説明 |
|------|------|
| `frontend.render.mount` |アセットを描画面に配置する |
| `frontend.render.unmount` |描画面から削除 |
| `frontend.render.update` |描画コンテンツを更新 |
| `frontend.message.send` |バックエンド → 描画面 |
| `frontend.message.receive` |描画面 → バックエンド |
| `frontend.message.stream` |データを継続的にストリーミングする |
| `frontend.asset.register` |資産登録を受け入れる |
| `frontend.asset.unregister` |資産のキャンセル |
| `frontend.asset.list` |登録されているもの |
| `frontend.layout.read` |現在のレイアウト情報を取得する |
| `frontend.layout.write` |レイアウトの変更と保存 |
| `frontend.theme.read` |現在のテーマ情報を取得する |


## 4. 資産モデル

アセットは、UI をフロントエンドにもたらすユニットです。どのパックまたはツールでもアセットを登録できます。フロントエンドはアセットが誰であるかを気にしません。

### 4.1 アセット構成

アセットには次のものがあります。

`asset_id` はエコシステム内で一意の文字列です。命名規則は`{source}.{category}.{name}`です。たとえば、`defaults.chat.messages` や `my_pack.dashboard.main` などです。

`entry` は、パック内の HTML ファイル (または JS バンドル) の相対パスです。フロントエンドはこのファイルを WebView にロードします。

`handler` は、バックエンドでメッセージを処理する Python ファイルの相対パスです。アセット宛てのメッセージはこのハンドラーに転送されます。

`permissions` は、このアセットに必要なドメイン権限の配列です。フロントエンド権限 (`frontend.*`) とは別に、それはアセット自体によって保持されます。

`placement` は、このアセットをどのスロットに配置するかに関するヒントです。 `slot`(スロット名)と`priority`(数値、大きい方が優先)があります。

`category`はUIの分類です。 `"chat"`、`"coding"`、`"settings"`などの自由な文字列。

`tags`は検索/フィルタ用のタグ配列です。

`requires` は他のアセットへの依存です。指定されたアセットが登録されていない場合、このアセットは機能しません。

`extensions` はスキーマフリーの拡張フィールドです。応答するのは読者の責任です。

### 4.2 アセット.yaml

アセット定義ファイル。パック内の `assets/` ディレクトリに配置します。

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

### 4.3 アセットの登録

`frontend.asset.register` を通じてアセットが登録されると、フロントエンドは以下を記録します。

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

フロントエンドはこの情報を使用してファイルを WebView にロードし、layout.json に従って配置します。アセットが何をするのか分かりません。

### 4.4 同一IDでの上書き

すでに登録されているasset_idと同じIDで`asset.register`が呼び出された場合、後の登録によって前の登録が置き換えられます。これにより、別のパックでアセットを置き換えることができます。

### 4.5 ツールがアセットを追加する方法

ツールの実行結果のウィジェット出力に加えて、ツールにはアセットを含めることができます。 toolsディレクトリに`assets/`を配置し、`*.asset.yaml`とHTMLファイルを配置します。ツールをインストールすると、アセットは「未配置」の状態で登録され、ユーザーがレイアウトエディターを使用して配置します。

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

スロットは、アセットが表示されるフレームです。シェル (shell.html) はスロットを定義します。

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

### 5.2 スロットレンダリングモード

|スロット |モード |説明 |
|----------|--------|------|
| `header` |シングル |横に並べる |
| `sidebar.left` |スタック |垂直方向にスタックすると、各アセットのサイズを変更できます。
| `sidebar.right` |スタック |垂直に積み重ねる |
| `main` |タブ |タブを切り替えたり分割したりすることもできます |
| `panel.bottom` |タブ |タブ切り替え |
| `statusbar` |シングル |横に並べる |
| `floating` |フロート |必要に応じてオーバーレイ表示 |

アセットは不明なスロット名を指定できます。シェルがスロットを認識しない場合、`floating` に戻ります。

### 5.3 配置の競合の解決

複数のアセットが同じスロットに配置される場合のルール。 place.priority が高いほう（数字が大きいほう）が優先されます。優先順位が同じ場合は、後から登録した方が優先されます。ユーザーがこれを明示的にlayout.jsonに配置した場合、その優先度が最も高くなります。場所を失ったアセットは「配置されていない」状態になります。


## 6. レイアウト

### 6.1 レイアウト.json

アセットの画面上の配置を定義します。 `user_data/layout/`に保存されました。

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

デフォルトはこのファイルの形式を定義します。具体的には、どのAssetをどこに配置するかはuser_data側で決定されます。

### 6.2 ユーザーによるレイアウト編集

通常モードでは、アセットの境界線をドラッグしてサイズを変更します。編集モードでは、スロット間でアセットをドラッグして移動したり、「未配置」パネルからドラッグしてアセットを追加したり、アセットを閉じて未配置に戻すことができます。複数のレイアウト プリセットを保存して切り替えます。

これらのメカニズムはシェル (shell.html) に組み込まれています。


## 7. ウィジェットのレンダリング

### 7.1 概要

ウィジェットは、バックエンドがこのデータをこのように表示することを宣言するために使用する JSON です。ツールのハンドラー、プロンプト、エージェント、ai_client、および任意のバックエンド コードはウィジェットを発行できます。フロントエンド ウィジェット レンダラーはこの JSON を受け取り、テーマに従って描画します。

ウィジェットは純粋なデータ (JSON) であり、UI ライブラリではありません。レンダリングの責任はフロントエンドにあります。

### 7.2 ウィジェットの JSON 形式

すべてのウィジェットには次の基本プロパティがあります。

```json
{
  "type": "widget_type",
  "id": "optional_id",
  "style_hint": {},
  "meta": {}
}
```

`type`はウィジェットの種類を示す文字列です。 `id`は任意の識別子です。 `style_hint` はテーマへのヒントです (フロントエンドによって解釈される場合と解釈されない場合があります)。 `meta` はオプションのメタデータです (フロントエンドでは無視できます)。

### 7.3 ウィジェットの種類一覧

**表示タイプ(14種類)**

|タイプ |説明 |主な特性 |
|------|------|---------------|
| `text` |テキスト |テキスト |
| `code_block` |コード |言語、コンテンツ、ファイル名、line_start |
| `diff` |違い |古いコンテンツ、新しいコンテンツ、ファイル名 |
| `image` |画像 |ソース、alt、幅、高さ |
| `screenshot` |スクリーンショット |ソース、URL、タイトル |
| `progress` |進捗状況 |ラベル、現在、合計、状態 |
| `terminal` |端子出力 |コマンド、出力、終了コード |
| `table` |テーブル |ヘッダー、行 |
| `chart` |グラフ |グラフの種類、データ、ラベル |
| `file_tree` |ファイルツリー |木 |
| `markdown` |マークダウン |コンテンツ |
| `audio` |オーディオ |ソース、期間 |
| `video` |ビデオ |ソース、期間 |
| `map` |地図 |緯度、経度、ズーム |

**制御タイプ(6種類)**

|タイプ |説明 |主な特性 |
|------|------|---------------|
| `input` |テキスト入力 |プレースホルダー、値、複数行 |
| `button` |ボタン |ラベル、アクション、バリアント |
| `select` |選択 |オプション、値、複数 |
| `toggle` |切り替え |ラベル、値 |
| `slider` |スライダー |最小、最大、値、ステップ |
| `checkbox` |チェックボックス |ラベル、チェック済み |

**レイアウトタイプ(6種類)**

|タイプ |説明 |主な特性 |
|------|------|---------------|
| `container` |汎用コンテナ |子供たち |
| `row` |並んで |子供、ギャップ | 写真
| `column` |垂直 |子供、ギャップ | 写真
| `tabs` |タブ切り替え |タブ |
| `collapsible` |折りたたむ |ラベル、default_open、子 |
| `card` |カード |ヘッダー、本文、フッター |

**ストリーミングタイプ(2種類)**

|タイプ |説明 |主な特性 |
|------|------|---------------|
| `stream` |状態ベースのストリーム |状態 |
| `indicator` |状態インジケータ |ラベル、状態、アニメーション |

**カスタム(1種類)**

|タイプ |説明 |主な特性 |
|------|------|---------------|
| `custom` |未定義のウィジェット |カスタムタイプ、フォールバック、データ |

### 7.4 ウィジェット レンダラーの責任

シェルの組み込みウィジェット レンダラー:

ウィジェットは JSON を受け取り、`type`に従って描画関数を呼び出します。描画は、テーマ (theme.yaml) の `widgets` セクションで定義されたスタイルに従います。不明な `type` はテキストに戻ります。 `custom` タイプは、`custom_type` レンダラーが登録されている場合は専用の描画を実行し、登録されていない場合は `fallback` ウィジェットを描画します。

ウィジェット レンダラーはシェルの一部であり、すべてのアセットによって共有されます。 Asset の JS は、Widget JSON を Widget レンダラーに渡すことで描画を委任できます。

### 7.5 カスタム ウィジェット レンダラー

カスタム レンダラーは `user_data/widget_renderers/` に配置できます。

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js
│   └── renderer.yaml
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml でメタデータ (custom_type、version など) を定義し、renderer.js でレンダリング ロジックを実装します。シェルのウィジェット レンダラがcustom_typeを検出すると、この JS を動的にロードして呼び出します。


## 8. テーマ

### 8.1 概要

テーマはすべてのレイヤーの外観を制御します。ウィジェットの色、フォント、アニメーション、描画スタイルを定義します。 `user_data/themes/` に `.theme.yaml` として配置されます。テーマの詳細な仕様は`docs/theme.md`で定義されています。

### 8.2 テーマの適用

シェルのテーマ エンジンは、`user_data/config.json` の `theme_id` を読み取り、対応する `theme.yaml` をロードします。テーマの `tokens` (色、フォント、間隔など) を CSS 変数として WebView に挿入します。ウィジェットレンダラーはこのCSS変数を参照して描画します。 Asset 内の HTML/JS でもこの CSS 変数を使用できます。

テーマの切り替えは、config.json の `theme_id` を変更するだけで行われ、アセットやバックエンドには影響しません。


## 9. 通信プロトコル

すべての通信は 3 つの層を通過します。

```
WebView ←→ Rust ←→ rumiai
        IPC      stdin/stdout
```

### 9.1 メッセージフォーマット

rumiai と Rust は JSON Lines (1 行に 1 つのメッセージ) を使用して通信します。

```json
{
  "type": "メッセージタイプ",
  "data": {}
}
```

`type`はフロントエンド権限に対応するオペレーション名です。 `data` は不透明なペイロードであり、フロントエンドと Rust はそのドメイン固有の内容を解釈しません。ただし、アセットの宛先を識別するために必要なフィールド (`asset_id` など) はフロントエンドによって読み取られます。

### 9.2 メッセージの種類

#### 資産.登録

資産登録。るみあい→錆び方面。

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

#### アセット.登録解除

資産のリリース。るみあい→錆び方面。

```json
{
  "type": "asset.unregister",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### render.mount

アセットの描画を開始します。るみあい→錆び方面。

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

アセットの描画が完了しました。るみあい→錆び方面。

```json
{
  "type": "render.unmount",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### render.update

描画内容を更新します。るみあい→錆び方面。

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

`payload`の内容はAssetによって決まります。フロントエンドはasset_idで宛先を特定し、対応するAssetにデータをそのまま渡します。

#### メッセージ.送信

バックエンド → WebView 方向の単一メッセージ。るみあい→錆び方面。

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

`payload` に `widget` フィールドがある場合、それを Widget JSON として Widget レンダラーに渡すことができます。これはアセット側の JS によって決定されます。フロントエンドは`payload`の内容を解釈しません。

#### メッセージ.受信

WebView → バックエンドへの単一メッセージ。サビ→るみあい方向。

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

ストリーミングを開始します。るみあい→錆び方面。

```json
{
  "type": "message.stream.start",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### メッセージ.ストリーム.データ

ストリーミング データ部分。るみあい→錆び方面。

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

`payload` にはウィジェット JSON を含めることもできます。ストリーミング中などに進行状況を表示するために使用されます。

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

#### メッセージ.ストリーム.終了

ストリーミングの終了。るみあい→錆び方面。

```json
{
  "type": "message.stream.end",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### レイアウト.更新

レイアウト変更のお知らせです。双方向。

```json
{
  "type": "layout.update",
  "data": {
    "layout": { "...layout.json の内容..." }
  }
}
```

#### レイアウト.保存

レイアウトを保存します。 WebView→rumiai方向。

```json
{
  "type": "layout.save",
  "data": {
    "layout_id": "my_layout",
    "layout": { "..." }
  }
}
```

#### テーマ.変更

テーマの切り替え。双方向。

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "dark_default"
  }
}
```

#### イベント.ブロードキャスト

汎用イベントのブロードキャスト。双方向。バックエンドの`emit_event`がこのメッセージになります。

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

アセットの JS はこのイベントを受信し、ポップアップを描画し、`event.broadcast` でユーザーの応答を返します。特定のアセットだけでなく、すべてのアセットがイベントを受信できます。 asset_id を含めると、特定のアセットにアドレス指定できますが、それはフロントエンドの並べ替えではなく、アセット自体のフィルタリングに委ねられます。


## 10. Rust Layer の責任

Rust 層は次のことのみを行います。 ドメインの知識はありません。

### 10.1 サイドカー管理

Tauri の起動時に、rumiai コンパイル済みバイナリをサイドカーとして起動します。 `ecosystem/` 起動引数としてディレクトリパスを渡します。サイドカー プロセスの stdin/stdout パイプを保持します。アプリを閉じるときにサイドカーを停止します。

### 10.2 stdin/stdout ブリッジ

rumiai の stdout から JSON Lines を 1 行ずつ読み取り、`type` フィールドに従って WebView に転送します。 `render.*`、`message.send`、`message.stream.*`、`event.broadcast`は、Tauri イベント/チャネルから WebView に変換されます。 `asset.*`はWebViewのアセットローダーにイベントとして通知します。 `layout.*` は、WebView のレイアウト エンジンに通知します。 `theme.*` は、WebView のテーマ エンジンに通知します。

WebViewから`invoke`を受け取り、`message.receive`、`layout.save`、`event.broadcast`形式に変換してrumiaiのstdinに書き込みます。

### 10.3 メッセージの誤解

Rust は、`type` および `data` 内の `asset_id` / `stream_id` / `event_type` のみを認識します。 `payload`の内容はいかなる形でも解釈されないものとします。


## 11. WebView 層の責任

### 11.1 シェル

WebView のエントリ ポイントはシェルです。シェルは、スロットを定義する空のフレームを描画します (`header`、`sidebar.left`、`main`、`panel.bottom`、`sidebar.right`、`statusbar`、`floating`)。スロットの配置とサイズはlayout.jsonに従います。

シェルには次のものが含まれます。

アセット ローダー: `asset.register` イベントを受信し、iframe を使用してアセットの HTML ファイルをロードし、スロットに配置します。

ウィジェット レンダラー: ウィジェット JSON を受け入れ、テーマに従ってそれを DOM に描画する一連の関数。アセットの JS はこの関数を呼び出します。

レイアウト エンジン:layout.json を読み取り、スロット サイズとアセットの配置を管理します。ドラッグアンドドロップによるレイアウト編集が可能です。

テーマ エンジン:theme.yaml 内のトークンを CSS 変数に変換し、WebView に適用します。

イベント ディスパッチャー: `event.broadcast` を受信し、postMessage を使用してそれをすべてのアセット (iframe) に転送します。

### 11.2 アセットローダー

`asset.register` を受信すると、ローダーはアセットの HTML ファイルをロードします。

iframe メソッド (デフォルト): iframe を使用して各アセットをロードします。資産間の分離性は高くなります。 `postMessage` は、iframe と親ウィンドウ間の通信に使用されます。

Asset の HTML から親ウィンドウの Widget レンダラーを呼び出す場合、postMessage で Widget JSON を送信すると、親はレンダリング結果を返します。もしくはAsset自体がWidgetレンダラーのJSを読み込んで描画します(`<script>`でシェルが提供する`widget-renderer.js`をAssetがインポートする方法)。

### 11.3 メッセージのディスパッチ

RustからTauri Event経由で届いた`message.send`と`message.stream.*`を`data.asset_id`でソートし、対応するiframeに転送します。

ユーザーの操作によりiframe内から`postMessage`が来た場合、それを`message.receive`としてRustに渡します。

### 11.4 イベントのディスパッチ

`event.broadcast` はすべての iframe に転送します。各アセットの JS は `event_type` を参照し、それに関連するイベントのみを処理します。


## 12. ファイル構造

### 12.1 デフォルト側

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

デフォルトにある唯一の UI ファイルは shell.html です。チャット、エージェント、コーディングなどのための特定の UI ファイルはありません。

### 12.2 おうし座側

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

### 12.3 user_data 側 (アセットの例)

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


## 14. ユーザーの操作フロー

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

このパックは、`*.asset.yaml` と HTML ファイルを `assets/` ディレクトリに配置します。 rumiai の承認プロセス (SHA-256 ハッシュ検証 + ユーザー承認) に合格します。それだけです。デフォルト側には変更はありません。

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

### 15.3 具体例: 天気ウィジェット パック

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

### 15.4 具体例: 既存の資産の置き換え

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

すべてのパックは rumiai の承認プロセスを経ます。 SHA-256 ハッシュ検証により、認証時のコードと実行時のコードが同じであることが保証されます。

### 16.2 特権の分離

フロントエンド権限 (`frontend.*`) では、アセットの登録、描画、およびメッセージングのみが許可されます。ドメイン操作は、アセット ハンドラーが保持するドメイン権限を使用して実行されます。

### 16.3 iframe の分離

各アセットの UI は個別の iframe で実行されます。アセット間で直接 DOM アクセスすることはできません。すべての通信は、`postMessage` を介してシェルによって中継されます。

### 16.4 データの不透明度

Rust 層とフロントエンドはメッセージ内の `payload` を解釈しません。中間層がデータを改ざんする範囲を最小限に抑えます。

### 16.5 イベントのフィルタリング

`event.broadcast`がすべてのアセットに転送されます。イベントに機密データが含まれる場合は、Asset側のJSで`event_type`、`asset_id`を使用してフィルタリングを行います。フロントエンド側のフィルタリングは信頼境界ではないため、イベント発行前にバックエンド側で権限チェックを行ってください。


## 17. アセット間の通信

アセット間の直接通信は定義されていません。アセット A がアセット B に情報を送信したい場合、それを行うには 2 つの方法があります。

まず、バックエンド経由です。アセット A が message.receive をバックエンドに送信し、バックエンド ハンドラーがそれを処理して、message.send をアセット B に送信します。

2 つ目は、イベント経由です。アセット A は、event.broadcast でイベントを発行し、アセット B がイベントを受信します。この場合、バックエンドも経由します (Asset → Rust → rumiai → Emit_event → Rust → All Assets)。

どちらの場合も、フロントエンド内のアセット間の直接通信はなく、常に rumiai バックエンドを経由します。


## 18. 設計上の制約と注意事項

### 18.1 UI ファイルの配信

アセットの HTML ファイルを WebView に読み込む方法は、Tauri のアセット プロトコル (`asset://` または `tauri://`) を使用することです。パック ディレクトリ パスを Tauri のアセット スコープに追加する必要があります。

### 18.2 レイアウトの柔軟性

スロットの種類と配置はシェル (shell.html) によって定義されます。シェル自体を別のパックに置き換えることもできます (`ui/shell.html` を上書きするアセットを登録することで)。

### 18.3 オフライン操作

すべての UI ファイルはローカルの `ecosystem/` または `user_data/` に配置されているため、UI はインターネット接続なしで描画されます。ドメイン処理にネットワークが必要かどうかを判断するのは資産の責任です。

### 18.4 CLI との共存

同じバックエンド (rumiai + ハンドラー) は、Tauri フロントエンドと CLI の両方からアクセスできます。 CLI の場合、トランスポートは stdio になり、ウィジェット JSON はテキストに戻ります。フロントエンドの有無はバックエンドの動作には影響しません。
