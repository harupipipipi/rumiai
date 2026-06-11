<!-- docs-i18n-links:start -->
[EN](../../frontend.md) | [JP](../ja/frontend.md) | [KR](../ko/frontend.md) | [CN](./frontend.md)
<!-- docs-i18n-links:end -->

# frontend.md — Rumi AI OS前端设计文档

## 1. 概述

默认的前端是一个由Tauri（Rust + WebView）组成的桌面应用程序。

前端没有领域知识。我不知道什么是聊天，我不知道什么是代理，我不知道什么是文件。我只知道四件事：“`There is a frame called a slot,'' ``UI blocks called Assets can be placed in the frame,'' ``Widgets can receive drawing instructions,'' and `‘消息来回发送。”

rumiai本身是一个没有领域知识的通用内核的相同结构也应用到了前端。所有域功能均由 Asset 引入。 Defaults仅提供一个空框架（外壳）来放置Asset以及绘制Asset并与Asset通信的机制。

所有特定的 UI（聊天屏幕、代理屏幕、编码屏幕等）均由 user_data 端的包注册为资产。默认值本身没有任何具体的 UI。

当前的 defaultspack 实现增加了这种概括`PlacementManifest`
我们正在逐步引入碱基放置候选者和引脚持久性。第一个应用程序是
右侧边栏/设置/作曲家、工具管理器、工具过滤器日志周围，
部署表面感知 YOLO 切换、模型管理器、Webhook 端点等。
我可以。


## 2. 架构

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

一共有三层。

Rust 层是 Tauri 的核心，是两者之间沟通的桥梁。 stdin/stdout 与 rumiai 进程和 Tauri IPC（调用/事件/通道）与 WebView。 Rust 层本身不解释消息的内容。

WebView层是绘图表面。它由外壳（空框架+槽定义）、资源加载器、Widget渲染器、布局引擎和主题引擎组成。

rumaii 层是后端。前端处理程序仅中继通信，不执行域处理。


## 3.权限

前端只有12个权限。不包括任何域权限。

|权限|描述 |
|------|------|
| `frontend.render.mount`|将资源放在绘图表面上 |
| `frontend.render.unmount`|从绘图表面移除 |
| `frontend.render.update`|更新绘图内容 |
| `frontend.message.send`|后端→绘图面|
| `frontend.message.receive`|绘图表面→后端|
| `frontend.message.stream`|连续传输数据 |
| `frontend.asset.register`|接受资产登记 |
| `frontend.asset.unregister`|资产注销 |
| `frontend.asset.list`|注册什么 |
| `frontend.layout.read`|获取当前布局信息 |
| `frontend.layout.write`|更改并保存布局 |
| `frontend.theme.read`|获取当前主题信息 |


## 4.资产模型

Asset是将UI带到前端的单元。任何包或工具都可以注册资产。前端并不关心Asset是谁。

### 4.1 资产配置

资产具有以下特点：

`asset_id` 是生态系统中的唯一字符串。命名约定为`{source}.{category}.{name}`。例如`defaults.chat.messages`和`my_pack.dashboard.main`。

`entry` 是包内 HTML 文件（或 JS 包）的相对路径。前端将此文件加载到WebView中。

`handler`是后端处理消息的Python文件的相对路径。发送至 Asset 的消息将转发至此处理程序。

`permissions` 是该资产所需的域权限数组。除了前端权限 (`frontend.*`) 之外，它由资产本身持有。

`placement` 是关于您想要放置此资源的插槽的提示。它有`slot`（插槽名称）和`priority`（数值，较大者优先）。

`category` 是 UI 的分类。 `"chat"`、`"coding"`、`"settings"`等自由字符串。

`tags` 是用于搜索/过滤的标签数组。

`requires` 是对其他资产的依赖。如果指定的资产未注册，则该资产将无法工作。

`extensions` 是无模式扩展字段。读者有责任做出回应。

### 4.2 asset.yaml

资产定义文件。将其放入包内的`assets/`目录中。

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

### 4.3 资产登记

当资产通过`frontend.asset.register`注册时，前端记录以下内容：

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

