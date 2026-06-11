<!-- docs-i18n-links:start -->
[EN](../../defaultspack-functions.md) | [JP](./defaultspack-functions.md) | [KR](../ko/defaultspack-functions.md) | [CN](../zh-cn/defaultspack-functions.md)
<!-- docs-i18n-links:end -->

# デフォルトパック関数

Defaultspack は、デフォルトの機能を Rumi 関数として公開します。 HTTP ルート、AI ツール、フロー ノードは、機能を安定したパブリック オペレーション コントラクトとして扱う必要があります。

## 関数の呼び出し

正規の修飾名がわかっている場合は、それを使用します。

```json
{
  "type": "function.call",
  "qualified_name": "defaultspack:ai_set_thinking_level",
  "args": {
    "scope": "profile",
    "profile_id": "openrouter/tencent/hy3-preview:free",
    "level": "high"
  }
}
```

関数は、`defaults.ai.set_thinking_level` や `defaultspack.ai.set_thinking_level` などの語彙エイリアスも公開します。正規関数 ID にはドットが含まれません。エイリアスはそうします。

## 関数とツール

関数はランタイム/API オペレーションです。ツールは AI モデルに示されるファサードにすぎません。

```json
{
  "tool_id": "set_thinking_level",
  "name": "set_thinking_level",
  "execution": {
    "type": "rumi_function",
    "qualified_name": "defaultspack:ai_set_thinking_level"
  }
}
```

`ToolExecutor` は共有の `CapabilityExecutor` を介して `rumi_function` 呼び出しを送信するため、ツールの使用とパック間の呼び出しは同じ権限境界を通過します。

## 思考レベル

モデルのランタイム設定は `ModelRuntimeSettingsService` によって所有されます。主なエントリポイントは次のとおりです。

- `defaultspack:ai_get_preferred_model`
- `defaultspack:ai_set_preferred_model`
- `defaultspack:ai_get_thinking_level`
- `defaultspack:ai_set_thinking_level`
- `defaultspack:ai_get_effective_thinking_level`
- `defaultspack:ai_normalize_thinking_level`

チャットまたは AI 補完パラメータに `thinking_level` が含まれていない場合、defaultspack は会話、プロファイル、次にグローバル設定から有効レベルのサーバー側を解決します。

## モデルの機能とルーティング

モデル カタログは、プロファイル対応ルーティングで使用される機能メタデータを公開するようになりました。

- `defaultspack:ai_search_models` / `defaults.ai.search_models`
- `defaultspack:ai_get_model_capabilities` / `defaults.ai.get_model_capabilities`
- `defaultspack:ai_recommend_model` / `defaults.ai.recommend_model`
- `defaultspack:ai_route_model` / `defaults.ai.route_model`
- `defaultspack:ai_explain_model_choice` / `defaults.ai.explain_model_choice`

能力フィールドには、`supports_vision`、`supports_tool_calling`、`supports_thinking`、`supports_fast`、`speed_tier`、`quality_tier`、`knowledge_level`、`knowledge_band`、および役割の推奨事項が含まれます。 `knowledge_level` は相対的な rumiai ルーティング スコアであり、インテリジェンスに関する絶対的な主張ではありません。

ビジョン ブリッジと互換性ユーティリティ ルーティングは、次の方法で利用できます。

- `defaultspack:vision_describe_images` / `defaults.vision.describe_images`
- `defaultspack:agent_run_subagent` / `defaults.agent.run_subagent` (ユーティリティ ルーティングまたは委任された実行の互換性エイリアス)
- `defaultspack:prompt_lint_prompt` / `defaults.prompt.lint_prompt`
- `defaultspack:prompt_compact_prompt` / `defaults.prompt.compact_prompt`

## フローの例

```yaml
- id: set_reasoning
  phase: prepare
  priority: 10
  type: function
  function: defaultspack.ai.set_thinking_level
  input:
    scope: turn
    level: high
  output: thinking_level_result
```

## セキュリティ

読み取り/リスト/検索/ステータス機能は低リスクです。チャット、AI 呼び出し、メモリ、アーティファクトの変異は、通常、中程度のリスクです。ファイルの書き込み、ターミナルの実行、git プッシュ/コミット、プロバイダー キーの変更、ブラウザ/コンピューターの制御、クリップボードの書き込み、およびパック パッチの強制操作は高リスクであり、`caller_requires` を宣言します。

パックの作成者は、呼び出し元のプリンシパルが保持されるように、`ToolExecutor` または共有の `CapabilityExecutor` を通じてdefaultspack 関数を呼び出す必要があります。 `domain.function_runtime.bridge.invoke_function()` は、HTTP ルート アダプタおよびその他のデフォルトパックが所有するフォールバックの内部 `defaultspack` プリンシパルにデフォルト設定されます。これを直接呼び出す外部パックは、明示的な `principal_id` を渡す必要があります。
