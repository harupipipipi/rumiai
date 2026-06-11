<!-- docs-i18n-links:start -->
[EN](../../startup_vs_capability_profile.md) | [JP](./startup_vs_capability_profile.md) | [KR](../ko/startup_vs_capability_profile.md) | [CN](../zh-cn/startup_vs_capability_profile.md)
<!-- docs-i18n-links:end -->

# スタートアップ プロファイルと機能プロファイル

起動プロファイルは、起動時の信頼できる情報源であり続けます。彼らはパックを選択し、
スロット、起動時のハンドオフ動作、および機能グラフをコンパイルする必要があるかどうか
打ち上げ時。

機能プロファイルは、グラフ/ランタイムのプリセットです。グラフのデフォルトを選択します。
有効化および無効化されたノード、ノード設定、および実行時ポリシー。

スタートアップ プロファイルのブリッジ フィールド:

```json
{
  "launch_capability_graph": true,
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "last_runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup"
}
```

`launch_capability_graph` が有効な場合、起動時にグラフがコンパイルされ、
`InterfaceRegistry`にランタイムプロファイルを登録します。フロー、エージェント、パネル
API は、`runtime_profile_key` を解決してコンパイルされたランタイム プロファイルに戻すことができます。

起動プロファイル `node_overrides` は、コンパイルを起動する前に適用されます。たとえば、
`{"frontend.surface": "frontendpack.web_surface"}` はグラフのエッジを書き換えます。
`frontend.surface` をフィードし、選択したサーフェス ノードが
コンパイルされたランタイム プロファイル。オーバーライド ノードは、そのパックが有効な場合にのみ有効になります。
スタートアップ プロファイル `packs` リストに含まれています。

ブリッジは、選択された `surface_launch_target` をアクティブなメタデータに保持します。
ハンドオフを再開すると、グラフ ワイヤリングで選択されたフロントエンドを開くことができます。打ち上げなしで
ターゲットの場合、ハンドオフを再起動すると、引き続きスタートアップ プロファイルの基本パックが開きます。
