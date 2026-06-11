<!-- docs-i18n-links:start -->
[EN](./widgets.md) | [JP](./i18n/ja/widgets.md) | [KR](./i18n/ko/widgets.md) | [CN](./i18n/zh-cn/widgets.md)
<!-- docs-i18n-links:end -->

# Widgets Guide

## 1. Widget concept

Widget is a unified JSON data format that allows the backend to declare ``I want this data to be displayed like this.'' Widgets are pure data, not UI libraries.

Every code in the backend (handler, tool's handler.py, prompt, Flow node) generates Widget JSON and sends it out with `emit_widget`. The Widget renderer in shell.html on the front end receives this JSON and draws it according to the theme.

Widgets are domain independent. There are no "chat widgets" or "agent widgets." Define only general-purpose display primitives such as text, code blocks, images, tables, and progress bars. Total of 29 types (Display 14 + Control 6 + Layout 6 + Streaming 2 + Custom 1).


## 2. Class list and usage of lib/rumi_widgets/

Python helper library located in `ecosystem/defaults/lib/rumi_widgets/`. Usage is optional and equivalent to returning a dict directly.

### display.py (14 display types)

| Class | Usage | Main parameters |
|---|---|---|
| `Text` | Text display | `text` |
| `CodeBlock` | View source code | `language`, `content`, `filename`, `line_start` |
| `Diff` | Difference display | `old_content`, `new_content`, `filename` |
| `Image` | Image display | `src`, `alt`, `width`, `height` |
| `Screenshot` | Screenshot display | `src`, `url`, `title` |
| `Progress` | Progress display | `label`, `current`, `total`, `state` |
| `Terminal` | Terminal output display | `command`, `output`, `exit_code` |
| `Table` | Table display | `headers`, `rows` |
| `Chart` | Graph display | `chart_type`, `labels`, `data` |
| `FileTree` | File tree display | `tree` |
| `Markdown` | Markdown rendering | `content` |
| `Audio` | Audio playback | `src`, `duration` |
| `Video` | Video playback | `src`, `duration` |
| `Map` | Map display | `lat`, `lng`, `zoom` |

### controls.py (6 types of controls)

| Class | Usage | Main parameters |
|---|---|---|
| `Input` | Text input | `placeholder`, `value`, `multiline` |
| `Button` | Button | `label`, `action`, `variant` |
| `Select` | Selection | `options`, `value`, `multiple` |
| `Toggle` | Toggle switch | `label`, `value` |
| `Slider` | Slider | `min`, `max`, `value`, `step` |
| `Checkbox` | Checkbox | `label`, `checked` |

### layout.py (6 layout types)

| Class | Usage | Main parameters |
|---|---|---|
| `Container` | General purpose container | `children` |
| `Row` | Side-by-side layout | `children`, `gap` |
| `Column` | Vertical layout | `children`, `gap` |
| `Tabs` | Tab switching | `tabs` (each `{label, content}`) |
| `Collapsible` | Collapse | `label`, `default_open`, `children` |
| `Card` | Card with header/body/footer | `header`, `body`, `footer` |

### stream.py (2 types of streaming type)

| Class | Usage | Main parameters |
|---|---|---|
| `Stream` | State-based stream display | `states` (dict) |
| `Indicator` | Single state indicators | `label`, `state`, `animation` |

### custom.py (1 type of custom)

| Class | Usage | Main parameters |
|---|---|---|
| `Custom` | Undefined Widget | `custom_type`, `fallback`, `data` |


## 3. How to generate JSON on the Python side

### How to use the rumi_widgets helper

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

`.to_dict()` is not required when passing to `emit_widget` (automatically called internally). It will also be automatically converted when passed to the `widget` field of return.

### How to return directly as dict

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

Both produce completely equivalent results.


## 4. How to draw on the front end side

The Widget renderer is built into shell.html and shared by all Assets.

There are two ways to draw a widget from Asset's JS.

postMessage method: JS in the iframe sends Widget JSON to the parent window using postMessage, and the parent Widget renderer returns the drawing result.

Direct call method: Asset imports `widget-renderer.js` provided by the shell with `<script>` and calls `renderWidget(widgetJson, targetElement)` directly.

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

Unknown widget types fall back to text. `custom` type will use dedicated drawing if a custom renderer is registered in `user_data/widget_renderers/`, otherwise it will draw `fallback` Widget.


## 5. Examples of usage

### Example 1: Displaying file reading results in widget

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

### Example 2: Display progress in real time

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

### Example 3: User confirmation button

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

### Example 4: Collapse search results

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

### Example 5: Streaming indicator

```python
context["emit_widget"]({
    "type": "indicator",
    "label": "Analyzing code...",
    "state": "running",
    "animation": "pulse"
})
```

animation specifies the name defined in the theme's `animations` section. Animation names not recognized by the theme will be ignored.
