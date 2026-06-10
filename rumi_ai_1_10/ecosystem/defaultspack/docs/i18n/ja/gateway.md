<!-- docs-i18n-links:start -->
[EN](../../gateway.md) | [JP](./gateway.md) | [KR](../ko/gateway.md) | [CN](../zh-cn/gateway.md)
<!-- docs-i18n-links:end -->

# ゲートウェイ

`domain/gateway` は、セッション ルーティングを備えたローカル コントロール プレーン シェルを提供し、
チャンネルアダプター。最初の実装では、軽量のローカル HTTP が開始されます。
ステータスと認証されたイベントの取り込み用のサーバー。 WebSocket プロトコル ヘルパーは次のとおりです。
`domain/gateway/ws.py` では型指定されたリクエスト/イベント エンベロープとして表されます。
ゲートウェイはデフォルトで `127.0.0.1` にバインドし、そうでない限り外部バインド アドレスを拒否します。
ランタイム設定でそれらを明示的に有効にし、ベアラーまたは
POST 取り込み用の `x-rumi-gateway-token` トークン。

セッションキーは次のとおりです。

- `agent:{agent_id}:main`
- `agent:{agent_id}:chat:{conversation_id}`
- `agent:{agent_id}:line:user:{line_user_id}`
- `agent:{agent_id}:discord:channel:{channel_id}`
- `cron:{job_id}`
- `webhook:{webhook_id}`

## 外部入力関係

ゲートウェイはローカルの取り込みシェルであり、外部入力フレームワーク自体ではありません。公共
またはプロバイダー固有のイベントは `ExternalEvent` に正規化され、次のようにチェックされる必要があります。
`AudiencePolicy`、`InputProfile` を通じてマッピングされ、を通じて送信されます。
`submit_input`。ゲートウェイ メッセージは、これらのイベントのソースの 1 つである可能性があります。

応答の配信は `ResponsePlanner` および `ResponseAdapter` を経由する必要があるため、
チャットとエージェントのコードは Slack、Discord、LINE、Webhook、トンネルを学習しません
詳細。

Cloudflare Quick Tunnel を使用する場合、それは単に、
ローカルエンドポイント。正規のゲートウェイ、認証システム、または
外部入力ランタイム。
