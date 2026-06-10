<!-- docs-i18n-links:start -->
[EN](../../prompt.md) | [JP](./prompt.md) | [KR](../ko/prompt.md) | [CN](../zh-cn/prompt.md)
<!-- docs-i18n-links:end -->

# 即時設計

プロンプトはパッシブ テキスト レイヤーです。保存、検証、解決、レンダリングを行います。
テンプレートのプロンプトは表示されますが、ツールの選択、権限の付与、AI の選択は行われません。
プロバイダー、呼び出しモデル、またはチャット状態自体を変更します。

## 有効なプロンプトの優先順位

`defaults.prompt.load_effective`と
`defaults.prompt.resolve_for_conversation` は同じ優先順位を使用します。

1. ワークスペース プロンプト ディレクトリからのプロファイル オーバーライド
   `profiles/<profile_id>/prompts/`。
2. プロファイルのスナップショット
   `profiles/<profile_id>/ecosystem/snapshots/<pack>/prompts/`。
3.defaultspack プロンプト コンポーネントまたはプロンプト拡張機能からデフォルトをパックします。

ワークスペース プロンプト ファイルは、正式な `profile_override` レイヤーです。それは
ユーザーが所有し、スナップショットよりも優先されます。効果的な即時応答には次のものが含まれます。
`source_type`、`source`、`source_chain`、`content`、`final_content`と流れます。
ステップでは、どのレイヤーが最終的なテキストを生成したかを監査できます。

## 関数

- `defaults.prompt.load_effective` は、選択したプロンプト テキストとソースを返します。
  会話変数をレンダリングせずにチェーンします。
- `defaults.prompt.resolve_for_conversation` は同じ有効なプロンプトを解決します
  明示的な `variables` とパッシブからの `{{...}}` 変数をレンダリングします。
  `context.*` の値 (例: `context.profile_id`、`context.conversation_id`、
  `context.message_count`、および`context.messages`。
- `defaults.prompt.validate_template` はテンプレート構文を検証し、ユーザーを報告します
  変数、コンテキスト変数、宣言された変数、警告、およびエラー。
- `defaults.prompt.render` は、提供された明示的なプロンプト/テンプレートをレンダリングします。
  変数。

## オーサリング ルール

プロンプト テンプレートでは、`{{variable}}` および `{{context.variable}}` プレースホルダーを使用できます。
欠落している変数はレンダラーによってテキストに残されます。検証は次の目的で使用できます
フローが実行される前にそれらを検出します。

プロンプトオーサリングでは、実行可能ツールを作成してはなりません。 `execution.type="prompt"`は
従来の互換性パスのみであり、オーサリング サーフェスではありません。ワークフローの場合
レンダリングされたプロンプト テキストが必要な場合は、フロー/関数から `defaults.prompt.render` を呼び出します。
ツールが必要な場合は、`rumi_function` または `capability` ツール ファサードを作成します。

プロンプトファイルはデータです。ファイルの読み取り、プロバイダーの呼び出し、または
タッチ ホスト機能はプロンプト オーサリングには属しません。そのロジックは生きていなければならない
信頼できる機能と明示的な機能付与の背後にあります。
