
```markdown
# widget.md — Rumi AI OS Widget System 仕様書

## 1. 概要

Widget はバックエンドが「このデータをこう表示してほしい」と宣言するための統一的なデータ形式である。Widget は純粋な JSON データであり、UI ライブラリではない。

バックエンドのあらゆるコード（handler、tool の handler.py、prompt、Flow ノード）が Widget JSON を生成し、`emit_widget` で送出する。フロントエンドの Asset がこの JSON を受け取り、テーマに従って描画する。

Widget はドメイン知識を持たない。「チャット用Widget」「エージェント用Widget」は存在しない。テキスト、コードブロック、画像、テーブル、プログレスバーといった汎用的な表示プリミティブのみを定義する。何をどう表示するかは Widget を生成する側（tool、handler 等）が決め、どう見せるかはテーマが決める。

## 2. 設計思想

**純粋なデータ**: Widget は JSON dict である。レンダリングロジックやイベントハンドラを含まない。描画はフロントエンドの責務。

**ドメイン非依存**: Widget の型は「テキスト」「画像」「テーブル」等の汎用表示プリミティブである。特定のドメイン（チャット、エージェント等）に特化した型は存在しない。

**ネスト可能**: Widget の中に Widget を入れられる。Card の中に CodeBlock と Text を入れる、Row の中に複数の Button を並べる、等。

**フォールバック前提**: フロントエンドがある Widget 型を描画できない場合、テキスト表現にフォールバックする。Custom Widget は明示的な fallback Widget を持つ。CLI 環境では全ての Widget がテキスト表現にフォールバックする。

**テーマとの分離**: Widget は「何を表示するか」のみを宣言する。「どう見せるか」（色、フォント、アニメーション、角丸、影等）はテーマが決定する。Widget は style_hint でテーマへのヒントを渡せるが、テーマはこれを無視してもよい。

## 3. Widget JSON 仕様

### 3.1 基底プロパティ

全ての Widget が持つ共通プロパティ。

```json
{
  "type": "text",
  "id": "widget_001",
  "style_hint": {},
  "meta": {}
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `type` | string | 必須 | Widget の型。後述の型一覧のいずれか |
| `id` | string | 任意 | Widget の識別子。ストリーミング更新時に特定の Widget を更新するために使用 |
| `style_hint` | dict | 任意 | テーマへのヒント。テーマが解釈してもしなくてもよい |
| `meta` | dict | 任意 | 任意のメタデータ。フロントエンドは無視してよい |

### 3.2 JSON 表現例

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

## 4. Widget 型一覧

### 4.1 表示系（14種）

#### Text

テキストを表示する。

```json
{
  "type": "text",
  "text": "Hello, world"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `text` | string | 必須 | 表示するテキスト |

CLI フォールバック: そのまま出力。

#### CodeBlock

ソースコードを表示する。

```json
{
  "type": "code_block",
  "language": "python",
  "content": "print('hello')",
  "filename": "main.py",
  "line_start": 1
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `language` | string | 任意 | プログラミング言語 |
| `content` | string | 必須 | コード本体 |
| `filename` | string | 任意 | ファイル名（表示用） |
| `line_start` | integer | 任意 | 開始行番号。デフォルト 1 |

CLI フォールバック: プレーンテキスト出力。

#### Diff

差分を表示する。

```json
{
  "type": "diff",
  "old_content": "old code",
  "new_content": "new code",
  "filename": "main.py"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `old_content` | string | 必須 | 変更前の内容 |
| `new_content` | string | 必須 | 変更後の内容 |
| `filename` | string | 任意 | ファイル名 |

CLI フォールバック: unified diff 形式。

#### Image

画像を表示する。

```json
{
  "type": "image",
  "src": "base64 or URL",
  "alt": "説明",
  "width": 800,
  "height": 600
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 データまたは URL |
| `alt` | string | 任意 | 代替テキスト |
| `width` | integer | 任意 | 幅（ピクセル） |
| `height` | integer | 任意 | 高さ（ピクセル） |

CLI フォールバック: `[Image: {alt} {width}x{height}]`

#### Screenshot

スクリーンショットを表示する。Image の上位で、URLとタイトルの付加情報を持つ。

```json
{
  "type": "screenshot",
  "src": "base64 data",
  "url": "https://example.com",
  "title": "Example Page"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 データ |
| `url` | string | 任意 | スクリーンショット元の URL |
| `title` | string | 任意 | ページタイトル |

CLI フォールバック: `[Screenshot: {title} - {url}]`

#### Progress

進捗を表示する。

```json
{
  "type": "progress",
  "label": "Reading file...",
  "current": 3,
  "total": 10,
  "state": "running"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | 進捗ラベル |
| `current` | number | 必須 | 現在値 |
| `total` | number | 必須 | 合計値 |
| `state` | string | 任意 | `"running"`, `"success"`, `"error"`. デフォルト `"running"` |

CLI フォールバック: `[████░░░░░░] 30% Reading file...`

#### Terminal

ターミナル出力を表示する。

```json
{
  "type": "terminal",
  "command": "ls -la",
  "output": "total 8\ndrwxr-xr-x ...",
  "exit_code": 0
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `command` | string | 任意 | 実行されたコマンド |
| `output` | string | 必須 | 出力内容 |
| `exit_code` | integer | 任意 | 終了コード |

CLI フォールバック: `$ {command}\n{output}`

#### Table

テーブルを表示する。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `headers` | list[string] | 必須 | 列ヘッダ |
| `rows` | list[list] | 必須 | 行データ |

CLI フォールバック: ASCII テーブル。

#### Chart

グラフを表示する。

```json
{
  "type": "chart",
  "chart_type": "bar",
  "labels": ["Jan", "Feb", "Mar"],
  "data": [10, 25, 15]
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `chart_type` | string | 必須 | `"bar"`, `"line"`, `"pie"`, `"scatter"` |
| `labels` | list[string] | 必須 | ラベル |
| `data` | list[number] | 必須 | データ |

CLI フォールバック: 数値要約テキスト。

#### FileTree

ファイルツリーを表示する。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `tree` | list[dict] | 必須 | ツリーノード。各ノードは `name`, `type`(`"file"` or `"dir"`), `children`(任意) を持つ |

CLI フォールバック: インデント付きテキスト。

#### Markdown

Markdown テキストをレンダリングして表示する。

```json
{
  "type": "markdown",
  "content": "# Title\n\nSome **bold** text"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `content` | string | 必須 | Markdown テキスト |

CLI フォールバック: プレーンテキスト。

#### Audio

音声を再生する。

```json
{
  "type": "audio",
  "src": "base64 or URL",
  "duration": 5000
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 データまたは URL |
| `duration` | integer | 任意 | 再生時間（ミリ秒） |

CLI フォールバック: `[Audio: {duration}ms]`

#### Video

動画を再生する。

```json
{
  "type": "video",
  "src": "base64 or URL",
  "duration": 30000
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 データまたは URL |
| `duration` | integer | 任意 | 再生時間（ミリ秒） |

CLI フォールバック: `[Video: {duration}ms]`

#### Map

地図を表示する。

```json
{
  "type": "map",
  "lat": 35.6812,
  "lng": 139.7671,
  "zoom": 15
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `lat` | number | 必須 | 緯度 |
| `lng` | number | 必須 | 経度 |
| `zoom` | integer | 任意 | ズームレベル。デフォルト 13 |

CLI フォールバック: `[Map: {lat}, {lng}]`

### 4.2 コントロール系（6種）

コントロール系 Widget はユーザーからの入力を受け付ける。Asset 内でのみ使用可能。ユーザーの操作結果は Asset の JS が emit_event でバックエンドに送信する。

#### Input

テキスト入力フィールド。

```json
{
  "type": "input",
  "placeholder": "Type here...",
  "value": "",
  "multiline": false
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `placeholder` | string | 任意 | プレースホルダ |
| `value` | string | 任意 | 初期値 |
| `multiline` | boolean | 任意 | 複数行。デフォルト false |

#### Button

ボタン。

```json
{
  "type": "button",
  "label": "Execute",
  "action": "run_task",
  "variant": "primary"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ボタンラベル |
| `action` | string | 必須 | クリック時に発行されるアクション名 |
| `variant` | string | 任意 | `"primary"`, `"secondary"`, `"danger"`. デフォルト `"primary"` |

#### Select

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `options` | list[dict] | 必須 | 選択肢。各要素は `label`, `value` を持つ |
| `value` | any | 任意 | 選択中の値 |
| `multiple` | boolean | 任意 | 複数選択。デフォルト false |

#### Toggle

トグルスイッチ。

```json
{
  "type": "toggle",
  "label": "Enable feature",
  "value": false
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `value` | boolean | 任意 | 現在の状態。デフォルト false |

#### Slider

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `min` | number | 必須 | 最小値 |
| `max` | number | 必須 | 最大値 |
| `value` | number | 任意 | 現在値 |
| `step` | number | 任意 | ステップ。デフォルト 1 |

#### Checkbox

チェックボックス。

```json
{
  "type": "checkbox",
  "label": "I agree",
  "checked": false
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `checked` | boolean | 任意 | チェック状態。デフォルト false |

### 4.3 レイアウト系（6種）

Widget 内部でネストを構成するための Widget。

#### Container

汎用コンテナ。子 Widget を包む。

```json
{
  "type": "container",
  "children": [
    {"type": "text", "text": "Title"},
    {"type": "code_block", "language": "python", "content": "..."}
  ]
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `children` | list[Widget] | 必須 | 子 Widget の配列 |

#### Row

子 Widget を横に並べる。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `children` | list[Widget] | 必須 | 子 Widget |
| `gap` | integer | 任意 | 子要素間の隙間（ピクセル） |

#### Column

子 Widget を縦に並べる。

```json
{
  "type": "column",
  "children": [...],
  "gap": 8
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `children` | list[Widget] | 必須 | 子 Widget |
| `gap` | integer | 任意 | 子要素間の隙間（ピクセル） |

#### Tabs

タブ切り替え。

```json
{
  "type": "tabs",
  "tabs": [
    {"label": "Output", "content": {"type": "text", "text": "..."}},
    {"label": "Logs", "content": {"type": "terminal", "output": "..."}}
  ]
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `tabs` | list[dict] | 必須 | 各タブ。`label`(string) と `content`(Widget) を持つ |

#### Collapsible

折りたたみ。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | 折りたたみラベル |
| `default_open` | boolean | 任意 | 初期状態。デフォルト false |
| `children` | list[Widget] | 必須 | 折りたたみ内の子 Widget |

#### Card

ヘッダ・ボディ・フッタの3区画を持つカード。

```json
{
  "type": "card",
  "header": {"type": "text", "text": "Title"},
  "body": {"type": "code_block", "content": "..."},
  "footer": {"type": "text", "text": "Footer"}
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `header` | Widget | 任意 | ヘッダ |
| `body` | Widget | 任意 | ボディ |
| `footer` | Widget | 任意 | フッタ |

### 4.4 ストリーミング系（2種）

#### Stream

状態を持つストリーミング表示。AI の思考過程やタスク進行の表示に使う。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `states` | dict[string, dict] | 必須 | 状態名をキーとする定義。各状態は `animation`(string, 任意) と `label`(string) を持つ |

#### Indicator

単一の状態インジケータ。

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `state` | string | 必須 | `"running"`, `"success"`, `"error"`, `"waiting"` |
| `animation` | string | 任意 | テーマで定義されたアニメーション名 |

### 4.5 カスタム（1種）

#### Custom

定義済み型に当てはまらない Widget。フロントエンドに custom_type のレンダラーがあれば専用表示を行い、なければ fallback Widget を表示する。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `custom_type` | string | 必須 | カスタム型の識別子 |
| `fallback` | Widget | 必須 | レンダラーが存在しない場合のフォールバック Widget |
| `data` | dict | 任意 | カスタムレンダラーに渡すデータ |

Custom Widget のレンダラーは `user_data/widget_renderers/` に配置可能。

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

## 5. rumi_widgets — Python ヘルパーライブラリ

defaults が `lib/rumi_widgets/` に配置する Python ヘルパー。handler.py や tool の handler.py 内で import して使える。使用は任意であり、直接 JSON dict を返しても等価。

### 5.1 配置場所

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

### 5.3 使い方

各クラスはコンストラクタで Widget のプロパティを受け取り、`.to_dict()` で JSON dict を返す。`emit_widget` に直接渡す場合は `.to_dict()` の呼び出しは不要（emit_widget が内部で呼ぶ）。

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

### 5.4 全クラスの基底

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

## 6. emit_widget による送出

Widget は tool の context API の汎用プリミティブ `emit_widget` で送出する。

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

emit_widget は途中経過の Widget をリアルタイムにフロントエンドに送出する。return の `widget` フィールドは最終結果として表示される Widget。

emit_widget で送出された Widget は message.stream.data メッセージの data 内に Widget JSON として格納され、フロントエンドに到達する。

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

### 7.1 Widget レンダラー

フロントエンドの shell.html が Widget レンダラーを内蔵する。Widget レンダラーは Widget JSON の `type` フィールドを見て対応する描画関数を呼び出す。

描画関数は Asset の iframe 内ではなく、shell レベルで提供される。Asset の JS は `window.renderWidget(widgetJson, targetElement)` を呼び出して Widget を描画する。

### 7.2 未知の type

Widget レンダラーが `type` を認識できない場合、以下の順でフォールバックする。

1. `user_data/widget_renderers/` にカスタムレンダラーがあれば使う
2. type が `"custom"` で `fallback` が存在すれば fallback Widget を描画する
3. いずれも該当しなければ `[Unknown widget: {type}]` とテキスト表示する

### 7.3 テーマとの連携

Widget レンダラーは描画時に現在のテーマ（theme.yaml）を参照する。テーマの `widgets` セクションに Widget 型ごとの描画設定が定義されている。

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

Widget の `style_hint` はテーマの variants 等を選択するヒントとして使われる。例えば `style_hint: {"variant": "compact"}` であれば、テーマの `card.variants.compact` が適用される。テーマはこのヒントを無視してもよい。

テーマの詳細は theme.md を参照。

## 8. CLI フォールバック

CLI 環境では全ての Widget がテキスト表現にフォールバックする。各 Widget 型のフォールバック表現は以下の通り。

| type | CLI 表現 |
|---|---|
| `text` | そのまま出力 |
| `code_block` | プレーンテキスト |
| `diff` | unified diff |
| `image` | `[Image: {alt} {width}x{height}]` |
| `screenshot` | `[Screenshot: {title} - {url}]` |
| `progress` | `[████░░░░░░] 30% {label}` |
| `terminal` | `$ {command}\n{output}` |
| `table` | ASCII テーブル |
| `chart` | 数値要約 |
| `file_tree` | インデント付きテキスト |
| `markdown` | プレーンテキスト |
| `audio` | `[Audio: {duration}ms]` |
| `video` | `[Video: {duration}ms]` |
| `map` | `[Map: {lat}, {lng}]` |
| `input` | `[Input: {placeholder}]` |
| `button` | `[{label}]` |
| `select` | `[Select: {options}]` |
| `toggle` | `[{label}: {value}]` |
| `slider` | `[{min}-{max}: {value}]` |
| `checkbox` | `[{checked ? "x" : " "}] {label}` |
| `container` | 子を順に出力 |
| `row` | 子を `  ` 区切りで横に出力 |
| `column` | 子を改行区切りで縦に出力 |
| `tabs` | `--- {label} ---\n{content}` を各タブで出力 |
| `collapsible` | `▸ {label}\n{children}` |
| `card` | `[{header}]\n{body}\n{footer}` |
| `stream` | `[{current_state.label}]` |
| `indicator` | `[{state}] {label}` |
| `custom` | fallback Widget の CLI 表現 |
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
# widget.md — Widget System 仕様書

## 1. 概要

Widget はバックエンドが「このデータをこう表示してほしい」と宣言するための統一的なデータ形式である。Widget は純粋な JSON データであり、UI ライブラリではない。

バックエンドのあらゆるコード（tool の handler.py、handler、Flow ノード）が Widget JSON を生成し、context の `emit_widget` で送出する。フロントエンドがこの JSON を受け取り、テーマに従って描画する。

Widget はドメイン知識を持たない。テキスト、コードブロック、画像、テーブル、プログレスバーといった汎用的な表示プリミティブのみを定義する。何をどう表示するかは Widget を生成する側が決め、どう見せるかはテーマが決める。


## 2. 設計思想

**純粋なデータ**: Widget は JSON dict である。レンダリングロジック、イベントハンドラ、スタイル定義を含まない。描画はフロントエンドの責務。

**ドメイン非依存**: Widget の型は「テキスト」「画像」「テーブル」等の汎用プリミティブである。「チャットメッセージ Widget」「エージェントステータス Widget」のような特定ドメインに特化した型は存在しない。

**ネスト可能**: Widget の中に Widget を入れられる。Card の body に CodeBlock を入れる、Row の中に複数の Button を並べる、Tabs の各タブに異なる Widget を配置する、等。

**フォールバック前提**: フロントエンドがある Widget 型を描画できない場合、テキスト表現にフォールバックする。Custom Widget は明示的な fallback Widget を持つ。CLI 環境では全ての Widget がテキスト表現にフォールバックする。

**テーマとの分離**: Widget は「何を表示するか」のみを宣言する。「どう見せるか」はテーマが決定する。Widget は `style_hint` でテーマへのヒントを渡せるが、テーマはこれを無視してよい。


## 3. 基底プロパティ

全ての Widget が持つ共通プロパティ。

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `type` | string | 必須 | Widget の型。セクション4の型一覧のいずれか |
| `id` | string | 任意 | 識別子。ストリーミング更新時に特定の Widget を差し替えるために使用 |
| `style_hint` | dict | 任意 | テーマへのヒント。テーマが解釈してもしなくてもよい |
| `meta` | dict | 任意 | 任意のメタデータ。フロントエンドは無視してよい |

```json
{
  "type": "text",
  "id": "msg_001",
  "style_hint": {"variant": "muted"},
  "meta": {"source": "file_read_tool"}
}
```


## 4. Widget 型一覧

29種。表示系14、コントロール系6、レイアウト系6、ストリーミング系2、カスタム1。


### 4.1 表示系（14種）

データを視覚的に表示する。

---

#### Text

```json
{ "type": "text", "text": "Hello, world" }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `text` | string | 必須 | 表示テキスト |

CLI: そのまま出力。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `language` | string | 任意 | 言語名 |
| `content` | string | 必須 | コード本体 |
| `filename` | string | 任意 | ファイル名 |
| `line_start` | integer | 任意 | 開始行番号。デフォルト 1 |

CLI: プレーンテキスト。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `old_content` | string | 必須 | 変更前 |
| `new_content` | string | 必須 | 変更後 |
| `filename` | string | 任意 | ファイル名 |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 データまたは URL |
| `alt` | string | 任意 | 代替テキスト |
| `width` | integer | 任意 | 幅 |
| `height` | integer | 任意 | 高さ |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 データ |
| `url` | string | 任意 | 元 URL |
| `title` | string | 任意 | タイトル |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `current` | number | 必須 | 現在値 |
| `total` | number | 必須 | 合計値 |
| `state` | string | 任意 | `"running"` / `"success"` / `"error"`。デフォルト `"running"` |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `command` | string | 任意 | 実行コマンド |
| `output` | string | 必須 | 出力 |
| `exit_code` | integer | 任意 | 終了コード |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `headers` | list[string] | 必須 | 列ヘッダ |
| `rows` | list[list] | 必須 | 行データ |

CLI: ASCII テーブル。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `chart_type` | string | 必須 | `"bar"` / `"line"` / `"pie"` / `"scatter"` |
| `labels` | list[string] | 必須 | ラベル |
| `data` | list[number] | 必須 | データ |

CLI: 数値要約。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `tree` | list[dict] | 必須 | ノード配列。各ノードは `name`(string), `type`(`"file"` or `"dir"`), `children`(list, 任意) |

CLI: インデント付きテキスト。

---

#### Markdown

```json
{ "type": "markdown", "content": "# Title\n\n**bold**" }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `content` | string | 必須 | Markdown テキスト |

CLI: プレーンテキスト。

---

#### Audio

```json
{ "type": "audio", "src": "base64 or URL", "duration": 5000 }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 or URL |
| `duration` | integer | 任意 | ミリ秒 |

CLI: `[Audio: {duration}ms]`

---

#### Video

```json
{ "type": "video", "src": "base64 or URL", "duration": 30000 }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `src` | string | 必須 | base64 or URL |
| `duration` | integer | 任意 | ミリ秒 |

CLI: `[Video: {duration}ms]`

---

#### Map

```json
{ "type": "map", "lat": 35.6812, "lng": 139.7671, "zoom": 15 }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `lat` | number | 必須 | 緯度 |
| `lng` | number | 必須 | 経度 |
| `zoom` | integer | 任意 | ズームレベル。デフォルト 13 |

CLI: `[Map: {lat}, {lng}]`


### 4.2 コントロール系（6種）

ユーザー入力を受け付ける。ユーザー操作の結果は Asset の JS が `emit_event` でバックエンドに返す。

---

#### Input

```json
{ "type": "input", "placeholder": "Type here...", "value": "", "multiline": false }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `placeholder` | string | 任意 | プレースホルダ |
| `value` | string | 任意 | 初期値 |
| `multiline` | boolean | 任意 | 複数行。デフォルト false |

---

#### Button

```json
{ "type": "button", "label": "Execute", "action": "run_task", "variant": "primary" }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `action` | string | 必須 | クリック時のアクション名 |
| `variant` | string | 任意 | `"primary"` / `"secondary"` / `"danger"`。デフォルト `"primary"` |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `options` | list[dict] | 必須 | 各要素は `label`(string), `value`(any) |
| `value` | any | 任意 | 現在値 |
| `multiple` | boolean | 任意 | 複数選択。デフォルト false |

---

#### Toggle

```json
{ "type": "toggle", "label": "Enable", "value": false }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `value` | boolean | 任意 | デフォルト false |

---

#### Slider

```json
{ "type": "slider", "min": 0, "max": 100, "value": 50, "step": 1 }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `min` | number | 必須 | 最小値 |
| `max` | number | 必須 | 最大値 |
| `value` | number | 任意 | 現在値 |
| `step` | number | 任意 | ステップ。デフォルト 1 |

---

#### Checkbox

```json
{ "type": "checkbox", "label": "I agree", "checked": false }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `checked` | boolean | 任意 | デフォルト false |


### 4.3 レイアウト系（6種）

Widget 内部のネスト構造を作る。

---

#### Container

```json
{ "type": "container", "children": [{"type": "text", "text": "..."}, {"type": "code_block", "content": "..."}] }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `children` | list[Widget] | 必須 | 子 Widget |

---

#### Row

```json
{ "type": "row", "children": [...], "gap": 8 }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `children` | list[Widget] | 必須 | 子 Widget |
| `gap` | integer | 任意 | 間隔（px） |

---

#### Column

```json
{ "type": "column", "children": [...], "gap": 8 }
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `children` | list[Widget] | 必須 | 子 Widget |
| `gap` | integer | 任意 | 間隔（px） |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `tabs` | list[dict] | 必須 | 各要素は `label`(string), `content`(Widget) |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `default_open` | boolean | 任意 | デフォルト false |
| `children` | list[Widget] | 必須 | 子 Widget |

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `header` | Widget | 任意 | ヘッダ |
| `body` | Widget | 任意 | ボディ |
| `footer` | Widget | 任意 | フッタ |


### 4.4 ストリーミング系（2種）

---

#### Stream

複数の状態を持つストリーミング表示。

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

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `states` | dict[string, dict] | 必須 | 状態名 → `label`(string) + `animation`(string, 任意) |

---

#### Indicator

単一の状態インジケータ。

```json
{
  "type": "indicator",
  "label": "file_read",
  "state": "success",
  "animation": "fade_in"
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | 必須 | ラベル |
| `state` | string | 必須 | `"running"` / `"success"` / `"error"` / `"waiting"` |
| `animation` | string | 任意 | テーマ定義のアニメーション名 |


### 4.5 カスタム（1種）

#### Custom

定義済み型に当てはまらない表示。`user_data/widget_renderers/` にレンダラーがあれば専用描画、なければ `fallback` を描画する。

```json
{
  "type": "custom",
  "custom_type": "3d_viewer",
  "fallback": {"type": "image", "src": "preview.png", "alt": "3D Preview"},
  "data": {"model_url": "model.glb", "rotation": [0, 45, 0]}
}
```

| プロパティ | 型 | 必須 | 説明 |
|---|---|---|---|
| `custom_type` | string | 必須 | カスタム型の識別子 |
| `fallback` | Widget | 必須 | レンダラー不在時のフォールバック |
| `data` | dict | 任意 | カスタムレンダラーに渡すデータ |

カスタムレンダラーの配置:

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

CLI: fallback Widget の CLI 表現。


## 5. rumi_widgets — Python ヘルパーライブラリ

defaults が `lib/rumi_widgets/` に配置する。handler.py 内で import して使える。使用は任意。直接 JSON dict を返しても等価。

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

### 5.3 基底クラス

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

クラス構築と JSON dict は等価。

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


## 6. 送出

### 6.1 emit_widget

tool の handler.py 内で `context["emit_widget"]` を呼ぶ。途中経過の Widget をリアルタイムにフロントエンドに送出する。

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

`emit_widget` で送出した Widget はストリーミングメッセージとして転送される。return の `widget` フィールドは最終結果 Widget。

### 6.2 通信上の表現

emit_widget が送出する Widget は JSON Lines メッセージの data 内に格納される。

```json
{"type":"message.stream.data","component":"target_asset","data":{"stream_id":"s1","widget":{"type":"progress","label":"Processing...","current":0,"total":3}}}
```

最終結果 Widget は message.send で送信される。

```json
{"type":"message.send","component":"target_asset","data":{"action":"tool_result","widget":{"type":"card","header":{"type":"indicator","label":"task","state":"success"},"body":{"type":"text","text":"done"}}}}
```

### 6.3 id による差し替え

Widget に `id` を付けて emit すると、フロントエンドは同じ `id` の Widget を上書き描画する。Progress の更新に使う。

```python
context["emit_widget"](Progress(id="p1", label="Step 1", current=1, total=3))
# ...
context["emit_widget"](Progress(id="p1", label="Step 2", current=2, total=3))
# フロントエンドは id="p1" の Widget を置き換える
```


## 7. フロントエンドでの描画

### 7.1 Widget レンダラー

shell が Widget レンダラーを内蔵する。レンダラーは Widget JSON の `type` を見て対応する描画関数を呼び出す。

Asset の JS 内からは以下で呼び出す。

```javascript
window.rumiWidgets.render(widgetJson, targetElement);
```

### 7.2 描画フォールバック順序

1. type が定義済み29種のいずれかであれば、組み込みレンダラーで描画する
2. type が `"custom"` であれば `user_data/widget_renderers/{custom_type}/` のレンダラーを探す
3. カスタムレンダラーがあれば専用描画する
4. なければ `fallback` Widget を組み込みレンダラーで描画する
5. いずれにも該当しなければ `[Unknown widget: {type}]` とテキスト表示する

### 7.3 テーマ連携

Widget レンダラーは描画時に現在のテーマ（theme.yaml）の `widgets` セクションを参照する。

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

Widget の `style_hint` でテーマの variant を選択できる。

```json
{"type": "card", "style_hint": {"variant": "compact"}, "body": {"type": "text", "text": "..."}}
```

テーマの `card.variants.compact` が適用される。テーマに該当 variant がなければ `default` が使われる。

テーマの詳細仕様は theme.md を参照。


## 8. CLI フォールバック

CLI 環境ではフロントエンドの Widget レンダラーが存在しない。全ての Widget はテキスト表現に変換される。

| type | CLI 表現 |
|---|---|
| `text` | そのまま出力 |
| `code_block` | プレーンテキスト |
| `diff` | unified diff |
| `image` | `[Image: {alt} {width}x{height}]` |
| `screenshot` | `[Screenshot: {title} - {url}]` |
| `progress` | `[████░░░░░░] 30% {label}` |
| `terminal` | `$ {command}\n{output}` |
| `table` | ASCII テーブル |
| `chart` | 数値要約 |
| `file_tree` | インデント付きテキスト |
| `markdown` | プレーンテキスト |
| `audio` | `[Audio: {duration}ms]` |
| `video` | `[Video: {duration}ms]` |
| `map` | `[Map: {lat}, {lng}]` |
| `input` | `[Input: {placeholder}]` |
| `button` | `[{label}]` |
| `select` | `[Select: {options}]` |
| `toggle` | `[{label}: {value}]` |
| `slider` | `[{min}-{max}: {value}]` |
| `checkbox` | `[{checked ? "x" : " "}] {label}` |
| `container` | 子を順に出力 |
| `row` | 子を空白区切りで横に出力 |
| `column` | 子を改行で縦に出力 |
| `tabs` | `--- {label} ---\n{content}` |
| `collapsible` | `▸ {label}\n{children}` |
| `card` | `[{header}]\n{body}\n{footer}` |
| `stream` | `[{current_state.label}]` |
| `indicator` | `[{state}] {label}` |
| `custom` | fallback の CLI 表現 |

CLI フォールバックの実装は `lib/rumi_widgets/` 内の各クラスに `to_cli()` メソッドとして持たせる。transport 層が CLI モードを検出した場合、emit_widget は `to_dict()` の代わりに `to_cli()` の結果を出力する。
```