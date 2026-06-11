<!-- docs-i18n-links:start -->
[EN](../../roadmap.md) | [JP](../ja/roadmap.md) | [KR](../ko/roadmap.md) | [CN](./roadmap.md)
<!-- docs-i18n-links:end -->

# rumiai 默认包 — 路线图

最后更新: 2026-03-06
状态图例： ✅ 已完成 / 🔧 需要修改 / ⬜ 未开始

---

## 第 0 阶段：基础（完成）

全部完成。从启动到浏览器访问AI聊天均已确认操作。

|身份证 |内容 |状态 |
|----|------|-----------|
| G0-G3 |骨架 ~ 聊天/流程层 | ✅ |
| P0|标准化| ✅ |
| G4 |代理/运输/前端| ✅ |
| G5 | AI 提供商（OpenAI、Anthropic、Google、Genspark）+ MCP | ✅ |
| G6 |用户体验增强 | ✅ |
| G7 |工具和提示扩展 | ✅ |
| G8 |代理增强+所有修复| ✅ |
| G9a/b |知识库+流程自动搜索| ✅ |
|文档 |文档 24 个文件 + 4 个修订版 | ✅ |
|启动/引导修复 | setup.py、ecosystem.json、组件/ | ✅ |
|步骤 0 |路由注册模式迁移（44→100路由分布）| ✅ |

---

## 第一阶段：增强（T1-T17）

17 并行执行任务。使用路由注册表完成，无需对 http.py 进行任何更改。

|身份证 |内容 |域 |块|根|状态 |
|----|------|--------|--------|--------|-----------|
| T1 |多对话会话管理 | ✅ session_manager.py | 🔧 块/聊天/会话/未创建 | 🔧 未注册 | 🔧 |
| T2 | AI 对话历史编辑 | ✅历史编辑器.py | 🔧 区块/聊天/历史/未创建 | 🔧 未注册 | 🔧 |
| T3 |运行时工具创建 | ✅runtime_creator.py | ✅ 与现有区块兼容 | ✅ | ✅ |
| T4 |免责协议工具| ✅ disclaimer_manager.py | ✅ 与现有区块相对应 | ✅ | ✅ |
| T5|高级提示（构建器、版本控制）| ✅ 构建器.py | ✅ 阻止/提示/高级/ | ✅ 8 条路线 | ✅ |
| T6|工具/提示统一模板| ✅ 统一.py | ✅ 块/提示/convert.py | ✅ | ✅ |
| T7| rumi模型（自动路由）| ✅ model_router.py | ✅ 块/ai/路由/ | ✅ 10 条路线 | ✅ |
| T8|上下文显示API | ✅ 分析器.py | 🔧 没有专用区块 | 🔧 路线未注册 | 🔧 |
| T9|开发工具扩展 | ✅ use_tracker.py | ✅ 与现有区块兼容 | ✅ | ✅ |
| T10|组织代理基地| ✅ org_manager.py | ✅blocks/agent/org/（11 个文件）| 🔧 Root 未注册 | 🔧 |
| T11 |类似Slack的AI聊天| ✅channel_manager.py | ✅ 区块/聊天/频道/（10 个文件）| ✅ 10 条路线 | ✅ |
| T12 |预定执行代理| ✅ 调度程序.py | ✅ 块/代理/调度程序/（9 个文件）| ✅ 9 根 | ✅ |
| T13 |在任务期间添加说明 | ✅ 中断管理器.py | ✅ 块/代理/中断/（8 个文件）| ✅ 9 条路线 | ✅ |
| T14 | Linux环境+坐标操作 | ✅ 容器管理器.py | ✅ 块/工具/容器/（12 个文件）| ✅ 13 根 | ✅ |
| T15 |权限管理 | ⬜ 未实施 | ⬜ 未实施 | ⬜ | ⬜ |
| T16 | CLI完全隔离| ✅ cli.py | ✅ 块/cli/entry.py | ✅ 2 根 | ✅ |
| T17 | T17 Tab系统后台| ⬜ 未实施 | ⬜ 未实施 | ⬜ | ⬜ |

---

## 第 2 阶段：质量保证 + 剩余修正

### 2-A：P1 修改（拦截器）

