<!-- docs-i18n-links:start -->
[EN](../../tool-prompt-conversion.md) | [JP](./tool-prompt-conversion.md) | [KR](../ko/tool-prompt-conversion.md) | [CN](../zh-cn/tool-prompt-conversion.md)
<!-- docs-i18n-links:end -->

# ツール/プロンプトリファレンス

ツールとプロンプトの定義は一部の語彙を共有していますが、共通の語彙は共有していません。
実行境界。

- ツールのオーサリングでは、`rumi_function` または `capability` ファサードを使用します。
- プロンプトオーサリングによりパッシブテキストテンプレートが作成されます。
- 新しい`execution.type="prompt"` ツールはサポートされていません。

## プロンプトを表示するツール

ツール定義をデータとして読み取り、ドキュメント、サンプル、または
プロンプト変数。これはツールを実行せず、ツールを許可しません
許可。

一般的な使用法:

```python
tool_schema = context["call_handler"]("defaults.tool.schema", {
    "tool_name": "file_read"
})
rendered = context["call_handler"]("defaults.prompt.render", {
    "prompt_id": "tool_usage_guide",
    "variables": {"tool_schema": tool_schema}
})
```

## ツールへのプロンプト

プロンプトからツールへの変換は、オーサリング パスとして無効になっています。フローが必要な場合
プロンプトテキスト、電話:

- `defaults.prompt.load_effective`
- `defaults.prompt.resolve_for_conversation`
- `defaults.prompt.render`

ユーザーに見えるツールが必要な場合は、通常の機能/機能ファサードを定義します
適切な信頼できる関数を呼び出します。プロンプトのレンダリングを
プロンプト実行ツール。

## 往復

保証されたツール/プロンプトの往復はありません。ツール実行メタデータ、
機能付与、承認ポリシー、およびプロンプト ソース チェーン メタデータには、
セマンティクスが異なるため、ネイティブ システムに残す必要があります。
