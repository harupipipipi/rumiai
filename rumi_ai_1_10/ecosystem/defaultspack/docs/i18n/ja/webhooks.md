<!-- docs-i18n-links:start -->
[EN](../../webhooks.md) | [JP](./webhooks.md) | [KR](../ko/webhooks.md) | [CN](../zh-cn/webhooks.md)
<!-- docs-i18n-links:end -->

# Webhook

Webhook は、外部入力フレームワークのトランスポートの 1 つです。 Webhook ハンドラー
プロバイダー要求を認証し、`ExternalEvent` を抽出して、
イベントからポリシーおよびプロファイルの選択。 Webhook コードは薄いままである必要があります。

## ハンドラーの形状

```text
HTTP request
  -> signature or token check
  -> provider parser
  -> ExternalEvent
  -> AudiencePolicy
  -> InputProfile
  -> RumiInputEnvelope
  -> dispatch_input / submit_input
  -> ResponsePlanner
  -> ResponseAdapter
```

ハンドラーはプロバイダー固有の作業のみを実行する必要があります。

- 署名、タイムスタンプ、または共有トークンを検証します。
- プロバイダーチャレンジリクエストに応答します。
- ペイロード フィールドを `ExternalEvent` にマップします。
- プロバイダーが必要とする確認応答の形式を返します。
- 選択した`ResponseAdapter`を呼び出します。

彼らはモデルの行動、会話の記憶戦略、プロンプトを決定すべきではありません。
選択、またはエージェントのルーティング。 `InputProfile`に属します。

## 検証のリクエスト

プロバイダーの検証は、ペイロード フィールドを信頼する前に行う必要があります。

|プロバイダー |検証 |
|---|---|
|スラック | `x-slack-signature` および `x-slack-request-timestamp` |
|ライン | `x-line-signature` |
|不和 | `x-signature-ed25519` および `x-signature-timestamp` |
|汎用 Webhook |ベアラー トークン、HMAC 署名、または別の構成された検証ツール |

未署名の開発モードはローカルテスト用に存在する可能性がありますが、運用プロファイルは
検証が必要である必要があります。検証結果はブール値または
ステータス文字列。生の署名シークレットと受信トークン値は決して使用しないでください。
示されています。

## べき等性

すべての Webhook イベントには安定した `event_id` が必要です。枠組みは落ちるべきだ
以下を使用して複製します。

```text
dedupe_key = provider + ":" + event_id
```

プロバイダーがイベント ID を提供しない場合、ハンドラーはイベント ID を
タイムスタンプとメッセージ ID、または安定したペイロード フィールドのハッシュから。ハッシュしないでください
生のシークレットを ID に変換します。

## チャレンジと肯定応答

一部のプロバイダーでは、通常の処理の前に特別な応答が必要です。

- Slack `url_verification` は、提供されたチャレンジを返します。
- Discord ping は ping 応答タイプを返します。
- LINE は通常、通常の HTTP 200 確認応答を受け入れます。

処理が非同期で継続する場合は、最初にプロバイダーに確認応答を返し、
`ResponseAdapter` が最終的な応答を返します。

LINE `computer_use_line_biz` エンドポイントは、次の方法で高速 ACK 動作を選択できます。
`response.background_processing: true`。これは Webhook 処理を次の場所に移動するだけです。
インプロセス ワーカーなので、プロバイダーは HTTP 200 をすぐに受信します。そうではありません
実験的なバックグラウンド デスクトップ ドライバーを有効にします。目に見えるコンピューター使用の痕跡
`RUMI_ENABLE_EXPERIMENTAL_BACKGROUND_COMPUTER_USE=1` が設定されていない限り、デフォルト。
LINE Biz のコンピューター使用ターンのデフォルトは現在のターンのチャット コンテキストが古すぎます
失敗したツールのログとスクリーンショットによって、次の外部応答プロンプトが肥大化することはありません。

## 一般的な Webhook プロファイル

汎用 Webhook は同じ外部入力パスを使用する必要があります。

```json
{
  "provider": "webhook",
  "event_id": "build_123",
  "kind": "event",
  "text": "Build failed on main",
  "metadata": {
    "repository": "example/repo",
    "status": "failed"
  }
}
```

プロファイルによって、これがチャット メッセージになるか、エージェント タスクになるか、フローになるかが決まります。
トリガー、または無視されたイベント。

Webhook エンドポイントで以下を定義できるようになりました。

- `target`
- `default_delivery`
- `allowed_delivery_actions`
- `ttl_seconds` または `expires_at`

受信汎用 Webhook は最初にエンドポイントのデフォルトを適用し、次にリクエストのみを許可します
明示的にホワイトリストに登録された配信オーバーライド。

## パブリック URL

Webhook には到達可能な URL が必要ですが、URL プロバイダーはフレームワークの外にあります。
Cloudflare Quick Tunnel は一時的な開発 URL を提供する場合がありますが、
ランタイムはそれを交換可能なプロバイダーとして扱う必要があります。同じ Webhook コントラクトが必要です
ローカルホスト、リバース プロキシ、プラットフォーム ルート、またはその他のトンネルの背後で動作します。
