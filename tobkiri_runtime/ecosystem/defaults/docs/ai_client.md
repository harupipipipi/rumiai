

思考: ユーザーは ai_client.md を修正するためのプロンプト（AIエージェントに渡す指示書）を書いてほしいと言っている。

このプロンプトは、別のAIエージェント（Claude Code等）に渡して、ai_client.md を修正させるためのもの。

コンテキストの制約：
- これ以上ファイルを読み込めない
- つまりプロンプト内で必要な情報を全て含める必要がある

プロンプトに含めるべき情報：
1. 修正対象ファイル: ai_client.md
2. 何を追加するか: events.ui.yaml の仕組み（stream_handler が profile の events.ui.yaml を読んで payload に widget を含める）
3. 設計原則: ai_client はアニメーション定義を持たない。仕組みだけ。中身は user_data のモデル profile が提供。
4. 既存の仕様との整合: message.stream.data の payload に widget を含められる仕様は既にある
5. events.ui.yaml の形式
6. stream_handler の変更内容
7. フロントエンドの挙動（Asset が独自実装を持っていればそちら優先、なければ payload の widget を使う）

プロンプトを書こう。

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
    auto_dismiss: {ms}  # 任意。指定ms後に自動消去
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

これでいいと思う。ただ、ユーザーは「プロンプトを書いて」と言っているので、このプロンプト自体を回答として出力する。

では出力する。

以下、ai_client.md を修正するエージェント用のプロンプト。

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
  {event_name}:          # セクション11.3の正規化イベント名と対応
    widget:               # widget.md に定義された任意の Widget JSON
      type: indicator
      label: "Thinking..."
      state: running
      animation: wave_dots
    auto_dismiss: 800     # 任意。指定ミリ秒後に自動消去のヒント
```

テンプレート変数: `{{key}}` はイベントの `data.key` の値で置換する。例えば `{{name}}` は `tool_call_start` イベントの `data.name`（ツール名）に展開される。

widget フィールドが null または省略されたイベントには何も付与しない。

### 2. stream_handler の処理追加

stream_handler.py が .jsonl のイベントを読む際の追加処理:

```
1. モデル profile に ui/events.ui.yaml が存在するか確認
2. 存在すれば起動時に1回読み込んでメモリに保持
3. 各ストリーミングイベント処理時:
   a. 現在のイベント名に対応する定義が events.ui.yaml にあるか確認
   b. あれば widget 定義のテンプレート変数（{{key}}）をイベントの data で置換
   c. 置換済み widget を event.data.widget に格納
   d. auto_dismiss があれば event.data.widget_auto_dismiss に格納
4. 定義がなければ何も付与しない
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
    """widget定義内の {{key}} を data[key] で置換"""
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