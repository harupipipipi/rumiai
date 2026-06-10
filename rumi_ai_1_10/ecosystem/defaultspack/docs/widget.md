<!-- docs-i18n-links:start -->
[EN](./widget.md) | [JP](./i18n/ja/widget.md) | [KR](./i18n/ko/widget.md) | [CN](./i18n/zh-cn/widget.md)
<!-- docs-i18n-links:end -->

# widget.md — Rumi AI OS Widget System specifications

## 1. Overview

Widget is a unified data format that allows the backend to declare ``I want this data to be displayed like this.'' Widgets are pure JSON data and are not UI libraries.

Every code in the backend (handler, tool's handler.py, prompt, Flow node) generates Widget JSON and sends it out with `emit_widget`. The front-end Asset receives this JSON and renders it according to the theme.

Widgets have no domain knowledge. There are no "chat widgets" or "agent widgets." Define only general-purpose display primitives such as text, code blocks, images, tables, and progress bars. What and how to display it is decided by the side that generates the widget (tool, handler, etc.), and how it is displayed is decided by the theme.

## 2. Design philosophy

**Pure data**: Widget is a JSON dict. Contains no rendering logic or event handlers. Drawing is the responsibility of the front end.

**Domain independent**: Widget types are general-purpose display primitives such as "text", "image", and "table". There are no specialized types for specific domains (chat, agents, etc.).

**Nestable**: Widgets can be placed inside Widgets. Put CodeBlock and Text in a Card, arrange multiple Buttons in a Row, etc.

**Fallback assumption**: If the front end cannot draw a certain Widget type, it will fall back to the text representation. Custom widgets have an explicit fallback widget. In the CLI environment, all widgets fall back to text representation.

**Separation from theme**: Widget declares only "what to display". The theme determines how it will be presented (colors, fonts, animations, rounded corners, shadows, etc.). The widget can pass a hint to the theme using style_hint, but the theme can ignore this.

## 3. Widget JSON specification

### 3.1 Base properties

Common properties that all widgets have.

```json
{
  "type": "text",
  "id": "widget_001",
  "style_hint": {},
  "meta": {}
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `type` | string | Required | Widget type. One of the types listed below |
| `id` | string | optional | Widget identifier. Used to update specific widgets during streaming updates |
| `style_hint` | dict | optional | hints to the theme. The theme may or may not be interpreted |
| `meta` | dict | any | any metadata. You can ignore the front end |

### 3.2 JSON expression example

```json
{
  "type": "card",
  "style_hint": {"variant": "compact"},
  "header": {
    "type": "indicator",
    "label": "file_read",
    "state": "success",
    "animation": "fade_in"
  },
  "body": {
    "type": "code_block",
    "language": "python",
    "content": "print('hello')",
    "filename": "main.py"
  },
  "footer": {
    "type": "text",
    "text": "1.2KB"
  }
}
```

## 4. Widget type list

### 4.1 Display system (14 types)

#### Text

Display text.

```json
{
  "type": "text",
  "text": "Hello, world"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `text` | string | Required | Text to display |

CLI fallback: Output as is.

#### CodeBlock

View source code.

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 1
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `language` | string | any | programming language |
| `content` | string | Required | Code body |
| `filename` | string | Optional | File name (for display) |
| `line_start` | integer | optional | starting line number. Default 1 |

CLI fallback: Plain text output.

#### Diff

Show differences.

```json
{
  "type": "diff",
  "old_content": "old code",
  "new_content": "new code",
  "filename": "main.py"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `old_content` | string | Required | Contents before change |
| `new_content` | string | Required | New content |
| `filename` | string | arbitrary | file name |

CLI fallback: unified diff format.

#### Image

Display images.

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "説明",
  "width": 800,
  "height": 600
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 data or URL |
| `alt` | string | any | alternative text |
| `width` | integer | any | width (pixels) |
| `height` | integer | arbitrary | height (pixels) |

CLI fallback: `[Image: {alt} {width}x{height}]`

#### Screenshot

View screenshot. It is above Image and has additional information such as URL and title.

```json
{
  "type": "screenshot",
  "src": "base64 data",
  "url": "https://example.com",
  "title": "Example Page"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 data |
| `url` | string | Any | Screenshot source URL |
| `title` | string | optional | page title |

CLI fallback: `[Screenshot: {title} - {url}]`

#### Progress

View progress.

```json
{
  "type": "progress",
  "label": "Reading file...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Progress label |
| `current` | number | Required | Current value |
| `total` | number | Required | Total value |
| `state` | string | Optional | `"running"`, `"success"`, `"error"`. Default `"running"` |

CLI fallback: `[████░░░░░░] 30% Reading file...`

#### Terminal

Display terminal output.

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\ndrwxr-xr-x ...",
  "exit_code": 0
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `command` | string | any | executed command |
| `output` | string | Required | Output content |
| `exit_code` | integer | optional | exit code |

CLI fallback: `$ {command}\n{output}`

#### Table

Show table.

```json
{
  "type": "table",
  "headers": ["Name", "Size", "Modified"],
  "rows": [
    ["main.py", "1.2KB", "2026-02-14"],
    ["test.py", "800B", "2026-02-13"]
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `headers` | list[string] | Required | Column header |
| `rows` | list[list] | Required | Row data |

CLI fallback: ASCII table.

#### Chart

Display the graph.

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb", "Mar"],
  "data": [10, 25, 15]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `chart_type` | string | Required | `"bar"`, `"line"`, `"pie"`, `"scatter"` |
| `labels` | list[string] | Required | Label |
| `data` | list[number] | Required | Data |

CLI fallback: Numerical summary text.

#### FileTree

Show file tree.

```json
{
  "type": "file_tree",
  "tree": [
    {"name": "src", "type": "dir", "children": [
      {"name": "main.py", "type": "file"},
      {"name": "utils.py", "type": "file"}
    ]},
    {"name": "README.md", "type": "file"}
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `tree` | list[dict] | required | tree node. Each node has `name`, `type`(`"file"` or `"dir"`), `children` (optional) |

CLI fallback: Indented text.

#### Markdown

Render and display Markdown text.

```json
{
  "type": "markdown",
  "content": "# Title\n\nSome **bold** text"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `content` | string | Required | Markdown text |

CLI fallback: Plain text.

#### Audio

Play audio.

```json
{
  "type": "audio",
  "src": "base64 or URL",
  "duration": 5000
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 data or URL |
| `duration` | integer | arbitrary | playback time (ms) |

CLI fallback: `[Audio: {duration}ms]`

#### Video

Play the video.

```json
{
  "type": "video",
  "src": "base64 or URL",
  "duration": 30000
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 data or URL |
| `duration` | integer | arbitrary | playback time (ms) |

CLI fallback: `[Video: {duration}ms]`

#### Map

Show map.

```json
{
  "type": "map",
  "lat": 35.6812,
  "lng": 139.7671,
  "zoom": 15
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `lat` | number | required | latitude |
| `lng` | number | required | longitude |
| `zoom` | integer | optional | zoom level. Default 13 |

CLI fallback: `[Map: {lat}, {lng}]`

### 4.2 Control system (6 types)

Control widgets accept input from the user. Available only within Asset. The user's operation results are sent to the backend by Asset's JS using emit_event.

#### Input

Text input field.

```json
{
  "type": "input",
  "placeholder": "Type here...",
  "value": "",
  "multiline": false
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `placeholder` | string | optional | placeholder |
| `value` | string | arbitrary | initial value |
| `multiline` | boolean | any | multiple lines. Default false |

#### Button

button.

```json
{
  "type": "button",
  "label": "Execute",
  "action": "run_task",
  "variant": "primary"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Button label |
| `action` | string | Required | Action name issued on click |
| `variant` | string | Optional | `"primary"`, `"secondary"`, `"danger"`. Default `"primary"` |

#### Select

Choice.

```json
{
  "type": "select",
  "options": [
    {"label": "Option A", "value": "a"},
    {"label": "Option B", "value": "b"}
  ],
  "value": "a",
  "multiple": false
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `options` | list[dict] | Required | Choices. Each element has `label`, `value` |
| `value` | any | any | selected value |
| `multiple` | boolean | Any | Multiple selection. Default false |

#### Toggle

toggle switch.

```json
{
  "type": "toggle",
  "label": "Enable feature",
  "value": false
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `value` | boolean | Any | Current state. Default false |

#### Slider

slider.

```json
{
  "type": "slider",
  "min": 0,
  "max": 100,
  "value": 50,
  "step": 1
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `min` | number | Required | Minimum value |
| `max` | number | Required | Maximum |
| `value` | number | arbitrary | current value |
| `step` | number | any | step. Default 1 |

#### Checkbox

Checkbox.

```json
{
  "type": "checkbox",
  "label": "I agree",
  "checked": false
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `checked` | boolean | Optional | Checked state. Default false |

### 4.3 Layout type (6 types)

A Widget for configuring nesting inside a Widget.

#### Container

General purpose container. Wraps the child widget.

```json
{
  "type": "container",
  "children": [
    {"type": "text", "text": "Title"},
    {"type": "code_block", "language": "python", "content": "..."}
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `children` | list[Widget] | Required | Array of child widgets |

#### Row

Arrange child widgets horizontally.

```json
{
  "type": "row",
  "children": [
    {"type": "button", "label": "OK", "action": "ok"},
    {"type": "button", "label": "Cancel", "action": "cancel"}
  ],
  "gap": 8
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `children` | list[Widget] | Required | Child Widget |
| `gap` | integer | any | gap between child elements (pixels) |

#### Column

Arrange child widgets vertically.

```json
{
  "type": "column",
  "children": [...],
  "gap": 8
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `children` | list[Widget] | Required | Child Widget |
| `gap` | integer | any | gap between child elements (pixels) |

#### Tabs

Switch tabs.

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `tabs` | list[dict] | Required | Each tab. with `label`(string) and `content`(Widget) |

#### Collapsible

Foldable.

```json
{
  "type": "collapsible",
  "label": "Details",
  "default_open": false,
  "children": [
    {"type": "text", "text": "Hidden content"}
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Folding label |
| `default_open` | boolean | Optional | Initial state. Default false |
| `children` | list[Widget] | Required | Child Widget in Collapse |

#### Card

A card with three sections: header, body, and footer.

```json
{
  "type": "card",
  "header": {"type": "text", "text": "Title"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "Footer"}
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `header` | Widget | Optional | Header |
| `body` | Widget | Any | Body |
| `footer` | Widget | Optional | Footer |

### 4.4 Streaming type (2 types)

#### Stream

Streaming display with state. Used to display AI's thought process and task progress.

```json
{
  "type": "stream",
  "states": {
    "thinking": {"animation": "wave_dots", "label": "Thinking..."},
    "executing": {"animation": "pulse", "label": "Executing..."},
    "done": {"animation": "fade_in", "label": "Complete"}
  }
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `states` | dict[string, dict] | Required | Definition with state name as key. Each state has `animation`(string, optional) and `label`(string) |

#### Indicator

Single status indicator.

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `state` | string | Required | `"running"`, `"success"`, `"error"`, `"waiting"` |
| `animation` | string | Optional | Animation name defined in the theme |

### 4.5 Custom (1 type)

#### Custom

Widgets that do not fit any predefined type. If the front end has a custom_type renderer, it will display a dedicated display, and if it does not, it will display a fallback widget.

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {
    "type": "image",
    "src": "preview.png",
    "alt": "3D Preview"
  },
  "data": {
    "model_url": "model.glb",
    "rotation": [0, 45, 0]
  }
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `custom_type` | string | Required | Custom type identifier |
| `fallback` | Widget | Required | Fallback Widget if no renderer exists |
| `data` | dict | Optional | Data to pass to custom renderer |

Custom Widget renderer can be placed in `user_data/widget_renderers/`.

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js         # 描画ロジック
│   └── renderer.yaml       # メタ情報
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

Structure of renderer.yaml:

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

## 5. rumi_widgets — Python helper library

Python helper that defaults places in `lib/rumi_widgets/`. You can use it by importing it in handler.py or handler.py of tool. Usage is optional and equivalent to returning a JSON dict directly.

### 5.1 Location

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py      # Text, CodeBlock, Image, etc.
├── controls.py     # Input, Button, Select, etc.
├── layout.py       # Container, Row, Column, etc.
├── stream.py       # Stream, Indicator
└── custom.py       # Custom widget
```

### 5.2 import

```python
from rumi_widgets import (
    # 表示系
    Text, CodeBlock, Diff, Image, Progress,
    Terminal, Table, Chart, FileTree, Markdown,
    Audio, Video, Map, Screenshot,
    # コントロール系
    Input, Button, Select, Toggle, Slider, Checkbox,
    # レイアウト系
    Container, Row, Column, Tabs, Collapsible, Card,
    # ストリーミング系
    Stream, Indicator,
    # カスタム
    Custom
)
```

### 5.3 How to use

Each class receives Widget properties in its constructor and returns a JSON dict in `.to_dict()`. If you pass it directly to `emit_widget`, there is no need to call `.to_dict()` (emit_widget calls it internally).

```python
# クラスで構築
widget = Card(
    header=Indicator(label="file_read", state="success"),
    body=CodeBlock(language="python", content="print('hello')", filename="main.py"),
    footer=Text(text="1.2KB")
)

# 等価な JSON dict
widget = {
    "type": "card",
    "header": {"type": "indicator", "label": "file_read", "state": "success"},
    "body": {"type": "code_block", "language": "python", "content": "print('hello')", "filename": "main.py"},
    "footer": {"type": "text", "text": "1.2KB"}
}
```

### 5.4 Base of all classes

```python
class Widget:
    def __init__(self, type: str, id: str = None, style_hint: dict = None, meta: dict = None, **kwargs):
        self._data = {"type": type}
        if id: self._data["id"] = id
        if style_hint: self._data["style_hint"] = style_hint
        if meta: self._data["meta"] = meta
        self._data.update(kwargs)

    def to_dict(self) -> dict:
        result = {}
        for k, v in self._data.items():
            if isinstance(v, Widget):
                result[k] = v.to_dict()
            elif isinstance(v, list):
                result[k] = [item.to_dict() if isinstance(item, Widget) else item for item in v]
            else:
                result[k] = v
        return result
```

## 6. Sending by emit_widget

Widgets are sent using the general-purpose primitive `emit_widget` of tool's context API.

```python
# tool の handler.py
def run(params, context):
    # 進捗を送出（リアルタイムに UI に表示される）
    context["emit_widget"](
        Progress(label="Processing...", current=0, total=3)
    )

    # 処理...

    context["emit_widget"](
        Progress(label="Done", current=3, total=3, state="success")
    )

    # 最終結果を返す（result の widget フィールド）
    return {
        "result": "File content here",
        "widget": Card(
            header=Indicator(label="file_read", state="success"),
            body=CodeBlock(language="python", content="...")
        )
    }
```

emit_widget sends the partially progressed Widget to the front end in real time. The return `widget` field is the widget that will be displayed as the final result.

The Widget sent by emit_widget is stored as Widget JSON in the data of message.stream.data message and reaches the front end.

```json
{
  "type": "message.stream.data",
  "component": "target_asset_id",
  "data": {
    "stream_id": "s1",
    "widget": {
      "type": "progress",
      "label": "Processing...",
      "current": 0,
      "total": 3
    }
  }
}
```

## 7. Drawing on the front end

### 7.1 Widget Renderer

The front end's shell.html has a built-in Widget renderer. The Widget renderer looks at the `type` field of Widget JSON and calls the corresponding drawing function.

Drawing functions are provided at the shell level, not within the Asset's iframe. Asset's JS calls `window.renderWidget(widgetJson, targetElement)` to draw the widget.

### 7.2 Unknown type

If the Widget renderer cannot recognize `type`, it will fall back in the following order.

1. If `user_data/widget_renderers/` has a custom renderer, use it
2. Draw fallback widget if type is `"custom"` and `fallback` exists
3. If none of these apply, display text as `[Unknown widget: {type}]`

### 7.3 Cooperation with themes

The Widget renderer refers to the current theme (theme.yaml) when rendering. The drawing settings for each widget type are defined in the `widgets` section of the theme.

```yaml
# theme.yaml の widgets セクション（抜粋）
widgets:
  indicator:
    states:
      running:
        color: "{color.primary}"
        default_animation: "pulse"
      success:
        color: "{color.success}"
        default_animation: "fade_in"
  code_block:
    syntax_theme: "one-dark-pro"
    show_line_numbers: true
    show_copy_button: true
    max_height: 500
  card:
    variants:
      default:
        background: "{color.surface}"
        border: "1px solid {color.border}"
      compact:
        padding: "{spacing.sm}"
```

Widget's `style_hint` is used as a hint to select theme variants, etc. For example, if it is `style_hint: {"variant": "compact"}`, `card.variants.compact` of the theme will be applied. Theme may ignore this hint.

See theme.md for theme details.

## 8. CLI fallback

In the CLI environment, all widgets fall back to text representation. The fallback expression for each widget type is as follows.

| type | CLI expression |
|---|---|
| `text` | Output as is |
| `code_block` | Plain text |
| `diff` | unified diff |
| `image` | `[Image: {alt} {width}x{height}]` |
| `screenshot` | `[Screenshot: {title} - {url}]` |
| `progress` | `[████░░░░░░] 30% {label}` |
| `terminal` | `$ {command}\n{output}` |
| `table` | ASCII table |
| `chart` | Numerical summary |
| `file_tree` | Indented text |
| `markdown` | Plain text |
| `audio` | `[Audio: {duration}ms]` |
| `video` | `[Video: {duration}ms]` |
| `map` | `[Map: {lat}, {lng}]` |
| `input` | `[Input: {placeholder}]` |
| `button` | `[{label}]` |
| `select` | `[Select: {options}]` |
| `toggle` | `[{label}: {value}]` |
| `slider` | `[{min}-{max}: {value}]` |
| `checkbox` | `[{checked ? "x" : " "}] {label}` |
| `container` | Output children in order |
| `row` | Output children horizontally, separated by `  ` |
| `column` | Output children vertically with line breaks |
| `tabs` | `--- {label} ---\n{content}` output on each tab |
| `collapsible` | `▸ {label}\n{children}` |
| `card` | `[{header}]\n{body}\n{footer}` |
| `stream` | `[{current_state.label}]` |
| `indicator` | `[{state}] {label}` |
| `custom` | CLI representation of fallback widget |
```

これで完全な widget.md の内容。

あ、でもユーザーが「思考と回答はクローラーで分けて」と言っている。これはどういう意味だろう？

おそらく「思考プロセスをまず見せて、次に完成品を見せて」ということ？それとも「クローラーを使って何か分けろ」？

「クローラーで分けて」は文脈的に、思考部分と回答部分をはっきり区切って出してほしいということだと思う。クローラーツールを使うという意味ではなさそう。

もしくは、長い出力を分割して出すために何かしてほしい？

いずれにしても、まず思考（方針整理）を出して、次に完全なコードを出す形にする。

ただ、ここまでの思考は内部で行っているので、回答として出すのは完全なドキュメントのみでいい。

長い出力になるが、「完全なコード」を求められているので省略せず全文出す。

widget.md を書き出す。引き継ぎ文書のセクション5.2をベースに、今回の理解に基づいて再構成する。

ユーザーの要望を整理：
1. 完全なコード
2. 仮回答はいらない
3. 思考と回答はクローラーで分けて

「クローラーで分けて」はおそらく、思考プロセスの部分は別途説明して、回答（コード）は純粋にコードだけ出してほしいということだと思う。

回答を構造化しよう：
- 最初に簡潔な思考/方針説明
- 次に完全な widget.md のコード

思考の整理結果。

widget.md の設計方針:
1. Widget は純粋な JSON データ。UI ライブラリではない。
2. ドメイン非依存。「チャット用Widget」は存在しない。
3. emit_widget という汎用プリミティブ経由で送出。
4. フロントエンドの shell が Widget レンダラーを持ち、type に応じて描画。
5. テーマが見た目を決める。Widget は style_hint でヒントを渡すだけ。
6. Custom Widget + fallback で未定義の型を受け入れ可能。
7. CLI フォールバックで全 Widget がテキスト表現に変換可能。
8. rumi_widgets Python ヘルパーは任意使用。直接 dict でも等価。
9. 全29種（表示14 + コントロール6 + レイアウト6 + ストリーミング2 + カスタム1）

Widget型一覧:

表示系（14種）:
- Text
- CodeBlock  
- Diff
- Image
- Screenshot
- Progress
- Terminal
- Table
- Chart
- FileTree
- Markdown
- Audio
- Video
- Map

コントロール系（6種）:
- Input
- Button
- Select
- Toggle
- Slider
- Checkbox

レイアウト系（6種）:
- Container
- Row
- Column
- Tabs
- Collapsible
- Card

ストリーミング系（2種）:
- Stream
- Indicator

カスタム（1種）:
- Custom

よし、完全版を書く。

思考の要約を最初に短く出して、その後に完全なマークダウンコードを出す。

## 思考

widget.md に必要な要素:
- defaults の思想に合致（仕組みだけ提供、ドメイン非依存）
- 汎用プリミティブ emit_widget で送出
- tool.md の新 context API と連携
- テーマ連携（theme.md から参照される）
- CLI フォールバック
- Custom Widget による拡張
- rumi_widgets ヘルパー

引き継ぎ文書セクション5.2をベースに、特化禁止・仕組みのみの原則で再構成する。

これを出力しよう。

## 思考まとめ

設計方針：
- Widget = 純粋な JSON。UI ライブラリではない
- ドメイン非依存。汎用表示プリミティブのみ
- emit_widget（汎用プリミティブ）で送出
- shell の Widget レンダラーが type に応じて描画
- テーマが見た目を決定。Widget は style_hint でヒントのみ
- Custom + fallback で未知の型を受容
- CLI で全 Widget がテキストにフォールバック
- rumi_widgets Python ヘルパーは任意使用
- 29種（表示14 + コントロール6 + レイアウト6 + ストリーミング2 + カスタム1）

## 思考

**設計方針**: Widget は純粋な JSON データで、ドメイン非依存の汎用表示プリミティブのみ。tool.md の汎用プリミティブ `emit_widget` で送出し、shell の Widget レンダラーが描画、テーマが見た目を決定。全29種。引き継ぎ文書セクション5.2をベースに「仕組みのみ提供・特化禁止」の原則で再構成。

---

## 回答: docs/widget.md 完全版

```markdown
# widget.md — Widget System specifications

## 1. Overview

Widget is a unified data format that allows the backend to declare ``I want this data to be displayed like this.'' Widgets are pure JSON data and are not UI libraries.

Any code in the backend (handler.py in the tool, handler, Flow node) generates Widget JSON and sends it out in the context's `emit_widget`. The front end receives this JSON and renders it according to the theme.

Widgets have no domain knowledge. Define only general-purpose display primitives such as text, code blocks, images, tables, and progress bars. What to display and how to display it is decided by the side that generates the widget, and how to display it is decided by the theme.


## 2. Design philosophy

**Pure data**: Widget is a JSON dict. Contains no rendering logic, event handlers, or style definitions. Drawing is the responsibility of the front end.

**Domain independent**: Widget types are general-purpose primitives such as "text", "image", and "table". There are no domain-specific types such as "Chat Message Widget" or "Agent Status Widget."

**Nestable**: Widgets can be placed inside Widgets. Inserting a CodeBlock in the body of a Card, arranging multiple Buttons in a Row, placing a different widget in each tab of Tabs, etc.

**Fallback assumption**: If the front end cannot draw a certain Widget type, it will fall back to the text representation. Custom widgets have an explicit fallback widget. In the CLI environment, all widgets fall back to text representation.

**Separation from theme**: Widget declares only "what to display". The theme determines how it will be presented. The widget can pass a hint to the theme with `style_hint`, but the theme can ignore this.


## 3. Base properties

Common properties that all widgets have.

| Property | Type | Required | Description |
|---|---|---|---|
| `type` | string | Required | Widget type. Any of the types listed in Section 4 |
| `id` | string | optional | identifier. Used to replace specific widgets during streaming updates |
| `style_hint` | dict | optional | hints to the theme. The theme may or may not be interpreted |
| `meta` | dict | any | any metadata. You can ignore the front end |

```json
{
  "type": "text",
  "id": "msg_001",
  "style_hint": {"variant": "muted"},
  "meta": {"source": "file_read_tool"}
}
```


## 4. Widget type list

29 types. 14 display systems, 6 control systems, 6 layout systems, 2 streaming systems, and 1 custom system.


### 4.1 Display system (14 types)

Display data visually.

---

#### Text

```json
{ "type": "text", "text": "Hello, world" }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `text` | string | Required | Display text |

CLI: Output as is.

---

#### CodeBlock

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 10
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `language` | string | any | language name |
| `content` | string | Required | Code body |
| `filename` | string | arbitrary | file name |
| `line_start` | integer | optional | starting line number. Default 1 |

CLI: Plain text.

---

#### Diff

```json
{
  "type": "diff",
  "old_content": "old",
  "new_content": "new",
  "filename": "main.py"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `old_content` | string | Required | Before change |
| `new_content` | string | Required | After change |
| `filename` | string | arbitrary | file name |

CLI: unified diff。

---

#### Image

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "description",
  "width": 800,
  "height": 600
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 data or URL |
| `alt` | string | any | alternative text |
| `width` | integer | arbitrary | width |
| `height` | integer | arbitrary | height |

CLI: `[Image: {alt} {width}x{height}]`

---

#### Screenshot

```json
{
  "type": "screenshot",
  "src": "base64",
  "url": "https://example.com",
  "title": "Example"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 data |
| `url` | string | any | original URL |
| `title` | string | arbitrary | title |

CLI: `[Screenshot: {title} - {url}]`

---

#### Progress

```json
{
  "type": "progress",
  "label": "Reading...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `current` | number | Required | Current value |
| `total` | number | Required | Total value |
| `state` | string | optional | `"running"` / `"success"` / `"error"`. Default `"running"` |

CLI: `[████░░░░░░] 30% Reading...`

---

#### Terminal

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\n...",
  "exit_code": 0
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `command` | string | arbitrary | execution command |
| `output` | string | Required | Output |
| `exit_code` | integer | optional | exit code |

CLI: `$ {command}\n{output}`

---

#### Table

```json
{
  "type": "table",
  "headers": ["Name", "Size"],
  "rows": [["main.py", "1.2KB"], ["test.py", "800B"]]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `headers` | list[string] | Required | Column header |
| `rows` | list[list] | Required | Row data |

CLI: ASCII table.

---

#### Chart

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb"],
  "data": [10, 25]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `chart_type` | string | Required | `"bar"` / `"line"` / `"pie"` / `"scatter"` |
| `labels` | list[string] | Required | Label |
| `data` | list[number] | Required | Data |

CLI: Numerical summary.

---

#### FileTree

```json
{
  "type": "file_tree",
  "tree": [
    {"name": "src", "type": "dir", "children": [
      {"name": "main.py", "type": "file"}
    ]},
    {"name": "README.md", "type": "file"}
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `tree` | list[dict] | Required | Node array. Each node is `name`(string), `type`(`"file"` or `"dir"`), `children`(list, optional) |

CLI: Indented text.

---

#### Markdown

```json
{ "type": "markdown", "content": "# Title\n\n**bold**" }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `content` | string | Required | Markdown text |

CLI: Plain text.

---

#### Audio

```json
{ "type": "audio", "src": "base64 or URL", "duration": 5000 }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 or URL |
| `duration` | integer | any | milliseconds |

CLI: `[Audio: {duration}ms]`

---

#### Video

```json
{ "type": "video", "src": "base64 or URL", "duration": 30000 }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `src` | string | Required | base64 or URL |
| `duration` | integer | any | milliseconds |

CLI: `[Video: {duration}ms]`

---

#### Map

```json
{ "type": "map", "lat": 35.6812, "lng": 139.7671, "zoom": 15 }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `lat` | number | required | latitude |
| `lng` | number | required | longitude |
| `zoom` | integer | optional | zoom level. Default 13 |

CLI: `[Map: {lat}, {lng}]`


### 4.2 Control system (6 types)

Accept user input. The result of the user operation is returned to the backend by Asset's JS using `emit_event`.

---

#### Input

```json
{ "type": "input", "placeholder": "Type here...", "value": "", "multiline": false }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `placeholder` | string | optional | placeholder |
| `value` | string | arbitrary | initial value |
| `multiline` | boolean | any | multiple lines. Default false |

---

#### Button

```json
{ "type": "button", "label": "Execute", "action": "run_task", "variant": "primary" }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `action` | string | Required | Click action name |
| `variant` | string | optional | `"primary"` / `"secondary"` / `"danger"`. Default `"primary"` |

---

#### Select

```json
{
  "type": "select",
  "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
  "value": "a",
  "multiple": false
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `options` | list[dict] | Required | Each element is `label`(string), `value`(any) |
| `value` | any | any | current value |
| `multiple` | boolean | Any | Multiple selection. Default false |

---

#### Toggle

```json
{ "type": "toggle", "label": "Enable", "value": false }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `value` | boolean | Optional | Default false |

---

#### Slider

```json
{ "type": "slider", "min": 0, "max": 100, "value": 50, "step": 1 }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `min` | number | Required | Minimum value |
| `max` | number | Required | Maximum |
| `value` | number | arbitrary | current value |
| `step` | number | any | step. Default 1 |

---

#### Checkbox

```json
{ "type": "checkbox", "label": "I agree", "checked": false }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `checked` | boolean | Optional | Default false |


### 4.3 Layout type (6 types)

Create a nested structure inside the widget.

---

#### Container

```json
{ "type": "container", "children": [{"type": "text", "text": "..."}, {"type": "code_block", "content": "..."}] }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `children` | list[Widget] | Required | Child Widget |

---

#### Row

```json
{ "type": "row", "children": [...], "gap": 8 }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `children` | list[Widget] | Required | Child Widget |
| `gap` | integer | arbitrary | interval (px) |

---

#### Column

```json
{ "type": "column", "children": [...], "gap": 8 }
```

| Property | Type | Required | Description |
|---|---|---|---|
| `children` | list[Widget] | Required | Child Widget |
| `gap` | integer | arbitrary | interval (px) |

---

#### Tabs

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `tabs` | list[dict] | Required | Each element is `label`(string), `content`(Widget) |

---

#### Collapsible

```json
{
  "type": "collapsible",
  "label": "Details",
  "default_open": false,
  "children": [{"type": "text", "text": "hidden"}]
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `default_open` | boolean | Optional | Default false |
| `children` | list[Widget] | Required | Child Widget |

---

#### Card

```json
{
  "type": "card",
  "header": {"type": "indicator", "label": "done", "state": "success"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "1.2KB"}
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `header` | Widget | Optional | Header |
| `body` | Widget | Any | Body |
| `footer` | Widget | Optional | Footer |


### 4.4 Streaming type (2 types)

---

#### Stream

Streaming display with multiple states.

```json
{
  "type": "stream",
  "states": {
    "thinking": {"animation": "wave_dots", "label": "Thinking..."},
    "executing": {"animation": "pulse", "label": "Executing..."},
    "done": {"animation": "fade_in", "label": "Complete"}
  }
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `states` | dict[string, dict] | Required | State name → `label`(string) + `animation`(string, optional) |

---

#### Indicator

Single status indicator.

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `label` | string | Required | Label |
| `state` | string | Required | `"running"` / `"success"` / `"error"` / `"waiting"` |
| `animation` | string | Optional | Theme-defined animation name |


### 4.5 Custom (1 type)

#### Custom

Displays that do not fit any predefined type. If `user_data/widget_renderers/` has a renderer, dedicated drawing is done, otherwise `fallback` is drawn.

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {"type": "image", "src": "preview.png", "alt": "3D Preview"},
  "data": {"model_url": "model.glb", "rotation": [0, 45, 0]}
}
```

| Property | Type | Required | Description |
|---|---|---|---|
| `custom_type` | string | Required | Custom type identifier |
| `fallback` | Widget | Required | Fallback when renderer is absent |
| `data` | dict | Optional | Data to pass to custom renderer |

Custom renderer placement:

```
user_data/widget_renderers/
└── 3d_viewer/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml:

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

CLI: CLI representation of the fallback widget.


## 5. rumi_widgets — Python helper library

defaults is placed in `lib/rumi_widgets/`. It can be used by importing it in handler.py. Use is optional. Equivalent to returning a JSON dict directly.

### 5.1 Placement

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py
├── controls.py
├── layout.py
├── stream.py
└── custom.py
```

### 5.2 import

```python
from rumi_widgets import (
    # 表示系
    Text, CodeBlock, Diff, Image, Progress,
    Terminal, Table, Chart, FileTree, Markdown,
    Audio, Video, Map, Screenshot,
    # コントロール系
    Input, Button, Select, Toggle, Slider, Checkbox,
    # レイアウト系
    Container, Row, Column, Tabs, Collapsible, Card,
    # ストリーミング系
    Stream, Indicator,
    # カスタム
    Custom
)
```

### 5.3 Base class

```python
class Widget:
    def __init__(self, type: str, id: str = None,
                 style_hint: dict = None, meta: dict = None, **kwargs):
        self._data = {"type": type}
        if id is not None:
            self._data["id"] = id
        if style_hint is not None:
            self._data["style_hint"] = style_hint
        if meta is not None:
            self._data["meta"] = meta
        self._data.update(kwargs)

    def to_dict(self) -> dict:
        result = {}
        for k, v in self._data.items():
            if isinstance(v, Widget):
                result[k] = v.to_dict()
            elif isinstance(v, list):
                result[k] = [
                    item.to_dict() if isinstance(item, Widget) else item
                    for item in v
                ]
            elif isinstance(v, dict):
                result[k] = {
                    dk: dv.to_dict() if isinstance(dv, Widget) else dv
                    for dk, dv in v.items()
                }
            else:
                result[k] = v
        return result
```

### 5.4 Usage example

Class construction and JSON dict are equivalent.

```python
# クラス
widget = Card(
    header=Indicator(label="file_read", state="success"),
    body=CodeBlock(language="python", content="print('hello')", filename="main.py"),
    footer=Text(text="1.2KB")
)

# 等価な dict
widget = {
    "type": "card",
    "header": {"type": "indicator", "label": "file_read", "state": "success"},
    "body": {"type": "code_block", "language": "python",
             "content": "print('hello')", "filename": "main.py"},
    "footer": {"type": "text", "text": "1.2KB"}
}
```


## 6. Sending

### 6.1 emit_widget

Call `context["emit_widget"]` in handler.py of tool. Sends the progressed Widget to the front end in real time.

```python
def run(params, context):
    context["emit_widget"](Progress(label="Processing...", current=0, total=3))

    result = do_work(params)

    context["emit_widget"](Progress(label="Done", current=3, total=3, state="success"))

    return {
        "result": result,
        "widget": Card(
            header=Indicator(label="task", state="success"),
            body=Text(text=result)
        )
    }
```

Widgets sent with `emit_widget` are transferred as streaming messages. The `widget` field of return is the final result widget.

### 6.2 Communication expressions

The Widget sent by emit_widget is stored in the data of the JSON Lines message.

```json
{"type":"message.stream.data","component":"target_asset","data":{"stream_id":"s1","widget":{"type":"progress","label":"Processing...","current":0,"total":3}}}
```

The final result Widget is sent using message.send.

```json
{"type":"message.send","component":"target_asset","data":{"action":"tool_result","widget":{"type":"card","header":{"type":"indicator","label":"task","state":"success"},"body":{"type":"text","text":"done"}}}}
```

### 6.3 Replacement by id

If you add `id` to a widget and emit it, the front end will overwrite and draw the widget with the same `id`. Used to update Progress.

```python
context["emit_widget"](Progress(id="p1", label="Step 1", current=1, total=3))
# ...
context["emit_widget"](Progress(id="p1", label="Step 2", current=2, total=3))
# フロントエンドは id="p1" の Widget を置き換える
```


## 7. Drawing on the front end

### 7.1 Widget Renderer

The shell has a built-in Widget renderer. The renderer looks at `type` of Widget JSON and calls the corresponding drawing function.

Call it from within Asset's JS as follows.

```javascript
window.rumiWidgets.render(widgetJson, targetElement);
```

### 7.2 Drawing fallback order

1. If type is one of the 29 predefined types, draw with the built-in renderer.
2. If type is `"custom"`, search for `user_data/widget_renderers/{custom_type}/` renderer
3. If you have a custom renderer, use dedicated rendering
4. If not, `fallback` Draw the widget using the built-in renderer
5. If none of the above apply, display text as `[Unknown widget: {type}]`

### 7.3 Theme collaboration

The Widget renderer refers to the `widgets` section of the current theme (theme.yaml) when rendering.

```yaml
# theme.yaml 抜粋
widgets:
  indicator:
    states:
      running:
        color: "{color.primary}"
        default_animation: "pulse"
      success:
        color: "{color.success}"
        default_animation: "fade_in"
      error:
        color: "{color.error}"
        default_animation: "fade_in"
      waiting:
        color: "{color.warning}"
        default_animation: "wave_dots"
  code_block:
    syntax_theme: "one-dark-pro"
    show_line_numbers: true
    show_copy_button: true
    max_height: 500
  card:
    variants:
      default:
        background: "{color.surface}"
        border: "1px solid {color.border}"
        border_radius: "{radius.md}"
        padding: "{spacing.md}"
      compact:
        padding: "{spacing.sm}"
        border_radius: "{radius.sm}"
      elevated:
        shadow: "{shadow.md}"
  progress:
    bar_color: "{color.primary}"
    background: "{color.surface}"
    height: 4
```

You can select a theme variant with Widget's `style_hint`.

```json
{"type": "card", "style_hint": {"variant": "compact"}, "body": {"type": "text", "text": "..."}}
```

`card.variants.compact` of the theme applies. If the theme does not have a corresponding variant, `default` will be used.

See theme.md for detailed theme specifications.


## 8. CLI fallback

There is no front-end widget renderer in the CLI environment. All widgets are converted to text representations.

| type | CLI expression |
|---|---|
| `text` | Output as is |
| `code_block` | Plain text |
| `diff` | unified diff |
| `image` | `[Image: {alt} {width}x{height}]` |
| `screenshot` | `[Screenshot: {title} - {url}]` |
| `progress` | `[████░░░░░░] 30% {label}` |
| `terminal` | `$ {command}\n{output}` |
| `table` | ASCII table |
| `chart` | Numerical summary |
| `file_tree` | Indented text |
| `markdown` | Plain text |
| `audio` | `[Audio: {duration}ms]` |
| `video` | `[Video: {duration}ms]` |
| `map` | `[Map: {lat}, {lng}]` |
| `input` | `[Input: {placeholder}]` |
| `button` | `[{label}]` |
| `select` | `[Select: {options}]` |
| `toggle` | `[{label}: {value}]` |
| `slider` | `[{min}-{max}: {value}]` |
| `checkbox` | `[{checked ? "x" : " "}] {label}` |
| `container` | Output children in order |
| `row` | Output children horizontally separated by spaces |
| `column` | Output children vertically with line breaks |
| `tabs` | `--- {label} ---\n{content}` |
| `collapsible` | `▸ {label}\n{children}` |
| `card` | `[{header}]\n{body}\n{footer}` |
| `stream` | `[{current_state.label}]` |
| `indicator` | `[{state}] {label}` |
| `custom` | CLI representation of fallback |

The CLI fallback implementation is provided as a `to_cli()` method in each class in `lib/rumi_widgets/`. If the transport layer detects CLI mode, emit_widget outputs the result of `to_cli()` instead of `to_dict()`.
