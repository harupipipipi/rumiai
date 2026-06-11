<!-- docs-i18n-links:start -->
[EN](../../defaultspack_authoring.md) | [JP](./defaultspack_authoring.md) | [KR](../ko/defaultspack_authoring.md) | [CN](../zh-cn/defaultspack_authoring.md)
<!-- docs-i18n-links:end -->

# Defaultspack オーサリング

Defaultspack リソースは、コンポーネント、ブロック、関数、フロー、プロンプト、ノード、グラフとして作成されます。

ブロックは `ecosystem/defaultspack/blocks/` の下に存在し、`run(input_data, context)` を公開します。関数マニフェストは `functions/<function_id>/manifest.json` の下に存在します。生成されたラッパーは、defaultspack 関数ディスパッチャーを呼び出します。コンポーネントは、`components/*/manifest.json` および `ecosystem.json` で呼び出し可能なエイリアスをアドバタイズします。

プロファイル スナップショットは、参照されたフロー、プロンプト、ノード、およびブロック リソースのみをコピーする必要があります。彼らは、ソース パスと SHA-256 ハッシュを使用して `manifest.lock.json` を記述するため、プロファイルの編集とdefaultspack の更新は説明可能なままになります。
