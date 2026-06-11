<!-- docs-i18n-links:start -->
[EN](../../frontend_pack_contract.md) | [JP](./frontend_pack_contract.md) | [KR](../ko/frontend_pack_contract.md) | [CN](../zh-cn/frontend_pack_contract.md)
<!-- docs-i18n-links:end -->

# フロントエンドパック契約

フロントエンド パックは、
`rumi.surface` 出力と `metadata.launch` を持つノード。

必須:

- 承認されたパック
- スタートアッププロファイルには`packs`のパックが含まれています
- `standards: ["rumi.surface"]`のノードポート
- ノードメタデータ `pack_id`
- ノードメタデータ `launch.kind: desktop_app`
- ノード パック ID に一致するノード メタデータ `launch.pack_id`
- `ecosystem.json` `desktop_app.command` により、デスクトップ アプリ マネージャーが起動できるようになります

ノードの例:

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "frontendpack.web_surface",
      "kind": "ecosystem.surface",
      "display_name": {
        "en": "Frontendpack Web Surface",
        "ja": "Frontendpack Web Surface"
      },
      "ports": [
        {
          "id": "surface",
          "direction": "output",
          "standards": ["rumi.surface"],
          "multiple": true
        }
      ],
      "metadata": {
        "pack_id": "frontendpack",
        "component_type": "frontend",
        "component_id": "web",
        "category": "surface",
        "launch": {
          "kind": "desktop_app",
          "pack_id": "frontendpack",
          "surface": "browser",
          "default": true,
          "env": {
            "FRONTENDPACK_SURFACE": "web"
          }
        }
      }
    }
  ]
}
```

`ecosystem.json` デスクトップ アプリ セクションの例:

```json
{
  "pack_id": "frontendpack",
  "desktop_app": {
    "command": "python desktop_app.py",
    "working_dir": "",
    "env": {
      "FRONTENDPACK_PORT": "8770"
    },
    "window": {
      "title": "Frontendpack",
      "width": 1280,
      "height": 800
    }
  }
}
```

スタートアップ プロファイルがこのノードに対して `frontend.surface` をオーバーライドすると、グラフ コンパイルが行われます。
正規ターゲットを `runtime_profile.launch.surface` に保存し、アクティブにします
メタデータは`startup_surface_launch_target`を格納します。再起動後、スタートアップは
サーフェスランチャーはベースパックの代わりに`frontendpack`を開きます。

起動ターゲットは意図的にパックローカルになっています。 `frontendpack` のノードはできません。
`launch.pack_id: otherpack`または`principal_id: otherpack`を主張する。コンパイルして
スタートアップ起動正規化はそのターゲットを拒否し、スタートアップにフォールバックします
必要に応じてベース パックのプロファイルを作成します。
