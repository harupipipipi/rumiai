<!-- docs-i18n-links:start -->
[EN](../../frontend_pack_contract.md) | [JP](../ja/frontend_pack_contract.md) | [KR](../ko/frontend_pack_contract.md) | [CN](./frontend_pack_contract.md)
<!-- docs-i18n-links:end -->

# 前端包合约

前端包可以通过暴露一个来参与启动能力图的启动
具有`rumi.surface`输出和`metadata.launch`的节点。

要求：

- 批准的包
- 启动配置文件包括`packs`中的包
- 带有`standards: ["rumi.surface"]`的节点端口
- 节点元数据`pack_id`
- 节点元数据`launch.kind: desktop_app`
- 节点元数据`launch.pack_id`与节点包ID匹配
- `ecosystem.json` `desktop_app.command`，以便桌面应用程序管理器可以启动它

示例节点：

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

示例`ecosystem.json`桌面应用程序部分：

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

当启动配置文件覆盖`frontend.surface`到该节点时，图形编译
将规范目标存储在`runtime_profile.launch.surface`中并处于活动状态
元数据存储`startup_surface_launch_target`。重启后，启动
表面发射器打开`frontendpack`而不是基础包。

启动目标有意为本地包。来自`frontendpack`的节点不能
主张`launch.pack_id: otherpack`或`principal_id: otherpack`；编译并
启动启动标准化拒绝该目标并回退到启动
需要时配置基础包。
