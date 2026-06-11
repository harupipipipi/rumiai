<!-- docs-i18n-links:start -->
[EN](./ai_client.md) | [JP](./i18n/ja/ai_client.md) | [KR](./i18n/ko/ai_client.md) | [CN](./i18n/zh-cn/ai_client.md)
<!-- docs-i18n-links:end -->

Thought: The user wants us to write a prompt (instructions to give to the AI ​​agent) to modify ai_client.md.

This prompt is for passing to another AI agent (such as Claude Code) to modify ai_client.md.

Context constraints:
- Cannot load any more files
- This means you need to include all the necessary information in the prompt.

Information to include in the prompt:
1. File to be modified: ai_client.md
2. What to add: How events.ui.yaml works (stream_handler reads events.ui.yaml of profile and includes widget in payload)
3. Design principle: ai_client has no animation definitions. Just how it works. The contents are provided by the model profile of user_data.
4. Consistency with existing specifications: There is already a specification that allows widgets to be included in the payload of message.stream.data.
5. Format of events.ui.yaml
6. Changes to stream_handler
7. Front-end behavior (if Asset has its own implementation, give priority to that, otherwise use payload widget)

Write a prompt.

```markdown
# ai_client.md 修正指示

## 修正対象
`ecosystem/defaults/docs/ai_client.md`

## 修正概要
ai_client の stream_handler に「モデル profile が提供するアニメーション Widget を自動的に payload に含める」仕組みを追加する。

## 設計原則
- ai_client 自体にアニメーション定義（"Thinking..." 等の具体的な Widget）は一切入れない
- ai_client は「events.ui.yaml があれば読んで payload に乗せる」仕組みだけを提供
- 具体的なアニメーション（何を表示するか）は user_data のモデル profile が events.ui.yaml で定義する
- これは defaults の原則「仕組みだけ提供、中身は全て user_data」と整合する

## 追加する仕様

### events.ui.yaml
モデル profile の ui/ ディレクトリに配置する YAML ファイル。ストリーミングイベントごとに、フロントエンドに表示する Widget JSON を定義する。

配置場所:
```
user_data/shared/ai_models/{provider_id}/profiles/{model_name}/ui/events.ui.yaml
```

形式:
```yaml
events:
  {event_name}:
    widget:
      type: ...
      label: ...
      ...
    auto_dismiss: {ms} # Optional. Automatically erase after specified ms
```

テンプレート変数: {{key}} はイベントの data.key で置換される。例: {{name}} → tool_call_start の data.name

events.ui.yaml がない場合: 何も付与しない。現行と同じ動作。

### stream_handler の変更
stream_handler.py がストリーミングイベントを処理する際:
1. モデル profile に ui/events.ui.yaml があるか確認
2. あれば読み込む
3. 現在のイベント名に対応する定義があれば、テンプレート変数を置換し、widget を payload に含めて送る
4. なければ何も付けずにイベントだけ送る

payload への含め方: 既存の message.stream.data の payload に widget フィールドとして含める。これは frontend.md で既に定義されている仕様。

### フロントエンドの挙動
- フロントエンドの Asset が thinking 等の独自表示を持っている場合 → payload の widget を無視し、独自の表示を使う
- 持っていない場合 → payload の widget を Widget レンダラーで表示する
- この判断は Asset 側の JS が行う。ai_client やシェルは関与しない

## 追記すべきセクション
ai_client.md のセクション 11（ストリーミング）の後、またはセクション 15（UI）に以下を追記:
- events.ui.yaml の仕様（形式、配置場所、テンプレート変数）
- stream_handler の変更内容（events.ui.yaml を読んで payload に含める）
- events.ui.yaml の具体例（thinking model、MoA、ツール呼び出し）

## 具体例

### thinking model の events.ui.yaml
```yaml
events:
  thinking_start:
    widget:
      type: indicator
      label: "Thinking..."
      state: running
      animation: wave_dots
  thinking_end:
    widget:
      type: indicator
      label: "Thought complete"
      state: success
      animation: fade_in
    auto_dismiss: 800
  content_start:
    widget:
      type: indicator
      label: "Responding..."
      state: running
      animation: typing_cursor
  tool_call_start:
    widget:
      type: indicator
      label: "Using {{name}}..."
      state: running
      animation: pulse
  tool_call_end:
    widget:
      type: indicator
      label: "{{name}} complete"
      state: success
      animation: fade_in
    auto_dismiss: 500
