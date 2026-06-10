<!-- docs-i18n-links:start -->
[EN](../../flow_spec.md) | [JP](./flow_spec.md) | [KR](../ko/flow_spec.md) | [CN](../zh-cn/flow_spec.md)
<!-- docs-i18n-links:end -->

# フロー仕様

フロードキュメントには、`flow_id`、オプションの`version`および`description`、`inputs`、`outputs`、および順序付けされた`steps`があります。

正規のステップ タイプは、`function`、`subflow`、`branch`、および `parallel` です。
従来のハンドラー/ツール/プロンプト ステップは互換性パスであり、
新しいdefaultspackフローのオーサリングサーフェス。

サポートされている関数ステップ フィールド:

- `id`: 安定したステップ識別子。
- `type`: `function`。
- `function`: 関数ステップの呼び出し可能なエイリアス (`defaults.ai.complete` など)。
- `input`: リテラル値またはテンプレート参照。
- `when`: オプションの条件式。
- `output`: ステップによって書き込まれる変数名。
- `on_error`: オプションのエラー処理ポリシー。

プロファイル スコープのチャット フローでは、プロンプト、ツール、権限、ルーティング、完了、永続性、または監査ステップの前に、アクティブなプロファイルとワークスペースをロードする必要があります。権限フィルターは、ツールを有効にした AI 呼び出しの前に実行する必要があります。

プロンプト解決は機能ステップであり、プロンプト実行ステップではありません。標準
チャットターンコール`defaults.prompt.load_effective` または
プロファイル ワークスペースの作成後、`defaults.prompt.resolve_for_conversation`
利用可能な場合は、そのテキストを AI リクエスト構築に渡します。効果的なプロンプト
解決には、プロファイル オーバーライド、プロファイル スナップショット、パックのデフォルト優先順位が使用されます。
