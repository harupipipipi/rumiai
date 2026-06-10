<!-- docs-i18n-links:start -->
[EN](../../pr_componentization_notes.md) | [JP](./pr_componentization_notes.md) | [KR](../ko/pr_componentization_notes.md) | [CN](../zh-cn/pr_componentization_notes.md)
<!-- docs-i18n-links:end -->

# PR ノート: Defaultspack のコンポーネント化

## 概要

この PR は、既存のパブリック動作を維持しながら、defaultspack を拡張機能のようなコンポーネント フォルダーに移動します。コンポーネント マニフェストには、Webhook のデフォルト、外部プロファイル、統合、ゲートウェイ チャネル、URL プロバイダー、ツール、プロバイダー、プロンプト、ルート、UI サーフェスが含まれるようになりました。

## アーキテクチャの目標

サーフェスの追加は、ファイル ドロップのワークフローになるはずです。

```text
domain/<category>/<component_id>/manifest.json
```

中央レジストリは互換性層と検出層のままです。ハードコードされたコネクタ/プロファイル/プロバイダー/ツール/プロンプトのデフォルトを復元しないでください。

## 新しいコンポーネント フォルダーの規則

新しいドメイン サーフェスをファイル ドロップ コンポーネントとして追加する必要があります。

```text
domain/<category>/<component_id>/
  manifest.json
  rules.py or rules.json
  handler.py / adapter.py / inbound.py / output.py
  README.md optional
  tests optional
```

マニフェストは証拠開示コントラクトです。 ID、カテゴリ/種類、バージョン/ステータス、エントリポイント、ルート、プロファイル、セキュリティ、UI、ポリシー、機能、エイリアス、互換性メタデータ、変換ターゲット、およびソース パックの所有権 (有用な場合) が含まれます。

## PR #92 の互換性

- Gitlawb OpenGateway プロバイダー ID は `gitlawb-opengateway` のままです。
- Gitlawb OpenGateway モデル ID は残ります。
  - `gitlawb-opengateway/mimo-v2.5-pro`
  - `gitlawb-opengateway/mimo-v2-flash`
  - `gitlawb-opengateway/mimo-v2-omni`
- キーなしの動作、デフォルトのベース URL の動作、ブラウザのユーザー エージェントの動作、および固定モデルのホワイトリストの動作は保持されます。
- MiMo Omni は検証済みの画像メタデータを保持します。
- `rumi_model_catalog_pack` プロバイダ/モデル マニフェストは保存され、マニフェストに基づいたままになります。
- LINE Biz Webhook の確認応答/バックグラウンド処理は保持されます。これには、確認応答テキスト、応答トークンの再利用抑制、現在のターンのチャット履歴モード、物理的なクリック プロンプトの動作、オリジン/ソースの記録、署名の検証、および視聴者ポリシーの動作が含まれます。
- ブラウザ/コンピュータ ドライバの安全性は、可視画面のみの動作、前景ガード、承認が必要な物理的アクション、URL スキーム制限、フォールバック順序などを含め、`rumi_default_tools_pack` で維持されています。

## フェーズごとに何が変わったのか

1. Documented the domain component folder convention.
2. Added shared manifest discovery, validation, registry, aliases, diagnostics, and multi-pack roots.
3. Moved webhook endpoint/security defaults into component manifests.
4. Moved input profiles, output profiles, and audience policies into component-backed manifests.
5. Split LINE, Discord, and Slack integrations behind component entrypoints while keeping block shims.
6. Componentized gateway channels and webhook URL providers with legacy import shims.
7. Added manifest-backed tool/browser/computer component metadata, including `rumi_default_tools_pack`.
8. Moved provider/model metadata into provider components, including Gitlawb OpenGateway.
9. コンポーネント化されたプロンプトおよびテンプレートの表面。
10. Loaded route and UI surface metadata from component manifests.
11. Added guardrail and compatibility tests to prevent re-centralizing component defaults.
12. Added migration docs, PR notes, and final quality checks.

## 互換性の保証

