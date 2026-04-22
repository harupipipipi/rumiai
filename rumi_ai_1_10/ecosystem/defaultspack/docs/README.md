# defaultspack Docs

`defaultspack` の canonical 入口です。root docs 側には紹介だけを置き、構造・運用・制約の本体はこの配下に集約します。

## Start Here

1. [architecture.md](./architecture.md)
2. [interfaces.md](./interfaces.md)
3. [operations.md](./operations.md)

## Reading Guide

| 目的 | 読む場所 |
|---|---|
| Pack 全体の責務と実装の骨格を掴む | [architecture.md](./architecture.md) |
| 外から見える surface を確認する | [interfaces.md](./interfaces.md) |
| 起動・開発・テスト・確認観点を知る | [operations.md](./operations.md) |
| chat / message 周りを追う | [chat.md](./chat.md) |
| agent 実行系を追う | [agent.md](./agent.md) |
| AI provider / client を追う | [ai_client.md](./ai_client.md), [ai-providers.md](./ai-providers.md) |
| tool / prompt を追う | [tool.md](./tool.md), [prompt.md](./prompt.md) |
| frontend と shell を追う | [frontend.md](./frontend.md), [frontend_extensions.md](./frontend_extensions.md) |
| flow / modifier / route を追う | [flows.md](./flows.md), [api.md](./api.md) |
| functions と setup-pack API を追う | [functions.md](./functions.md) |
| 永続データと migration を確認する | [data-model.md](./data-model.md), [migration.md](./migration.md) |
| 制約と事故対応を確認する | [security.md](./security.md), [troubleshooting.md](./troubleshooting.md) |

## Contract Coverage

この Pack は [pack-documentation-contract.md](../../../docs/pack-documentation-contract.md) の最初の実例として、required docs と conditionally required docs を `ecosystem/defaultspack/docs/` に集約します。
