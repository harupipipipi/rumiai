<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 鲁米远程手机

Rumi Remote Mobile 是 Flutter 客户端，用于管理 PC 托管的 Rumi
`defaultspack` 来自受信任网络上的 iOS 和 Android 设备。

该应用程序针对端口 `8765` 上的内核包 API，而不是独立的
端口 `8766` 上的默认包聊天传输。内核API需要一个承载者
令牌，是 LAN 访问的更安全的表面。

## 电脑设置

使用绑定到受信任 LAN 的内核 API 启动 Rumi：

```powershell
$env:RUMI_API_BIND_ADDRESS="0.0.0.0"
python -m rumi_ai
```

从 `rumi_ai_1_10/user_data/hmac_keys.json` 读取活动 API 令牌或运行：

```powershell
cd rumi_ai_1_10
python -c "from core_runtime.hmac_key_manager import HMACKeyManager; print(HMACKeyManager().get_active_key())"
```

在应用程序中，将服务器 URL 设置为`http://<pc-lan-ip>:8765` 并粘贴令牌。
将 PC 防火墙限制在您的专用网络内。不要暴露这个端口
直接连接到公共互联网。

使用 Tauri 桌面查看器时，关闭查看器窗口会将其发送到
后台并保持内核 API 对远程客户端可用。使用托盘
当您想要停止内核并完全退出 Rumi 时，请使用菜单的`Quit` 项。

Android 调试/配置文件构建允许用于可信 LAN 开发的明文 HTTP。
Android 版本不允许全局允许明文流量；使用 HTTPS 或
如果分发仅 LAN 版本，则显式发布网络策略。

## API 覆盖范围

|目的|方法|路径|
| --- | --- | --- |
|健康检查| §鲁米§0§| §鲁米§1§ |
|模块列表 | §鲁米§0§| §鲁米§1§ |
|模块详情 | §鲁米§0§| §鲁米§1§ |
|启用模块 | §鲁米§0§| §鲁米§1§ |
|禁用模块 | §鲁米§0§| §鲁米§1§ |
|重新加载模块 | §鲁米§0§| §鲁米§1§ |
|回滚模块| §鲁米§0§| §鲁米§1§ |
|移民状况 | §鲁米§0§| §鲁米§1§ |
|打包请求 | §鲁米§0§| §鲁米§1§ |

## 发展

```powershell
cd rumi_mobile
flutter pub get
flutter analyze
flutter test
```

Android 调试版本需要 Flutter/Android SDK 环境：

```powershell
flutter build apk --debug
```

iOS 构建需要 macOS 和 Xcode：

```bash
flutter build ios --no-codesign
```
