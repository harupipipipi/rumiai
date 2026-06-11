<!-- docs-i18n-links:start -->
[EN](../../compaction.md) | [JP](../ja/compaction.md) | [KR](../ko/compaction.md) | [CN](./compaction.md)
<!-- docs-i18n-links:end -->

# 压缩

`domain/context_engine`提供令牌估计，稳定的提示层，
溢出检测、压缩数据包和替换历史记录助手。

紧凑的数据包包括目标、当前状态、进度、决策、约束、
更改的文件、工具结果、固定上下文、删除的上下文日志、内存刷新
参考文献、后续步骤、关键上下文、源记录和替换
转录标识符。

更换历史记录保留系统消息并保留最近的工具调用/结果
配对在一起。缺失的工具结果会收到一个紧凑的存根；孤立工具结果
被丢弃。
