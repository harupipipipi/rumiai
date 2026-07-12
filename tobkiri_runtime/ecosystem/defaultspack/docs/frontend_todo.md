# defaultspack Frontend TODO

この TODO は `defaultspack` standalone frontend を「本体が全部知る UI」ではなく「registry で増築される shell」にしていくための作業メモです。

## Done

- `/api/ui/catalog` を追加
- `/api/ui/settings` を追加
- `/api/ui/conversations/{id}/preview` を追加
- right sidebar を backend catalog 駆動に変更
- settings modal を schema 駆動に変更
- preview pane を conversation preview API 駆動に変更
- chat renderer に code/image/widget/unknown fallback を追加

## Next

- `chat_renderers` metadata と frontend renderer 実装を完全に分離する
- widget type ごとの専用 renderer registry を `webapp/src/renderers/` に切り出す
- preview source を tool execution event と stream event からも直接生成する
- settings 保存を section ごとの validation 付きにする
- frontend extension manifest に JSON schema を付ける
- `RightSidebar` の item icon を manifest 指定可能にする
- custom renderer bundle の lazy load を導入する
- viewer 側 panel でも同じ registry contract を使い回せるようにする

## Nice To Have

- `user_data/shared/frontend_extensions/` 用 scaffold CLI
- live reload 付き manifest watcher
- widget renderer error boundary
- preview pane の pin/tab/split
- settings 変更履歴
