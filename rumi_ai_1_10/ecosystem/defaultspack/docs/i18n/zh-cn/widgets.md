<!-- docs-i18n-links:start -->
[EN](../../widgets.md) | [JP](../ja/widgets.md) | [KR](../ko/widgets.md) | [CN](./widgets.md)
<!-- docs-i18n-links:end -->

# 小工具指南

## 1. 小部件概念

Widget 是统一的 JSON 数据格式，允许后端声明“我希望这个数据像这样显示”。Widget 是纯数据，而不是 UI 库。

后端中的每个代码（处理程序、工具的 handler.py、提示符、流程节点）都会生成 Widget JSON 并使用`emit_widget` 将其发送出去。前端shell.html中的Widget渲染器接收这个JSON并根据主题进行绘制。

小部件是独立于域的。没有“聊天小部件”或“代理小部件”。仅定义通用显示基元，例如文本、代码块、图像、表格和进度条。总共 29 种（显示 14 + 控制 6 + 布局 6 + 流媒体 2 + 自定义 1）。


## 2. lib/rumi_widgets/ 的类列表和使用

Python 帮助程序库位于`ecosystem/defaults/lib/rumi_widgets/`。用法是可选的，相当于直接返回一个字典。

### display.py（14种显示类型）

|班级 |用途 |主要参数|
|---|---|---|
| §鲁米§0§|文字显示| §鲁米§1§ |
| §鲁米§0§|查看源代码 | §鲁米§1§、§鲁米§2§、§鲁米§3§、§鲁米§4§|
| §鲁米§0§|差异展示| §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|图片展示| §鲁米§1§、§鲁米§2§、§鲁米§3§、§鲁米§4§|
| §鲁米§0§|截图展示| §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|进度显示| §鲁米§1§、§鲁米§2§、§鲁米§3§、§鲁米§4§|
| §鲁米§0§|终端输出显示| §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|桌面展示| §鲁米§1§，§鲁米§2§|
| §鲁米§0§|图表显示 | §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|文件树显示 | §鲁米§1§ |
| §鲁米§0§| Markdown 渲染 | §鲁米§1§ |
| §鲁米§0§|音频播放 | §鲁米§1§，§鲁米§2§|
| §鲁米§0§|视频播放| §鲁米§1§，§鲁米§2§|
| §鲁米§0§|地图显示| §鲁米§1§、§鲁米§2§、§鲁米§3§|

###controls.py（6种控件）

|班级 |用途 |主要参数|
|---|---|---|
| §鲁米§0§|文字输入 | §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|按钮| §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|选择| §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|拨动开关| §鲁米§1§，§鲁米§2§|
| §鲁米§0§|滑块| §鲁米§1§、§鲁米§2§、§鲁米§3§、§鲁米§4§|
| §鲁米§0§|复选框| §鲁米§1§，§鲁米§2§|

###layout.py（6种布局类型）

|班级 |用途 |主要参数|
|---|---|---|
| §鲁米§0§|通用集装箱| §鲁米§1§ |
| §鲁米§0§|并排布局 | §鲁米§1§，§鲁米§2§|
| §鲁米§0§|垂直布局| §鲁米§1§，§鲁米§2§|
| §鲁米§0§|标签切换 | `tabs`（每个`{label, content}`）|
| §鲁米§0§|折叠 | §鲁米§1§、§鲁米§2§、§鲁米§3§|
| §鲁米§0§|带页眉/正文/页脚的卡片 | §鲁米§1§、§鲁米§2§、§鲁米§3§|

###stream.py（2种流类型）

|班级 |用途 |主要参数|
|---|---|---|
| §鲁米§0§|基于状态的流显示| `states`（字典）|
| §鲁米§0§|单状态指示器| §鲁米§1§、§鲁米§2§、§鲁米§3§|

### custom.py（1 种自定义类型）

|班级 |用途 |主要参数|
|---|---|---|
| §鲁米§0§|未定义的小部件 | §鲁米§1§、§鲁米§2§、§鲁米§3§|


## 3.Python端如何生成JSON

### 如何使用rumi_widgets助手

