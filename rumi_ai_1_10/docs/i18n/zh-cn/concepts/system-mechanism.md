<!-- docs-i18n-links:start -->
[EN](../../../concepts/system-mechanism.md) | [JP](../../ja/concepts/system-mechanism.md) | [KR](../../ko/concepts/system-mechanism.md) | [CN](./system-mechanism.md)
<!-- docs-i18n-links:end -->

# 运行时机制（无代码版本）

本文档的组织方式是为了让您无需阅读代码即可了解“Rumi AI 的工作原理”。

## 1. 启动时会发生什么

1. `python -m rumi_ai`开始`rumi_ai_1_10/app.py`。
2. 内核处理程序按照`flows/00_startup.flow.yaml`的顺序执行。
3. 当安全初始化、包扫描和API服务器初始化完成时，将发出`system.ready`。

启动流程有四个阶段：`init -> security -> ecosystem -> finalize`。

## 2. Flow 和 Modifier 的加载顺序

流按以下顺序加载（优先级较高）：

1.`flows/`（官方）
2.`user_data/shared/flows/`（分享）
3.`ecosystem/<pack_id>/.../flows/`（Pack提供）
4.`ecosystem/flows/`（兼容旧版）

修改器以相同的方式加载，并将`inject_before / inject_after / append / replace / remove`应用于目标流。

## 3.允许Pack执行的条件

Pack执行需要以下三个步骤：

1. **批准**：包已获得批准
2. **信任**：批准哈希和当前哈希必须匹配
3. **Grant**：能力执行权限授予principal

如果缺少其中任何一项，则不会被执行。包含文件更改的包将被视为`modified`，需要重新批准。

## 4. API server的定位

- 内核在`127.0.0.1:8765`中公开API。
- 该 API 是包管理、流程执行、秘密、授权、桌面令牌等的网关。
- 除了核心 API 之外，还通过加载 Pack 端`api_routes` 来扩展路由。

## 5.查看器和运行时之间的关系

`rumi_viewer` 是“启动内核并连接到面板的外壳”。

1.查看器解析Python/venv/运行时路径
2. 使用`python -m app`启动内核
3. 引导至`/panel/`并显示 UI

`defaultspack`的独立前端（`8766`）和面板（`8765/panel`）是独立的导体。

## 6.包分发执行路径（导入/应用）

1. PackImporter 阶段和部署 zip/文件夹（Zip Slip/Bomb 保护）
2. 验证ecosystem.json
3. PackApplier 创建备份并将其反映在`ecosystem/<pack_id>/`中
4.反映后，将被视为`modified`，因此进入重新审批流程

## 7. 我可以在哪里阅读以进行更深入的研究？

- 整体设计：[../architecture.md](../architecture.md)
- 操作/API：[../operations.md](../operations.md)
- 查看器启动路径：[../rumi_viewer_start.md](../rumi_viewer_start.md)
- 包开发：[../pack-development.md](../pack-development.md)
