<!-- docs-i18n-links:start -->
[EN](../../profile_workspace.md) | [JP](../ja/profile_workspace.md) | [KR](../ko/profile_workspace.md) | [CN](./profile_workspace.md)
<!-- docs-i18n-links:end -->

# 配置文件工作区

配置文件工作区位于`<RUMI_USER_DATA>/profiles/<profile_id>/`下，并隔离每个配置文件的运行时数据，而无需删除旧版`settings/startup_profiles.json`。

```text
profiles/<profile_id>/
  profile.yaml
  user_data/
  database/rumi.sqlite
  startup/launch.yaml
  startup/surface.yaml
  flows/
  prompts/
  ecosystem/snapshots/
  permissions/grants.yaml
  permissions/tool_policy.yaml
  permissions/approvals.yaml
  audit/events.jsonl
```

`profile.yaml` 镜像启动配置文件的核心字段：身份、包和图形选择、运行时配置文件字段、策略、权限默认值、节点覆盖和时间戳。

`user_data/` 是未来每个配置文件运行时数据根。 `database/rumi.sqlite` 是解析器 API 返回的配置文件范围的数据库路径。 `startup/` 存储发射和表面配置。 `flows/` 和`prompts/` 保留配置文件覆盖。 `ecosystem/snapshots/` 包含复制的默认包资源的锁定文件。 `permissions/` 是默认的来源，而不是授权绕过。 `audit/events.jsonl` 记录配置文件范围内的事件。

迁移读取`<RUMI_USER_DATA>/settings/startup_profiles.json`，创建丢失的`profile.yaml`文件，写入`profiles/active_profile.json`，并记录`profiles/.migration_state.json`。旧文件仍然是 StartupProfileManager 状态的兼容性源，直到存储完全移动。

## 运行时数据库范围

此 PR 通过 `resolve_runtime_database_path()` 引入配置文件数据库路径解析，并通过 `resolve_runtime_user_data_dir()` 引入配置文件用户数据根解析。创建或启动配置文件会初始化`<RUMI_USER_DATA>/profiles/<profile_id>/database/rumi.sqlite`，并在启动有效负载和活动生态系统元数据中公开该路径。

此 PR 尚未将每个运行时存储迁移到配置文件范围的数据库。将运行时存储完全迁移到配置文件范围的数据库和配置文件范围的用户数据仍然是后续工作，除非存储已经显式连接。

后续待办事项：

- ChatStore：在打开聊天持久性之前使用`resolve_runtime_database_path()`。
- MemoryStore：对 SQLite 支持的内存使用`resolve_runtime_database_path()`。
- 设置管理器和设置文件：使用`resolve_runtime_user_data_dir()`代替旧的全局用户数据根。
- 附件和上传的文件：使用`resolve_runtime_user_data_dir()`进行配置文件范围的存储。
