<!-- docs-i18n-links:start -->
[EN](../../startup_vs_capability_profile.md) | [JP](../ja/startup_vs_capability_profile.md) | [KR](../ko/startup_vs_capability_profile.md) | [CN](./startup_vs_capability_profile.md)
<!-- docs-i18n-links:end -->

# 启动配置文件与功能配置文件

启动配置文件仍然是启动时的事实来源。他们选择包，
插槽、启动切换行为以及是否应编译能力图
在发射时。

功能配置文件是图形/运行时预设。他们选择图形默认值，
启用和禁用的节点、节点设置和运行时策略。

启动配置文件上的桥接字段：

```json
{
  "launch_capability_graph": true,
  "default_graph": "defaultspack.startup",
  "capability_profile_id": "defaultspack.startup",
  "last_runtime_profile_key": "runtime_profile.defaultspack.startup.defaultspack.startup"
}
```

当启用`launch_capability_graph`时，启动启动会编译图表并
在`InterfaceRegistry`中注册运行时配置文件。流程、代理和面板
API 可以将`runtime_profile_key`解析回已编译的运行时配置文件。

启动配置文件`node_overrides`在启动编译之前应用。例如，
`{"frontend.surface": "frontendpack.web_surface"}` 重写了图的边
馈送`frontend.surface`，使选定的表面节点成为
编译的运行时配置文件。仅当其包被启用时，才会启用覆盖节点
包含在启动配置文件`packs`列表中。

桥将所选的`surface_launch_target`保留在活动元数据中，以便
重新启动切换可以打开图形连线选择的前端。没有发射
目标，重新启动切换继续打开启动配置文件基础包。