```

### stream_handler の処理（擬似コード）
```python
def process_event(self, event):
    event_type = event["event"]
    event_data = event.get("data", {})

    ui_def = self.events_ui.get("events", {}).get(event_type) if self.events_ui else None

    if ui_def and ui_def.get("widget"):
        widget = self._resolve_templates(ui_def["widget"], event_data)
        event["data"]["widget"] = widget
        if ui_def.get("auto_dismiss"):
            event["data"]["widget_auto_dismiss"] = ui_def["auto_dismiss"]

    return event
```

## 注意事項
- ai_client.md の既存の構造・記法・トーンを維持すること
- 既存のセクション（ストリーミング、.jsonl フォーマット、正規化イベント一覧等）との整合性を保つこと
- events.ui.yaml は「任意」ファイル（なくても動く）であることを明記
- Widget の型は widget.md に定義されている既存の型のみを使用（新しい Widget 型は追加しない）
```

I think this is fine. However, since the user is saying, "Write a prompt," this prompt itself is output as the answer.

Now output.

Below is the prompt for the agent to modify ai_client.md.

---

```markdown
# 指示: ai_client.md への events.ui.yaml 仕様追記

## あなたの役割
`ecosystem/defaults/docs/ai_client.md` を修正し、ストリーミング中のアニメーション表示の仕組みを追記してください。

## 前提知識

### defaults の設計原則
defaults は「仕組みだけ提供」し、「中身は全て user_data」。ai_client 自体にアニメーション定義（"Thinking..." 等）は一切入れない。ai_client は「モデル profile に events.ui.yaml があれば読んで、ストリーミングイベントの payload に widget を含めて送る」という仕組みだけを持つ。

### 解決する問題
thinking model の推論中や MoA の並列実行中、ユーザーのフロントエンドに何も表示されない空白時間が発生する。これを解決するため、モデル profile 側がイベントごとの表示用 Widget を YAML で定義し、ai_client の stream_handler がそれを読んでストリーミングデータに含める。

### 既存の仕様との整合
- `message.stream.data` の payload に `widget` フィールドを含められる仕様は frontend.md で既に定義済み
- Widget の型（indicator, progress, container 等）は widget.md で定義済み
- テーマのアニメーション（wave_dots, pulse, fade_in 等）は theme.md で定義済み
- 正規化イベント（thinking_start, thinking_delta, content_delta 等）は ai_client.md セクション 11.3 で定義済み
- モデル profile の ui/ ディレクトリは ai_client.md セクション 4.7 で既に言及済み

## 追記内容

### 1. events.ui.yaml の仕様

配置場所:
```
user_data/shared/ai_models/{provider_id}/profiles/{model_name}/ui/events.ui.yaml
```

このファイルは任意。なければ何も付与せず、現行と同じ動作になる。

形式:
```yaml
events:
  {event_name}: # Corresponds to normalized event name in section 11.3
    widget: # Any Widget JSON defined in widget.md
      type: indicator
      label: "Thinking..."
      state: running
      animation: wave_dots
    auto_dismiss: 800 # Optional. Auto-clear after specified milliseconds hint
