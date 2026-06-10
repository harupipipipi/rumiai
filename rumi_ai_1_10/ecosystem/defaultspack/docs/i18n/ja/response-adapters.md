<!-- docs-i18n-links:start -->
[EN](../../response-adapters.md) | [JP](./response-adapters.md) | [KR](../ko/response-adapters.md) | [CN](../zh-cn/response-adapters.md)
<!-- docs-i18n-links:end -->

# 応答アダプター

応答アダプターは、Rumi 出力をプロバイダー固有の応答に変換します。彼らは
外部入力フレームワークのアウトバウンド半分。

```text
runtime result
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponsePlan
  -> ResponseAdapter
  -> provider API or HTTP response
```

ランタイムは、Slack への投稿方法、LINE 返信トークンの使用方法、または
Discord インタラクション応答をフォーマットします。プロバイダーに依存しないものを返す必要があります
プランナーが適応できる結果になります。

## レスポンスプランナー

`ResponsePlanner` は、実行時の結果がどうなるかを決定します。

- `reply_text`: アシスタント テキストをソースに送り返します。
- `store_only`: 外部からの返信なしでチャット結果を保持します。
- `summarize_then_reply`: 短い範囲の要約を送信します。
- `run_browser_use`、`run_computer_use`、`run_python`、`run_tool`:
  直接の実行ではなく、フォローアップの行動計画。
- `send_file_if_allowed`: 機能チェック後の通常のファイル計画を許可します。
- `ask_for_approval`: 承認が必要な計画で停止します。

プランナーは、即時決定、プロバイダーの制限、イベントの対象者、および
ランタイム出力メタデータ。プロバイダーの長さ制限、ファイル制限、および機密性
即時決定後もチェックが行われます。

出力プロファイルは、入力プロファイルの送信に対応するものです。内蔵
プロフィールには、LINE の返信/プッシュ、Discord ボット チャネル メッセージ、Discord Webhook が含まれます
URL、Slack チャネル/スレッド メッセージ、汎用 Webhook コールバック、ローカル Web
出力。カスタムプロファイルは`user_data/shared/output_profiles`に配置できます。
組み込みの LINE/Discord/Slack 出力の場合、セットアップは意図的にコピー＆ペーストされます。
選択: 出力テンプレート/プロファイルを選択し、非シークレット ターゲット ID を貼り付けます。
UI に保存し、ボット トークンまたは Webhook URL をマスクされた外部トークンとして保存します。任意
送信者と自由形式のプロンプト指示はカスタムの下にあります。

Discord は、運用モデルが次のとおりであるため、2 つの組み込み出力テンプレートを公開します。
違う：

- `discord.output.bot_channel`: ローカル Rumi ランタイムは Discord ボット トークンを使用します
  そしてターゲット`channel_id`。
- `discord.output.webhook`: Rumi はチャネル Webhook URL を通じて投稿し、
  その出力パスにはボット トークンは必要ありません。

どちらのパスも引き続き対応計画を通過し、`allowed_mentions` を安全に保ちます。
デフォルトでは。

## 応答プロンプトポリシー

`response_prompt` は、プロンプト ルーティングの計画ポリシーです。イベントを視察することもありますが、
入力テキストと実行時の結果から、`plan_only` の決定を返します。
`ResponsePlanner` ただし、ツールを実行したり、プロバイダー API を直接呼び出したりしてはなりません。
実行可能ステップは、既存のツール ポリシーを通じて後で作成されます。
承認、ターンランナー、および応答アダプターのパス。

ポリシー フィールドは `schemas/response_prompt_policy.schema.yaml` で定義されています。

- `allowed_actions`: プロンプトが表示できる唯一の `ResponsePlan.action` 値
  戻る;
- `tools`: 計画コンテキストに対するツールの可視性と承認要件。
- `output_schema`: 即時決定の予想される構造化形状。
- `allowed_outputs`: プロンプトに表示されるオプションの出力プロファイル ID またはプロバイダー
  ターゲット;
- `fallback`: プロンプト出力が無効または無効な場合に使用する安全なアクション
  否定されました。
- `sensitivity`: 可視性のデフォルトと外部配信の制約。

`allowed_actions`に記載されていない行動を伴う決定は拒否されなければなりません
`fallback`を通じて処理されます。

例:

