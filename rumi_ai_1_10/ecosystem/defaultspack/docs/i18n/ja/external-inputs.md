<!-- docs-i18n-links:start -->
[EN](../../external-inputs.md) | [JP](./external-inputs.md) | [KR](../ko/external-inputs.md) | [CN](../zh-cn/external-inputs.md)
<!-- docs-i18n-links:end -->

# 外部入力

外部入力は、ローカル UI の外部のシステムから Rumi に入るメッセージです。
Webhook、チャット プラットフォーム、自動化コールバック、トンネル、ローカル スクリプト、または
将来のコネクタ。これらはすべて同じフレームワーク境界を使用します。

```text
provider payload
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> dispatch_input / submit_input
  -> ResponsePromptPolicy
  -> ResponsePlanner
  -> ResponseAdapter
```

目標は、プロバイダーの詳細をエッジに保つことです。チャット、エージェント、フロー ロジック
Slack、Discord、LINE、またはトンネル固有ではなく、正規化された入力を受け取る必要があります
ペイロード。

## コアの種類

`ExternalEvent` は正規化された受信レコードです。これには安定したフィールドが含まれています。
`provider`、`workspace`、`scope`、`actor`、`conversation`、`event`、`payload`、
`verified`、および編集された`metadata`。プロバイダー固有の識別子は吸収されます
それらのプリンシパルに。生のリクエストボディは署名チェックに使用できますが、
生のシークレットとトークン値は、返されるイベント オブジェクト内で公開されることはありません。
UI、ログ、またはドキュメント。

`AudiencePolicy` は、Rumi へのイベントの入力を許可するかどうかを決定します。ポリシーでできること
プロバイダー、チーム、チャネル、ユーザー、メンション スタイル、ダイレクト メッセージ ステータスごとのゲート、
レート制限、または必要な検証。ポリシー出力は明示的です: `allow`、
`ignore`、`deny`、または `needs_approval`。

`InputProfile` は、許可されたイベントを `RumiInputEnvelope` にマップします: ロール、入力テキスト、
外部キー/タイトル/モデル、ソースメタデータ、パラメータ、およびツールをチャットします。実行します
変換のみ。イベントが許可されるかどうかは決定されません。

入力と出力の構成は分離されています。入力プロファイルは「何が来たのか」に答えます
出力プロファイルは、「どこに応答できますか?」という質問に答えます。
LINE には組み込みの入力テンプレートが存在しますが、
Discord、Slack、および汎用 Webhook。カスタム テンプレートは次の方法で登録できます。
`/api/external/templates` または `user_data/shared/external_io_templates` に配置されます。
組み込みテンプレートは `setup_mode: copy_paste_select` を公開します: UI レンダリング
テンプレート/プロファイル/プロバイダーの選択に加え、コピー可能なルート パスと貼り付け専用トークン
またはターゲットフィールド。自由形式の YAML/プロファイル編集はカスタムに属します。
LINE、Slack、Discord インタラクションなどの Webhook プロバイダーの場合、
外部入力パネルには、一時パブリック URL ランチャーが含まれています。クラウドフレア
[クイック トンネル] ボタンは、選択したルート パスの一時的なパブリック URL を作成します。
例: `/api/integrations/line/webhook` なので、ユーザーは完全な URL を貼り付けることができます
プロバイダーのダッシュボードに移動します。

`submit_input` は、プロファイル変換後の互換性エントリポイントです。
内部的には `dispatch_input` に転送されるようになり、
`RumiInputEnvelope` by `delivery.action_id`。

`ResponsePlanner` は、実行時の結果をプロバイダーに依存しない応答に変換します。
計画。応答するか、確認のみするか、延期するか、分割するか、切り捨てるか、または
スキップします。

`ResponsePromptPolicy` は、プランナーの前にあるオプションの計画専用レイヤーです。
`reply_text`、`store_only`、`run_browser_use`などのアクションを選択できます。
`run_python`、または `ask_for_approval` ですが、決定オブジェクトのみを返します。
ツールの実行は、通常のツール ポリシー、承認、ターンを経ます。
ランナーの道。

`ResponseAdapter` は、プロバイダー固有のメソッドを通じてそのプランをレンダリングおよび配信します。
Slackスレッド、LINE返信トークン、Discordインタラクションレスポンスなどのサーフェス、
または一般的な Webhook 応答。

デフォルトの入力テンプレートは `include_source_context: true` に設定されています。ルミが順番を告げる
以前に LINE、Discord、Slack、または他のプロバイダーから入力があったランナー
ユーザーのテキストを表示し、生のトークンとリクエスト シークレットをプロンプトに表示しないようにします。

## イベント契約

正規化されたイベントの例:

```json
{
  "provider": "line",
  "workspace": {
    "type": "line_destination",
    "id": "destination-id"
  },
  "scope": {
    "type": "group",
    "id": "C123"
  },
  "actor": {
    "type": "user",
    "id": "U123"
  },
  "conversation": {
    "type": "external",
    "id": "line:group:C123"
  },
  "event": {
    "id": "evt_01",
    "message_id": "msg_01",
    "type": "message",
    "message_type": "text"
  },
  "payload": {
    "type": "message"
  },
  "verified": true,
  "metadata": {
    "reply_token": "short-lived-provider-handle"
  }
}
```

有効期間の短いプロバイダー応答ハンドルは、アダプターで使用するためにメタデータ内に保持されます。彼らは
有効期間の長い構成済みトークンとして扱ったり、UI に表示し直したりしないでください。

## 処理ルール

