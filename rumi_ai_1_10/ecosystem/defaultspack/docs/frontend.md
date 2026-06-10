<!-- docs-i18n-links:start -->
[EN](./frontend.md) | [JP](./i18n/ja/frontend.md) | [KR](./i18n/ko/frontend.md) | [CN](./i18n/zh-cn/frontend.md)
<!-- docs-i18n-links:end -->

# frontend.md — Rumi AI OS front end design document

## 1. Overview

The front end of defaults is a desktop application composed of Tauri (Rust + WebView).

The front end has no domain knowledge. I don't know what a chat is, I don't know what an agent is, I don't know what a file is. There are only four things I know about: ``There is a frame called a slot,'' ``UI blocks called Assets can be placed in the frame,'' ``Widgets can receive drawing instructions,'' and ``Messages are sent back and forth.''

The same structure that rumiai itself is a general-purpose kernel with no domain knowledge is applied to the front end. All domain functionality is brought in by Asset. Defaults only provides an empty frame (shell) to place the Asset and a mechanism to draw and communicate with the Asset.

All specific UI (chat screen, agent screen, coding screen, etc.) are registered as Assets by the pack on the user_data side. Defaults themselves do not have any concrete UI.

The current defaultspack implementation adds to this generalization `PlacementManifest`
We are gradually introducing base placement candidates and pin persistence. The first application is
Around right sidebar / settings / composer, Tool Manager, Tool Filter Log,
Deploy surface-aware YOLO toggle, Model Manager, Webhook Endpoints, etc.
I can.


## 2. Architecture

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

There are three layers.

The Rust layer is the core of Tauri and bridges the communication between the two. stdin/stdout with the rumiai process and Tauri IPC (invoke/event/channel) with WebView. The Rust layer itself does not interpret the contents of messages.

The WebView layer is the drawing surface. It consists of a shell (empty frame + slot definition), Asset loader, Widget renderer, Layout engine, and Theme engine.

The rumiai layer is the backend. The frontend handler only relays communication and does not perform domain processing.


## 3. Permissions

Frontend has only 12 permissions. Does not include any domain authority.

| Permissions | Description |
|------|------|
| `frontend.render.mount` | Put Asset on the drawing surface |
| `frontend.render.unmount` | Remove from drawing surface |
| `frontend.render.update` | Update drawing content |
| `frontend.message.send` | Backend → drawing surface |
| `frontend.message.receive` | Drawing surface → backend |
| `frontend.message.stream` | Stream data continuously |
| `frontend.asset.register` | Accept Asset Registration |
| `frontend.asset.unregister` | Cancellation of Asset |
| `frontend.asset.list` | What is registered |
| `frontend.layout.read` | Get current layout information |
| `frontend.layout.write` | Change and save layout |
| `frontend.theme.read` | Get current theme information |


## 4. Asset model

Asset is a unit that brings UI to the front end. Any pack or tool can register Assets. The front end does not care who the Asset is.

### 4.1 Asset configuration

Asset has the following:

`asset_id` is a unique string within the ecosystem. The naming convention is `{source}.{category}.{name}`. For example `defaults.chat.messages` and `my_pack.dashboard.main`.

`entry` is the relative path of the HTML file (or JS bundle) within the pack. The front end loads this file into WebView.

`handler` is the relative path of the Python file that processes messages in the backend. Messages addressed to Asset will be forwarded to this handler.

`permissions` is an array of domain authorities required by this Asset. Apart from front-end authority (`frontend.*`), it is held by the Asset itself.

`placement` is a hint as to which slot you want to place this Asset. It has `slot` (slot name) and `priority` (numeric value, larger one takes priority).

`category` is a classification of UI. `"chat"`, `"coding"`, `"settings"` etc. free string.

`tags` is a tag array for search/filter.

`requires` is dependence on other Assets. This Asset will not work if the specified Asset is not registered.

`extensions` is a schema-free extension field. It is the responsibility of the reader to respond.

### 4.2 asset.yaml

Asset definition file. Place it in the `assets/` directory within the pack.

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

### 4.3 Asset registration

When an Asset is registered through `frontend.asset.register`, the front end records the following:

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

The front end uses this information to load files onto the WebView and arrange them according to layout.json. I don't know what Asset does.

### 4.4 Overwriting with the same ID

If `asset.register` is called with the same ID as an already registered asset_id, the later registration replaces the previous one. This allows another pack to replace any Asset.

### 4.5 How tool adds Asset

In addition to the Widget output of tool execution results, a tool can have Assets. Place `assets/` in the tools directory, and place `*.asset.yaml` and the HTML file. When the tool is installed, the Asset is registered in the "unplaced" state, and the user places it using the Layout editor.