前端使用这些信息将文件加载到WebView上并根据layout.json排列它们。我不知道资产是做什么的。

### 4.4 同ID覆盖

如果使用与已注册的 asset_id 相同的 ID 调用`asset.register`，则后一个注册将取代前一个注册。这允许另一个包替换任何资产。

### 4.5 工具如何添加Asset

工具除了工具执行结果的Widget输出之外，还可以拥有Assets。将`assets/`放置在工具目录中，然后放置`*.asset.yaml`和HTML文件。安装该工具后，资产会注册为“未放置”状态，用户使用布局编辑器放置它。

```
user_data/shared/tools/browser_navigate/
├── tool.json
├── handler.py
└── assets/
    ├── browser_view.asset.yaml
    └── ui/
        └── browser_view.html
```


## 5. 插槽

插槽是显示资产的框架。 shell (shell.html) 定义了槽。

### 5.1 老虎机模型

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

### 5.2 槽渲染模式

|插槽|模式|描述 |
|----------|--------|------|
| `header`|单身|水平排列 |
| `sidebar.left`|堆栈|垂直堆叠，每个Asset都可以调整大小 |
| `sidebar.right`|堆栈|垂直堆叠 |
| `main`|标签 |您还可以切换和拆分选项卡 |
| `panel.bottom`|标签 |标签切换 |
| `statusbar`|单身|水平排列 |
| `floating`|浮动|必要时叠加显示|

资产可以指定未知的插槽名称。如果外壳无法识别该插槽，则会返回`floating`。

### 5.3 放置冲突解决

将多个资产放置在同一个插槽中时的规则。 Placement.priority 较高的优先（数字较大的）。如果优先级相同，则先注册的获胜。如果用户明确将其放置在layout.json中，则它具有最高优先级。失去位置的资产变得“未放置”。


## 6. 布局

### 6.1 布局.json

定义资产在屏幕上的位置。保存在`user_data/layout/`中。

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

默认值定义该文件的格式。具体来说，哪个Asset放在哪里，是由user_data这边决定的。

### 6.2 用户编辑布局

在普通模式下，拖动资源的边框可以调整其大小。在编辑模式下，您可以在插槽之间拖动和移动资源，通过从“未放置”面板拖动资源来添加资源，以及关闭资源以将其返回到未放置状态。保存并在多个布局预设之间切换。

这些机制内置于 shell (shell.html) 中。


## 7. Widget 渲染

### 7.1 概述

Widget 是后端用来声明它希望此数据像这样显示的 JSON。工具的处理程序、提示、代理、ai_client 和任何后端代码都可以发出 Widget。前端Widget渲染器接收这个JSON并根据主题进行绘制。

小部件是纯数据 (JSON)，不是 UI 库。渲染的责任在于前端。

### 7.2 小部件 JSON 格式

所有小部件都具有以下基本属性。

```json
{
  "type": "widget_type",
  "id": "optional_id",
  "style_hint": {},
  "meta": {}
}
```

`type` 是一个字符串，指示小部件的类型。 `id` 是任意标识符。 `style_hint` 是主题的提示（前端可能会也可能不会解释）。 `meta`是可选元数据（可以被前端忽略）。

### 7.3 小部件类型列表

**显示类型（14种）**

|类型 |描述 |主要性能 |
|------|------|---------------|
| `text`|文字|文字|
| `code_block`|代码|语言、内容、文件名、line_start |
| `diff`|差异|旧内容、新内容、文件名 |
| `image`|图片| src、alt、宽度、高度 |
| `screenshot`|截图|来源、网址、标题 |
| `progress`|进展|标签、当前、总计、状态 |
| `terminal`|终端输出|命令、输出、退出代码 |
| `table`|表|标题、行|
| `chart`|图|图表类型、数据、标签 |
| `file_tree`|文件树|树|
| `markdown`|降价|内容 |
| `audio`|音频|源代码，持续时间 |
| `video`|视频 |源代码，持续时间 |
| `map`|地图 |纬度、经度、缩放 |

**控制类型（6种）**

