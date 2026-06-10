<!-- docs-i18n-links:start -->
[EN](../../startup_capability_bridge.md) | [JP](../ja/startup_capability_bridge.md) | [KR](../ko/startup_capability_bridge.md) | [CN](./startup_capability_bridge.md)
<!-- docs-i18n-links:end -->

# 启动能力桥

启动配置文件仍然是 Rumi 模式启动时的真实来源，例如
桌面、CLI 和工作配置文件。能力概况保持图形编译
预设。启动能力桥将它们连接起来，无需替换任何一个
模型。

## 选择加入字段

启动配置文件可以选择使用以下字段进行图形编译：

```json
{
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "launch_capability_graph": true,
  "last_runtime_profile_key": null
}
```

- `default_graph` 选择要编译的能力图。
- `capability_profile_id` 选择用于图策略的能力配置文件，
  节点设置以及启用或禁用的节点。
- `launch_capability_graph` 控制启动是否编译图表。
- `last_runtime_profile_key`记录最后注册的运行时配置文件密钥
  成功启动编译后。

省略`launch_capability_graph`或将其设置为`false`的配置文件，保留
之前的启动启动行为。他们的发布结果包括
`capability_graph.skipped: true`有理由
§鲁米§0§；这是非致命的。

## 启动行为

当`launch_capability_graph`为真时，`StartupProfileManager.launch_profile()`
启动启动配置文件，然后调用桥接器。桥：

1. 解决`default_graph`和`capability_profile_id`。
2. 注册defaultspack Capability Graph 绑定处理程序。
3. 加载批准的能力配置文件、能力图和节点定义。
4. 将`node_overrides`应用于匹配图形边缘目标。
5.仅使用添加的节点扩展仅启动的功能配置文件副本
`node_overrides`，并且仅当其包列在启动配置文件中时。
6. 使用`CapabilityGraphCompiler`编译图表。
7. 提取选定的前端表面启动目标。
8. 在`InterfaceRegistry`中注册编译的运行时配置文件。
9. 在启动结果中返回`capability_graph`元数据。

编译失败是软失败。启动启动仍然成功，并且
启动结果包括`capability_graph.ok: false`以及诊断。

## 启动结果

成功的图形编译会添加如下结果：

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

消费者应该使用`runtime_profile_key`来检索注册的运行时
个人资料来自`InterfaceRegistry`。现有的显式编译流程步骤
图表仍然像以前一样工作。

`StartupProfileManager` 还保留 `startup_surface_launch_target` 处于活动状态
生态系统元数据。重新启动后，`startup_surface_launcher` 读取该目标
并启动其`pack_id`，而不是总是启动启动基础包。如果
不存在图形启动目标，启动启动会回退到之前的启动目标
`startup_base_pack`行为。

## 编译预览

控制面板可以预览准确的Startup Profile编译路径，无需
启动或保存状态：

```http
POST /api/panel/startup/profiles/{id}/compile-preview
```

可选主体可以包括草稿轮廓：

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

响应反映了启动编译结果并包括
`surface_launch_target`，因此启动配置文件编辑器可以显示前端
重启后将打开的包。预览编译不注册
`InterfaceRegistry`中的运行时配置文件；启动编译仍然注册
运行时配置文件并保留其密钥。