```
user_data/shared/tools/browser_navigate/
├── tool.json
├── handler.py
└── assets/
    ├── browser_view.asset.yaml
    └── ui/
        └── browser_view.html
```


## 5. Slot

A slot is a frame in which an Asset is displayed. The shell (shell.html) defines the slot.

### 5.1 Slot Model

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

### 5.2 Slot rendering modes

| Slot | Mode | Description |
|----------|--------|------|
| `header` | single | line up horizontally |
| `sidebar.left` | stack | Stack vertically, each Asset can be resized |
| `sidebar.right` | stack | stack vertically |
| `main` | tabs | You can also switch and split tabs |
| `panel.bottom` | tabs | Tab switching |
| `statusbar` | single | line up horizontally |
| `floating` | float | Overlay display when necessary |

Asset can specify an unknown slot name. If the shell does not recognize the slot, it falls back to `floating`.

### 5.3 Placement conflict resolution

Rules when multiple Assets are placed in the same slot. The one with higher placement.priority has priority (the one with the larger number). If the priority is the same, the one registered later wins. If the user explicitly places it in layout.json, it has the highest priority. Assets that have lost their location become "unplaced".


## 6. Layout

### 6.1 layout.json

Define the on-screen placement of Assets. Saved in `user_data/layout/`.

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

defaults defines the format of this file. Specifically, which Asset is placed where is determined by the user_data side.

### 6.2 Layout editing by user

In normal mode, drag the border of the Asset to resize it. In edit mode, you can drag and move Assets between slots, add Assets by dragging them from the "Unplaced" panel, and close Assets to return them to unplaced. Save and switch between multiple layout presets.

These mechanisms are built into the shell (shell.html).


## 7. Widget rendering

### 7.1 Overview

Widget is JSON that the backend uses to declare that it wants this data to be displayed like this. Tool's handler, prompt, agent, ai_client, and any backend code can emit Widgets. The front-end Widget renderer receives this JSON and draws it according to the theme.

Widgets are pure data (JSON) and are not UI libraries. The responsibility for rendering lies with the front end.

### 7.2 Widget JSON format

All widgets have the following base properties.

```json
{
  "type": "widget_type",
  "id": "optional_id",
  "style_hint": {},
  "meta": {}
}
```

`type` is a string indicating the type of widget. `id` is an arbitrary identifier. `style_hint` is a hint to the theme (which may or may not be interpreted by the front end). `meta` is optional metadata (can be ignored by the front end).

### 7.3 Widget type list

**Display type (14 types)**

| type | Description | Main properties |
|------|------|---------------|
| `text` | text | text |
| `code_block` | code | language, content, filename, line_start |
| `diff` | Difference | old_content, new_content, filename |
| `image` | Image | src, alt, width, height |
| `screenshot` | Screenshot | src, url, title |
| `progress` | Progress | label, current, total, state |
| `terminal` | Terminal output | command, output, exit_code |
| `table` | table | headers, rows |
| `chart` | Graph | chart_type, data, labels |
| `file_tree` | File tree | tree |
| `markdown` | Markdown | content |
| `audio` | Audio | src, duration |
| `video` | Video | src, duration |
| `map` | Map | lat, lng, zoom |

**Control type (6 types)**

| type | Description | Main properties |
|------|------|---------------|
| `input` | Text input | placeholder, value, multiline |
| `button` | Button | label, action, variant |
| `select` | Selection | options, value, multiple |
| `toggle` | Toggle | label, value |
| `slider` | Slider | min, max, value, step |
| `checkbox` | Checkbox | label, checked |

**Layout type (6 types)**

| type | Description | Main properties |
|------|------|---------------|
| `container` | Generic container | children |
| `row` | Side by side | children, gap |
| `column` | Vertical | children, gap |
| `tabs` | Tab switching | tabs |
| `collapsible` | Collapse | label, default_open, children |
| `card` | Card | header, body, footer |

**Streaming type (2 types)**

| type | Description | Main properties |
|------|------|---------------|
| `stream` | state-based stream | states |
| `indicator` | State indicator | label, state, animation |

**Custom (1 type)**

| type | Description | Main properties |
|------|------|---------------|
| `custom` | Undefined Widget | custom_type, fallback, data |

### 7.4 Widget Renderer Responsibilities

The shell's built-in Widget renderer:

Widget Receives JSON and calls the drawing function according to `type`. Drawing follows the style defined in the `widgets` section of the theme (theme.yaml). Unknown `type` falls back to text. The `custom` type performs dedicated drawing if the `custom_type` renderer is registered, and if not, draws the `fallback` Widget.

The Widget renderer is part of the shell and is shared by all Assets. JS in Asset can delegate drawing by passing Widget JSON to Widget renderer.

