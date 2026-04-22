# defaultspack Flows

`defaultspack` が持つ Flow / modifier の入口です。

## Flow Inventory

- `simple_chat`: chat conversation 系の基本 Flow
- `agent_chat`: agent 実行と承認ループ
- `planning_agent`: planning 専用 Flow

実体は `flows/<flow_id>/flow.yaml` と `handler.py` にあります。

## Related Surfaces

- Flow ベース route: `routes.json`
- function-first route: `ecosystem.json` の `api_routes`
- Flow 設計の背景: [flow.md](./flow.md)

## When To Update

- 新しい flow / modifier を追加したとき
- trigger, input, output, side effect を変えたとき
- route から到達する Flow が変わったとき
