<!-- docs-i18n-links:start -->
[EN](../../vision_bridge.md) | [JP](./vision_bridge.md) | [KR](../ko/vision_bridge.md) | [CN](../zh-cn/vision_bridge.md)
<!-- docs-i18n-links:end -->

#ビジョンブリッジ

Vision Bridge を使用すると、非視覚プライマリ モデルが画像との会話を続けることができます。ビジョン対応ユーティリティ モデルは、構造化された画像理解を作成し、defaultspack が概要、OCR テキスト、関連詳細、および不確実性をテキスト コンテキストとして挿入します。

会話メタデータには `conversation_image_context` が格納されるため、非ビジョン モデルに切り替えるときに同じ画像コンテキストを再利用できます。