```python
from rumi_widgets import Card, Indicator, CodeBlock, Text, Row, Button

widget = Card(
    header=Indicator(label="file_read", state="success", animation="fade_in"),
    body=CodeBlock(language="python", content="print('hello')", filename="main.py"),
    footer=Row(children=[
        Button(label="Copy", action="copy"),
        Text(text="1.2KB")
    ])
)

# handler の戻り値で返す
return {"result": "File content", "widget": widget}
```

传递给`emit_widget`（内部自动调用）时不需要`.to_dict()`。当传递到返回的`widget`字段时，它也会自动转换。

### 如何直接返回为dict

```python
widget = {
    "type": "card",
    "header": {"type": "indicator", "label": "file_read", "state": "success", "animation": "fade_in"},
    "body": {"type": "code_block", "language": "python", "content": "print('hello')", "filename": "main.py"},
    "footer": {
        "type": "row",
        "children": [
            {"type": "button", "label": "Copy", "action": "copy"},
            {"type": "text", "text": "1.2KB"}
        ]
    }
}
return {"result": "File content", "widget": widget}
```

两者产生完全相同的结果。


## 4.前端侧如何绘制

Widget 渲染器内置于 shell.html 中并由所有资源共享。

从 Asset 的 JS 中绘制 widget 有两种方法。

postMessage方法：iframe中的JS使用postMessage将Widget JSON发送到父窗口，父Widget渲染器返回绘制结果。

直接调用方式：资产通过`<script>`导入shell提供的`widget-renderer.js`，直接调用`renderWidget(widgetJson, targetElement)`。

```javascript
// Asset の JS 内
// 方法1: postMessage
window.parent.postMessage({
  type: "render_widget",
  widget: widgetJson,
  target: "my-container-id"
}, "*");

// 方法2: 直接呼び出し（widget-renderer.js を読み込み済みの場合）
renderWidget(widgetJson, document.getElementById("my-container"));
```

未知的小部件类型会回退到文本。如果在`user_data/widget_renderers/`中注册了自定义渲染器，`custom`类型将使用专用绘图，否则它将绘制`fallback`小部件。


## 5. 使用示例

### 示例1：在widget中显示文件读取结果

```python
def run(params, context):
    content = context["call_handler"]("defaults.coding.file_read", {
        "path": params["path"]
    })
    return {
        "result": content["content"],
        "widget": {
            "type": "card",
            "header": {"type": "indicator", "label": params["path"], "state": "success"},
            "body": {"type": "code_block", "language": "python", "content": content["content"], "filename": params["path"]}
        }
    }
```

### 示例2：实时显示进度

```python
def run(params, context):
    files = params["files"]
    for i, f in enumerate(files):
        context["emit_widget"]({
            "type": "progress",
            "label": f"Processing {f}...",
            "current": i,
            "total": len(files),
            "state": "running"
        })
        process(f)

    context["emit_widget"]({
        "type": "progress",
        "label": "Complete",
        "current": len(files),
        "total": len(files),
        "state": "success"
    })
    return {"result": f"Processed {len(files)} files"}
```

### 示例 3：用户确认按钮

```python
def run(params, context):
    context["emit_widget"]({
        "type": "card",
        "body": {"type": "text", "text": "この操作を実行しますか？"},
        "footer": {
            "type": "row",
            "children": [
                {"type": "button", "label": "実行", "action": "confirm", "variant": "primary"},
                {"type": "button", "label": "キャンセル", "action": "cancel", "variant": "secondary"}
            ]
        }
    })
    response = context["wait_event"]("widget.action", timeout=60)
    if response and response.get("action") == "confirm":
        return {"result": "Executed"}
    return {"result": "Cancelled"}
```

### 示例 4：折叠搜索结果

```python
def run(params, context):
    results = context["call_handler"]("defaults.memory.vector_query", {
        "query": params["query"], "top_k": 5
    })
    return {
        "result": "\n---\n".join([r["content"] for r in results["matches"]]),
        "widget": {
            "type": "collapsible",
            "label": f"{len(results['matches'])} results found",
            "default_open": True,
            "children": [
                {"type": "markdown", "content": r["content"]}
                for r in results["matches"]
            ]
        }
    }
```

### 示例 5：流媒体指示器

```python
context["emit_widget"]({
    "type": "indicator",
    "label": "Analyzing code...",
    "state": "running",
    "animation": "pulse"
})
```

动画指定主题的`animations`部分中定义的名称。主题无法识别的动画名称将被忽略。
