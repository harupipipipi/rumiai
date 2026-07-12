# Widgets ガイド

## 1. ウィジェットの概念

Widget はバックエンドが「このデータをこう表示してほしい」と宣言するための統一的な JSON データ形式である。Widget は UI ライブラリではなく純粋なデータである。

バックエンドのあらゆるコード（handler、tool の handler.py、prompt、Flow ノード）が Widget JSON を生成し、`emit_widget` で送出する。フロントエンドの shell.html 内の Widget レンダラーがこの JSON を受け取り、テーマに従って描画する。

Widget はドメイン非依存である。「チャット用Widget」「エージェント用Widget」は存在しない。テキスト、コードブロック、画像、テーブル、プログレスバーといった汎用的な表示プリミティブのみを定義する。全 29 種（表示 14 + コントロール 6 + レイアウト 6 + ストリーミング 2 + カスタム 1）。


## 2. lib/rumi_widgets/ のクラス一覧と用途

`ecosystem/defaults/lib/rumi_widgets/` に配置される Python ヘルパーライブラリ。使用は任意であり、直接 dict を返しても等価。

### display.py（表示系 14 種）

| クラス | 用途 | 主要パラメータ |
|---|---|---|
| `Text` | テキスト表示 | `text` |
| `CodeBlock` | ソースコード表示 | `language`, `content`, `filename`, `line_start` |
| `Diff` | 差分表示 | `old_content`, `new_content`, `filename` |
| `Image` | 画像表示 | `src`, `alt`, `width`, `height` |
| `Screenshot` | スクリーンショット表示 | `src`, `url`, `title` |
| `Progress` | 進捗表示 | `label`, `current`, `total`, `state` |
| `Terminal` | ターミナル出力表示 | `command`, `output`, `exit_code` |
| `Table` | テーブル表示 | `headers`, `rows` |
| `Chart` | グラフ表示 | `chart_type`, `labels`, `data` |
| `FileTree` | ファイルツリー表示 | `tree` |
| `Markdown` | Markdown レンダリング | `content` |
| `Audio` | 音声再生 | `src`, `duration` |
| `Video` | 動画再生 | `src`, `duration` |
| `Map` | 地図表示 | `lat`, `lng`, `zoom` |

### controls.py（コントロール系 6 種）

| クラス | 用途 | 主要パラメータ |
|---|---|---|
| `Input` | テキスト入力 | `placeholder`, `value`, `multiline` |
| `Button` | ボタン | `label`, `action`, `variant` |
| `Select` | 選択 | `options`, `value`, `multiple` |
| `Toggle` | トグルスイッチ | `label`, `value` |
| `Slider` | スライダー | `min`, `max`, `value`, `step` |
| `Checkbox` | チェックボックス | `label`, `checked` |

### layout.py（レイアウト系 6 種）

| クラス | 用途 | 主要パラメータ |
|---|---|---|
| `Container` | 汎用コンテナ | `children` |
| `Row` | 横並びレイアウト | `children`, `gap` |
| `Column` | 縦並びレイアウト | `children`, `gap` |
| `Tabs` | タブ切り替え | `tabs` (各 `{label, content}`) |
| `Collapsible` | 折りたたみ | `label`, `default_open`, `children` |
| `Card` | ヘッダ/ボディ/フッタ付きカード | `header`, `body`, `footer` |

### stream.py（ストリーミング系 2 種）

| クラス | 用途 | 主要パラメータ |
|---|---|---|
| `Stream` | 状態ベースストリーム表示 | `states` (dict) |
| `Indicator` | 単一状態インジケータ | `label`, `state`, `animation` |

### custom.py（カスタム 1 種）

| クラス | 用途 | 主要パラメータ |
|---|---|---|
| `Custom` | 定義外Widget | `custom_type`, `fallback`, `data` |


## 3. Python 側での JSON 生成方法

### rumi_widgets ヘルパーを使う方法

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

`emit_widget` に渡す場合は `.to_dict()` 不要（内部で自動呼び出し）。return の `widget` フィールドに渡す場合も自動変換される。

### 直接 dict で返す方法

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

両方とも完全に等価な結果を生む。


## 4. フロントエンド側での描画方法

Widget レンダラーは shell.html に組み込まれ、全 Asset が共有する。

Asset の JS から Widget を描画する方法は 2 つある。

postMessage 方式: iframe 内の JS が親ウィンドウに Widget JSON を postMessage で送り、親の Widget レンダラーが描画結果を返す。

直接呼び出し方式: shell が提供する `widget-renderer.js` を Asset が `<script>` で取り込み、`renderWidget(widgetJson, targetElement)` を直接呼び出す。

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

未知の Widget type はテキストにフォールバックする。`custom` type は `user_data/widget_renderers/` にカスタムレンダラーが登録されていれば専用描画、なければ `fallback` Widget を描画する。


## 5. 使い方の例

### 例1: ファイル読み取り結果を Widget で表示

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

### 例2: 進捗をリアルタイム表示

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

### 例3: ユーザー確認ボタン

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

### 例4: 検索結果を折りたたみ表示

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

### 例5: ストリーミング中のインジケータ

```python
context["emit_widget"]({
    "type": "indicator",
    "label": "Analyzing code...",
    "state": "running",
    "animation": "pulse"
})
```

animation はテーマの `animations` セクションで定義された名前を指定する。テーマが認識しない animation 名は無視される。
