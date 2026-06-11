<!-- docs-i18n-links:start -->
[EN](../../ai_client.md) | [JP](./ai_client.md) | [KR](../ko/ai_client.md) | [CN](../zh-cn/ai_client.md)
<!-- docs-i18n-links:end -->

考え: ユーザーは、ai_client.md を変更するためのプロンプト (AI エージェントに与える指示) を書いてほしいと考えています。

このプロンプトは、ai_client.md を変更するために別の AI エージェント (Claude Code など) に渡すためのものです。

コンテキストの制約:
- これ以上ファイルをロードできません
- これは、プロンプトに必要な情報をすべて含める必要があることを意味します。

プロンプトに含める情報:
1. 変更するファイル：ai_client.md
2. 追加するもの: events.ui.yaml の仕組み (stream_handler はプロファイルの events.ui.yaml を読み取り、ペイロードにウィジェットを含めます)
3. 設計原則: ai_client にはアニメーション定義がありません。それがどのように機能するか。コンテンツは user_data のモデル プロファイルによって提供されます。
4. 既存の仕様との一貫性: message.stream.data のペイロードにウィジェットを含めることを許可する仕様がすでに存在します。
5. events.ui.yaml の形式
6. stream_handler の変更
7. フロントエンドの動作 (アセットに独自の実装がある場合はそれを優先し、そうでない場合はペイロード ウィジェットを使用します)

プロンプトを書きます。

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
イベント:
  {イベント名}:
    ウィジェット:
      タイプ: ...
      ラベル: ...
      ...
    auto_dismiss: {ms} # オプション。指定したミリ秒後に自動的に消去
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
イベント:
  思考開始:
    ウィジェット:
      タイプ: インジケーター
      ラベル：「考え中…」
状態: 実行中
      アニメーション: wave_dots
  思考終了:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「思考完了」
      状態: 成功
      アニメーション: フェードイン
    自動解除: 800
  コンテンツ開始:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「応答中...」
状態: 実行中
      アニメーション: タイピング_カーソル
  ツール呼び出し開始:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「{{name}} を使用しています...」
状態: 実行中
      アニメーション：パルス
  ツール呼び出し終了:
    ウィジェット:
      タイプ: インジケーター
      ラベル: "{{name}} 完了"
      状態: 成功
      アニメーション: フェードイン
    自動解除: 500
```

### stream_handler の処理（擬似コード）
```python
def process_event(self, イベント):
    イベントタイプ = イベント["イベント"]
    イベントデータ = イベント.get("データ", {})

    ui_def = self.events_ui.get("events", {}).get(event_type) if self.events_ui else なし

    ui_def と ui_def.get("ウィジェット") の場合:
        ウィジェット = self._resolve_templates(ui_def["ウィジェット"],event_data)
        イベント["データ"]["ウィジェット"] = ウィジェット
        if ui_def.get("auto_dismiss"):
            イベント["データ"]["ウィジェット_自動解除"] = ui_def["自動解除"]

    リターンイベント
```

## 注意事項
- ai_client.md の既存の構造・記法・トーンを維持すること
- 既存のセクション（ストリーミング、.jsonl フォーマット、正規化イベント一覧等）との整合性を保つこと
- events.ui.yaml は「任意」ファイル（なくても動く）であることを明記
- Widget の型は widget.md に定義されている既存の型のみを使用（新しい Widget 型は追加しない）
```

これでいいと思います。ただし、ユーザーは「プロンプトを書いて」と言っているので、このプロンプト自体が回答として出力されます。

今度は出力します。

以下は、エージェントが ai_client.md を変更するためのプロンプトです。

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
イベント:
  {event_name}: # セクション 11.3 の正規化されたイベント名に対応します
widget: # widget.md で定義された任意のウィジェット JSON
      タイプ: インジケーター
      ラベル：「考え中…」
状態: 実行中
      アニメーション: wave_dots
    auto_dismiss: 800 # オプション。指定したミリ秒後に自動クリアするヒント
