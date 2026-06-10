<!-- docs-i18n-links:start -->
[EN](../../widget.md) | [JP](../ja/widget.md) | [KR](../ko/widget.md) | [CN](./widget.md)
<!-- docs-i18n-links:end -->

# widget.md — Rumi AI OS Widget 系统规范

## 1. 概述

Widget 是一种统一的数据格式，允许后端声明“我希望这个数据像这样显示。”Widget 是纯 JSON 数据，不是 UI 库。

后端中的每个代码（处理程序、工具的 handler.py、提示符、流程节点）都会生成 Widget JSON 并使用`emit_widget` 将其发送出去。前端Asset接收这个JSON并根据主题进行渲染。

小部件没有领域知识。没有“聊天小部件”或“代理小部件”。仅定义通用显示基元，例如文本、代码块、图像、表格和进度条。显示什么以及如何显示由生成小部件的一方（工具、处理程序等）决定，而如何显示则由主题决定。

## 2.设计理念

**纯数据**：Widget 是一个 JSON 字典。不包含渲染逻辑或事件处理程序。绘图是前端的职责。

**与域无关**：Widget 类型是通用显示基元，例如“文本”、“图像”和“表格”。没有针对特定领域（聊天、代理等）的专门类型。

**可嵌套**：小部件可以放置在小部件内部。将代码块和文本放入卡片中，将多个按钮排列成一行等。

**回退假设**：如果前端无法绘制某种Widget类型，它将回退到文本表示。自定义小部件有一个明确的后备小部件。在 CLI 环境中，所有小部件都会回退到文本表示形式。

**与主题分离**：小部件仅声明“显示什么”。主题决定了它的呈现方式（颜色、字体、动画、圆角、阴影等）。小部件可以使用 style_hint 将提示传递给主题，但主题可以忽略这一点。

## 3. Widget JSON 规范

### 3.1 基本属性

所有小部件都具有的通用属性。

