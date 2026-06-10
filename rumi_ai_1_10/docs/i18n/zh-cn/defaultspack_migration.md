<!-- docs-i18n-links:start -->
[EN](../../defaultspack_migration.md) | [JP](../ja/defaultspack_migration.md) | [KR](../ko/defaultspack_migration.md) | [CN](./defaultspack_migration.md)
<!-- docs-i18n-links:end -->

# defaultspack 迁移说明

## 旧版兼容性

- 旧版`ecosystem/defaults` 可以作为参考/兼容性数据保留。
- 新包的生产路由是规范的`/api/defaultspack/*`命名空间。
- `user_data/user.csv` 在需要时在安装包安装时迁移到`user_data/user.json`。

## 回滚

- 使用模块`rollback`或`disable`来隔离故障模块。
- 撤销`all OK`和`POST /api/setup/packs/{setup_pack_id}/revoke-all-ok`。
- 如果需要手动恢复，请删除`user_data/settings/setup_pack_selection.json`以清除安装包选择。

## 弃用路径

- 新功能应登陆`ecosystem/defaultspack/functions/*`。
- 新的生产代码不应为默认行为添加直接的`blocks.*.run`导入。