1. 信頼性の高いフィールドを解析する前にリクエストを検証します。
2. プロバイダーのペイロードを `ExternalEvent` に正規化します。
3. `provider + event_id` を使用して重複を削除します。
4. `AudiencePolicy`を評価します。
5. `InputProfile`を選択します。
6. `submit_input` を呼び出します。
7. 必要に応じて、`ResponsePromptPolicy` を実行して、安全なアクションの決定を行います。
8. `ResponsePlanner` を実行します。
9. `ResponseAdapter`を通じて納品します。

いずれかのステップがイベントを拒否した場合、アダプターはプロバイダーが期待するイベントを返す必要があります。
チャット メッセージを作成せずに確認を行います。

プロンプト ルーティングされた応答アクションは計画専用です。`response_prompt` が返される場合があります。
`ResponsePlan` の決定が行われますが、外部配信は依然として
アダプター パス。許可されるアクション、感度、機能、および承認
要件が再度確認されます。

## ローカルの最初の境界

外部入力サポートは、デフォルトではローカル ランタイムをパブリックにしません。の
明示的に構成しない限り、ゲートウェイと HTTP トランスポートはループバックにバインドされます
それ以外の場合は許可します。パブリック URL プロバイダーは、単なる置き換え可能なエッジ コンポーネントです。
Cloudflare Quick Tunnelは開発中に使用できますが、Cloudflareの一部ではありません。
コア アーキテクチャであり、別のトンネルと交換可能な状態を維持する必要があります。
プロキシ、またはプラットフォームのイングレス。

## 内蔵セットアップ形状

組み込み UI は、YAML エディターではなく、意図的にガイド付きセットアップです。

- `External Input`: プロバイダー/テンプレート/プロファイルを選択し、
  Webhook URL を選択し、デフォルトの応答動作を選択します。
- `External Output`: 送信モードと出力テンプレートを選択し、マスクして貼り付けます
  外部トークンを使用し、Discord `channel_id` などの非シークレット ターゲット ID を貼り付けます。
- `External Custom`: カスタム テンプレート/プロファイルを登録または削除し、保持します
  コンピュータ使用のブラウザワークフローなどの自由形式の応答プロンプト。

LINE はプロバイダーが作成した Webhook URL と `Channel Secret` 検証を使用し、
`Channel Access Token`が返信します。 Discord には 2 つのアウトバウンド モードがあります: `Bot + Channel`
ボット トークンと `channel_id` を使用し、`Webhook URL` はチャネル Webhook を使用します
マスクされた外部トークンとしての URL。 Slack はイベント リクエスト URL、署名を使用します。
シークレット、ボット トークン、およびスレッド対応 `chat.postMessage`。

## 安全上の注意事項

- Webhook エンドポイント管理およびパブリック URL 作成ルートは次のように扱われます。
  ローカル管理者に依存するルートであり、ローカル認証ガードが必要です。
- 外部受信 Webhook ルートは引き続き外部から到達可能ですが、各エンドポイントは
  プロバイダーの署名または共有秘密の検証を強制することが期待されます。
- 新しく作成された汎用 Webhook エンドポイントはデフォルトで無効 +shared_secret に設定されます
  明示的に別の方法で設定されていない限り。
- Cloudflare Quick Tunnel は、交換可能なパブリック URL プロバイダーのみです。それはではありません
  セキュリティ境界線。エンドポイント セキュリティとローカル管理ルート ガードはそのまま残ります
  必須です。

## 既知の制限事項

- この PR の LINE アダプターと Discord アダプターは MVP テキスト応答アダプターであり、そうではありません。
  完全な運用ボットの実装。
- LINE の非テキスト メッセージは、現時点ではプレースホルダー テキストに正規化されています。
- Discord のインタラクション処理は意図的に最小限に抑えられています。完全延期/フォローアップ
  インタラクション行動は、フォローアップ PR で処理する必要があります。
- Cloudflare Quick Tunnel は、交換可能なパブリック URL プロバイダーのみです。そうすべきではありません
  セキュリティ境界として扱われます。エンドポイントセキュリティとローカル管理ルート
  警備員は引き続き必要です。

## 現在のデフォルトパックのルート

現在の統合ルートはプロバイダー固有のアダプターであり、統合する必要があります。
上のフレームワーク境界上:

|ルート |目的 |
|---|---|
| `POST /api/integrations/slack/events` | Slack イベント API の導入 |
| `POST /api/integrations/line/webhook` | LINE Messaging API Webhook の取り込み |
| `POST /api/integrations/discord/interactions` | Discord インタラクションの摂取 |
| `POST /api/integrations/discord/events` | Discordメッセージイベント受付 |
| `GET /api/integrations/secrets` |シークレットステータスのみ |
| `POST /api/integrations/secrets` |書き込み専用シークレットを設定またはクリアする |
| `GET /api/external/tokens` | API キーのような外部トークンのステータス |
| `POST /api/external/tokens` |名前付き外部トークンの更新挿入、名前変更、または削除 |
| `GET /api/external/templates` |組み込みおよびカスタムの入出力テンプレートをリストする |
| `POST /api/external/templates` |カスタムの入力または出力テンプレートを登録する |
| `POST /api/webhooks/inbound/{webhook_id}` |一般的な Webhook の取り込み |
| `GET /api/webhooks/endpoints` | Webhook エンドポイント構成をリストする |

## ローカルホスト入力エンドポイント

AI によって作成された受信エンドポイントは `input_endpoint_create` を使用し、のみを返します
ローカルホストの URL:

```text
http://localhost:{port}/api/webhooks/inbound/{endpoint_id}
```

これらのエンドポイントには、共有シークレットとデフォルトの TTL 保護が必要です。公共
Cloudflare またはトンネル URL は依然として別の懸念事項です。