- 既存のエンドポイント ID は安定しています: `line-main`、`discord-main`、`slack-main`、`test-webhook`。
- 既存のプロファイル ID は安定しています: `line.default`、`discord.default`、`slack.default`、`generic.webhook.default`。
- 既存のプロバイダー エイリアス、ルート パス、ツール ID、プロンプト ID、および古いインポート パスは、互換性レイヤーを通じて引き続き使用できます。
- コンポーネントの検出は、不正なマニフェストではソフト的に失敗し、任意のコードを実行する代わりに診断を報告します。
- 承認とセキュリティの動作は、既存のポリシー/実行者のパスに残ります。

## 既存の ID とルートは保持されます

- エンドポイント ID は、`line-main`、`discord-main`、`slack-main`、および `test-webhook` のままです。
- プロファイル ID は、`line.default`、`discord.default`、`slack.default`、および `generic.webhook.default` のままです。
- Public webhook, setup, UI, provider, prompt, and tool route paths remain backed by the existing route table, with manifest-backed routes added as metadata/discovery rather than replacing public paths.
- プロバイダーのエイリアス、ツール ID、プロンプト ID、エンドポイント ID、および古いブロック/インポート パスは、互換性シムによって保持されます。

## テストの実行

- `python -m pytest rumi_ai_1_10/tests/test_defaultspack_webhook_endpoints.py rumi_ai_1_10/tests/test_defaultspack_external_send_tool.py rumi_ai_1_10/tests/test_defaultspack_tool_policy.py rumi_ai_1_10/tests/test_defaultspack_ui_registry.py rumi_ai_1_10/tests/test_defaultspack_mcp_registry.py rumi_ai_1_10/tests/test_defaultspack_agent_service_plan.py rumi_ai_1_10/tests/test_defaultspack_opengateway_provider.py rumi_ai_1_10/tests/test_defaultspack_google_provider.py rumi_ai_1_10/tests/test_defaultspack_line_origin_regression.py rumi_ai_1_10/tests/test_browser_cdp_driver.py rumi_ai_1_10/tests/test_browser_computer_security_windows.py rumi_ai_1_10/tests/test_computer_fallback_order.py rumi_ai_1_10/tests/test_defaultspack_domain_components.py rumi_ai_1_10/tests/test_defaultspack_external_components.py rumi_ai_1_10/tests/test_defaultspack_integration_components.py rumi_ai_1_10/tests/test_defaultspack_gateway_url_components.py rumi_ai_1_10/tests/test_defaultspack_tool_components.py rumi_ai_1_10/tests/test_defaultspack_provider_components.py rumi_ai_1_10/tests/test_defaultspack_prompt_components.py rumi_ai_1_10/tests/test_defaultspack_route_ui_components.py rumi_ai_1_10/tests/test_defaultspack_component_guardrails.py -q`: 373 が合格しました。
- `python -m compileall rumi_ai_1_10/ecosystem/defaultspack`: 合格。
- `python .github/scripts/quality_gate_nonregression.py --base-ref origin/master`: 可決、Ruff は変更せず、mypy の負債は減りました。
- `python -m pytest rumi_ai_1_10/tests -q`: 4339 件が合格、20 件がスキップされました。

## 既知のリスク

- PR は互換性シムを意図的に保持するため、ダウンストリームのインポートと呼び出しサイトが移行されるまで一部のフォールバック テーブルが残ります。
- コンポーネントのメタデータとレガシー レジストリが共存します。今後のクリーンアップでは、対象範囲が広くなった後にのみ、重複したフォールバック宣言を廃止する必要があります。
- 検出は複数のエコシステム パックにまたがるようになったため、ランタイム動作が継続している場合でも、不正なサードパーティ マニフェストによって診断が表面化する可能性があります。

## ロールバックのメモ

各フェーズは一貫したコミットです。必要に応じて、後のドキュメント/テストをガイダンスとして保持しながら、関連するフェーズのコミットを元に戻します。古いインポートとルート パスがまだ存在するため、互換性シムによりロールバックがローカライズされます。

## フォローアップのクリーンアップ

- 対象範囲が拡大するにつれて、レガシー フォールバック テーブルをマニフェストに引き続き移動します。
- 残りのプロバイダー/カタログ メタデータのコンポーネント マニフェストを展開します。
- ルート/コンポーネント診断のためのより豊富な UI を追加します。
- ダウンストリームのインポートが移行された後にのみ、互換性シムを段階的に廃止します。