|类型 |描述 |主要性能 |
|------|------|---------------|
| `input`|文字输入 |占位符、值、多行 |
| `button`|按钮|标签、动作、变体 |
| `select`|选择|选项、值、多个 |
| `toggle`|切换 |标签，值 |
| `slider`|滑块|最小值、最大值、值、步长 |
| `checkbox`|复选框 |标签，检查|

**布局类型（6种）**

|类型 |描述 |主要性能 |
|------|------|---------------|
| `container`|通用容器|儿童 |
| `row`|并肩|儿童，差距|
| `column`|垂直|儿童，差距|
| `tabs`|标签切换 |标签 |
| `collapsible`|折叠 |标签、default_open、子项 |
| `card`|卡|页眉、正文、页脚 |

**流媒体类型（2种）**

|类型 |描述 |主要性能 |
|------|------|---------------|
| `stream`|基于状态的流|状态 |
| `indicator`|状态指示灯|标签、状态、动画 |

**定制（1 种）**

|类型 |描述 |主要性能 |
|------|------|---------------|
| `custom`|未定义的小部件 |自定义类型、后备、数据 |

### 7.4 小部件渲染器职责

shell 的内置 Widget 渲染器：

Widget接收JSON并根据`type`调用绘图函数。绘图遵循主题 (theme.yaml) `widgets` 部分中定义的样式。未知的`type`退回到文本。如果`custom_type`渲染器已注册，则`custom`类型执行专用绘制，如果未注册，则绘制`fallback`小部件。

Widget 渲染器是 shell 的一部分，由所有资源共享。 Asset中的JS可以通过将Widget JSON传递给Widget渲染器来委托绘制。

### 7.5 自定义小部件渲染器

自定义渲染器可以放置在`user_data/widget_renderers/`中。

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js
│   └── renderer.yaml
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

在renderer.yaml中定义元数据（custom_type、version等）并在renderer.js中实现渲染逻辑。当shell的Widget渲染器检测到custom_type时，它会动态加载并调用这个JS。


## 8. 主题

### 8.1 概述

主题控制所有图层的外观。定义小部件的颜色、字体、动画和绘图样式。放置在`user_data/themes/`中作为`.theme.yaml`。主题的详细规范在`docs/theme.md`中定义。

### 8.2 应用主题

shell 的主题引擎读取`user_data/config.json`中的`theme_id`并加载相应的`theme.yaml`。将主题的`tokens`（颜色、字体、间距等）作为 CSS 变量注入到 WebView 中。小部件渲染器引用此 CSS 变量并进行绘制。 Asset 中的 HTML/JS 也可以使用此 CSS 变量。

切换主题只需更改 config.json 中的`theme_id`即可完成，不会影响资产或后端。


## 9. 通讯协议

所有通信都经过三层。

```
WebView ←→ Rust ←→ rumiai
        IPC      stdin/stdout
```

### 9.1 消息格式

rumiai 和 Rust 使用 JSON Lines 进行通信（每行一条消息）。

```json
{
  "type": "メッセージタイプ",
  "data": {}
}
```

`type`是前端权限对应的操作名称。 `data` 是一个不透明的有效负载，前端和 Rust 不会解释其特定于域的内容。但是，识别资产目的地所需的字段（例如`asset_id`）由前端读取。

### 9.2 消息类型

#### 资产.注册

资产登记。 rumiai→铁锈方向。

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

#### 资产.注销

资产释放。 rumiai→铁锈方向。

