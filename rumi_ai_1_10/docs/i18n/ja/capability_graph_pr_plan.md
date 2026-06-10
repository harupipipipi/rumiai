<!-- docs-i18n-links:start -->
[EN](../../capability_graph_pr_plan.md) | [JP](./capability_graph_pr_plan.md) | [KR](../ko/capability_graph_pr_plan.md) | [CN](../zh-cn/capability_graph_pr_plan.md)
<!-- docs-i18n-links:end -->

# ケイパビリティグラフ PR プラン

このロードマップにより、Capability Graph の作業がレビュー可能になります。各 PR は小さく、既存の `.flow.yaml` の動作を維持し、バックエンドの基盤が安定するまでビューア UI を回避する必要があります。

## PR 0: ドキュメントと仕様

範囲:

- `docs/capability_graph.md`
- `docs/node_spec.md`
- `docs/profile_spec.md`
- `docs/port_standards.md`
- `docs/capability_graph_pr_plan.md`

受け入れ:

- ドキュメントのみ
- ランタイム実装なし
- ビューア UI なし
- 既存のテストは影響を受けないはずです

## PR 1: NodeDefinition と NodeDiscovery

範囲:

- `core_runtime/node_models.py`
- `core_runtime/ecosystem_nodes.py`
- `kernel:node.load_all`
- `kernel:node.list`
- `kernel:node.get`
- 最小限のデフォルトパック `node.json`
- テスト

必要な動作:

- エコシステム ノードの検出前にコア所有の `rumi.start` を登録します
- 出力ポート `out` および標準 `rumi.flow.start` を使用して `rumi.start` を定義します。
- エコシステム パックがコア所有の組み込みノード ID をオーバーライドしないようにします
- 既存の承認とハッシュ検証に合格したパックからのみ、パックが提供するノード ファイルをロードします
- `rumi.node.v1`を解析します
- `contract` を `standards` に正規化します
- `name` を `display_name.en` に正規化します
- 重複を検出`node_id`
- 無効なポート方向を検出します
- 無効な規格を検出する
- `node.<node_id>`を`InterfaceRegistry`に登録する

目標以外:

- グラフローダー
- グラフコンパイラ
- ビューアUI

## PR 2: プロファイル ローダーとプロファイル対応ノード レジストリ

範囲:

- `core_runtime/profile_models.py`
- `core_runtime/profile_loader.py`
- `core_runtime/profile_node_registry.py`
- `core_runtime/node_state.py`
- `kernel:profile.load_all`
- `kernel:profile.list`
- `kernel:profile.get`
- `kernel:profile.node_state`
- サンプルプロファイル
- テスト

必要な動作:

- ロード`*.profile.yaml`
- 既存の承認とハッシュ検証に合格したパックからのみ、パックが提供するプロファイル ファイルをロードします
- `enabled_nodes` および `disabled_nodes` を解析します
- セキュリティの信頼できる情報源にせずにプロファイル権限を解析します
- ロケールと `node_settings` を解析します
- プロファイルノードの状態を計算します
- `profile.<profile_id>`を`InterfaceRegistry`に登録する
- `StartupProfileManager`と共存して適応します。 PR 2 は、起動時のスタートアップ プロファイルをブリッジしたり置き換えたりしません。

目標以外:

- グラフコンパイラ
- ビューアUI
- 既存のスタートアップ プロファイル モデルに取って代わる

## PR 3: GraphLoader と PortStandardsValidator

範囲:

- `core_runtime/graph_models.py`
- `core_runtime/capability_graph_loader.py`
- `core_runtime/port_standards.py`
- `kernel:graph.load_all`
- `kernel:graph.get`
- `kernel:graph.validate`
- `.graph.yaml` 備品
- テスト

必要な動作:

- ロード`.graph.yaml`
- 既存の承認とハッシュ検証に合格したパックからのみ、パックが提供するグラフ ファイルをロードします
- グラフスキーマを検証する
- ノード参照を確認する
- プロファイル対応ノードの可用性を確認する
- エンドポイントを解析する
- 不足しているポートを検出する
- ソースとターゲットの方向を検証する
- 標準の交差を検証する
- 入力ポートに`multiple: false`を適用します
- 必要な入力ポートを強制します

目標以外:

- コンパイル
- バインディングハンドラーの実行

## PR 4: AgentEngine ツールの挿入は最小限

範囲:

- AgentEngine AI 完了に実行ツールを渡します
- 承認/拒否ループを通じてツールを維持する
- グラフ適用の基礎として、接続されていないツール呼び出しを拒否します。
- テスト

目標以外:

- グラフコンパイラ
- 完全なプロバイダー固有のスキーマ アダプター

## PR 5: GraphCompiler と BindingHandlerResolver

