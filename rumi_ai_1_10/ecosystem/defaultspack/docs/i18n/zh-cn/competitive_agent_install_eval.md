<!-- docs-i18n-links:start -->
[EN](../../competitive_agent_install_eval.md) | [JP](../ja/competitive_agent_install_eval.md) | [KR](../ko/competitive_agent_install_eval.md) | [CN](./competitive_agent_install_eval.md)
<!-- docs-i18n-links:end -->

# 竞争性代理安装评估

日期：2026-06-03

本注释记录了针对
Genspark、Manus、Cline、Hermes 和 OpenClaw 的当前公共安装流程。
它的目的是保持 defaultspack 与浏览器优先和
代理运行时产品，不会削弱本地优先的安全模型。

## 测试流程

|产品 |观察到的安装或启动路径 |实用吧defaultspack必须满足|
| --- | --- | --- |
|金斯帕克 |浏览器工作区位于`https://www.genspark.ai/ja`，具有可见的 Claw、工作流程、驱动器和应用程序入口点。 |第一个屏幕必须使聊天、工具、工作区和设置无需阅读文档即可发现。 |
|马努斯 |浏览器应用程序位于`https://manus.im/app`。 |应用程序 shell 必须从一个 URL 加载并容忍身份验证或空初始状态。 |
|克莱恩 |官方安装文档显示 IDE 扩展、CLI、看板和 SDK 路径。 IDE安装是：打开扩展，搜索Cline，安装，打开活动栏，然后授权提供者。 CLI 安装是`npm install -g cline`、`cline auth`，然后是`cline`。 | defaultspack 必须支持 UI 优先和命令优先设置，并且提供程序设置必须在安装后明确。 |
|爱马仕 | `NousResearch/hermes-agent` GitHub 页面公开了一个大型代理运行时，其中包含安装程序、桌面构建、网关、提供程序、插件、技能和仪表板界面。 | defaultspack 需要可见的提供者、工具、批准和仪表板原语，而不仅仅是原始聊天。 |
|开爪|官方文档提供安装程序脚本、npm install、入门、网关状态、仪表板启动和通道设置。 Windows 安装程序是`iwr -useb https://openclaw.ai/install.ps1 | iex`；无人机载模式也有记录。 | defaultspack 需要较短的安装路径、无网络/无密钥本地模式以及对网关/UI/模型状态的明确下一步检查。 |

## defaultspack 结果

- `python -m rumi_ai --health`为磁盘和可写温度探测器返回`UP`。
- `ecosystem/defaultspack/webapp` 中的`npm test` 通过了 207 项测试。
- `npm run build` 生产了生产外壳资产。
- Chrome 在`http://127.0.0.1:39766/`处打开了开发 UI 并渲染了
  defaultspack 豪华外壳。
- `npm run lint` 最初在 Windows 上失败，因为使用了 lint 脚本
  `new URL(...).pathname`，生产`C:\C:\...`；这是固定的
  §鲁米§0§。

## 竞争对手本地安装说明

- `npm install --prefix work/competitor-installs/cline cline@3.0.15`已完成，
  `cline --help` 显示提供者身份验证、本地数据目录、工作树、挂钩、MCP、
  集线器、调度程序和看板命令。
- `npm install --prefix work/competitor-installs/hermes --ignore-scripts
  hermes-agent@0.15.2` completed, but `hermes-agent --help` 失败
  在此 Windows 环境中`ModuleNotFoundError: No module named 'run_agent'`。
- §鲁米§0§
  超过五分钟，而安装后/运行状况进程仍在运行。
  第二次`--ignore-scripts`尝试也超过了三分钟。这使得
  OpenClaw 的安装程序在运行时很有吸引力，但它的软件包安装是一个
  比 defaultspack 的本地优先启动更重的操作路径。

## OpenCode Zen 检查

- 直接 Python/urllib 访问`https://opencode.ai/zen/go/v1/models` 是
  在此环境中被 Cloudflare 错误 1010 阻止。
- 使用提供的 Zen 密钥访问 Chrome 通道 API 会返回当前模型
  列表，包括`minimax-m3`和`qwen3.7-max`。
- `minimax-m3` 的实时完成尝试达到了 OpenCode，但返回了
  `CreditsError` 因为工作区没有配置付款方式。
- 默认包现在包括`opencode-go/minimax-m3`和
  Python 提供程序白名单和静态中的 `opencode-go/qwen3.7-max`
  提供商模型目录。

## 竞争准备清单

- 本地优先启动，无需云密钥。
- 来自一个本地主机 URL 的可见 UI shell。
- 安装后提供程序密钥设置，而不是在克隆/构建期间设置。
- 模型目录包括评估者当前使用的 OpenCode Zen 模型。
- 浏览器/计算机/工具批准保持明确且可审核。
- Windows lint/构建路径适用于绝对工作空间路径。
- 安装证据可从运行状况、单位、lint、构建和 Chrome 中重现
  烟雾检查。