```json
{
  "type": "text",
  "id": "widget_001",
  "style_hint": {},
  "meta": {}
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |小部件类型。下面列出的类型之一 |
| §鲁米§0§|字符串|可选 |小部件标识符。用于在流式更新期间更新特定的小部件 |
| §鲁米§0§|字典 |可选 |主题的提示。主题可能会也可能不会被解释 |
| §鲁米§0§|字典 |任何|任何元数据。前端可以忽略|

### 3.2 JSON表达式示例

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

## 4. 小部件类型列表

### 4.1 显示系统（14种）

#### 文字

显示文本。

```json
{
  "type": "text",
  "text": "Hello, world"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |要显示的文本 |

CLI 后备：按原样输出。

#### 代码块

查看源代码。

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 1
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|任何|编程语言|
| §鲁米§0§|字符串|必填 |代码正文 |
| §鲁米§0§|字符串|可选|文件名（用于显示）|
| §鲁米§0§|整数 |可选 |起始行号。默认 1 |

CLI 后备：纯文本输出。

#### 差异

显示差异。

```json
{
  "type": "diff",
  "old_content": "old code",
  "new_content": "new code",
  "filename": "main.py"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |变更前内容 |
| §鲁米§0§|字符串|必填 |新内容 |
| §鲁米§0§|字符串|任意|文件名 |

CLI 后备：统一 diff 格式。

#### 图片

显示图像。

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "説明",
  "width": 800,
  "height": 600
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 数据或 URL |
| §鲁米§0§|字符串|任何|替代文本|
| §鲁米§0§|整数 |任何|宽度（像素）|
| §鲁米§0§|整数 |任意|高度（像素）|

CLI 后备：`[Image: {alt} {width}x{height}]`

#### 截图

查看截图。它位于图像上方，并具有 URL 和标题等附加信息。

```json
{
  "type": "screenshot",
  "src": "base64 data",
  "url": "https://example.com",
  "title": "Example Page"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 数据 |
| §鲁米§0§|字符串|任何 |截图来源网址|
| §鲁米§0§|字符串|可选 |页面标题 |

CLI 后备：`[Screenshot: {title} - {url}]`

#### 进展

查看进度。

```json
{
  "type": "progress",
  "label": "Reading file...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |进度标签|
| §鲁米§0§|数量 |必填 |当前值|
| §鲁米§0§|数量 |必填 |总价值|
| §鲁米§0§|字符串|可选| §鲁米§1§、§鲁米§2§、§鲁米§3§。默认`"running"` |

CLI 后备：`[████░░░░░░] 30% Reading file...`

#### 终端

显示终端输出。

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\ndrwxr-xr-x ...",
  "exit_code": 0
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|任何|执行的命令 |
| §鲁米§0§|字符串|必填 |输出内容 |
| §鲁米§0§|整数 |可选 |退出代码 |

CLI 后备：`$ {command}\n{output}`

#### 表

显示表格。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字符串] |必填 |列标题|
| §鲁米§0§|列表[列表] |必填 |行数据|

CLI 后备：ASCII 表。

#### 图表

显示图表。

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb", "Mar"],
  "data": [10, 25, 15]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | §鲁米§1§、§鲁米§2§、§鲁米§3§、§鲁米§4§|
| §鲁米§0§|列表[字符串] |必填 |标签|
| §鲁米§0§|列表[数字] |必填 |数据|

CLI 后备：数字摘要文本。

#### 文件树

显示文件树。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字典] |必填|树节点。每个节点都有`name`，`type`（`"file"`或`"dir"`），`children`（可选）|

CLI 后备：缩进文本。

#### 降价

渲染并显示 Markdown 文本。

```json
{
  "type": "markdown",
  "content": "# Title\n\nSome **bold** text"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |降价文本 |

CLI 后备：纯文本。

#### 音频

播放音频。

```json
{
  "type": "audio",
  "src": "base64 or URL",
  "duration": 5000
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 数据或 URL |
| §鲁米§0§|整数 |任意|播放时间（毫秒）|

CLI 后备：`[Audio: {duration}ms]`

#### 视频

播放视频。

```json
{
  "type": "video",
  "src": "base64 or URL",
  "duration": 30000
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 数据或 URL |
| §鲁米§0§|整数 |任意|播放时间（毫秒）|

CLI 后备：`[Video: {duration}ms]`

#### 地图

显示地图。

```json
{
  "type": "map",
  "lat": 35.6812,
  "lng": 139.7671,
  "zoom": 15
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|数量 |必填|纬度 |
| §鲁米§0§|数量 |必填|经度 |
| §鲁米§0§|整数 |可选 |缩放级别。默认 13 |

CLI 后备：`[Map: {lat}, {lng}]`

### 4.2 控制系统（6种）

控制小部件接受用户的输入。仅在资产中可用。用户的操作结果由Asset的JS使用emit_event发送到后端。

#### 输入

文本输入字段。

```json
{
  "type": "input",
  "placeholder": "Type here...",
  "value": "",
  "multiline": false
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|可选 |占位符 |
| §鲁米§0§|字符串|任意|初始值|
| §鲁米§0§|布尔 |任何|多行。默认 false |

#### 按钮

按钮。

```json
{
  "type": "button",
  "label": "Execute",
  "action": "run_task",
  "variant": "primary"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |按钮标签|
| §鲁米§0§|字符串|必填 |单击时发出的操作名称 |
| §鲁米§0§|字符串|可选| §鲁米§1§、§鲁米§2§、§鲁米§3§。默认`"primary"` |

#### 选择

选择。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字典] |必填 |选择。每个元素都有`label`、`value` |
| §鲁米§0§|任何|任何|选定值 |
| §鲁米§0§|布尔 |任何 |多项选择。默认 false |

#### 切换

拨动开关。

```json
{
  "type": "toggle",
  "label": "Enable feature",
  "value": false
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|布尔 |任何 |当前状态。默认 false |

#### 滑块

滑块。

```json
{
  "type": "slider",
  "min": 0,
  "max": 100,
  "value": 50,
  "step": 1
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|数量 |必填 |最小值|
| §鲁米§0§|数量 |必填 |最大|
| §鲁米§0§|数量 |任意|当前值|
| §鲁米§0§|数量 |任何|步。默认 1 |

#### 复选框

复选框。

```json
{
  "type": "checkbox",
  "label": "I agree",
  "checked": false
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|布尔 |可选|检查状态。默认 false |

### 4.3 布局类型（6种）

用于配置 Widget 内嵌套的 Widget。

#### 容器

通用容器。包装子部件。

```json
{
  "type": "container",
  "children": [
    {"type": "text", "text": "Title"},
    {"type": "code_block", "language": "python", "content": "..."}
  ]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[小部件] |必填 |子部件数组 |

#### 行

水平排列子部件。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[小部件] |必填 |子部件 |
| §鲁米§0§|整数 |任何|子元素之间的间隙（像素）|

####专栏

垂直排列子部件。

```json
{
  "type": "column",
  "children": [...],
  "gap": 8
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[小部件] |必填 |子部件 |
| §鲁米§0§|整数 |任何|子元素之间的间隙（像素）|

#### 标签

切换标签。

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字典] |必填 |每个选项卡。与`label`（字符串）和`content`（小部件）|

#### 可折叠

可折叠。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |折叠标签|
| §鲁米§0§|布尔 |可选|初始状态。默认 false |
| §鲁米§0§|列表[小部件] |必填 |折叠中的子部件 |

####卡

卡片包含三个部分：页眉、正文和页脚。

```json
{
  "type": "card",
  "header": {"type": "text", "text": "Title"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "Footer"}
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|小部件 |可选|标题|
| §鲁米§0§|小部件 |任何 |身体|
| §鲁米§0§|小部件 |可选|页脚|

### 4.4 流媒体类型（2种）

#### 流

带状态的流式显示。用于展示AI的思维过程和任务进度。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字典[字符串，字典] |必填 |以状态名称作为键的定义。每个州都有`animation`（字符串，可选）和`label`（字符串）|

#### 指标

单一状态指示器。

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|字符串|必填 | §鲁米§1§、§鲁米§2§、§鲁米§3§、§鲁米§4§|
| §鲁米§0§|字符串|可选|主题中定义的动画名称 |

### 4.5 定制（1 种）

#### 自定义

不适合任何预定义类型的小部件。如果前端有custom_type渲染器，它将显示一个专用显示，如果没有，它将显示一个后备小部件。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |自定义类型标识符 |
| §鲁米§0§|小部件 |必填 |如果不存在渲染器则后备小部件 |
| §鲁米§0§|字典 |可选|传递给自定义渲染器的数据 |

自定义小部件渲染器可以放置在`user_data/widget_renderers/`中。

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js         # 描画ロジック
│   └── renderer.yaml       # メタ情報
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml的结构：

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

## 5.rumi_widgets — Python 帮助程序库

默认放置在`lib/rumi_widgets/`中的Python帮助器。您可以通过在handler.py或tool的handler.py中导入来使用它。用法是可选的，相当于直接返回 JSON 字典。

### 5.1 地点

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py      # Text, CodeBlock, Image, etc.
├── controls.py     # Input, Button, Select, etc.
├── layout.py       # Container, Row, Column, etc.
├── stream.py       # Stream, Indicator
└── custom.py       # Custom widget
```

### 5.2 导入

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

### 5.3 使用方法

每个类在其构造函数中接收 Widget 属性，并在 `.to_dict()` 中返回一个 JSON 字典。如果直接将其传递给`emit_widget`，则无需调用`.to_dict()`（emit_widget在内部调用它）。

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

### 5.4 所有类的基础

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

## 6. 通过emit_widget发送

小部件使用工具上下文 API 的通用原语`emit_widget` 发送。

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

emit_widget 将部分进度的 Widget 实时发送到前端。返回`widget`字段是将显示为最终结果的小部件。

emit_widget 发送的 Widget 以 Widget JSON 的形式存储在 message.stream.data 消息的数据中并到达前端。

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

## 7.前端绘图

### 7.1 小部件渲染器

前端的shell.html有一个内置的Widget渲染器。 Widget 渲染器查看 Widget JSON 的`type`字段并调用相应的绘图函数。

绘图函数是在 shell 级别提供的，而不是在资源的 iframe 内提供的。 Asset的JS调用`window.renderWidget(widgetJson, targetElement)`来绘制小部件。

### 7.2 未知类型

如果 Widget 渲染器无法识别`type`，它将按以下顺序回退。

1.如果`user_data/widget_renderers/`有自定义渲染器，请使用它
2. 如果类型为`"custom"`且`fallback`存在，则绘制后备小部件
3. 如果这些都不适用，则将文本显示为`[Unknown widget: {type}]`

### 7.3 主题合作

Widget渲染器在渲染时引用当前主题（theme.yaml）。每种小部件类型的绘图设置在主题的`widgets`部分中定义。

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

小部件的`style_hint`用作选择主题变体等的提示。例如，如果它是`style_hint: {"variant": "compact"}`，则将应用主题的`card.variants.compact`。主题可能会忽略此提示。

有关主题详细信息，请参阅 theme.md。

## 8. CLI 后备

在 CLI 环境中，所有小部件都会回退到文本表示形式。每个小部件类型的后备表达式如下。

|类型 | CLI 表达式 |
|---|---|
| §鲁米§0§|按原样输出 |
| §鲁米§0§|纯文本 |
| §鲁米§0§|统一差异|
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| ASCII 表 |
| §鲁米§0§|数值总结|
| §鲁米§0§|缩进文本|
| §鲁米§0§|纯文本 |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§|按顺序输出子项 |
| §鲁米§0§|水平输出子项，以`  ` | 分隔
| §鲁米§0§|带换行符垂直输出子项 |
| §鲁米§0§|每个选项卡上的`--- {label} ---\n{content}`输出 |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§|后备小部件的 CLI 表示 |
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
# widget.md — Widget 系统规范

## 1. 概述

Widget 是一种统一的数据格式，允许后端声明“我希望这个数据像这样显示。”Widget 是纯 JSON 数据，不是 UI 库。

后端中的任何代码（工具、处理程序、流程节点中的 handler.py）都会生成 Widget JSON 并将其在上下文的`emit_widget`中发送出去。前端接收到这个JSON并根据主题进行渲染。

小部件没有领域知识。仅定义通用显示基元，例如文本、代码块、图像、表格和进度条。显示什么、如何显示是由生成widget的一方决定的，而如何显示则是由主题决定的。


## 2.设计理念

**纯数据**：Widget 是一个 JSON 字典。不包含渲染逻辑、事件处理程序或样式定义。绘图是前端的职责。

**与领域无关**：Widget 类型是通用原语，例如“文本”、“图像”和“表格”。没有特定于域的类型，例如“聊天消息小部件”或“代理状态小部件”。

**可嵌套**：小部件可以放置在小部件内部。在卡片主体中插入代码块、在行中排列多个按钮、在选项卡的每个选项卡中放置不同的小部件等。

**回退假设**：如果前端无法绘制某种Widget类型，它将回退到文本表示。自定义小部件有一个明确的后备小部件。在 CLI 环境中，所有小部件都会回退到文本表示形式。

**与主题分离**：小部件仅声明“显示什么”。主题决定了它的呈现方式。小部件可以使用`style_hint`向主题传递提示，但主题可以忽略这一点。


## 3. 基本属性

所有小部件都具有的通用属性。

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |小部件类型。第 4 节 | 中列出的任何类型
| §鲁米§0§|字符串|可选 |标识符。用于在流式更新期间替换特定小部件 |
| §鲁米§0§|字典 |可选 |主题的提示。主题可能会也可能不会被解释 |
| §鲁米§0§|字典 |任何|任何元数据。前端可以忽略|

```json
{
  "type": "text",
  "id": "msg_001",
  "style_hint": {"variant": "muted"},
  "meta": {"source": "file_read_tool"}
}
```


## 4. 小部件类型列表

29种。 14 个显示系统、6 个控制系统、6 个布局系统、2 个流媒体系统和 1 个自定义系统。


### 4.1 显示系统（14种）

直观地显示数据。

---

#### 文字

```json
{ "type": "text", "text": "Hello, world" }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |显示文字|

CLI：按原样输出。

---

#### 代码块

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 10
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|任何|语言名称 |
| §鲁米§0§|字符串|必填 |代码正文 |
| §鲁米§0§|字符串|任意|文件名 |
| §鲁米§0§|整数 |可选 |起始行号。默认 1 |

CLI：纯文本。

---

#### 差异

```json
{
  "type": "diff",
  "old_content": "old",
  "new_content": "new",
  "filename": "main.py"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |变更前 |
| §鲁米§0§|字符串|必填 |变更后|
| §鲁米§0§|字符串|任意|文件名 |

CLI：统一差异。

---

#### 图片

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "description",
  "width": 800,
  "height": 600
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 数据或 URL |
| §鲁米§0§|字符串|任何|替代文本|
| §鲁米§0§|整数 |任意|宽度|
| §鲁米§0§|整数 |任意|高度|

CLI：`[Image: {alt} {width}x{height}]`

---

#### 截图

```json
{
  "type": "screenshot",
  "src": "base64",
  "url": "https://example.com",
  "title": "Example"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 数据 |
| §鲁米§0§|字符串|任何|原始网址 |
| §鲁米§0§|字符串|任意|标题 |

CLI：`[Screenshot: {title} - {url}]`

---

#### 进展

```json
{
  "type": "progress",
  "label": "Reading...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|数量 |必填 |当前值|
| §鲁米§0§|数量 |必填 |总价值|
| §鲁米§0§|字符串|可选 | §鲁米§1§ / §鲁米§2§ / §鲁米§3§。默认`"running"` |

CLI：`[████░░░░░░] 30% Reading...`

---

#### 终端

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\n...",
  "exit_code": 0
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|任意|执行命令 |
| §鲁米§0§|字符串|必填 |输出|
| §鲁米§0§|整数 |可选 |退出代码 |

CLI：`$ {command}\n{output}`

---

#### 表

```json
{
  "type": "table",
  "headers": ["Name", "Size"],
  "rows": [["main.py", "1.2KB"], ["test.py", "800B"]]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字符串] |必填 |列标题|
| §鲁米§0§|列表[列表] |必填 |行数据|

CLI：ASCII 表。

---

#### 图表

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb"],
  "data": [10, 25]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | §鲁米§1§ / §鲁米§2§ / §鲁米§3§ / §鲁米§4§ |
| §鲁米§0§|列表[字符串] |必填 |标签|
| §鲁米§0§|列表[数字] |必填 |数据|

CLI：数值摘要。

---

#### 文件树

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字典] |必填 |节点数组。每个节点都是`name`（字符串），`type`（`"file"`或`"dir"`），`children`（列表，可选）|

CLI：缩进文本。

---

#### 降价

```json
{ "type": "markdown", "content": "# Title\n\n**bold**" }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |降价文本 |

CLI：纯文本。

---

#### 音频

```json
{ "type": "audio", "src": "base64 or URL", "duration": 5000 }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 或 URL |
| §鲁米§0§|整数 |任何|毫秒 |

CLI：`[Audio: {duration}ms]`

---

#### 视频

```json
{ "type": "video", "src": "base64 or URL", "duration": 30000 }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 | Base64 或 URL |
| §鲁米§0§|整数 |任何|毫秒 |

CLI：`[Video: {duration}ms]`

---

#### 地图

```json
{ "type": "map", "lat": 35.6812, "lng": 139.7671, "zoom": 15 }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|数量 |必填|纬度 |
| §鲁米§0§|数量 |必填|经度 |
| §鲁米§0§|整数 |可选 |缩放级别。默认 13 |

CLI：`[Map: {lat}, {lng}]`


### 4.2 控制系统（6种）

接受用户输入。用户操作的结果由Asset的JS使用`emit_event`返回到后端。

---

#### 输入

```json
{ "type": "input", "placeholder": "Type here...", "value": "", "multiline": false }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|可选 |占位符 |
| §鲁米§0§|字符串|任意|初始值|
| §鲁米§0§|布尔 |任何|多行。默认 false |

---

#### 按钮

```json
{ "type": "button", "label": "Execute", "action": "run_task", "variant": "primary" }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|字符串|必填 |单击操作名称 |
| §鲁米§0§|字符串|可选 | §鲁米§1§ / §鲁米§2§ / §鲁米§3§。默认`"primary"` |

---

#### 选择

```json
{
  "type": "select",
  "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
  "value": "a",
  "multiple": false
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字典] |必填 |每个元素都是`label`（字符串），`value`（任何）|
| §鲁米§0§|任何|任何|当前值|
| §鲁米§0§|布尔 |任何 |多项选择。默认 false |

---

#### 切换

```json
{ "type": "toggle", "label": "Enable", "value": false }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|布尔 |可选|默认 false |

---

#### 滑块

```json
{ "type": "slider", "min": 0, "max": 100, "value": 50, "step": 1 }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|数量 |必填 |最小值|
| §鲁米§0§|数量 |必填 |最大|
| §鲁米§0§|数量 |任意|当前值|
| §鲁米§0§|数量 |任何|步。默认 1 |

---

#### 复选框

```json
{ "type": "checkbox", "label": "I agree", "checked": false }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|布尔 |可选|默认 false |


### 4.3 布局类型（6种）

在小部件内创建嵌套结构。

---

#### 容器

```json
{ "type": "container", "children": [{"type": "text", "text": "..."}, {"type": "code_block", "content": "..."}] }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[小部件] |必填 |子部件 |

---

#### 行

```json
{ "type": "row", "children": [...], "gap": 8 }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[小部件] |必填 |子部件 |
| §鲁米§0§|整数 |任意|间隔（像素）|

---

####专栏

```json
{ "type": "column", "children": [...], "gap": 8 }
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[小部件] |必填 |子部件 |
| §鲁米§0§|整数 |任意|间隔（像素）|

---

#### 标签

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|列表[字典] |必填 |每个元素都是`label`（字符串），`content`（小部件）|

---

#### 可折叠

```json
{
  "type": "collapsible",
  "label": "Details",
  "default_open": false,
  "children": [{"type": "text", "text": "hidden"}]
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|布尔 |可选|默认 false |
| §鲁米§0§|列表[小部件] |必填 |子部件 |

---

####卡

```json
{
  "type": "card",
  "header": {"type": "indicator", "label": "done", "state": "success"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "1.2KB"}
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|小部件 |可选|标题|
| §鲁米§0§|小部件 |任何 |身体|
| §鲁米§0§|小部件 |可选|页脚|


### 4.4 流媒体类型（2种）

---

#### 流

具有多种状态的流式显示。

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

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字典[字符串，字典] |必填 |州名 → `label`(字符串) + `animation`(字符串，可选) |

---

#### 指标

单一状态指示器。

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |标签|
| §鲁米§0§|字符串|必填 | §鲁米§1§ / §鲁米§2§ / §鲁米§3§ / §鲁米§4§ |
| §鲁米§0§|字符串|可选|主题定义动画名称 |


### 4.5 定制（1 种）

#### 自定义

不适合任何预定义类型的显示。如果`user_data/widget_renderers/`有渲染器，则完成专用绘制，否则绘制`fallback`。

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {"type": "image", "src": "preview.png", "alt": "3D Preview"},
  "data": {"model_url": "model.glb", "rotation": [0, 45, 0]}
}
```

|物业 |类型 |必填 |描述 |
|---|---|---|---|
| §鲁米§0§|字符串|必填 |自定义类型标识符 |
| §鲁米§0§|小部件 |必填 |渲染器不存在时的回退 |
| §鲁米§0§|字典 |可选|传递给自定义渲染器的数据 |

自定义渲染器放置：

```
user_data/widget_renderers/
└── 3d_viewer/
    ├── renderer.js
    └── renderer.yaml
```

渲染器.yaml：

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

CLI：后备小部件的 CLI 表示。


## 5.rumi_widgets — Python 帮助程序库

默认值位于`lib/rumi_widgets/`中。可以通过在handler.py中导入来使用。使用是可选的。相当于直接返回一个JSON dict。

### 5.1 安置

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py
├── controls.py
├── layout.py
├── stream.py
└── custom.py
```

### 5.2 导入

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

### 5.3 基类

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

### 5.4 使用示例

类构造和 JSON 字典是等效的。

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


## 6. 发送

### 6.1 发出小部件

在工具的handler.py中调用`context["emit_widget"]`。将进度Widget实时发送到前端。

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

使用`emit_widget`发送的小部件将作为流消息传输。返回的`widget`字段是最终结果小部件。

### 6.2 通讯表达

emit_widget 发送的 Widget 存储在 JSON Lines 消息的数据中。

```json
{"type":"message.stream.data","component":"target_asset","data":{"stream_id":"s1","widget":{"type":"progress","label":"Processing...","current":0,"total":3}}}
```

最终结果Widget是使用message.send发送的。

```json
{"type":"message.send","component":"target_asset","data":{"action":"tool_result","widget":{"type":"card","header":{"type":"indicator","label":"task","state":"success"},"body":{"type":"text","text":"done"}}}}
```

### 6.3 通过id替换

如果您将`id`添加到小部件并发出它，前端将覆盖并使用相同的`id`绘制小部件。用于更新进度。

```python
context["emit_widget"](Progress(id="p1", label="Step 1", current=1, total=3))
# ...
context["emit_widget"](Progress(id="p1", label="Step 2", current=2, total=3))
# フロントエンドは id="p1" の Widget を置き換える
```


## 7.前端绘图

### 7.1 小部件渲染器

shell 有一个内置的 Widget 渲染器。渲染器查看 Widget JSON 的`type`并调用相应的绘图函数。

从 Asset 的 JS 中调用它，如下所示。

```javascript
window.rumiWidgets.render(widgetJson, targetElement);
```

### 7.2 绘图后备顺序

1. 如果 type 是 29 种预定义类型之一，则使用内置渲染器进行绘制。
2. 如果类型为`"custom"`，则搜索`user_data/widget_renderers/{custom_type}/`渲染器
3.如果有自定义渲染器，请使用专用渲染器
4. 如果没有，`fallback` 使用内置渲染器绘制小部件
5. 如果以上都不适用，则将文本显示为`[Unknown widget: {type}]`

### 7.3 主题协作

Widget渲染器在渲染时引用当前主题（theme.yaml）的`widgets`部分。

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

您可以使用 Widget 的`style_hint` 选择主题变体。

```json
{"type": "card", "style_hint": {"variant": "compact"}, "body": {"type": "text", "text": "..."}}
```

主题的`card.variants.compact`适用。如果主题没有相应的变体，则将使用`default`。

有关详细的主题规范，请参阅 theme.md。


## 8. CLI 后备

CLI 环境中没有前端小部件渲染器。所有小部件都转换为文本表示形式。

|类型 | CLI 表达式 |
|---|---|
| §鲁米§0§|按原样输出 |
| §鲁米§0§|纯文本 |
| §鲁米§0§|统一差异|
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| ASCII 表 |
| §鲁米§0§|数值总结|
| §鲁米§0§|缩进文本|
| §鲁米§0§|纯文本 |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§|按顺序输出子项 |
| §鲁米§0§|输出以空格水平分隔的子项 |
| §鲁米§0§|带换行符垂直输出子项 |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§| §鲁米§1§ |
| §鲁米§0§|后备的 CLI 表示 |

CLI 回退实现作为`to_cli()` 方法在`lib/rumi_widgets/` 中的每个类中提供。如果传输层检测到 CLI 模式，emit_widget 会输出`to_cli()`而不是`to_dict()`的结果。
