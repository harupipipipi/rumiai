<!-- docs-i18n-links:start -->
[EN](../../model-packs.md) | [JP](./model-packs.md) | [KR](../ko/model-packs.md) | [CN](../zh-cn/model-packs.md)
<!-- docs-i18n-links:end -->

# モデルパックと`model.call`

モデル ルーティングは、プレーン モデル ID に加えて `modelpack/<id>` をサポートするようになりました。
従来の複合モデル。

## モデルパックの形状

`ModelPack` は、小さなルーティング マニフェストです。

- `id`
- `display_name`
- `members`
- `rules`
- `fallback`
- オプションの予算、安全性、メタデータ

最初の実装はフォールバック チェーン スタイルの選択に焦点を当てていますが、
アンサンブルまたはレビューチェーンモードのためのスペースを確保します。

## 解決策

`ModelRouter` と `AIClient` は、現在のターンを使用して `modelpack/<id>` を解決します。

- 画像入力/視覚ニーズ
- ツール呼び出しのニーズ
- 要求された思考レベル
- タスクのヒント
- カスタムパックルール
- フォールバックメンバー

レガシー `composite_models` は互換性を維持し、内部コンポーネントとして扱うことができます。
パックのような構造。

## `model.call`

`model.call` は、「別のモデルに質問する」ための限定されたユーティリティ パスです。

- デフォルトではツールにアクセスできません
- `required_capabilities`、`model_hint`、`output_schema`、`max_tokens`を受け入れます
  そして`attachments`
- 転送前に非表示のメタデータとシークレットを削除します
- 再帰の深さの制限を強制します

このように境界を使用します。

- `model.call`: 別のモデルへの限定された質問
- `agent.delegate`: 委任されたツール対応作業
- `model.switch`: 永続的な会話のデフォルトの変更
- `model.route`: ターンスコープのルーティングオーバーライド
