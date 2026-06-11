<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](../ko/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# Rumi 查看器前端

Rumi AI控制面板的前端应用程序。
该目录是`/panel/` UI 的规范源。

`npm run build` 将 Vite 工件复制到`../../rumi_ai_1_10/core_runtime/core_pack/core_control_panel/web`。查看器和浏览器都使用内核提供的相同`/panel/`工件。 Tauri 的`splash` 是内核启动之前的仅供查看器的屏幕，并且与面板前端分开。

## 技术栈

- React 19 + TypeScript
- 维特
- 顺风 CSS v4
- Zustand（状态管理）
- React Flow（流程编辑器）

## 发展

### 先决条件

- Node.js 18+
- npm

### 设置

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

可以通过http://localhost:3000.访问
对后端 API (`http://localhost:8765`) 的请求会通过 Vite 代理自动转发。

### 构建

```bash
npm run build
```

### 类型检查

```bash
npm run lint
```

## 目录结构

```
src/
├── components/    UI コンポーネント
├── hooks/         カスタムフック
├── lib/           ユーティリティ・API クライアント・型定義
├── pages/         ページコンポーネント
├── store.ts       Zustand ストア
└── main.tsx       エントリーポイント
```

## 图形编辑器扩展

`Flows`页面上的图形编辑器现在支持简单垂直步进显示的以下扩展。

- 从`rumi_start`开始的图形编辑
- 每个节点多个端口
- 每个端口受`contracts`（专有标准标签）的连接约束
- `rumi_graph` 将编辑器状态保留在 YAML 中作为元数据
- 保留`basepack`作为流元数据

`rumi_graph` 是编辑器的元数据，以避免破坏运行时兼容性。查看器可以恢复端口/连接信息，同时输出可由现有运行时读取的`steps`。
