<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# コアコントロールパネル

このパネルの正規のフロントエンド ソースは `../../../../../rumi_viewer/frontend` にあります。

このパックは、`web/` から `/panel` で構築された静的アーティファクトを提供します。ブラウザ ルート (`http://127.0.0.1:8765/panel/`) と Rumi Viewer ブートストラップ フローは両方とも同じアーティファクトを使用します。

Tauri `splash` 画面は独立したままであり、カーネルの準備が整う前にのみ使用されます。
