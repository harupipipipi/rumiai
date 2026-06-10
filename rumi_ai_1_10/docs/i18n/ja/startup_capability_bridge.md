<!-- docs-i18n-links:start -->
[EN](../../startup_capability_bridge.md) | [JP](./startup_capability_bridge.md) | [KR](../ko/startup_capability_bridge.md) | [CN](../zh-cn/startup_capability_bridge.md)
<!-- docs-i18n-links:end -->

# スタートアップ機能ブリッジ

スタートアップ プロファイルは、引き続き、次のような Rumi モードの起動時の信頼できる情報源となります。
デスクトップ、CLI、および仕事用プロファイル。能力プロファイルはグラフコンパイルのまま
プリセット。スタートアップ機能ブリッジは、どちらも交換せずにそれらを接続します。
モデル。

## オプトインフィールド

スタートアップ プロファイルは、次のフィールドを使用してグラフのコンパイルをオプトインできます。

```json
{
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "launch_capability_graph": true,
  "last_runtime_profile_key": null
}
```

- `default_graph` は、コンパイルする能力グラフを選択します。
- `capability_profile_id` は、グラフ ポリシーに使用される機能プロファイルを選択します。
  ノード設定、および有効または無効なノード。
- `launch_capability_graph` は、launch がグラフをコンパイルするかどうかを制御します。
- `last_runtime_profile_key` は、最後に登録されたランタイム プロファイル キーを記録します。
  起動が成功したらコンパイルします。

`launch_capability_graph` を省略するか、`false` に設定したプロファイルでは、
以前の起動時の起動動作。彼らの立ち上げ結果には以下が含まれます：
`capability_graph.skipped: true` 訳あり
`launch_capability_graph_disabled`;これは致命的ではありません。

## 起動動作

`launch_capability_graph`が真の場合、`StartupProfileManager.launch_profile()`
スタートアップ プロファイルを起動し、ブリッジを呼び出します。橋:

1. `default_graph` および `capability_profile_id` を解決します。
2.defaultspack Capability Graph バインディング ハンドラーを登録します。
3. 承認された機能プロファイル、機能グラフ、およびノード定義をロードします。
4. `node_overrides` を一致するグラフ エッジ ターゲットに適用します。
5. によって追加されたノードのみを使用して、起動専用の機能プロファイルのコピーを拡張します。
`node_overrides`、およびそのパックがスタートアップ プロファイルにリストされている場合のみ。
6. `CapabilityGraphCompiler` でグラフをコンパイルします。
7. 選択したフロントエンド サーフェス起動ターゲットを抽出します。
8. コンパイルしたランタイムプロファイルを`InterfaceRegistry`に登録します。
9. 起動結果で`capability_graph` メタデータを返します。

コンパイル失敗はソフトエラーです。スタートアップの起動は引き続き成功し、
起動結果には `capability_graph.ok: false` と診断が含まれます。

## 起動結果

グラフのコンパイルが成功すると、次のような結果が追加されます。

```json
{
  "capability_graph": {
    "ok": true,
    "graph_id": "defaultspack.startup",
    "capability_profile_id": "defaultspack.startup",
    "runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup",
    "surface_launch_target": {
      "kind": "desktop_app",
      "pack_id": "frontendpack",
      "node_id": "frontendpack.web_surface"
    }
  }
}
```

コンシューマは、`runtime_profile_key` を使用して、登録されたランタイムを取得する必要があります。
プロフィールは`InterfaceRegistry`より。コンパイルする既存の明示的なフロー ステップ
グラフは以前と同様に機能します。

`StartupProfileManager` もアクティブな `startup_surface_launch_target` を維持します
エコシステムのメタデータ。再起動後、`startup_surface_launcher` がそのターゲットを読み取ります。
そして、常にスタートアップ基本パックを起動する代わりに、その `pack_id` を起動します。もし
グラフ起動ターゲットが存在しないため、起動起動は以前にフォールバックします
`startup_base_pack`の動作。

## コンパイルプレビュー

コントロール パネルは、正確なスタートアップ プロファイルのコンパイル パスをプレビューすることができます。
起動または状態の保存:

```http
POST /api/panel/startup/profiles/{id}/compile-preview
```

オプションの本文には、ドラフト プロファイルを含めることができます。

```json
{
  "profile": {
    "profile_id": "custom",
    "packs": ["defaultspack", "frontendpack"],
    "node_overrides": {
      "frontend.surface": "frontendpack.web_surface"
    }
  }
}
```

応答は起動コンパイル結果を反映しており、以下が含まれます。
`surface_launch_target`、スタートアップ プロファイル エディターでフロントエンドを表示できるようにする
再起動後に開かれるパック。プレビュー コンパイルでは登録されません
`InterfaceRegistry` のランタイム プロファイル。コンパイルを起動してもまだ登録されています
実行時プロファイルを作成し、そのキーを永続化します。
