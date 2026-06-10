<!-- docs-i18n-links:start -->
[EN](../../prompt_authoring.md) | [JP](./prompt_authoring.md) | [KR](../ko/prompt_authoring.md) | [CN](../zh-cn/prompt_authoring.md)
<!-- docs-i18n-links:end -->

# プロンプトオーサリング

プロンプトは受動的なテキスト リソースです。 AIリクエストに対する動作を記述していますが、
モデルの選択、ツールの検出、権限の付与、プロバイダーの呼び出し、または
ランタイム状態を独自に変更します。

各プロンプトには、安定したプロンプト ID、コンテンツ、オーナー パックまたはプロファイルが必要です。
lint/圧縮の期待。

有効なプロンプトの優先順位は次のとおりです。

1. `profiles/<profile_id>/prompts/` のプロファイル オーバーライド。
2. `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/` のプロファイル スナップショット。
3.defaultspack プロンプト コンポーネントまたはプロンプト拡張機能からデフォルトをパックします。

プロファイル オーバーライドはユーザー所有のワークスペース プロンプト ファイルであり、
`source_chain`の`profile_override`層。スナップショットはパック プロンプトを保持します
プロファイルの作成時にキャプチャされたバージョン。パックのデフォルトはフォールバックです
プロファイル固有のプロンプトが存在しない場合。

`defaults.prompt.load_effective` は選択したソース、`source_type` を返します。
`source_chain`、生の`content`、および`final_content`。 §るみ§3§
同じ優先順位を使用して、会話変数を最終的な変数にレンダリングします。
内容。

`execution.type="prompt"` を使用してツールを作成しないでください。プロンプトは受動的のままです。使う
レンダリングされたプロンプト テキストが必要な場合は、フロー/関数からの `defaults.prompt.render`。

迅速なリンティングにより、冗長性、ロールコンテキストの欠落、およびトークンバジェットにフラグが立てられます。
リスク。圧縮では、安全性、許可、ツール使用の制約を維持する必要があります。