```json
{
  "type": "asset.unregister",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### 渲染.mount

开始绘制资源。 rumiai→铁锈方向。

```json
{
  "type": "render.mount",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "slot": "main"
  }
}
```

#### 渲染.卸载

资产绘制完成。 rumiai→铁锈方向。

```json
{
  "type": "render.unmount",
  "data": {
    "asset_id": "my_pack.chat.messages"
  }
}
```

#### 渲染.更新

更新绘图内容。 rumiai→铁锈方向。

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

`payload`的内容由资产决定。前端使用 asset_id 识别目的地，并将数据按原样传递给相应的 Asset。

#### 消息.发送

后端→WebView方向的单条消息。 rumiai→铁锈方向。

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

如果`payload`中有`widget`字段，它可以作为Widget JSON传递到Widget渲染器。这是由Asset端的JS决定的。前端不解释`payload`的内容。

#### 消息接收

WebView → 发送至后端的单个消息。锈→入米爱方向。

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

#### 消息.stream.start

开始串流。 rumiai→铁锈方向。

```json
{
  "type": "message.stream.start",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### 消息.流.数据

流数据片。 rumiai→铁锈方向。

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

`payload` 还可以包含 Widget JSON。用于显示流媒体过程中的进度等。

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

#### 消息.stream.end

流媒体结束。 rumiai→铁锈方向。

```json
{
  "type": "message.stream.end",
  "data": {
    "asset_id": "my_pack.chat.messages",
    "stream_id": "stream-1"
  }
}
```

#### 布局.更新

布局更改通知。双向。

```json
{
  "type": "layout.update",
  "data": {
    "layout": { "...layout.json の内容..." }
  }
}
```

#### 布局.保存

保存布局。 WebView→入米爱方向。

```json
{
  "type": "layout.save",
  "data": {
    "layout_id": "my_layout",
    "layout": { "..." }
  }
}
```

#### 主题.change

主题切换。双向。

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "dark_default"
  }
}
```

#### 事件.广播

广播通用事件。双向。后端的`emit_event`成为这条消息。

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

Asset 的 JS 接收此事件，绘制弹出窗口，并在`event.broadcast`中发回用户的响应。所有资产都可以接收事件，而不仅仅是特定资产。如果包含asset_id，则可以将其寻址到特定的Asset，但这留给Asset本身的过滤，而不是前端的排序。


## 10. Rust 层的职责

Rust 层仅执行以下操作： 没有任何领域知识。

### 10.1 sidecar管理

当 Tauri 启动时，将 rumiai 编译的二进制文件作为 sidecar 启动。 `ecosystem/` 将目录路径作为启动参数传递。保存 sidecar 进程的 stdin/stdout 管道。应用程序关闭时停止 sidecar。

### 10.2 标准输入/标准输出桥

从rumiai的stdout中逐行读取JSON Lines，并根据`type`字段将其传输到WebView。 `render.*`、`message.send`、`message.stream.*`、`event.broadcast` 转换为 Tauri 事件/通道到 WebView。 `asset.*` 将 WebView 的资源加载器作为事件通知。 `layout.*` 通知 WebView 的布局引擎。 `theme.*` 通知 WebView 的主题引擎。

从WebView接收`invoke`，将其转换为`message.receive`，`layout.save`，`event.broadcast`格式并写入rumiai的stdin。

### 10.3 消息的误解

Rust 只能看到 `type` 和 `data` 中的 `asset_id` / `stream_id` / `event_type`。 `payload` 的内容不得以任何方式解释。


## 11.WebView层的职责

### 11.1 外壳

WebView 的入口点是 shell。 shell 绘制定义槽的空帧（`header`、`sidebar.left`、`main`、`panel.bottom`、`sidebar.right`、`statusbar`、`floating`）。槽位置和大小遵循layout.json。

外壳包含：

资源加载器：接收`asset.register`事件，使用iframe加载资源的HTML文件，并将其放置在插槽中。

Widget 渲染器：一组接受 Widget JSON 并根据主题将其绘制到 DOM 的函数。 Asset的JS调用这个函数。

布局引擎：读取layout.json并管理插槽大小和资源放置。提供拖放布局编辑。

主题引擎：将 theme.yaml 中的 token 转换为 CSS 变量并将其应用到 WebView。

事件调度程序：接收`event.broadcast`并使用postMessage将其转发到所有资产（iframe）。

### 11.2 资源加载器

当收到`asset.register`时，加载器将加载资源的 HTML 文件。

iframe 方法（默认）：使用 iframe 加载每个资源。资产之间具有高度隔离性。 `postMessage` 用于 iframe 和父窗口之间的通信。

当从Asset的HTML调用父窗口的Widget渲染器时，用postMessage发送Widget JSON，父窗口返回渲染结果。或者 Asset 本身加载 Widget 渲染器的 JS 并自行绘制（Asset 使用 `<script>` 导入 shell 提供的`widget-renderer.js` 的方法）。

### 11.3 消息发送

通过 Tauri 事件从 Rust 到达的`message.send` 和 `message.stream.*` 按`data.asset_id` 排序并传输到相应的 iframe。

当 `postMessage` 由于用户操作而来自 iframe 时，将其作为 `message.receive` 传递给 Rust。

### 11.4 事件调度

`event.broadcast` 转发到所有 iframe。每个资产的 JS 都会查看`event_type`并仅处理与其相关的事件。


## 12. 文件结构

### 12.1 默认端

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

默认情况下唯一的 UI 文件是 shell.html。它没有任何用于聊天、代理、编码等的特定 UI 文件。

### 12.2 金牛座方面

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

### 12.3 user_data 端（资产示例）

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


## 13. 启动流程

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


## 14.用户操作流程

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


## 15. 另一个群体如何加入

### 15.1 程序

该包将`*.asset.yaml`和HTML文件放在`assets/`目录中。通过rumiai的审批流程（SHA-256哈希验证+用户审批）。就这样。默认值方面的更改为零。

### 15.2 所需权限

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

### 15.3 具体示例：天气小部件包

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

### 15.4 具体示例：替换现有资产

```yaml
# better_chat.asset.yaml
asset_id: "my_pack.chat.messages"    # 同じ ID で上書き
entry: "ui/better_chat.html"
handler: "components/better_chat.py"
placement:
  slot: "main"
  priority: 200                       # 元より高い priority
