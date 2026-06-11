<!-- docs-i18n-links:start -->
[EN](../../goal-command.md) | [JP](../ja/goal-command.md) | [KR](../ko/goal-command.md) | [CN](./goal-command.md)
<!-- docs-i18n-links:end -->

# /目标斜线命令

`/goal <description>` 在 defaultspack 控制台中运行目标追求循环，无需直接执行工具：

1. **Worker** 代理为目标做出下一个具体贡献。
2. 每个Worker轮流后，有一个独立的第三方**评估者**代理
   检查目标是否已实现。
3. 如果目标尚未实现，评估器返回一个新的
   `next_instruction`，并且再次提示工人。
4. 当评估者将目标标记为已实现或当
   达到`max_iterations`上限（默认`5`，硬上限`20`）。

## 参数

|名称 |类型 |必填|默认|描述 |
|------------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `goal`|字符串|是的 | — |对工人应追求的目标的自由形式描述。                 |
| `max_iterations`|字符串|没有| `5` |最大工作人员/评估人员往返次数。限制为 1–20。                      |
| `model`|字符串|没有|活跃 |传递给 Worker 和 Evaluator 轮次的可选模型提示。              |

斜杠命令注册在
[`commands/manifests/goal.json`](../commands/manifests/goal.json) 和
行为存在于[`blocks/goal/run.py`](../blocks/goal/run.py)中。

## 结果信封

成功后命令返回：

```json
{
  "status": "ok",
  "data": {
    "command": { "...": "manifest fields" },
    "executed": true,
    "result": {
      "goal": "Write a haiku about programming",
      "achieved": true,
      "reason": "Three-line haiku produced as requested.",
      "iterations": [
        {
          "iteration": 1,
          "worker_output": "...",
          "verdict": { "achieved": true, "reason": "...", "next_instruction": "" }
        }
      ],
      "iteration_count": 1,
      "final_output": "...",
      "max_iterations": 5,
      "stopped_reason": "achieved"
    }
  }
}
```

当循环到达`max_iterations`但未达到目标时，`achieved`
变成`false`并且`stopped_reason`是`"max_iterations_reached"`。当
Worker 或 Evaluator 模型调用失败命令返回
`status: "error"` 与 `code: "WORKER_FAILED"` 或 `code: "EVALUATOR_FAILED"`
以及记录任何部分进度的`iterations`数组。

## 扩展性说明：`pack_block`执行类型

`pack_block`钩子到位后，`/goal`本身通过文件添加来实现：

* `commands/manifests/goal.json` 声明斜杠命令。
* `blocks/goal/run.py` 实现目标追求循环。

该功能通过`pack_block`执行类型连接
`SlashCommandRegistry`，它允许清单分派到下面的 Python 块
`blocks/<dotted.path>` 暴露`run(input, context) -> dict`。

该块不直接执行工具；它只进行模型调用
工人和评估员轮流。
`pack_block` 仅适用于 `default` 和 `pack` 明显来源（绝不
对于`user_data/shared/commands/`)下的用户清单，因此不受信任的命令
清单无法加载任意模块。

现在可以通过以下方式添加需要后端行为的未来斜杠命令：

1. 将清单放入`commands/manifests/<command>.json`中。
2. 在`blocks/<area>/<file>.py`处丢弃一个块，暴露`run`可调用。

不需要为这些添加更改现有文件。
