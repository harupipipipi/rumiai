<!-- docs-i18n-links:start -->
[EN](../../port_standards.md) | [JP](./port_standards.md) | [KR](../ko/port_standards.md) | [CN](../zh-cn/port_standards.md)
<!-- docs-i18n-links:end -->

# ポート規格

ポート標準は、2 つのポートが接続できるかどうかを決定するために使用される文字列識別子です。

これらは意図的に一般的なものになっています。コアは文字列を比較し、交差を計算します。エコシステムは独自のドメインの意味をパックします。

## 互換性ルール

フェーズ 1 の互換性:

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

## 例

```text
rumi.flow.start
rumi.ai.client
rumi.ai.provider
rumi.tool.bundle
rumi.agent.runtime
rumi.memory.store
rumi.prompt.bundle
rumi.ui.surface
rumi.cli.surface
pack.github.repository.v1
company.internal.docs.v1
```

## 名前空間のガイダンス

```text
rumi.*       reserved for rumiai standard names
<pack_id>.* pack-owned standards
company.*   organization-owned standards
org.*       organization-owned standards
```

コアは名前空間を権限境界として扱ってはなりません。名前空間は互換性ラベルのみです。

## 複数の標準

ポートは複数の標準を宣言する場合があります。

```json
{
  "id": "tools",
  "direction": "input",
  "standards": [
    "rumi.tool.bundle",
    "defaultspack.tool.bundle.v1",
    "openai.function_tools.compat"
  ]
}
```

これにより、ドメイン固有のロジックをコアに導入することなく、1 つのポートで複数の互換性のある機能形状を受け入れることができます。

## レガシー契約

`contract` はレガシー入力互換性のみです。

```json
{
  "id": "tools",
  "direction": "input",
  "contract": "rumi.tool.bundle"
}
```

ローダーはそれを次のように正規化します。

```json
{
  "id": "tools",
  "direction": "input",
  "standards": ["rumi.tool.bundle"]
}
```

新しいファイルには `standards` を使用する必要があります。

## 複数かつ必須

入力ポートの検証:

- `multiple: false` では、最大 1 つの入力エッジが許可されます
- `multiple: true` は複数の入力エッジを許可します
- `required: true` には少なくとも 1 つの入力エッジが必要です

出力側の `multiple` はフェーズ 1 では厳密に適用されません。

## アダプター

アダプターはフェーズ 1 が終わるまで延期されます。初期検証では正確な標準交差のみが使用されます。

予約された将来の形状:

```json
{
  "from": "rumi.cli.surface",
  "to": "rumi.ui.surface",
  "adapter": "defaultspack.frontend.adapt_cli_surface"
}
```