### 7.5 Custom Widget Renderer

Custom renderers can be placed in `user_data/widget_renderers/`.

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js
│   └── renderer.yaml
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

Define metadata (custom_type, version, etc.) in renderer.yaml and implement rendering logic in renderer.js. When the shell's Widget renderer detects custom_type, it dynamically loads and calls this JS.


## 8. Theme

### 8.1 Overview

Themes control the appearance of all layers. Define colors, fonts, animations, and drawing styles for widgets. Placed in `user_data/themes/` as `.theme.yaml`. Detailed specifications of the theme are defined in `docs/theme.md`.

### 8.2 Applying a theme

The shell's Theme engine reads `theme_id` in `user_data/config.json` and loads the corresponding `theme.yaml`. Inject the theme's `tokens` (colors, fonts, spacing, etc.) into WebView as CSS variables. Widget renderer refers to this CSS variable and draws. HTML/JS in Asset can also use this CSS variable.

Switching the theme is done by simply changing `theme_id` in config.json and does not affect Assets or the backend.


## 9. Communication protocol

All communications pass through three layers.

```
WebView ←→ Rust ←→ rumiai
        IPC      stdin/stdout
```

### 9.1 Message format

rumiai and Rust communicate using JSON Lines (one message per line).

```json
{
  "type": "メッセージタイプ",
  "data": {}
}
```

`type` is the operation name corresponding to the front-end authority. `data` is an opaque payload, and the front end and Rust do not interpret its domain-specific contents. However, the fields required to identify the Asset destination (such as `asset_id`) are read by the front end.

### 9.2 Message types

#### asset.register

Asset registration. rumiai → Rust direction.

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

Release of Asset. rumiai → Rust direction.

```json
{
  "type": "asset.unregister",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### render.mount

Start drawing Asset. rumiai → Rust direction.

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

Asset drawing finished. rumiai → Rust direction.

```json
{
  "type": "render.unmount",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### render.update

Update drawing content. rumiai → Rust direction.

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

The contents of `payload` are determined by Asset. The front end identifies the destination using asset_id and passes the data as is to the corresponding Asset.

#### message.send

Single message in the backend → WebView direction. rumiai → Rust direction.

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

If there is a `widget` field in `payload`, it can be passed to the Widget renderer as Widget JSON. This is determined by the JS on the Asset side. The front end does not interpret the contents of `payload`.

#### message.receive

WebView → Single message towards backend. Rust → rumiai direction.

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

Start streaming. rumiai → Rust direction.

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

Streaming data piece. rumiai → Rust direction.

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

`payload` can also contain Widget JSON. Used to display progress during streaming, etc.

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

End of streaming. rumiai → Rust direction.

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

Layout change notification. Bidirectional.

```json
{
  "type": "layout.update",
  "data": {
    "layout": { "...layout.json の内容..." }
  }
}
```

#### layout.save

Save layout. WebView → rumiai direction.

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

Theme switching. Bidirectional.

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "dark_default"
  }
}
```

#### event.broadcast

Broadcasting of general purpose events. Bidirectional. `emit_event` in the backend becomes this message.

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

Asset's JS receives this event, draws the popup, and sends back the user's response in `event.broadcast`. All Assets can receive events, not just a specific Asset. If you include asset_id, you can address it to a specific Asset, but that is left to the filtering of the Asset itself, not to the front end's sorting.


## 10. Rust Layer Responsibilities

The Rust layer only does the following: Does not have any domain knowledge.

### 10.1 sidecar management

Start the rumiai compiled binary as sidecar when Tauri starts. `ecosystem/` Pass the directory path as a startup argument. Holds the stdin/stdout pipes for sidecar processes. Stop sidecar when the app closes.

### 10.2 stdin/stdout bridge

Read JSON Lines line by line from rumiai's stdout and transfer it to WebView according to the `type` field. `render.*`, `message.send`, `message.stream.*`, `event.broadcast` are converted to Tauri Event/Channel to WebView. `asset.*` notifies the Asset loader of WebView as an event. `layout.*` informs the WebView's layout engine. `theme.*` informs the WebView's Theme engine.

Receive `invoke` from WebView, convert it to `message.receive`, `layout.save`, `event.broadcast` format and write it to stdin of rumiai.

### 10.3 Misinterpretation of messages

Rust only sees `asset_id` / `stream_id` / `event_type` within `type` and `data`. The contents of `payload` shall not be interpreted in any way.


## 11. Responsibilities of WebView layer

### 11.1 Shell

WebView's entry point is the shell. The shell draws empty frames that define the slots (`header`, `sidebar.left`, `main`, `panel.bottom`, `sidebar.right`, `statusbar`, `floating`). Slot placement and size follow layout.json.

The shell contains:

Asset loader: Receives the `asset.register` event, loads the Asset's HTML file with an iframe, and places it in the slot.

Widget renderer: A set of functions that accepts Widget JSON and draws it to the DOM according to a theme. Asset's JS calls this function.

Layout engine: reads layout.json and manages slot size and Asset placement. Provides drag-and-drop layout editing.

Theme engine: Convert tokens in theme.yaml to CSS variables and apply them to WebView.

Event dispatcher: Receives `event.broadcast` and forwards it to all Assets (iframes) using postMessage.

### 11.2 Asset Loader

When `asset.register` is received, the loader loads the Asset's HTML file.

iframe method (default): Load each Asset with an iframe. There is high isolation between assets. `postMessage` is used to communicate between the iframe and the parent window.

When calling the parent window's Widget renderer from Asset's HTML, send Widget JSON with postMessage, and the parent returns the rendering result. Or Asset itself loads the JS of the Widget renderer and draws it itself (a method in which Asset imports `widget-renderer.js` provided by the shell with `<script>`).

### 11.3 Message Dispatch

`message.send` and `message.stream.*` that arrived from Rust via Tauri Event are sorted by `data.asset_id` and transferred to the corresponding iframe.

When `postMessage` comes from within an iframe due to user operation, pass it to Rust as `message.receive`.

### 11.4 Event dispatch

`event.broadcast` forwards to all iframes. The JS of each Asset looks at `event_type` and processes only the events that are relevant to it.


## 12. File structure

### 12.1 defaults side

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

The only UI file that defaults has is shell.html. It does not have any specific UI files for chat, agents, coding, etc.

### 12.2 Tauri side

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

### 12.3 user_data side (Asset example)

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


## 13. Startup flow

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


## 14. User operation flow

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


## 15. How another pack joins

### 15.1 Procedure

The pack puts `*.asset.yaml` and HTML files in the `assets/` directory. Pass rumiai's approval process (SHA-256 hash verification + user approval). That's all. There are zero changes on the defaults side.

### 15.2 Required privileges

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

### 15.3 Specific example: Weather widget pack

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

### 15.4 Specific example: Replacing an existing Asset

```yaml
# better_chat.asset.yaml
asset_id: "my_pack.chat.messages"    # 同じ ID で上書き
entry: "ui/better_chat.html"
handler: "components/better_chat.py"
placement:
  slot: "main"
  priority: 200                       # 元より高い priority
