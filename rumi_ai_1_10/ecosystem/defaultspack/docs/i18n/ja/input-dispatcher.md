<!-- docs-i18n-links:start -->
[EN](../../input-dispatcher.md) | [JP](./input-dispatcher.md) | [KR](../ko/input-dispatcher.md) | [CN](../zh-cn/input-dispatcher.md)
<!-- docs-i18n-links:end -->

# 入力ディスパッチャー

`submit_input` はパブリック互換性エントリポイントのままですが、正規
現在のパスは次のとおりです:

```text
RumiInputEnvelope
  -> dispatch_input
  -> action_registry
  -> delivery.action_id handler
```

## 封筒の形状

すべてのインバウンド ターンは `RumiInputEnvelope` に正規化されます。

- `source`: 入力を作成した人または内容
- `target`: 会話、ルート、またはランタイム ターゲット
- `delivery`: アクション選択メタデータ
- `input`: プライマリ テキスト ペイロード
- `params`: アクション固有の構造化データ
- `tools`: オプションの明示的なツール選択
- `attachments`: ターンとともに運ばれるファイルまたは画像
- `metadata`: 監査およびプロバイダーのメタデータ

`delivery.action_id` のデフォルトは `chat.message` です。

## 組み込みアクション

- `chat.message`: 通常のユーザー メッセージ フロー
- `run.instruction`: ランタイムステア/命令をキューに入れる
- `run.interrupt`: 将来の一時停止/キャンセル/リダイレクト セマンティクスの余地のある緊急ランタイム命令
- `agent.delegate`: 構造化ペイロードから 1 つの委任されたエージェントの実行を開始します。
- `model.switch`: 会話のデフォルト モデルの変更を永続化します。
- `model.route`: ターンスコープのルートオーバーライドを設定します

不明な `delivery.action_id` 値は、代わりに構造化エラーを返します。
プロバイダー固有のロジックに違反します。

## 互換性

- 既存の `submit_input(...)` 呼び出し元は引き続き機能します。
- 既存のチャット送信動作は、引き続き同じストアとブロックを経由してルーティングされます。
- 従来の `subagent` の名前付き呼び出しサイトでは、`agent.delegate` または
`model.call` スタイルのユーティリティの内部ルーティング。
