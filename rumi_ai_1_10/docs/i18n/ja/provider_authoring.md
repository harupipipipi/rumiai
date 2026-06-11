<!-- docs-i18n-links:start -->
[EN](../../provider_authoring.md) | [JP](./provider_authoring.md) | [KR](../ko/provider_authoring.md) | [CN](../zh-cn/provider_authoring.md)
<!-- docs-i18n-links:end -->

# プロバイダオーサリング

プロバイダーのオーサリングはマニフェストファーストです。 OpenAI 互換プロバイダーは、
プロバイダー マニフェストとモデル定義ファイルで追加可能。 Pythonプロバイダー
コードはカスタム プロトコルの場合にのみ必要です。

プロバイダー マニフェストを `extensions/llm/providers/<provider_id>/manifest.json` に配置します。
または、同じ拡張レイアウトを公開するインストール済みのカタログ パック。モデルを配置する
`extensions/llm/providers/<provider_id>/models/*.json` の定義。

OpenAI 互換プロバイダーの場合は、次のように設定します。

- `category: "llm_provider"`
- `adapter: "openai_compatible"`
- `api_key_env` およびオプションの `base_url_env`
- `default_base_url`
- `default_model` または `default_model_for`
- `streaming`、`vision`、`native_tool_calling` などの機能メタデータ

モデル機能には、既知の場合、`vision`、`thinking`、`tool_calling`、`fast`、および `knowledge_level`を含める必要があります。ルーティングは、リクエストがモデルを直接使用できるか、ブリッジ ステップが必要かどうかをこれらのフィールドに基づいて決定します。

API キーは、既存のシークレット/プロバイダー キー パスに存在する必要があります。キーをプロファイル ワークスペースやプロバイダー マニフェストに保存しないでください。プロバイダーのテストでは、カタログの読み込み、キーのステータス、モデル機能の解決、ルーティングの互換性、および障害動作をカバーする必要があります。

厳選されたプロバイダー テーブルは、不足しているレガシーの互換性フォールバックです。
メタデータ。新しいプロバイダーでは、ランタイム コードにハードコーディングされた行を追加する必要はありません。
