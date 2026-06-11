<!-- docs-i18n-links:start -->
[EN](../../input-profiles.md) | [JP](./input-profiles.md) | [KR](../ko/input-profiles.md) | [CN](../zh-cn/input-profiles.md)
<!-- docs-i18n-links:end -->

# 入力プロファイル

`InputProfile` は、許可された `ExternalEvent` が実行時入力になる方法を記述します。
これは、外部の視聴者のコンテキストと Rumi の行動の間の架け橋です。

プロファイルにより、プロバイダー エッジ コードが小さく抑えられます。 Webhook ハンドラーはイベントを正規化します。
プロファイルは、Rumi がそれらのイベントに対して何をすべきかを選択します。

## 責任

入力プロファイルは以下を選択します。

- 宛先タイプ: チャット、エージェント、フロー、または無視。
- 会話の鍵となる戦略。
- モデルとプロンプトのデフォルト。
- メモリとコンテキストのポリシー。
- 応答アダプター;
- 許可されるイベントの種類。
- テキスト変換と添付ファイルの処理;
- イベントに応答できない場合のフォールバック動作。

プロファイルには生のシークレット値は保存されません。シークレット名を参照したり、
資格情報 ID。

## 例

```json
{
  "id": "slack-support-thread",
  "enabled": true,
  "provider": "slack",
  "match": {
    "team_id": "T123",
    "channel_id": "C_SUPPORT",
    "event_kinds": ["message", "app_mention"]
  },
  "audience_policy_id": "support-channel-policy",
  "destination": {
    "type": "chat",
    "conversation_kind": "external",
    "session_key": "slack:{team_id}:{channel_id}:{thread_id}"
  },
  "runtime": {
    "model": "stub/default",
    "system_prompt_id": "support_assistant"
  },
  "response": {
    "adapter_id": "slack-thread",
    "mode": "reply"
  }
}
```

## 視聴者ポリシーのリンク

`AudiencePolicy`は「このイベントはルーミに入ってもいいですか？」に答えます。
`InputProfile`は「ルーミはどうすればいいですか?」に答えます。

プロファイルは、広範な許可ルールを埋め込むのではなく、ポリシーを参照する必要があります。
これにより、モデレーション、レート制限、視聴者ゲートを複数の環境で再利用できるようになります。
プロフィール。

## セッションキー

プロファイルは安定したセッション キーを生成して、外部の会話をマップバックする必要があります。
既存の Rumi の会話へ:

|プロバイダー |セッションキーの例 |
|---|---|
|たるみスレッド | `slack:{team_id}:{channel_id}:{thread_id}` |
|スラックDM | `slack:{team_id}:dm:{user_id}` |
| LINEソース | `line:{source_type}:{source_id}` |
|ディスコードチャンネル | `discord:{guild_id}:{channel_id}` |
|汎用 Webhook | `webhook:{profile_id}:{external_subject}` |

セッションキーは資格情報ではありません。シークレットが含まれていない場合はログに記録できます
または機密性の高いメッセージの内容。

## submit_input ペイロード

`submit_input` は、正規化されたイベントと選択されたプロファイルを受け取る必要があります。

```json
{
  "event": {
    "event_id": "evt_01",
    "provider": "slack",
    "text": "summarize the thread"
  },
  "profile": {
    "id": "slack-support-thread",
    "destination": {"type": "chat"}
  },
  "policy": {
    "decision": "allow"
  }
}
```

この関数は、プロバイダーに依存しないランタイム結果を返します。プロバイダーの配送は、
後で `ResponsePlanner` および `ResponseAdapter` によって処理されます。

## プロファイルの安全性のデフォルト

- 明示的に有効にするまでデフォルトは無効になります。
- ローカル開発フラグがアクティブでない限り、検証済みのイベントが必要です。
- デフォルトではボット/セルフメッセージを無視します。
- 最小権限のモデル、ツール、エージェント設定を使用します。
- 安全でない公的反応よりも反応しないことを好みます。
- 監査または UI 表示の前にメタデータを編集します。