```

テンプレート変数: `{{key}}` はイベントの `data.key` の値で置換する。例えば `{{name}}` は `tool_call_start` イベントの `data.name`（ツール名）に展開される。

widget フィールドが null または省略されたイベントには何も付与しない。

### 2. stream_handler の処理追加

stream_handler.py が .jsonl のイベントを読む際の追加処理:

```
1. Check if ui/events.ui.yaml exists in model profile
2. If it exists, it will be read once at startup and kept in memory.
3. When processing each streaming event:
   a. Check if there is a definition corresponding to the current event name in events.ui.yaml
   b. Replace the template variable ({{key}}) in the widget definition with the event data, if any.
   c. Store the replaced widget in event.data.widget
   d. If auto_dismiss exists, store it in event.data.widget_auto_dismiss
4. Give nothing if there is no definition
```

擬似コード:
```python
class StreamHandler:
    def __init__(self, model_profile_path):
        events_ui_path = f"{model_profile_path}/ui/events.ui.yaml"
        self.events_ui = load_yaml(events_ui_path) if exists(events_ui_path) else None

    def process_event(self, event):
        if not self.events_ui:
            return event

        event_type = event["event"]
        event_data = event.get("data", {})
        ui_def = self.events_ui.get("events", {}).get(event_type)

        if ui_def and ui_def.get("widget"):
            widget = resolve_templates(ui_def["widget"], event_data)
            event["data"]["widget"] = widget
            if ui_def.get("auto_dismiss"):
                event["data"]["widget_auto_dismiss"] = ui_def["auto_dismiss"]

        return event

def resolve_templates(widget_dict, data):
"""Replace {{key}} with data[key] in widget definition"""
    raw = json.dumps(widget_dict)
    for key, value in data.items():
        raw = raw.replace("{{" + key + "}}", str(value))
    return json.loads(raw)
```

### 3. フロントエンド側の挙動（説明のみ、ai_client の責務外）

以下を「補足」として簡潔に記載:
- フロントエンドの Asset が thinking 等の独自表示を持っている場合、payload の widget を無視して独自表示を使う
- 持っていない場合、payload の widget を Widget レンダラーで表示する
- この判断は Asset 側の責務であり、ai_client は関与しない

### 4. 具体例（3つ）

例1 — thinking model（Anthropic Claude）:
```yaml
events:
  thinking_start:
    widget:
      type: indicator
      label: "Thinking..."
      state: running
      animation: wave_dots
  thinking_end:
    widget:
      type: indicator
      label: "Thought complete"
      state: success
      animation: fade_in
    auto_dismiss: 800
  content_start:
    widget:
      type: indicator
      label: "Responding..."
      state: running
      animation: typing_cursor
  tool_call_start:
    widget:
      type: indicator
      label: "Using {{name}}..."
      state: running
      animation: pulse
  tool_call_end:
    widget:
      type: indicator
      label: "{{name}} complete"
      state: success
      animation: fade_in
    auto_dismiss: 500
```

例2 — reasoning model（OpenAI o3）:
```yaml
events:
  thinking_start:
    widget:
      type: container
      children:
        - type: indicator
          label: "Reasoning..."
          state: running
          animation: pulse
        - type: text
          text: "Deep analysis in progress"
          style_hint: { color: "secondary", size: "sm" }
  thinking_end:
    widget:
      type: indicator
      label: "Analysis complete"
      state: success
      animation: fade_in
    auto_dismiss: 600
```

例3 — events.ui.yaml がないモデル:
何も付与されない。フロントエンドにはイベントデータのみ届く。Asset が独自に表示するか、何も表示されないかは Asset 次第。

## 追記する場所
ai_client.md 内の適切な場所に追記。候補:
- セクション 11（ストリーミング）の末尾に 11.5 等として追加
- またはセクション 15（UI）がui/ディレクトリに言及しているので、そこに詳細化

既存のセクション構成を壊さず、自然に挿入できる場所を選んでください。

## 注意事項
- ai_client.md の既存の記法・トーン・構造を維持
- events.ui.yaml は「任意」（optional）であることを繰り返し明記
- 新しい Widget 型は追加しない（widget.md 既存の型のみ使用）
- ai_client にデフォルトのアニメーション定義をハードコードしない
- 「仕組みだけ提供」の原則を守る
```
