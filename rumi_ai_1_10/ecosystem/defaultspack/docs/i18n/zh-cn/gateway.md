<!-- docs-i18n-links:start -->
[EN](../../gateway.md) | [JP](../ja/gateway.md) | [KR](../ko/gateway.md) | [CN](./gateway.md)
<!-- docs-i18n-links:end -->

# 网关

`domain/gateway` 提供本地控制平面 shell，具有会话路由和
通道适配器。第一个实现启动一个轻量级本地HTTP
用于状态和经过身份验证的事件接收的服务器； WebSocket 协议助手是
表示为`domain/gateway/ws.py`中键入的请求/事件信封。
网关默认绑定到`127.0.0.1`，拒绝外部绑定地址，除非
运行时配置显式启用它们，并且需要持有者或
用于 POST 摄入的`x-rumi-gateway-token` 代币。

会话密钥如下：

- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§
- §鲁米§0§

## 外部输入关系

网关是本地输入外壳，而不是外部输入框架本身。公共
或特定于提供商的事件应标准化为`ExternalEvent`，由
`AudiencePolicy`，通过`InputProfile`映射，并通过
§鲁米§0§。网关消息可以是这些事件的来源之一。

响应传递应经过 `ResponsePlanner` 和 `ResponseAdapter`，以便
聊天和代理代码不学习 Slack、Discord、LINE、webhook 或隧道
详细信息。

Cloudflare Quick Tunnel（如果使用）只是前面的一个可交换 URL 提供程序
本地端点。不得将其视为规范网关、身份验证系统或
外部输入运行时。