範囲:

- `core_runtime/capability_graph_compiler.py`
- `core_runtime/binding_handlers.py`
- `kernel:graph.compile`
- テスト

必要な動作:

- プロファイルを意識したコンパイル
- コンパイル前に検証する
- 安全なバインディング ハンドラー解決
- 直接の任意インポートは禁止
- ランタイムプロファイル辞書を返します
- `runtime_profile.<profile_id>.<graph_id>`を`InterfaceRegistry`に登録する
- 診断を返す
- コンパイラ コアに AI/ツール/エージェント固有の分岐ロジックがないことを示す回帰テスト

## PR 6:defaultspack ノードと最小限のバインディング

範囲:

-defaultspackエージェント、AIクライアント、ツール、フロントエンドノード定義
-defaultspack バインディング ハンドラー
- バインディングハンドラの登録
- サンプルグラフ
- テスト

必要な動作:

- `tool -> agent.tools` は、パック バインディングを通じてランタイム プロファイルにツール ID を追加します
- `ai_client -> agent.ai` はパック バインディングを通じて AI クライアント参照を追加します
- `cli surface -> frontend.surface` はパック バインディングを通じてフロントエンド サーフェス参照を追加します

## PR 7: フローは明示的なグラフ コンパイル ステップを使用します

範囲:

- `kernel:graph.compile`を明示的なステップとして呼び出すフィクスチャフロー
- テスト

必要な動作:

- フローステップでグラフコンパイルを呼び出すことができます
- コンパイルされたランタイム プロファイルは、出力キーを通じて利用可能です
- グラフコンパイルのないフローは変更されません。

非目標:

- `FlowDefinition` の自動 `capability_graph` フィールド

## PR 8: 接続されたツールの適用とスキーマ アダプター

範囲:

-defaultspack ツール スキーマ アダプター
- グラフ/プロファイル/プリンシパルコンテキストをツール実行に渡します
- 接続されたツールの強制
- `max_tool_calls` などのプロファイル ポリシーの基礎

## PR 9: バックエンド API の統合

範囲:

- プロファイル API
- グラフAPI
- プロファイルノード状態API
- ケイパビリティ グラフ プロファイルと既存のスタートアップ プロファイルの間の関係を文書化して公開します。

必要な動作:

- `StartupProfileManager` を起動時の真実の情報源として保持します
- ケイパビリティグラフプロファイルをグラフ/ランタイムプリセットとして公開
- 2 つのシステム間の明示的な API ブリッジを選択します
- 既存のスタートアップ プロファイル モデルを暗黙的に置き換えないでください。
- テスト

実装された API サーフェス:

- `GET /api/nodes` および `GET /api/nodes/{node_id}`
- `GET /api/profiles` および `GET /api/profiles/{profile_id}`
- `GET /api/profiles/{profile_id}/nodes`
- `GET /api/graphs` および `GET /api/graphs/{graph_id}`
- `POST /api/graphs/{graph_id}/validate`
- `POST /api/graphs/{graph_id}/compile`
- `/api/panel/*` コントロール パネル ビューア セッションのエイリアス

プロファイル API は、`StartupProfileManager` が起動時の信頼できる情報源であることを示す起動プロファイル関係オブジェクトを返します。ケイパビリティ グラフ プロファイルは、スタートアップ プロファイルのサイレント置換としてではなく、グラフ/ランタイム プリセットおよびパレット フィルターとして公開されます。

## PR 10: ビューア ノード マネージャ

範囲:

- プロファイル切り替えUI
- プロファイルスコープのノードパレット
- 有効/無効の表示
- 権限が許可されている場合にのみ、プロファイルの作成/クローン UI を作成します

実装されたビューア サーフェス:

- `/panel/nodes` ノード マネージャ ルート
- プロファイルスイッチャー
- プロファイルスコープのノードカタログとパレット数
- 有効、無効、準備完了、構成欠落、ノード欠落、および未承認の状態表示
- ノードポート、標準、バインディング、およびメタデータの詳細
- グラフの検証とコンパイルのプレビュー コントロール
- プロファイル クローン アクションは、`permissions.can_create_profile` が true の場合にのみ表示されます。

## すべての PR にガードレールを

- `.flow.yaml` の動作の互換性を維持します。
- コアにドメインの意味を追加しないでください。
- 正規ポート互換性フィールドとして `standards` を使用します。
- `contract` および `name` はローダーの互換性としてのみ保持します。
- デフォルト/デフォルトパックの責任を明示的に保ちます。
- ローダー、バリデーター、およびコンパイラーから診断を返します。
- 1 つの PR 内でノード、プロファイル、グラフ、コンパイラ、AgentEngine、およびビューアの作業を組み合わせることは避けてください。
