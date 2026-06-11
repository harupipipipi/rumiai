<!-- docs-i18n-links:start -->
[EN](../../ai_client.md) | [JP](../ja/ai_client.md) | [KR](../ko/ai_client.md) | [CN](./ai_client.md)
<!-- docs-i18n-links:end -->

想法：用户希望我们写一个提示（给AI代理的指令）来修改ai_client.md。

该提示用于传递给另一个AI代理（例如Claude Code）来修改ai_client.md。

上下文约束：
- 无法加载更多文件
- 这意味着您需要在提示中包含所有必要的信息。

提示中要包含的信息：
1.需要修改的文件：ai_client.md
2. 添加内容：events.ui.yaml 的工作原理（stream_handler 读取配置文件的 events.ui.yaml 并在有效负载中包含小部件）
3.设计原则：ai_client没有动画定义。就是它是如何工作的。内容由 user_data 的模型配置文件提供。
4. 与现有规范的一致性：已经有一个规范允许将小部件包含在 message.stream.data 的有效负载中。
5. events.ui.yaml的格式
6.stream_handler 的更改
7. 前端行为（如果Asset有自己的实现，优先考虑，否则使用payload widget）

写一个提示。

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
事件：
  {事件名称}：
    小部件：
      类型：...
      标签： ...
      ...
    auto_dismiss: {ms} # 可选。指定毫秒后自动擦除
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
事件：
  思考开始：
    小部件：
      类型： 指标
      标签：“思考……”
状态：运行中
      动画：wave_dots
  思考结束：
    小部件：
      类型： 指标
      标签：“思想完整”
      状态：成功
      动画：淡入
    自动关闭：800
  内容开始：
    小部件：
      类型： 指标
      标签：“正在响应...”
状态：运行中
      动画：打字光标
  工具调用开始：
    小部件：
      类型： 指标
      标签：“使用{{name}}...”
状态：运行中
      动画：脉冲
  工具调用结束：
    小部件：
      类型： 指标
      标签：“{{name}}完成”
      状态：成功
      动画：淡入
    自动关闭：500
```

### stream_handler の処理（擬似コード）
```python
def process_event(自身, 事件):
    event_type = 事件[“事件”]
    event_data = event.get("数据", {})

    ui_def = self.events_ui.get("events", {}).get(event_type) if self.events_ui else None

    如果 ui_def 和 ui_def.get("widget"):
        widget = self._resolve_templates(ui_def["widget"], event_data)
        事件["数据"]["小部件"] = 小部件
        如果 ui_def.get("auto_dismiss"):
            事件[“数据”][“widget_auto_dismiss”] = ui_def[“auto_dismiss”]

    返回事件
```

## 注意事項
- ai_client.md の既存の構造・記法・トーンを維持すること
- 既存のセクション（ストリーミング、.jsonl フォーマット、正規化イベント一覧等）との整合性を保つこと
- events.ui.yaml は「任意」ファイル（なくても動く）であることを明記
- Widget の型は widget.md に定義されている既存の型のみを使用（新しい Widget 型は追加しない）
```

我认为这很好。然而，由于用户说“编写提示”，因此该提示本身将作为答案输出。

现在输出。

下面是代理修改ai_client.md的提示。

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
事件：
  {event_name}: # 对应11.3节中规范化的事件名称
widget: # widget.md 中定义的任何 Widget JSON
      类型： 指标
      标签：“思考……”
状态：运行中
      动画：wave_dots
    auto_dismiss: 800 # 可选。指定毫秒提示后自动清除
```

テンプレート変数: `{{key}}` はイベントの `data.key` の値で置換する。例えば `{{name}}` は `tool_call_start` イベントの `data.name`（ツール名）に展開される。

widget フィールドが null または省略されたイベントには何も付与しない。

### 2. stream_handler の処理追加

stream_handler.py が .jsonl のイベントを読む際の追加処理:

```
1. 检查模型配置文件中是否存在 ui/events.ui.yaml
2、如果存在，启动时会读取一次并保存在内存中。
3. 处理每个流事件时：
   a.检查events.ui.yaml中是否有当前事件名对应的定义
   b.将小部件定义中的模板变量 ({{key}}) 替换为事件数据（如果有）。
   c.将替换的小部件存储在 event.data.widget 中
   d.如果 auto_dismiss 存在，则将其存储在 event.data.widget_auto_dismiss 中
4. 如果没有定义则什么也不给出
```

擬似コード:
```python
类流处理程序：
    def __init__(self, model_profile_path):
        events_ui_path = f“{model_profile_path}/ui/events.ui.yaml”
        self.events_ui = load_yaml(events_ui_path) 如果存在(events_ui_path) 否则无

    def process_event(自身, 事件):
        如果不是 self.events_ui：
            返回事件

        event_type = 事件[“事件”]
        event_data = event.get("数据", {})
        ui_def = self.events_ui.get("事件", {}).get(event_type)

        如果 ui_def 和 ui_def.get("widget"):
            小部件=resolve_templates(ui_def[“小部件”]，event_data)
            事件["数据"]["小部件"] = 小部件
            如果 ui_def.get("auto_dismiss"):
事件[“数据”][“widget_auto_dismiss”] = ui_def[“auto_dismiss”]

        返回事件

defresolve_templates（widget_dict，数据）：
"""在小部件定义中将 {{key}} 替换为 data[key]"""
    raw = json.dumps(widget_dict)
    对于 data.items() 中的键、值：
        raw = raw.replace("{{" + key + "}}", str(value))
    返回 json.loads(原始)
```

### 3. フロントエンド側の挙動（説明のみ、ai_client の責務外）

以下を「補足」として簡潔に記載:
- フロントエンドの Asset が thinking 等の独自表示を持っている場合、payload の widget を無視して独自表示を使う
- 持っていない場合、payload の widget を Widget レンダラーで表示する
- この判断は Asset 側の責務であり、ai_client は関与しない

### 4. 具体例（3つ）

例1 — thinking model（Anthropic Claude）:
```yaml
事件：
  思考开始：
    小部件：
      类型： 指标
      标签：“思考……”
状态：运行中
      动画：wave_dots
  思考结束：
    小部件：
      类型： 指标
      标签：“思想完整”
      状态：成功
      动画：淡入
    自动关闭：800
  内容开始：
    小部件：
      类型： 指标
      标签：“正在响应...”
状态：运行中
      动画：打字光标
  工具调用开始：
    小部件：
      类型： 指标
      标签：“使用{{name}}...”
状态：运行中
      动画：脉冲
  工具调用结束：
    小部件：
      类型： 指标
      标签：“{{name}}完成”
      状态：成功
      动画：淡入
    自动关闭：500
```

例2 — reasoning model（OpenAI o3）:
```yaml
事件：
  思考开始：
    小部件：
      类型：集装箱
      儿童：
        - 类型：指标
          标签：“推理……”
          状态：运行中
          动画：脉冲
        - 类型：文本
          文本：“正在进行深入分析”
          style_hint: { 颜色: "次要", 尺寸: "sm" }
  思考结束：
    小部件：
      类型： 指标
      标签：“分析完成”
      状态：成功
      动画：淡入
    自动关闭：600
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
