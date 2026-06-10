<!-- docs-i18n-links:start -->
[EN](../../widget.md) | [JP](./widget.md) | [KR](../ko/widget.md) | [CN](../zh-cn/widget.md)
<!-- docs-i18n-links:end -->

# widget.md — Rumi AI OS ウィジェット システムの仕様

## 1. 概要

ウィジェットは、バックエンドで「このデータをこのように表示したい」と宣言できる統一データ形式です。ウィジェットは純粋な JSON データであり、UI ライブラリではありません。

バックエンドのすべてのコード (ハンドラー、ツールの handler.py、プロンプト、フロー ノード) はウィジェット JSON を生成し、`emit_widget` で送信します。フロントエンド アセットはこの JSON を受け取り、テーマに従ってレンダリングします。

ウィジェットにはドメインの知識がありません。 「チャット ウィジェット」や「エージェント ウィジェット」はありません。テキスト、コード ブロック、画像、テーブル、プログレス バーなどの汎用表示プリミティブのみを定義します。何をどのように表示するかはウィジェットを生成する側（ツールやハンドラーなど）で決まり、どのように表示されるかはテーマによって決まります。

## 2. 設計哲学

**純粋なデータ**: ウィジェットは JSON 辞書です。レンダリング ロジックやイベント ハンドラーは含まれません。描画はフロントエンドの責任です。

**ドメイン非依存**: ウィジェット タイプは、「テキスト」、「イメージ」、「テーブル」などの汎用表示プリミティブです。特定のドメイン (チャット、エージェントなど) に特化したタイプはありません。

**ネスト可能**: ウィジェットはウィジェット内に配置できます。コードブロックとテキストをカードに配置したり、複数のボタンを一列に配置したりできます。

**フォールバックの仮定**: フロントエンドが特定のウィジェット タイプを描画できない場合は、テキスト表現にフォールバックします。カスタム ウィジェットには明示的なフォールバック ウィジェットがあります。 CLI 環境では、すべてのウィジェットはテキスト表現に戻ります。

**テーマからの分離**: Widget は「何を表示するか」のみを宣言します。テーマによって、その表示方法 (色、フォント、アニメーション、丸い角、影など) が決まります。ウィジェットは style_hint を使用してテーマにヒントを渡すことができますが、テーマはこれを無視できます。

## 3. ウィジェットのJSON仕様

### 3.1 基本プロパティ

すべてのウィジェットが持つ共通のプロパティ。