|身份证 |内容 |详情 |
|----|------|------|
| P1-1 |系统路由404修正|将 /api/health、/、/api/context、/static/* 注册到 io.http.route。即使在注册表模式下也可以访问它 |
| P1-2 | T15 权限管理的实现 | domain/permission/manager.py、user_store.py、role_store.py、auth.py、audit.py + block/permission/ + setup.py 路由注册 |
| P1-3 | T17 Tab系统实现| domain/frontend/tab_manager.py, tab_presets.py + block/frontend/tabs/ + setup.py 路由注册 |

### 2-B：P2修改（功能完成）

|身份证 |内容 |详情 |
|----|------|------|
| P2-1 | P2-1 T10组织代理路线注册|将组织系统 11 路由添加到blocks/agent/setup.py |
| P2-2 | T1会话管理块+路由|创建blocks/chat/session/ + 添加8条路由到chat/setup.py |
| P2-3 | T2历史编辑区块+路线 |创建blocks/chat/history/ + 添加4条路由到chat/setup.py |
| P2-4 | T8上下文API的根源|注册 /api/context/conversation/{id}, /api/context/system |
| P2-5 |提供 Ecosystem.json 的更新 |反映 T10/T12/T13/T14 的新处理程序 |

### 2-C：文件检查

|身份证 |内容 |详情 |
|----|------|------|
| FC-1 |检查所有块的 def run 签名 |是 def run(input_data, context): 统一 |
| FC-2 |进口款式一致性检查| sys.path.insert（0，pack_root）+来自blocks._common导入... |
| FC-3 |通过 / TODO / NotImplementedError 残留检查 |是否有禁止未实现的功能 |
| FC-4 | setup.py 路由数量和真实块数量匹配 |所有已注册的路由目标模块是否都存在？ |
| FC-5 |删除不需要的文件 | Transport/uds.py、blocks/frontend/stop.py 等 |

### 2-D：rumiai内核规则合规性检查

|身份证 |内容 |详情 |
|----|------|------|
| RC-1 |符合生态系统.json 架构 |兼容W26内核的ecosystem.schema.json |
| RC-2 |检查 Components/manifest.json | 是否存在11个组件都有manifest.json |
| RC-3 |使用 setup.py 上下文的有效性 | context["interface_registry"]等的使用是否符合内核规范|
| RC-4 |遵守 KernelFacade API 限制 |您是否调用了除 get_interface、list_interfaces 或 emit 之外的其他函数？ |
| RC-5 |包审批流程兼容性 |文件变更 → 修改状态 → 重新审批是否正常？ |

### 2-E：默认中立检查

|身份证 |内容 |详情 |
|----|------|------|
| NC-1 |不偏袒人工智能提供商 |特定提供者是否是硬编码的？存根/默认是后备吗？
| NC-2 |不偏袒模特| rumi 模型路由公平吗？某些模型是否被给予了不适当的优先权？ |
| NC-3 |存储中立性 | user_data/ 的路径不是固定的而是通过内核的 userdata_manager |
| NC-4 |最大限度地减少外部依赖 |除了标准库之外是否还有其他必需的依赖项（Docker SDK 是可选的吗？） |
| NC-5 |覆盖设置的可能性|是否可以使用环境变量或 API 来更改所有行为？是否有任何硬编码设置？

---

## 第 3 阶段：可扩展性验证

### 3-A：user_data 可扩展性

|身份证 |内容 |详情 |
|----|------|------|
| UX-1 |来自其他包的 user_data 访问其他包可以有自己的 user_data 子目录吗？
| UX-2 |数据迁移|更改 user_data 的架构时有没有办法迁移 |
| UX-3 |备份/恢复|是否可以批量导出/导入user_data |
| UX-4 |存储插件 |是否可以将其替换为 JSON 文件以外的存储后端（SQLite 等） |
| UX-5 |并发访问安全 |从多个线程/进程写入user_data是否安全（锁定机制）|

### 3-B：包间可扩展性

|身份证 |内容 |详情 |
|----|------|------|
| PX-1 |测试从其他包添加路由 |创建一个虚拟Pack并在io.http.route中注册路由，http.py会收集它吗？ |
| PX-2 |从其他包替换域名 |是否可以用InterfaceRegistry替换AIClient等 |
| PX-3 |事件挂钩| EventBus 可以挂钩默认包行为吗？ |
| PX-4 |提供商插件 |是否可以从另一个包中添加新的 AI 提供程序（复制 Genspark 方法）|

---

## 第 4 阶段：生产准备

### 4-A：权限系统完成

|身份证 |内容 |详情 |
|----|------|------|
| AUTH-1 |全面实施T15 |阶段 2-A P1-2 中的基础实施。此处集成测试 + 边缘案例支持 |
| AUTH-2 |每条路线的权限定义|定义所有 100 多个路由所需的权限 |
| AUTH-3 |认证中间件集成 |在 http.py 的 _handle_request 中插入权限检查 |
| AUTH-4 |默认用户+初始设置流程 |首次启动时创建管理员用户 |

### 4-B：创建一组工具/提示

|身份证 |内容 |详情 |
|----|------|------|
| TP-1 |内置工具集 | web_search、计算器、code_exec、file_read、file_write、http_request |
| TP-2 |内置提示模板|通用助理、编码员、分析师、翻译员、摘要员、创意作家 |
| TP-3 |工具/提示文档|每个工具/提示的用法、参数和示例 |
| TP-4 |测试工具/提示|检查各工具/提示的操作 |

### 4-C：前端设置（用户责任）

|身份证 |内容 |详情 |负责人 |
|----|------|------|------|
| FE-1 | shell.html大规模分裂 |分为背景、侧边栏、输入栏、标题、聊天选项卡、设置 |用户 |
| FE-2 |选项卡用户界面 |类似浏览器的选项卡（正常、工作、编码、代理、最大、监视器）|用户 |
| FE-3 |会话用户界面 |并行显示对话选项卡（历史记录 1 / 历史记录 2 / 历史记录 3）|用户 |
| FE-4 |频道用户界面 | Slack风格的频道列表+消息展示|用户 |
| FE-5 |上下文面板 |实时显示当前上下文信息 |用户 |
| FE-6 |开发面板|即时使用，实时编辑 |用户 |
| FE-7 |权限管理UI |用户/角色/权限管理屏幕 |用户 |
| FE-8 |免责声明弹出窗口 |同意工具弹出显示|用户 |
| FE-9 |容器操作UI | Linux环境操作画面+截图显示 |用户 |

---

## 第 5 阶段：桌面应用程序

|身份证 |内容 |详情 |
|----|------|------|
| DA-1 | Electron 或 Tauri 包装器 |将 shell.html 打包为桌面应用程序 |
| DA-2 |原生通知 | OS通知配合（定期执行代理结果通知等）|
| DA-3 |托盘图标|后台操作+托盘图标|
| DA-4 |自动启动设置|操作系统启动时自动启动内核+默认包 |
| DA-5 |更新者 |基于 git pull 的自动更新（或 GitHub 发布）|

---

## 第 6 阶段：编译 + 发布

|身份证 |内容 |详情 |
|----|------|------|
| CP-1 | Python 包 |单个二进制内核 + 使用 PyInstaller 或 Nuitka 的默认包 |
| CP-2 |前端优化 | minify shell.html + 资源包 |
| CP-3 |跨平台构建 |为 macOS、Linux、Windows 构建 |
| CP-4 |安装人员 | macOS：.dmg、Linux：.AppImage/.deb、Windows：.msi |
| CP-5 | CI/CD 管道 |使用 GitHub Actions 构建 + 测试 + 发布自动化 |
| CP-6 |发行说明 |为所有功能创建发行说明 |

---

## 第 7 阶段：最终清理

|身份证 |内容 |详情 |
|----|------|------|
| CL-1 |删除不需要的文件 | Transport/uds.py、transport/stdio.py（CLI 迁移后）、blocks/frontend/stop.py |
| CL-2 |文档最终同步 | 24 文档已更新以获得完整功能 |
| CL-3 | README.md 已更新 |安装说明、功能列表、屏幕截图 |
| CL-4 | CHANGELOG.md 创建 |完整发布历史 |
| CL-5 |许可证确认 |许可文件的最终确认 |
| CL-6 | feature/genspark-provider 分支删除 |合并分支清理|

---

## 统计数据

|项目 |数量 |
|------|------|
|总相数| 8（0-7）|
|任务总数 |大约。 80|
|已完成任务 |约 45 |
|剩余任务 |大约。 35 | 35
|登记路线数量 | 100+ |
|块数| 100+ |
|域模块数量| 30+ |
|文件| 24 个文件 |
