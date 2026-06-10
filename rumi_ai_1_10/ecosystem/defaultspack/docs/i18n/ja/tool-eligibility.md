<!-- docs-i18n-links:start -->
[EN](../../tool-eligibility.md) | [JP](./tool-eligibility.md) | [KR](../ko/tool-eligibility.md) | [CN](../zh-cn/tool-eligibility.md)
<!-- docs-i18n-links:end -->

# ツールの適格性とブロックされた理由

ツールの可用性は 2 つの場所で計算されるようになりました。

1. チャット/エージェントの準備中のプロバイダーの事前フィルタリング
2. フィルタリングされたツールが何らかの理由でまだ呼び出された場合の実行時の拒否

## ランタイム機能のスナップショット

各ターンは正規化されたトークンを含む `RuntimeCapabilitySnapshot` を記録します。

- 入力特性: `input.text`、`input.image`、`input.file`
- モデル機能: `model.text`、`model.image_input`、`model.tool_calling`、
  `model.thinking`、`model.fast`
- ランタイム機能
- ポリシー機能
- タグ

このデータはメタデータ/イベントに保存され、通常の会話には挿入されません
テキスト。

## ツールの要件

ツール定義では以下を宣言できます。

- `capability_requirements.requires_all`
- `capability_requirements.requires_any`
- `capability_requirements.forbids`
- `requires_model_capabilities`
- `requires_input_modalities`
- `requires_runtime_capabilities`
- `attachment_policy`
- `supports_attachments`

## 安定した理由コード

ブロックまたは拒否されたツールは、安定した理由コードを使用します。

- `missing_capability`
- `missing_input`
- `model_unsupported`
- `disabled_by_user`
- `disabled_by_policy`
- `requires_approval`
- `not_connected_to_profile`
- `requires_trusted_workspace`
- `missing_api_key`
- `attachment_not_supported`
- `risk_blocked`

実行時の拒否は、次のような構造化された結果を返します。

- `status: rejected`
- プロバイダーセーフ `code`
- `reason`
- `required`
- `actual`
- `repair_suggestions`
