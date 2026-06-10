<!-- docs-i18n-links:start -->
[EN](../../model-packs.md) | [JP](../ja/model-packs.md) | [KR](../ko/model-packs.md) | [CN](./model-packs.md)
<!-- docs-i18n-links:end -->

# 模型包和`model.call`

除了普通模型 ID 之外，模型路由现在还支持 `modelpack/<id>` 和
遗留的复合模型。

## 模型包形状

`ModelPack` 是一个小型路由清单：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- 可选的预算、安全和元数据

第一个实现侧重于后备链样式选择，而
为集成或审查链模式留出空间。

## 分辨率

`ModelRouter`和`AIClient`使用当前回合解决`modelpack/<id>`：

- 图像输入/视觉需求
- 工具调用需求
- 要求的思维水平
- 任务提示
- 自定义包规则
- 后备成员

旧版`composite_models`保持兼容并可被视为内部
包状结构。

## §鲁米§0§

`model.call` 是“向另一个模型询问问题”的有界效用路径。

- 默认情况下没有工具访问权限
- 接受`required_capabilities`、`model_hint`、`output_schema`、`max_tokens`
  和§鲁米§0§
- 在转发之前删除隐藏的元数据和秘密
- 强制递归深度限制

以这种方式使用边界：

- `model.call`：对另一个模型的有界问题
- `agent.delegate`：委托工具支持的工作
- `model.switch`：持久对话默认更改
- `model.route`：回合范围的路由覆盖