```


## 16. 安全

### 16.1 包批准

所有包均经过rumiai的审批流程。 SHA-256哈希验证确保授权时的代码和运行时的代码相同。

### 16.2 权限分离

前端权限 (`frontend.*`) 仅允许资产注册、绘图和消息传递。域操作是使用资产处理程序拥有的域权限来执行的。

### 16.3 iframe隔离

每个资产的 UI 都在单独的 iframe 中运行。资产之间的直接 DOM 访问是不可能的。所有通信均由 shell 通过 `postMessage` 中继。

### 16.4 数据不透明

Rust 层和前端不解释消息中的`payload`。最大限度地减少中间层篡改数据的范围。

### 16.5 过滤事件

`event.broadcast` 转移至所有资产。如果事件中包含机密数据，请在资产端的JS中使用`event_type`和`asset_id`进行过滤。前端侧的过滤不是信任边界，因此在发出事件之前需要在后端侧进行权限检查。


## 17. 资产之间的通信

未定义资产之间的直接通信。如果资产 A 想要向资产 B 发送信息，有两种方法可以实现。

首先，通过后端。资产A发送message.receive到后端，后端处理程序处理它并将message.send发送到资产B。

第二，通过事件。资产 A 在 event.broadcast 上发出事件，资产 B 接收该事件。在这种情况下，它还会经过后端（Asset → Rust → rumiai → emmit_event → Rust → All Assets）。

无论哪种情况，前端内的资产之间都没有直接通信，而是始终通过 rumiai 后端进行通信。


## 18. 设计约束及注意事项

### 18.1 传递UI文件

将Asset的HTML文件读入WebView的方法是使用Tauri的asset协议（`asset://`或`tauri://`）。您需要将包目录路径添加到 Tauri 的资产范围中。

### 18.2 布局灵活性

插槽的类型和排列由 shell (shell.html) 定义。外壳本身也可以替换为另一个包（通过注册覆盖`ui/shell.html`的资产）。

### 18.3 离线操作

所有 UI 文件都位于本地`ecosystem/` 或`user_data/` 中，因此 UI 是在没有互联网连接的情况下绘制的。资产有责任确定域处理是否需要网络。

### 18.4 与 CLI 共存

可以从 Tauri 前端和 CLI 访问相同的后端（rumiai + 处理程序）。对于 CLI，传输将是 stdio，而 Widget JSON 将回退到文本。前端的存在或不存在不会影响后端的行为。