```json
{
  "type": "text",
  "id": "widget_001",
  "style_hint": {},
  "meta": {}
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `type` |文字列 |必須 |ウィジェットの種類。以下にリストされているタイプの 1 つ |
| `id` |文字列 |オプション |ウィジェットの識別子。ストリーミング更新中に特定のウィジェットを更新するために使用されます。
| `style_hint` |辞書 |オプション |テーマへのヒント。テーマは解釈される場合と解釈されない場合があります。
| `meta` |辞書 |任意 |あらゆるメタデータ。フロントエンドは無視して構いません。

### 3.2 JSON 式の例

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

## 4. ウィジェットの種類一覧

### 4.1 表示方式（14種類）

#### テキスト

テキストを表示します。

```json
{
  "type": "text",
  "text": "Hello, world"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `text` |文字列 |必須 |表示するテキスト |

CLI フォールバック: そのまま出力します。

#### コードブロック

ソースコードを表示します。

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 1
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `language` |文字列 |任意 |プログラミング言語 |
| `content` |文字列 |必須 |コード本体 |
| `filename` |文字列 |オプション |ファイル名(表示用) |
| `line_start` |整数 |オプション |開始行番号。デフォルト 1 |

CLI フォールバック: プレーン テキスト出力。

#### 相違点

違いを示します。

```json
{
  "type": "diff",
  "old_content": "old code",
  "new_content": "new code",
  "filename": "main.py"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `old_content` |文字列 |必須 |変更前の内容 |
| `new_content` |文字列 |必須 |新しいコンテンツ |
| `filename` |文字列 |任意 |ファイル名 |

CLI フォールバック: 統合された diff 形式。

#### 画像

画像を表示します。

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "説明",
  "width": 800,
  "height": 600
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 データまたは URL |
| `alt` |文字列 |任意 |代替テキスト |
| `width` |整数 |任意 |幅 (ピクセル) |
| `height` |整数 |任意 |高さ (ピクセル) |

CLI フォールバック: `[Image: {alt} {width}x{height}]`

#### スクリーンショット

スクリーンショットを表示します。画像の上にあり、URL やタイトルなどの追加情報が含まれています。

```json
{
  "type": "screenshot",
  "src": "base64 data",
  "url": "https://example.com",
  "title": "Example Page"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 データ |
| `url` |文字列 |任意 |スクリーンショットのソース URL |
| `title` |文字列 |オプション |ページタイトル |

CLI フォールバック: `[Screenshot: {title} - {url}]`

#### 進捗状況

進行状況を表示します。

```json
{
  "type": "progress",
  "label": "Reading file...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |進行状況ラベル |
| `current` |番号 |必須 |現在の値 |
| `total` |番号 |必須 |合計値 |
| `state` |文字列 |オプション | `"running"`、`"success"`、`"error"`。デフォルト `"running"` |

CLI フォールバック: `[████░░░░░░] 30% Reading file...`

#### ターミナル

ディスプレイ端子出力。

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\ndrwxr-xr-x ...",
  "exit_code": 0
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `command` |文字列 |任意 |実行されたコマンド |
| `output` |文字列 |必須 |出力内容 |
| `exit_code` |整数 |オプション |終了コード |

CLI フォールバック: `$ {command}\n{output}`

####テーブル

テーブルを表示します。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `headers` |リスト[文字列] |必須 |列ヘッダー |
| `rows` |リスト[リスト] |必須 |行データ |

CLI フォールバック: ASCII テーブル。

#### チャート

グラフを表示します。

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb", "Mar"],
  "data": [10, 25, 15]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `chart_type` |文字列 |必須 | `"bar"`、`"line"`、`"pie"`、`"scatter"` |
| `labels` |リスト[文字列] |必須 |ラベル |
| `data` |リスト[番号] |必須 |データ |

CLI フォールバック: 数値の概要テキスト。

#### ファイルツリー

ファイルツリーを表示します。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `tree` |リスト[辞書] |必須 |ツリーノード。各ノードには、`name`、`type`(`"file"` または `"dir"`)、`children` (オプション) があります。

CLI フォールバック: インデントされたテキスト。

#### マークダウン

Markdown テキストをレンダリングして表示します。

```json
{
  "type": "markdown",
  "content": "# Title\n\nSome **bold** text"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `content` |文字列 |必須 |マークダウンテキスト |

CLI フォールバック: プレーンテキスト。

#### オーディオ

オーディオを再生します。

```json
{
  "type": "audio",
  "src": "base64 or URL",
  "duration": 5000
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 データまたは URL |
| `duration` |整数 |任意 |再生時間 (ミリ秒) |

CLI フォールバック: `[Audio: {duration}ms]`

#### ビデオ

ビデオを再生します。

```json
{
  "type": "video",
  "src": "base64 or URL",
  "duration": 30000
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 データまたは URL |
| `duration` |整数 |任意 |再生時間 (ミリ秒) |

CLI フォールバック: `[Video: {duration}ms]`

#### 地図

地図を表示します。

```json
{
  "type": "map",
  "lat": 35.6812,
  "lng": 139.7671,
  "zoom": 15
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `lat` |番号 |必須 |緯度 |
| `lng` |番号 |必須 |経度 |
| `zoom` |整数 |オプション |ズームレベル。デフォルト 13 |

CLI フォールバック: `[Map: {lat}, {lng}]`

### 4.2 制御方式(6種類)

コントロール ウィジェットはユーザーからの入力を受け入れます。アセット内でのみ使用可能です。ユーザーの操作結果は、アセットの JS によって、emit_event を使用してバックエンドに送信されます。

#### 入力

テキスト入力フィールド。

```json
{
  "type": "input",
  "placeholder": "Type here...",
  "value": "",
  "multiline": false
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `placeholder` |文字列 |オプション |プレースホルダー |
| `value` |文字列 |任意 |初期値 |
| `multiline` |ブール値 |任意 |複数行。デフォルトは false |

#### ボタン

ボタン。

```json
{
  "type": "button",
  "label": "Execute",
  "action": "run_task",
  "variant": "primary"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ボタンラベル |
| `action` |文字列 |必須 |クリック時に発行されるアクション名 |
| `variant` |文字列 |オプション | `"primary"`、`"secondary"`、`"danger"`。デフォルト `"primary"` |

#### 選択

選択。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `options` |リスト[辞書] |必須 |選択肢。各要素には `label`、`value` があります。
| `value` |任意 |任意 |選択された値 |
| `multiple` |ブール値 |任意 |複数選択。デフォルトは false |

#### トグル

トグルスイッチ。

```json
{
  "type": "toggle",
  "label": "Enable feature",
  "value": false
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `value` |ブール値 |任意 |現在の状態。デフォルトは false |

#### スライダー

スライダー。

```json
{
  "type": "slider",
  "min": 0,
  "max": 100,
  "value": 50,
  "step": 1
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `min` |番号 |必須 |最小値 |
| `max` |番号 |必須 |最大 |
| `value` |番号 |任意 |現在値 |
| `step` |番号 |任意 |ステップ。デフォルト 1 |

#### チェックボックス

チェックボックス。

```json
{
  "type": "checkbox",
  "label": "I agree",
  "checked": false
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `checked` |ブール値 |オプション |チェックした状態。デフォルトは false |

### 4.3 レイアウトタイプ(6種類)

ウィジェット内にネストを構成するためのウィジェット。

#### コンテナ

汎用コンテナです。子ウィジェットをラップします。

```json
{
  "type": "container",
  "children": [
    {"type": "text", "text": "Title"},
    {"type": "code_block", "language": "python", "content": "..."}
  ]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `children` |リスト[ウィジェット] |必須 |子ウィジェットの配列 |

#### 行

子ウィジェットを横に並べます。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `children` |リスト[ウィジェット] |必須 |子ウィジェット |
| `gap` |整数 |任意 |子要素間のギャップ (ピクセル) |

####列

子ウィジェットを縦に並べます。

```json
{
  "type": "column",
  "children": [...],
  "gap": 8
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `children` |リスト[ウィジェット] |必須 |子ウィジェット |
| `gap` |整数 |任意 |子要素間のギャップ (ピクセル) |

#### タブ

タブを切り替えます。

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `tabs` |リスト[辞書] |必須 |各タブ。 `label`(文字列) と `content`(ウィジェット) を使用します。

#### 折りたたみ可能

折りたたみ可能。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |折りたたみラベル |
| `default_open` |ブール値 |オプション |初期状態。デフォルトは false |
| `children` |リスト[ウィジェット] |必須 |折りたたみ中の子ウィジェット |

#### カード

ヘッダー、本文、フッターの 3 つのセクションで構成されるカード。

```json
{
  "type": "card",
  "header": {"type": "text", "text": "Title"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "Footer"}
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `header` |ウィジェット |オプション |ヘッダー |
| `body` |ウィジェット |任意 |本文 |
| `footer` |ウィジェット |オプション |フッター |

### 4.4 ストリーミング型(2種類)

#### ストリーム

状態付きのストリーミング表示。 AIの思考プロセスやタスクの進捗状況を表示するために使用されます。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `states` | dict[文字列, dict] |必須 |状態名をキーとした定義。各状態には `animation`(文字列、オプション) と `label`(文字列) があります。

#### インジケーター

単一のステータスインジケーター。

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `state` |文字列 |必須 | `"running"`、`"success"`、`"error"`、`"waiting"` |
| `animation` |文字列 |オプション |テーマで定義されたアニメーション名 |

### 4.5カスタム(1種類)

#### カスタム

事前定義されたタイプに適合しないウィジェット。フロントエンドにcustom_typeレンダラーがある場合は専用のディスプレイが表示され、ない場合はフォールバックウィジェットが表示されます。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `custom_type` |文字列 |必須 |カスタムタイプ識別子 |
| `fallback` |ウィジェット |必須 |レンダラーが存在しない場合のフォールバック ウィジェット |
| `data` |辞書 |オプション |カスタム レンダラーに渡すデータ |

カスタムウィジェットレンダラーは`user_data/widget_renderers/`に配置できます。

```
user_data/widget_renderers/
├── 3d_viewer/
│   ├── renderer.js         # 描画ロジック
│   └── renderer.yaml       # メタ情報
└── graph_editor/
    ├── renderer.js
    └── renderer.yaml
```

renderer.yaml の構造:

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

## 5. rumi_widgets — Python ヘルパー ライブラリ

デフォルトで `lib/rumi_widgets/` に配置される Python ヘルパー。ツールのhandler.pyまたはhandler.pyにインポートして使用できます。使用法はオプションであり、JSON dict を直接返すのと同等です。

### 5.1 場所

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py      # Text, CodeBlock, Image, etc.
├── controls.py     # Input, Button, Select, etc.
├── layout.py       # Container, Row, Column, etc.
├── stream.py       # Stream, Indicator
└── custom.py       # Custom widget
```

### 5.2 インポート

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

各クラスはコンストラクターで Widget プロパティを受け取り、`.to_dict()` で JSON dict を返します。 `emit_widget` に直接渡す場合、`.to_dict()` を呼び出す必要はありません (emit_widget が内部で呼び出します)。

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

### 5.4 すべてのクラスのベース

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

## 6. Emit_widgetによる送信

ウィジェットは、ツールのコンテキスト API の汎用プリミティブ `emit_widget` を使用して送信されます。

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

Emit_widget は、途中まで進行した Widget をリアルタイムでフロントエンドに送信します。返される `widget` フィールドは、最終結果として表示されるウィジェットです。

Emit_widget で送信された Widget は、message.stream.data メッセージのデータに Widget JSON として格納され、フロントエンドに到達します。

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

## 7. フロントエンドでの描画

### 7.1 ウィジェット レンダラー

フロントエンドのshell.htmlには、ウィジェットレンダラーが組み込まれています。ウィジェット レンダラは、ウィジェット JSON の `type` フィールドを調べ、対応する描画関数を呼び出します。

描画関数は、アセットの iframe 内ではなく、シェル レベルで提供されます。アセットの JS は `window.renderWidget(widgetJson, targetElement)` を呼び出してウィジェットを描画します。

### 7.2 不明な型

ウィジェット レンダラーが `type` を認識できない場合は、次の順序でフォールバックします。

1. `user_data/widget_renderers/` にカスタム レンダラーがある場合は、それを使用します。
2. タイプが `"custom"` で、`fallback` が存在する場合、フォールバック ウィジェットを描画します
3. これらのいずれにも当てはまらない場合は、テキストを `[Unknown widget: {type}]` として表示します。

### 7.3 テーマとの連携

ウィジェット レンダラーは、レンダリング時に現在のテーマ (theme.yaml) を参照します。各ウィジェット タイプの描画設定は、テーマの `widgets` セクションで定義されます。

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

ウィジェットの`style_hint`は、テーマバリアント選択等のヒントとして使用されます。例えば、`style_hint: {"variant": "compact"}`であれば、テーマの`card.variants.compact`が適用されます。テーマはこのヒントを無視する可能性があります。

テーマの詳細については、theme.md を参照してください。

## 8. CLI フォールバック

CLI 環境では、すべてのウィジェットはテキスト表現に戻ります。各ウィジェットタイプのフォールバック式は次のとおりです。

|タイプ | CLI 式 |
|---|---|
| `text` |そのまま出力 |
| `code_block` |プレーンテキスト |
| `diff` |統合された差分 |
| `image` | `[Image: {alt} {width}x{height}]` |
| `screenshot` | `[Screenshot: {title} - {url}]` |
| `progress` | `[████░░░░░░] 30% {label}` |
| `terminal` | `$ {command}\n{output}` |
| `table` | ASCII テーブル |
| `chart` |数値サマリー |
| `file_tree` |インデントされたテキスト |
| `markdown` |プレーンテキスト |
| `audio` | `[Audio: {duration}ms]` |
| `video` | `[Video: {duration}ms]` |
| `map` | `[Map: {lat}, {lng}]` |
| `input` | `[Input: {placeholder}]` |
| `button` | `[{label}]` |
| `select` | `[Select: {options}]` |
| `toggle` | `[{label}: {value}]` |
| `slider` | `[{min}-{max}: {value}]` |
| `checkbox` | `[{checked ? "x" : " "}] {label}` |
| `container` |子を順番に出力する |
| `row` |子を `  ` で区切って水平方向に出力します。
| `column` |子を改行して縦方向に出力します。
| `tabs` | `--- {label} ---\n{content}` 各タブの出力 |
| `collapsible` | `▸ {label}\n{children}` |
| `card` | `[{header}]\n{body}\n{footer}` |
| `stream` | `[{current_state.label}]` |
| `indicator` | `[{state}] {label}` |
| `custom` |フォールバック ウィジェットの CLI 表現 |
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
# widget.md — ウィジェット システムの仕様

## 1. 概要

ウィジェットは、バックエンドで「このデータをこのように表示したい」と宣言できる統一データ形式です。ウィジェットは純粋な JSON データであり、UI ライブラリではありません。

バックエンドのコード (ツール、ハンドラー、フロー ノードの handler.py) はウィジェット JSON を生成し、コンテキストの `emit_widget` で送信します。フロントエンドはこの JSON を受け取り、テーマに従ってレンダリングします。

ウィジェットにはドメインの知識がありません。テキスト、コード ブロック、画像、テーブル、プログレス バーなどの汎用表示プリミティブのみを定義します。何をどのように表示するかはウィジェットを生成する側で決まり、どのように表示するかはテーマで決まります。


## 2. 設計哲学

**純粋なデータ**: ウィジェットは JSON 辞書です。レンダリング ロジック、イベント ハンドラー、スタイル定義は含まれません。描画はフロントエンドの責任です。

**ドメイン非依存**: ウィジェット タイプは、「テキスト」、「イメージ」、「テーブル」などの汎用プリミティブです。 「チャット メッセージ ウィジェット」や「エージェント ステータス ウィジェット」などのドメイン固有のタイプはありません。

**ネスト可能**: ウィジェットはウィジェット内に配置できます。カードの本文にコードブロックを挿入する、複数のボタンを一列に配置する、タブの各タブに異なるウィジェットを配置するなど。

**フォールバックの仮定**: フロントエンドが特定のウィジェット タイプを描画できない場合は、テキスト表現にフォールバックします。カスタム ウィジェットには明示的なフォールバック ウィジェットがあります。 CLI 環境では、すべてのウィジェットはテキスト表現に戻ります。

**テーマからの分離**: Widget は「何を表示するか」のみを宣言します。テーマによって、それがどのように提示されるかが決まります。ウィジェットは `style_hint` を使用してテーマにヒントを渡すことができますが、テーマはこれを無視できます。


## 3. 基本プロパティ

すべてのウィジェットが持つ共通のプロパティ。

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `type` |文字列 |必須 |ウィジェットの種類。セクション 4 にリストされているタイプのいずれか |
| `id` |文字列 |オプション |識別子。ストリーミング更新中に特定のウィジェットを置き換えるために使用されます。
| `style_hint` |辞書 |オプション |テーマへのヒント。テーマは解釈される場合と解釈されない場合があります。
| `meta` |辞書 |任意 |あらゆるメタデータ。フロントエンドは無視して構いません。

```json
{
  "type": "text",
  "id": "msg_001",
  "style_hint": {"variant": "muted"},
  "meta": {"source": "file_read_tool"}
}
```


## 4. ウィジェットの種類一覧

29種類。 14 ディスプレイ システム、6 コントロール システム、6 レイアウト システム、2 ストリーミング システム、および 1 カスタム システム。


### 4.1 表示方式（14種類）

データを視覚的に表示します。

---

#### テキスト

```json
{ "type": "text", "text": "Hello, world" }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `text` |文字列 |必須 |表示テキスト |

CLI: そのまま出力します。

---

#### コードブロック

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 10
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `language` |文字列 |任意 |言語名 |
| `content` |文字列 |必須 |コード本体 |
| `filename` |文字列 |任意 |ファイル名 |
| `line_start` |整数 |オプション |開始行番号。デフォルト 1 |

CLI: プレーンテキスト。

---

#### 相違点

```json
{
  "type": "diff",
  "old_content": "old",
  "new_content": "new",
  "filename": "main.py"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `old_content` |文字列 |必須 |変更前 |
| `new_content` |文字列 |必須 |変更後 |
| `filename` |文字列 |任意 |ファイル名 |

CLI: 統合差分。

---

#### 画像

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "description",
  "width": 800,
  "height": 600
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 データまたは URL |
| `alt` |文字列 |任意 |代替テキスト |
| `width` |整数 |任意 |幅 |
| `height` |整数 |任意 |身長 |

CLI: `[Image: {alt} {width}x{height}]`

---

#### スクリーンショット

```json
{
  "type": "screenshot",
  "src": "base64",
  "url": "https://example.com",
  "title": "Example"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 データ |
| `url` |文字列 |任意 |元の URL |
| `title` |文字列 |任意 |タイトル |

CLI: `[Screenshot: {title} - {url}]`

---

#### 進捗状況

```json
{
  "type": "progress",
  "label": "Reading...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `current` |番号 |必須 |現在の値 |
| `total` |番号 |必須 |合計値 |
| `state` |文字列 |オプション | `"running"` / `"success"` / `"error"`。デフォルト `"running"` |

CLI: `[████░░░░░░] 30% Reading...`

---

#### ターミナル

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\n...",
  "exit_code": 0
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `command` |文字列 |任意 |実行コマンド |
| `output` |文字列 |必須 |出力 |
| `exit_code` |整数 |オプション |終了コード |

CLI: `$ {command}\n{output}`

---

####テーブル

```json
{
  "type": "table",
  "headers": ["Name", "Size"],
  "rows": [["main.py", "1.2KB"], ["test.py", "800B"]]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `headers` |リスト[文字列] |必須 |列ヘッダー |
| `rows` |リスト[リスト] |必須 |行データ |

CLI: ASCII テーブル。

---

#### チャート

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb"],
  "data": [10, 25]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `chart_type` |文字列 |必須 | `"bar"` / `"line"` / `"pie"` / `"scatter"` |
| `labels` |リスト[文字列] |必須 |ラベル |
| `data` |リスト[番号] |必須 |データ |

CLI: 数値の概要。

---

#### ファイルツリー

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `tree` |リスト[辞書] |必須 |ノード配列。各ノードは `name`(文字列)、`type`(`"file"` または `"dir"`)、`children`(リスト、オプション) | です。

CLI: インデントされたテキスト。

---

#### マークダウン

```json
{ "type": "markdown", "content": "# Title\n\n**bold**" }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `content` |文字列 |必須 |マークダウンテキスト |

CLI: プレーンテキスト。

---

#### オーディオ

```json
{ "type": "audio", "src": "base64 or URL", "duration": 5000 }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 または URL |
| `duration` |整数 |任意 |ミリ秒 |

CLI: `[Audio: {duration}ms]`

---

#### ビデオ

```json
{ "type": "video", "src": "base64 or URL", "duration": 30000 }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `src` |文字列 |必須 | Base64 または URL |
| `duration` |整数 |任意 |ミリ秒 |

CLI: `[Video: {duration}ms]`

---

#### 地図

```json
{ "type": "map", "lat": 35.6812, "lng": 139.7671, "zoom": 15 }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `lat` |番号 |必須 |緯度 |
| `lng` |番号 |必須 |経度 |
| `zoom` |整数 |オプション |ズームレベル。デフォルト 13 |

CLI: `[Map: {lat}, {lng}]`


### 4.2 制御方式(6種類)

ユーザー入力を受け入れます。ユーザー操作の結果は、`emit_event` を使用してアセットの JS によってバックエンドに返されます。

---

#### 入力

```json
{ "type": "input", "placeholder": "Type here...", "value": "", "multiline": false }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `placeholder` |文字列 |オプション |プレースホルダー |
| `value` |文字列 |任意 |初期値 |
| `multiline` |ブール値 |任意 |複数行。デフォルトは false |

---

#### ボタン

```json
{ "type": "button", "label": "Execute", "action": "run_task", "variant": "primary" }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `action` |文字列 |必須 |アクション名 | をクリックします。
| `variant` |文字列 |オプション | `"primary"` / `"secondary"` / `"danger"`。デフォルト `"primary"` |

---

#### 選択

```json
{
  "type": "select",
  "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
  "value": "a",
  "multiple": false
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `options` |リスト[辞書] |必須 |各要素は `label`(文字列)、`value`(任意) | です。
| `value` |任意 |任意 |現在値 |
| `multiple` |ブール値 |任意 |複数選択。デフォルトは false |

---

#### トグル

```json
{ "type": "toggle", "label": "Enable", "value": false }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `value` |ブール値 |オプション |デフォルトは false |

---

#### スライダー

```json
{ "type": "slider", "min": 0, "max": 100, "value": 50, "step": 1 }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `min` |番号 |必須 |最小値 |
| `max` |番号 |必須 |最大 |
| `value` |番号 |任意 |現在値 |
| `step` |番号 |任意 |ステップ。デフォルト 1 |

---

#### チェックボックス

```json
{ "type": "checkbox", "label": "I agree", "checked": false }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `checked` |ブール値 |オプション |デフォルトは false |


### 4.3 レイアウトタイプ(6種類)

ウィジェット内に入れ子構造を作成します。

---

#### コンテナ

```json
{ "type": "container", "children": [{"type": "text", "text": "..."}, {"type": "code_block", "content": "..."}] }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `children` |リスト[ウィジェット] |必須 |子ウィジェット |

---

#### 行

```json
{ "type": "row", "children": [...], "gap": 8 }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `children` |リスト[ウィジェット] |必須 |子ウィジェット |
| `gap` |整数 |任意 |間隔 (ピクセル) |

---

####列

```json
{ "type": "column", "children": [...], "gap": 8 }
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `children` |リスト[ウィジェット] |必須 |子ウィジェット |
| `gap` |整数 |任意 |間隔 (ピクセル) |

---

#### タブ

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `tabs` |リスト[辞書] |必須 |各要素は `label`(文字列)、`content`(ウィジェット) |

---

#### 折りたたみ可能

```json
{
  "type": "collapsible",
  "label": "Details",
  "default_open": false,
  "children": [{"type": "text", "text": "hidden"}]
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `default_open` |ブール値 |オプション |デフォルトは false |
| `children` |リスト[ウィジェット] |必須 |子ウィジェット |

---

#### カード

```json
{
  "type": "card",
  "header": {"type": "indicator", "label": "done", "state": "success"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "1.2KB"}
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `header` |ウィジェット |オプション |ヘッダー |
| `body` |ウィジェット |任意 |本文 |
| `footer` |ウィジェット |オプション |フッター |


### 4.4 ストリーミング型(2種類)

---

#### ストリーム

複数の状態を含むストリーミング表示。

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

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `states` | dict[文字列, dict] |必須 |州名 → `label`(文字列) + `animation`(文字列、オプション) |

---

#### インジケーター

単一のステータスインジケーター。

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `label` |文字列 |必須 |ラベル |
| `state` |文字列 |必須 | `"running"` / `"success"` / `"error"` / `"waiting"` |
| `animation` |文字列 |オプション |テーマ定義のアニメーション名 |


### 4.5カスタム(1種類)

#### カスタム

事前定義されたタイプに適合しない表示。 `user_data/widget_renderers/`がレンダラーを持っている場合は専用の描画が行われ、そうでない場合は`fallback`が描画されます。

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {"type": "image", "src": "preview.png", "alt": "3D Preview"},
  "data": {"model_url": "model.glb", "rotation": [0, 45, 0]}
}
```

|プロパティ |タイプ |必須 |説明 |
|---|---|---|---|
| `custom_type` |文字列 |必須 |カスタムタイプ識別子 |
| `fallback` |ウィジェット |必須 |レンダラーが存在しない場合のフォールバック |
| `data` |辞書 |オプション |カスタム レンダラーに渡すデータ |

カスタムレンダラーの配置:

```
user_data/widget_renderers/
└── 3d_viewer/
    ├── renderer.js
    └── renderer.yaml
```

レンダラー.yaml:

```yaml
custom_type: "3d_viewer"
name: "3D Model Viewer"
version: "1.0.0"
entry: "renderer.js"
```

CLI: フォールバック ウィジェットの CLI 表現。


## 5. rumi_widgets — Python ヘルパー ライブラリ

デフォルトは`lib/rumi_widgets/`に配置されます。 handler.pyにインポートして利用できます。使用は任意です。 JSON dict を直接返すのと同じです。

### 5.1 配置

```
ecosystem/defaults/lib/rumi_widgets/
├── __init__.py
├── display.py
├── controls.py
├── layout.py
├── stream.py
└── custom.py
```

### 5.2 インポート

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

### 5.3 基本クラス

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

### 5.4 使用例

クラス構築と JSON dict は同等です。

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


## 6. 送信

### 6.1 エミットウィジェット

ツールのhandler.py内で`context["emit_widget"]`を呼び出します。進行中のウィジェットをリアルタイムでフロントエンドに送信します。

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

`emit_widget` で送信されたウィジェットはストリーミング メッセージとして転送されます。戻り値の `widget` フィールドは、最終結果ウィジェットです。

### 6.2 コミュニケーション表現

Emit_widget によって送信された Widget は、JSON Lines メッセージのデータに格納されます。

```json
{"type":"message.stream.data","component":"target_asset","data":{"stream_id":"s1","widget":{"type":"progress","label":"Processing...","current":0,"total":3}}}
```

最終結果ウィジェットは、message.send を使用して送信されます。

```json
{"type":"message.send","component":"target_asset","data":{"action":"tool_result","widget":{"type":"card","header":{"type":"indicator","label":"task","state":"success"},"body":{"type":"text","text":"done"}}}}
```

### 6.3 IDによる置換

`id`をウィジェットに追加して発行すると、フロントエンドは同じ`id`でウィジェットを上書き描画します。進行状況を更新するために使用されます。

```python
context["emit_widget"](Progress(id="p1", label="Step 1", current=1, total=3))
# ...
context["emit_widget"](Progress(id="p1", label="Step 2", current=2, total=3))
# フロントエンドは id="p1" の Widget を置き換える
```


## 7. フロントエンドでの描画

### 7.1 ウィジェット レンダラー

シェルにはウィジェット レンダラーが組み込まれています。レンダラーは Widget JSON の `type` を参照し、対応する描画関数を呼び出します。

次のように Asset の JS 内から呼び出します。

```javascript
window.rumiWidgets.render(widgetJson, targetElement);
```

### 7.2 描画フォールバック順序

1. タイプが 29 の定義済みタイプのいずれかである場合、組み込みレンダラーを使用して描画します。
2. タイプが `"custom"` の場合、`user_data/widget_renderers/{custom_type}/` レンダラーを検索します。
3. カスタム レンダラーがある場合は、専用のレンダリングを使用します。
4. そうでない場合は、`fallback` 組み込みレンダラーを使用してウィジェットを描画します
5. 上記のいずれにも当てはまらない場合は、テキストを`[Unknown widget: {type}]`として表示します。

### 7.3 テーマのコラボレーション

ウィジェット レンダラーは、レンダリング時に現在のテーマ (theme.yaml) の `widgets` セクションを参照します。

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

ウィジェットの`style_hint`でテーマのバリアントを選択できます。

```json
{"type": "card", "style_hint": {"variant": "compact"}, "body": {"type": "text", "text": "..."}}
```

テーマの`card.variants.compact`が該当します。テーマに対応するバリアントがない場合は、`default` が使用されます。

テーマの詳細な仕様については、theme.md を参照してください。


## 8. CLI フォールバック

CLI 環境にはフロントエンド ウィジェット レンダラーがありません。すべてのウィジェットはテキスト表現に変換されます。

|タイプ | CLI 式 |
|---|---|
| `text` |そのまま出力 |
| `code_block` |プレーンテキスト |
| `diff` |統合された差分 |
| `image` | `[Image: {alt} {width}x{height}]` |
| `screenshot` | `[Screenshot: {title} - {url}]` |
| `progress` | `[████░░░░░░] 30% {label}` |
| `terminal` | `$ {command}\n{output}` |
| `table` | ASCII テーブル |
| `chart` |数値サマリー |
| `file_tree` |インデントされたテキスト |
| `markdown` |プレーンテキスト |
| `audio` | `[Audio: {duration}ms]` |
| `video` | `[Video: {duration}ms]` |
| `map` | `[Map: {lat}, {lng}]` |
| `input` | `[Input: {placeholder}]` |
| `button` | `[{label}]` |
| `select` | `[Select: {options}]` |
| `toggle` | `[{label}: {value}]` |
| `slider` | `[{min}-{max}: {value}]` |
| `checkbox` | `[{checked ? "x" : " "}] {label}` |
| `container` |子を順番に出力する |
| `row` |子を水平方向にスペースで区切って出力します。
| `column` |子を改行して縦方向に出力します。
| `tabs` | `--- {label} ---\n{content}` |
| `collapsible` | `▸ {label}\n{children}` |
| `card` | `[{header}]\n{body}\n{footer}` |
| `stream` | `[{current_state.label}]` |
| `indicator` | `[{state}] {label}` |
| `custom` |フォールバックの CLI 表現 |

CLI フォールバック実装は、`lib/rumi_widgets/` の各クラスの `to_cli()` メソッドとして提供されます。トランスポート層が CLI モードを検出した場合、emit_widget は `to_dict()` ではなく `to_cli()` の結果を出力します。