```


## 16. Security

### 16.1 Pack Approval

All packs go through rumiai's approval process. SHA-256 hash verification ensures that the code at authorization and the code at runtime are the same.

### 16.2 Separation of Privileges

Front-end authority (`frontend.*`) only allows Asset registration, drawing, and messaging. Domain operations are performed using the domain authority held by the Asset handler.

### 16.3 iframe isolation

Each Asset's UI runs in a separate iframe. Direct DOM access between Assets is not possible. All communications are relayed by the shell via `postMessage`.

### 16.4 data opacity

The Rust layer and front end do not interpret `payload` in messages. Minimize the scope for middle tiers to tamper with data.

### 16.5 Filtering events

`event.broadcast` is transferred to all Assets. If confidential data is included in the event, perform filtering using `event_type` and `asset_id` in JS on the Asset side. Filtering on the front-end side is not a trust boundary, so perform an authority check on the back-end side before issuing an event.


## 17. Communication between Assets

Direct communication between Assets is not defined. If Asset A wants to send information to Asset B, there are two ways to do it.

Firstly, via the backend. Asset A sends message.receive to the backend, the backend handler processes it and sends message.send to Asset B.

Second, via events. Asset A emits an event on event.broadcast and Asset B receives the event. In this case, it also goes through the backend (Asset → Rust → rumiai → emit_event → Rust → All Assets).

In either case, there is no direct communication between Assets within the front end, but always via the rumiai back end.


## 18. Design constraints and precautions

### 18.1 Delivering UI files

The method to read Asset's HTML file into WebView is to use Tauri's asset protocol (`asset://` or `tauri://`). You need to add the pack directory path to Tauri's asset scope.

### 18.2 Layout flexibility

The type and arrangement of slots are defined by the shell (shell.html). The shell itself can also be replaced with another pack (by registering an Asset that overwrites `ui/shell.html`).

### 18.3 Offline operation

All UI files are located locally in `ecosystem/` or `user_data/`, so the UI is drawn without an internet connection. It is the Asset's responsibility to determine whether domain processing requires a network.

### 18.4 Coexistence with CLI

The same backend (rumiai + handlers) can be accessed from both Tauri frontend and CLI. In the case of CLI, the transport will be stdio, and the Widget JSON will fall back to text. The presence or absence of a front end does not affect the behavior of the back end.
