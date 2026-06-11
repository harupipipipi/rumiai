<!-- docs-i18n-links:start -->
[EN](../../pack-documentation-contract.md) | [JP](../ja/pack-documentation-contract.md) | [KR](../ko/pack-documentation-contract.md) | [CN](./pack-documentation-contract.md)
<!-- docs-i18n-links:end -->

# 打包文档合同

将 Pack 特定文档合并到`ecosystem/<pack_id>/docs/` 中的通用规则。

## 责任划分

`rumi_ai_1_10/docs/`仅包含运行时通用文档和包通用规则。

- 运行时常见解释，如内核、流程、批准、授予等。
- 如何制作包
-文档术语

`ecosystem/<pack_id>/docs/`仅放置特定于该包的描述。

- 打包职责
- 安装结构
- 流程/功能/处理程序/路线
- 如何操作
- 限制

根文档不描述包本身。它只有包的入口链接和常用术语。

## 所需文件

每个包至少有：

- `ecosystem/<pack_id>/README.md`
- `ecosystem/<pack_id>/docs/README.md`
- `ecosystem/<pack_id>/docs/architecture.md`
- `ecosystem/<pack_id>/docs/interfaces.md`
- `ecosystem/<pack_id>/docs/operations.md`

各文件的职责：

- `README.md`：3 分钟概述、我们提供什么、我们不提供什么、文档入口
- `docs/README.md`：包内文档目录、阅读指南、首次读者指南
- `docs/architecture.md`：职责、主目录、执行路径以及与运行时的接触点
- `docs/interfaces.md`：流程/功能/处理程序/路线/事件/存储/所需的秘密/网络/赠款
- `docs/operations.md`：启动方法、开发方法、测试方法、常见破损方法、变更时的确认点

## 有条件需要的文件

具有该功能的包放置了额外的文档。

- `docs/flows.md`：当有流量/调节剂时

## 交叉链接规则

- 当从根文档描述包时，请保留简短的介绍和入口链接。
- 包特定说明链接至`ecosystem/<pack_id>/docs/README.md`
- 如有必要，可以从`docs/README.md`中追踪包内的各个文档。

## 公关规则

以下更改将需要更新文档。

- 添加了新的流程/修改器
- 添加了新功能/处理程序/路线
- 所需的秘密/赠款/网络已更改
- 启动方法和操作方法发生了变化
- Pack 的职责发生了变化。

## 脚手架期望

`pack_scaffold` 维护合同所需的文档。创建新包时，目标是使自述文件和`docs/README.md`/`architecture.md`/`interfaces.md`/`operations.md`自然对齐。
