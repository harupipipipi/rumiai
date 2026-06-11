<!-- docs-i18n-links:start -->
[EN](../../domain_component_migration_guide.md) | [JP](./domain_component_migration_guide.md) | [KR](../ko/domain_component_migration_guide.md) | [CN](../zh-cn/domain_component_migration_guide.md)
<!-- docs-i18n-links:end -->

# Defaultspack ドメイン コンポーネント移行ガイド

このガイドでは、中央レジストリを拡張せずにドメイン サーフェスを追加または移行する方法について説明します。

## 互換性を第一に

移行中にパブリック ID、ルート、またはインポートの名前を変更しないでください。コードをコンポーネント フォルダーに移動するときに、古いインポート パスをシムとして保持します。既存のルート パス、エンドポイント ID、プロファイル ID、プロンプト ID、プロバイダー エイリアス、およびツール ID を安定した状態に保ちます。

## Webhook または統合の追加

作成:

```text
domain/webhooks/<provider>/manifest.json
domain/integrations/<provider>/manifest.json
domain/integrations/<provider>/inbound.py
domain/integrations/<provider>/security.py
domain/integrations/<provider>/normalizer.py
domain/integrations/<provider>/output.py
domain/integrations/<provider>/rules.json
```

`domain/webhooks/<provider>/manifest.json` でエンドポイントのデフォルトを宣言します。実行時の動作とルートのメタデータを `domain/integrations/<provider>/manifest.json` に記述します。 `blocks/integrations/<provider>.py`はシムとして残しておきます。

## プロバイダーまたはモデルの追加

作成:

```text
domain/providers/<provider_id>/manifest.json
domain/providers/<provider_id>/models.json
```

プロバイダー コンポーネントはランタイム メタデータを強化します。 `rumi_model_catalog_pack` などのマニフェストベースのカタログ パックは分離されたままで、引き続きプロバイダー/モデル カタログ マニフェストを所有します。プロバイダー アダプターは、ツール レジストリまたはツール ポリシー モジュールをインポートしてはなりません。

## ツールの追加

作成:

```text
domain/tools/<tool_id>/manifest.json
```

コンポーネント マニフェストは、`entrypoints.tool_manifest` を持つ既存の `tools/<tool_id>/manifest.json` を指すことができます。承認と実行は引き続き、`ToolRegistry`、`ToolOrchestrator`、`ToolExecutor`、および既存のポリシー チェックを経由する必要があります。

## ブラウザまたはコンピュータのドライバ サーフェスの追加

所有するパックの下にコンポーネントのメタデータを作成します。次に例を示します。

```text
rumi_default_tools_pack/domain/browser/<driver_id>/manifest.json
rumi_default_tools_pack/domain/computer/<driver_id>/manifest.json
```

表示画面のみの動作、前景のガード、明示的な物理的アクションの承認、および既存のフォールバック順序を保持します。

## プロンプトまたはテンプレートの追加

作成:

```text
domain/prompts/<prompt_id>/manifest.json
domain/prompts/<prompt_id>/prompt.md
domain/prompts/<prompt_id>/rules.json
domain/templates/<template_id>/manifest.json
```

プロンプト コンポーネントはプロバイダーやツールに依存しません。ユーザーが保存したプロンプトは引き続き `user_data/shared/prompts` に存在します。

## ルートまたは UI メタデータの追加

コンポーネントは `routes` でルート レコードを宣言できます。既存のルート テーブルはフォールバック互換性を維持します。 UI サーフェスは以下に存在します。

```text
domain/ui_surfaces/<surface_id>/manifest.json
```

マニフェストの `ui` を通じて UI メタデータを公開し、フロントエンド カタログの形状を安定させます。

## チェックリストを確認する

- コンポーネント マニフェストは診断なしで検証されます。
- 古いインポート パスは引き続きインポートされます。
- 古い ID とルートは引き続き解決されます。
- テストは、移動されたデフォルトとシムをカバーします。
- セキュリティデフォルトは弱まりませんでした。
- 中央レジストリは、新しいデフォルトを所有するのではなく、コンポーネントをロードまたは検出します。