```yaml
response_prompt:
  enabled: true
  model: inherit
  mode: plan_only
  allowed_actions:
    - reply_text
    - store_only
    - run_browser_use
    - run_python
  tools:
    browser_use:
      enabled: true
      requires_approval: false
    python:
      enabled: true
      requires_approval: false
      sandbox: true
    external_send:
      enabled: true
      requires_approval: true
  system_prompt: |
    Decide how Rumi should respond. Use browser_use only when current
    external information is needed. Return strict JSON.
  user_prompt: |
    Provider: ${event.provider}
    Scope: ${event.scope.type}:${event.scope.id}
    Actor: ${event.actor.id}
    User input: ${input.text}
    Assistant result: ${response.text}
```

プロバイダー間のアクションの場合、プロンプトは次のようなプランを返す必要があります。
`run_tool`と`tool: external_send`。このツールは承認ゲート型であり、
通常の応答と同じ LINE、Discord、Slack、および汎用 Webhook アダプター
配達。プロンプトは、生のボット トークンや Webhook シークレットを受け取ることはありません。

## 対応計画

プラン例:

```json
{
  "provider": "discord",
  "messages": [
    {
      "type": "text",
      "text": "Here is the summary..."
    }
  ],
  "metadata": {
    "response_prompt_decision": {
      "action": "reply_text",
      "sensitivity": "public"
    },
    "response_action_plan": {
      "type": "reply",
      "external_reply": true
    }
  }
}
```

ターゲットにはプロバイダー識別子が含まれる場合がありますが、生の認証値は含まれない場合があります。どれでも
有効期間が短い応答ハンドルは内部参照として渡され、解決される必要があります。
アダプターの内部。

## アダプターの責任

`ResponseAdapter` は以下を担当します。

- プロバイダー固有のメッセージ形状をレンダリングします。
- プロバイダーの長さ制限を強制する。
- ポリシーが許可しない限り、大量のメンションを避ける。
- アクティブ応答プロンプト ポリシー外のアクションを拒否する。
- 外部から返信する前に感度と機能を再確認します。
- シークレット ストアからのシークレット参照を解決します。
- プロバイダー API の呼び出し。
- 編集された配信ステータスを返す。
- プロバイダーのエラーを安定したフレームワークのエラーにマッピングします。

アダプターは同期または非同期の場合があります。プロバイダーが高速な HTTP 応答を必要とする場合、
Webhook ハンドラーは、アダプターが後で送信する間に ACK を返すことができます。

## 組み込みアダプターターゲット

|アダプター |配信対象 |
|---|---|
| `slack-thread` | Slack `chat.postMessage` (オプションの `thread_ts`) |
| `line-reply` |有効期限の短い返信トークンを使用した LINE 返信 API リファレンス |
| `discord-interaction` | Discord インタラクション応答本体 |
| `discord-channel` | Discord チャンネル メッセージ API |
| `discord-webhook` | Discord Webhook URL |
| `webhook-json` |汎用 JSON 応答またはコールバック URL |
| `external_send` |ツール支援 LINE/Discord/Slack/汎用承認後送信 |

アダプター ID は、チャット ハンドラーではなく、`InputProfile` によって選択されます。

## エラー動作

パブリック チャネルは、プロファイルで許可されている場合にのみ、安全で短いエラーを受信する必要があります。
その行動。詳細なプロバイダー エラーは編集されたログまたは配信に含まれます
ステータス、チャネル応答ではありません。

例:

|状態 |推奨されるアクション |
|---|---|
|送信トークンがありません |生の秘密を持たない編集された配信エラー |
|プロバイダーのレート制限 | `store_only` またはプロバイダー固有の遅延処理 |
|メッセージが長すぎます |通常のプランナーのチャンク化 |
|計画後にポリシーが拒否されました | `store_only` |

## 安全規則

応答プロンプト ポリシーは、アクション境界でデフォルトで拒否されます。

- `computer_use` は、たとえそれが表示されているとしても、デフォルトで明示的な承認を必要とします。
計画のコンテキスト。
- `allowed_actions` 以外のプランはアダプターの納品前に拒否されます。
- `browser_use` は、アクティブなネットワーク ポリシーを尊重する必要があります。
- `python` フォローアップ計画では、サンドボックス/ローカルのみの期待を宣言する必要があります。
- 外部からの応答の前に、アダプタ パスは `sensitivity` と現在の値を再チェックします。
  機能により、古いプロンプト出力がローカルのみのコンテンツや機密コンテンツを漏らすことがなくなります。
