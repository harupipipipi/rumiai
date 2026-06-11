<!-- docs-i18n-links:start -->
[EN](../../model_routing.md) | [JP](./model_routing.md) | [KR](../ko/model_routing.md) | [CN](../zh-cn/model_routing.md)
<!-- docs-i18n-links:end -->

# モデルルーティング

モデル ルーティングは、ユーザーの優先モデル グループから始まり、画像、ファイル、要求されたツール、要求された思考レベル、速度のヒント、およびユーティリティ モデルの設定をチェックします。

ルーターは、`selected_model`、`original_model`、`selected_group`、`reason_codes`、`warnings`、`bridge_required`、`bridge_plan`、および `utility_models`を返します。ツールの選択は依然として助言です。既存の許可と付与のチェックが依然として最終的な権限となります。
