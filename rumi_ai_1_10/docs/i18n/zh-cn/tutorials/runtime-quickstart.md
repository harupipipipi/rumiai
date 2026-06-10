<!-- docs-i18n-links:start -->
[EN](../../../tutorials/runtime-quickstart.md) | [JP](../../ja/tutorials/runtime-quickstart.md) | [KR](../../ko/tutorials/runtime-quickstart.md) | [CN](./runtime-quickstart.md)
<!-- docs-i18n-links:end -->

# 教程：运行时快速入门

本教程是让运行时能够使用当前存储库的最快方法。

## 假设

- 在回购路线中工作
- 可以使用Python

## 步骤 1. 运行健康检查

```bash
python -m rumi_ai --health
```

如果返回`status: "UP"`或`status: "DEGRADED"`，则运行时已准备好启动（需要调查`DOWN`）。

## 步骤 2. 启动运行时

```bash
python -m rumi_ai --headless
```

如果出现`[Rumi] startup.success`，则启动完成。

## 步骤3.API通信确认

在另一个终端中：

```bash
curl http://127.0.0.1:8765/health
```

如果它返回 HTTP 200 和 JSON，则该 API 可用。

## 步骤 4. 面板路线确认（可选）

在浏览器中打开`http://127.0.0.1:8765/panel/`并确保屏幕可见。

## 步骤 5. 停止

在启动的终端中，`Ctrl+C`。

## 验证截图

> 这是执行确认时获得的图像。根据环境的不同，显示可能会略有不同。

### /health（浏览器显示）

![运行时运行状况截图](../assets/tutorials/runtime-health.png)

### /panel（浏览器显示）

![运行时面板截图](../assets/tutorials/runtime-panel.png)

## 执行日志

执行的原始日志保存在下面。

- §鲁米§0§

## 继续阅读

- 遵循机制：[../concepts/system-mechanism.md](../concepts/system-mechanism.md)
- 操作/API 详细信息：[../operations.md](../operations.md)
- 查看器端启动路径：[../rumi_viewer_start.md](../rumi_viewer_start.md)
