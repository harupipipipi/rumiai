<!-- docs-i18n-links:start -->
[EN](../../prompt_authoring.md) | [JP](./prompt_authoring.md) | [KR](../ko/prompt_authoring.md) | [CN](../zh-cn/prompt_authoring.md)
<!-- docs-i18n-links:end -->

# プロンプトオーサリング

Rumi の製品ボキャブラリーでは、常にロードされる命令については `rule` を優先します。
トリガーまたはオンデマンドの命令/ワークフロー バンドルの場合は `skill`。

`prompt` は、組み立てられた生のモデル入力テキストの下位レベルの実行時用語です。
実行時。 `system prompt` は、システム ロールのトランスポート/API 形式です。
ユーザー向けの主要な概念ではなく、プロンプト テキストです。

プロンプトは受動的なテキスト リソースです。 AI リクエストの動作を記述します。
ただし、モデルの選択、ツールの検出、権限の付与、呼び出しは行われません。
プロバイダーを使用するか、独自にランタイム状態を変更します。

各プロンプトには、安定したプロンプト ID、コンテンツ、オーナー パックまたはプロファイルが必要です。
lint/圧縮の期待。

有効なプロンプトの優先順位は次のとおりです。

1. `profiles/<profile_id>/prompts/` のプロファイルの上書き。
2. `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/` のプロファイル スナップショット。
3.defaultspack プロンプト コンポーネントまたはプロンプト拡張機能からデフォルトをパックします。

プロファイル オーバーライドはユーザー所有のワークスペース プロンプト ファイルであり、
`source_chain`の`profile_override`層。スナップショットはパック プロンプトを保持します
プロファイルの作成時にキャプチャされたバージョン。パックのデフォルトはフォールバックです
プロファイル固有のプロンプトが存在しない場合。

`defaults.prompt.load_effective` は選択したソース、`source_type` を返します。
`source_chain`、生の`content`、および`final_content`。 `defaults.prompt.resolve_for_conversation`
同じ優先順位を使用して、会話変数を最終的な変数にレンダリングします。
内容。

`execution.type="prompt"` を含むツールを作成しないでください。プロンプトは受動的のままです。使用
レンダリングされたプロンプト テキストが必要な場合は、フロー/関数からの `defaults.prompt.render`。

迅速なリンティングにより、冗長性、ロールコンテキストの欠落、およびトークンバジェットにフラグが立てられます。
リスク。圧縮では、安全性、許可、ツール使用の制約を維持する必要があります。

ドキュメントまたは UI コピーを作成するときは、作成された動作を `rules` および
`skills`、およびランタイムについて議論する場合のみ `prompt` または `system prompt` について説明します。
アセンブリ、プロバイダーのペイロード、またはデバッグ。
