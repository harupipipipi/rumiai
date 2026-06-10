<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# Rumi 浏览器伴侣

`Rumi Browser Companion` 是 Manifest V3 Chromium 扩展，可让 Rumi 通过本地桥驱动用户的真实浏览器会话。它旨在补充现有的`browser_use`和`computer_use`工具：

- `computer_use` / `browser_computer`：可见窗口，计算机使用风格控制
- `browser_companion`：用户登录的浏览器配置文件中的 DOM 感知浏览器控件

这为 Rumi 提供了一条“计算机使用 + 浏览器使用”路径，其中模型可以检查 DOM 状态、在连接的浏览器之间进行选择以及使用用户的实时 cookie 和会话进行操作。

## 文件

- `manifest.json`：扩展清单
- `background.js`：桥接轮询、浏览器元数据、选项卡操作、捕获编排
- `content_script.js`：DOM 快照和元素级操作
- `options.html`、`options.css`、`options.js`：本地网桥配置 UI

## 安装

1. 打开基于 Chromium 的浏览器，例如 Chrome、Edge、Brave 或 Vivaldi。
2. 打开浏览器的扩展页面并启用开发者模式。
3. 选择“加载已解压的文件”并选择此文件夹：

   §鲁米§0§

4. 在 Rumi 中，使用 `action: "bridge.pairing"` 调用 `browser_companion` 来获取配对令牌和候选服务器 URL。
5.打开扩展选项页面并粘贴：

   - `Server URL` 例如`http://127.0.0.1:8766`
   - §鲁米§0§

6. 单击`Poll Bridge Now` 确认分机可以连接。

## 桥接API

该扩展与这些本地端点进行通信：

- §鲁米§0§
- §鲁米§0§

`poll`请求正文：

```json
{
  "pairing_token": "example-token",
  "client": {
    "client_id": "uuid",
    "label": "My Edge Companion",
    "browser_name": "Microsoft Edge",
    "browser_version": "136.0.0.0",
    "extension_version": "0.1.0",
    "platform": "Win32",
    "user_agent": "...",
    "active_tab_id": 123,
    "tabs": [
      {
        "id": 123,
        "windowId": 1,
        "active": true,
        "title": "Example",
        "url": "https://example.com",
        "status": "complete"
      }
    ]
  }
}
```

`poll`响应正文：

```json
{
  "status": "ok",
  "data": {
    "accepted": true,
    "client_id": "uuid",
    "command": {
      "command_id": "cmd_123",
      "action": "page.snapshot",
      "payload": {
        "tab_id": 123,
        "include_capture": true,
        "limit": 200
      }
    }
  }
}
```

`result`请求正文：

```json
{
  "pairing_token": "example-token",
  "client_id": "uuid",
  "results": [
    {
      "command_id": "cmd_123",
      "ok": true,
      "result": {
        "snapshot": {
          "url": "https://example.com",
          "title": "Example",
          "nodes": []
        }
      }
    }
  ]
}
```

## 支持的操作

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

## 安全注意事项

- 此扩展可以检查用户真实浏览器配置文件中的页面并对其进行操作。
- 仅将其与您控制的本地 Rumi 服务器配对。
- 请勿共享配对令牌。
- 捕获和选项卡选择可能会将浏览器选项卡置于前台。
- DOM 操作是尽力而为的，可能不适用于所有页面。

## 注释

- 该扩展程序使用用户的真实浏览器配置文件，因此经过身份验证的页面可以使用用户现有的 cookie 和会话。
- DOM 快照和元素操作可以定位已加载内容脚本的选项卡。
- 可见选项卡捕获仍然取决于浏览器的活动可见选项卡，因此捕获请求可能会激活目标选项卡。
