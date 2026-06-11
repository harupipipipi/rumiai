<!-- docs-i18n-links:start -->
[EN](../../widgets.md) | [JP](./widgets.md) | [KR](../ko/widgets.md) | [CN](../zh-cn/widgets.md)
<!-- docs-i18n-links:end -->

# ウィジェットガイド

## 1. ウィジェットの概念

ウィジェットは、バックエンドが「このデータをこのように表示したい」と宣言できるようにする統一された JSON データ形式です。ウィジェットは純粋なデータであり、UI ライブラリではありません。

バックエンドのすべてのコード (ハンドラー、ツールの handler.py、プロンプト、フロー ノード) はウィジェット JSON を生成し、`emit_widget` で送信します。フロントエンドのshell.html内のウィジェットレンダラーはこのJSONを受け取り、テーマに従って描画します。

ウィジェットはドメインに依存しません。 「チャット ウィジェット」や「エージェント ウィジェット」はありません。テキスト、コード ブロック、画像、テーブル、プログレス バーなどの汎用表示プリミティブのみを定義します。全29種類（ディスプレイ14＋コントロール6＋レイアウト6＋ストリーミング2＋カスタム1）。


## 2. クラスリストとlib/rumi_widgets/の使い方

Python ヘルパー ライブラリは `ecosystem/defaults/lib/rumi_widgets/` にあります。使用法はオプションであり、dict を直接返すのと同等です。

### display.py (14 種類の表示)

|クラス |使い方 |主なパラメータ |
|---|---|---|
| `Text` |テキスト表示 | `text` |
| `CodeBlock` |ソースコードを表示 | `language`、`content`、`filename`、`line_start` |
| `Diff` |差分表示 | `old_content`、`new_content`、`filename` |
| `Image` |画像表示 | `src`、`alt`、`width`、`height` |
| `Screenshot` |スクリーンショット表示 | `src`、`url`、`title` |
| `Progress` |進行状況表示 | `label`、`current`、`total`、`state` |
| `Terminal` |端子出力表示 | `command`、`output`、`exit_code` |
| `Table` |テーブル表示 | `headers`、`rows` |
| `Chart` |グラフ表示 | `chart_type`、`labels`、`data` |
| `FileTree` |ファイルツリー表示 | `tree` |
| `Markdown` |マークダウンレンダリング | `content` |
| `Audio` |オーディオの再生 | `src`、`duration` |
| `Video` |ビデオ再生 | `src`、`duration` |
| `Map` |地図表示 | `lat`、`lng`、`zoom` |

### controls.py (6種類のコントロール)

|クラス |使い方 |主なパラメータ |
|---|---|---|
| `Input` |テキスト入力 | `placeholder`、`value`、`multiline` |
| `Button` |ボタン | `label`、`action`、`variant` |
| `Select` |選択 | `options`、`value`、`multiple` |
| `Toggle` |トグルスイッチ | `label`、`value` |
| `Slider` |スライダー | `min`、`max`、`value`、`step` |
| `Checkbox` |チェックボックス | `label`、`checked` |

### layout.py (6種類のレイアウト)

|クラス |使い方 |主なパラメータ |
|---|---|---|
| `Container` |汎用コンテナ | `children` |
| `Row` |並列レイアウト | `children`、`gap` |
| `Column` |縦型レイアウト | `children`、`gap` |
| `Tabs` |タブ切り替え | `tabs` (各`{label, content}`) |
| `Collapsible` |折りたたむ | `label`、`default_open`、`children` |
| `Card` |ヘッダー/本文/フッター付きカード | `header`、`body`、`footer` |

### stream.py (ストリーミングタイプ2種類)

|クラス |使い方 |主なパラメータ |
|---|---|---|
| `Stream` |状態ベースのストリーム表示 | `states` (辞書) |
| `Indicator` |単一状態インジケータ | `label`、`state`、`animation` |

### custom.py (カスタム1種類)

|クラス |使い方 |主なパラメータ |
|---|---|---|
| `Custom` |未定義のウィジェット | `custom_type`、`fallback`、`data` |


## 3. Python側でJSONを生成する方法

### rumi_widgets ヘルパーの使用方法

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

`.to_dict()` は、`emit_widget` に渡す場合には必要ありません (内部で自動的に呼び出されます)。また、戻り値の `widget` フィールドに渡されるときにも自動的に変換されます。

### dict として直接返す方法

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

どちらも完全に同等の結果を生成します。


## 4. フロントエンド側の描画方法

ウィジェット レンダラーは shell.html に組み込まれており、すべてのアセットで共有されます。

Asset の JS からウィジェットを描画するには 2 つの方法があります。

postMessage メソッド: iframe 内の JS は、postMessage を使用して Widget JSON を親ウィンドウに送信し、親 Widget レンダラが描画結果を返します。

直接呼び出し方式：シェルが提供する`widget-renderer.js`を`<script>`でアセットインポートし、`renderWidget(widgetJson, targetElement)`を直接呼び出します。

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

不明なウィジェット タイプはテキストに戻ります。 `custom`タイプは、`user_data/widget_renderers/`にカスタムレンダラーが登録されている場合は専用の描画を使用し、そうでない場合は`fallback`のウィジェットを描画します。


## 5. 使用例

### 例1: ファイルの読み込み結果をウィジェットに表示する

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

### 例 2: 進行状況をリアルタイムで表示する

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

### 例 3: ユーザー確認ボタン

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

### 例 4: 検索結果を折りたたむ

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

### 例 5: ストリーミングインジケーター

```python
context["emit_widget"]({
    "type": "indicator",
    "label": "Analyzing code...",
    "state": "running",
    "animation": "pulse"
})
```

アニメーションでは、テーマの `animations` セクションで定義された名前を指定します。テーマで認識されないアニメーション名は無視されます。