```

テンプレート変数: `{{key}}` はイベントの `data.key` の値で置換する。例えば `{{name}}` は `tool_call_start` イベントの `data.name`（ツール名）に展開される。

widget フィールドが null または省略されたイベントには何も付与しない。

### 2. stream_handler の処理追加

stream_handler.py が .jsonl のイベントを読む際の追加処理:

```
1. ui/events.ui.yaml がモデル プロファイルに存在するかどうかを確認します
2. 存在する場合は、起動時に 1 回読み取られ、メモリに保持されます。
3. 各ストリーミング イベントを処理するとき:
   ａ． events.ui.yamlに現在のイベント名に対応する定義があるか確認する
   b.ウィジェット定義内のテンプレート変数 ({{key}}) をイベント データ (存在する場合) に置き換えます。
   c.置き換えたウィジェットをevent.data.widgetに保存します
   d. auto_dismiss が存在する場合は、event.data.widget_auto_dismiss に格納します。
4. 定義がない場合は何も指定しない
```

擬似コード:
```python
クラスStreamHandler:
    def __init__(self, model_profile_path):
        events_ui_path = f"{model_profile_path}/ui/events.ui.yaml"
        self.events_ui = load_yaml(events_ui_path) if存在する場合(events_ui_path) else なし

    def process_event(self, イベント):
        self.events_ui でない場合:
            リターンイベント

        イベントタイプ = イベント["イベント"]
        イベントデータ = イベント.get("データ", {})
        ui_def = self.events_ui.get("イベント", {}).get(event_type)

        ui_def と ui_def.get("ウィジェット") の場合:
            ウィジェット =solve_templates(ui_def["ウィジェット"],event_data)
            イベント["データ"]["ウィジェット"] = ウィジェット
            if ui_def.get("auto_dismiss"):
イベント["データ"]["ウィジェット_自動解除"] = ui_def["自動解除"]

        リターンイベント

defsolve_templates(widget_dict, data):
"""ウィジェット定義の {{key}} を data[key] に置き換えます"""
    raw = json.dumps(widget_dict)
    data.items() のキーと値の場合:
        raw = raw.replace("{{" + キー + "}}", str(値))
    json.loads(生)を返す
```

### 3. フロントエンド側の挙動（説明のみ、ai_client の責務外）

以下を「補足」として簡潔に記載:
- フロントエンドの Asset が thinking 等の独自表示を持っている場合、payload の widget を無視して独自表示を使う
- 持っていない場合、payload の widget を Widget レンダラーで表示する
- この判断は Asset 側の責務であり、ai_client は関与しない

### 4. 具体例（3つ）

例1 — thinking model（Anthropic Claude）:
```yaml
イベント:
  思考開始:
    ウィジェット:
      タイプ: インジケーター
      ラベル：「考え中…」
状態: 実行中
      アニメーション: wave_dots
  思考終了:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「思考完了」
      状態: 成功
      アニメーション: フェードイン
    自動解除: 800
  コンテンツ開始:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「応答中...」
状態: 実行中
      アニメーション: タイピング_カーソル
  ツール呼び出し開始:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「{{name}} を使用しています...」
状態: 実行中
      アニメーション：パルス
  ツール呼び出し終了:
    ウィジェット:
      タイプ: インジケーター
      ラベル: "{{name}} 完了"
      状態: 成功
      アニメーション: フェードイン
    自動解除: 500
```

例2 — reasoning model（OpenAI o3）:
```yaml
イベント:
  思考開始:
    ウィジェット:
      タイプ: コンテナ
      子供たち:
        - タイプ: インジケーター
          ラベル：「推理…」
          状態: 実行中
          アニメーション：パルス
        - タイプ: テキスト
          テキスト: 「詳細な分析が進行中」
          style_hint: { カラー: "セカンダリ"、サイズ: "sm" }
  思考終了:
    ウィジェット:
      タイプ: インジケーター
      ラベル: 「分析完了」
      状態: 成功
      アニメーション: フェードイン
    自動解除: 600
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
