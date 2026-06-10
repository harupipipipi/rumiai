<!-- docs-i18n-links:start -->
[EN](../../theme.md) | [JP](../ja/theme.md) | [KR](../ko/theme.md) | [CN](./theme.md)
<!-- docs-i18n-links:end -->

# theme.md — Rumi AI OS 主题规范

## 1. 概述

主题是定义 UI 外观的声明性文件。将每个小部件的颜色、字体、间距、动画和绘图样式合并到单个 YAML 文件中，并将其应用到整个前端。

默认值为主题提供“`format specification'' and ``执行机制”。所有特定的主题文件（配色方案和字体规范）都放置在 user_data 中。主题对后端没有影响。 Widget JSON 生成、处理程序执行和流程处理不知道主题的存在。即使主题发生变化，Asset HTML/JS 代码也不需要更改。这是因为它只引用 CSS 变量。


## 2.设计理念

**声明性**：主题不是代码。只需将值写入 YAML 中即可。它不包含任何执行逻辑。

**基于标记**：主题定义为命名标记（`color.primary`、`spacing.md`等），而不是直接写入颜色和尺寸值。资产查找代币名称，主题解析实际值。

**后端独立**：主题仅由前端层（shell.html 中的主题引擎）读取。后端处理程序、工具和流程不知道主题的存在。 emit_widget 发送的 Widget JSON 是与主题无关的数据，主题引擎在渲染时应用外观。

**完全可替换**：初始设置期间默认放置的默认主题可以由用户或包自由覆盖或替换。

**可继承**：一个主题可以通过`extends`继承另一个主题并仅定义差异。


## 3.目录结构

```
user_data/themes/
├── dark.theme.yaml              # デフォルトのダークテーマ
├── light.theme.yaml             # デフォルトのライトテーマ
└── installed/                   # Pack がインストールしたテーマ
    ├── monokai.theme.yaml
    └── nord.theme.yaml
```

可以使用`theme_id`或`user_data/config.json`切换主题。

```json
{
  "theme_id": "dark"
}
```

`theme_id` 与 theme.yaml 中的`theme_id` 字段匹配。


## 4. theme.yaml完整规范

```yaml
# ──────────────────────────────────────────────
# メタデータ
# ──────────────────────────────────────────────
theme_id: "dark"
name: "Dark"
description: "デフォルトのダークテーマ"
version: "1.0.0"
author: "defaults"
extends: null                          # 継承元の theme_id（null で継承なし）

# ──────────────────────────────────────────────
# トークン
# ──────────────────────────────────────────────
tokens:

  color:
    # 基本色
    primary: "#6366f1"
    primary_hover: "#818cf8"
    primary_active: "#4f46e5"
    secondary: "#8b5cf6"
    accent: "#06b6d4"

    # 背景
    background: "#0f0f0f"
    surface: "#1a1a1a"
    surface_hover: "#252525"
    surface_active: "#2f2f2f"
    overlay: "rgba(0, 0, 0, 0.5)"

    # テキスト
    text: "#e5e5e5"
    text_secondary: "#a3a3a3"
    text_disabled: "#525252"
    text_inverse: "#0f0f0f"
    text_link: "#818cf8"

    # ボーダー
    border: "#2a2a2a"
    border_hover: "#3a3a3a"
    border_focus: "#6366f1"

    # セマンティック
    success: "#22c55e"
    success_bg: "rgba(34, 197, 94, 0.1)"
    warning: "#f59e0b"
    warning_bg: "rgba(245, 158, 11, 0.1)"
    error: "#ef4444"
    error_bg: "rgba(239, 68, 68, 0.1)"
    info: "#3b82f6"
    info_bg: "rgba(59, 130, 246, 0.1)"

  typography:
    font_family: "Inter, system-ui, -apple-system, sans-serif"
    font_family_mono: "JetBrains Mono, Fira Code, Consolas, monospace"
    font_size_xs: 11
    font_size_sm: 12
    font_size_base: 14
    font_size_lg: 16
    font_size_xl: 20
    font_size_2xl: 24
    font_weight_normal: 400
    font_weight_medium: 500
    font_weight_bold: 600
    line_height_tight: 1.25
    line_height_normal: 1.5
    line_height_relaxed: 1.75

  spacing:
    xs: 4
    sm: 8
    md: 16
    lg: 24
    xl: 32
    2xl: 48

  radius:
    none: 0
    sm: 4
    md: 8
    lg: 12
    xl: 16
    full: 9999

  shadow:
    none: "none"
    sm: "0 1px 2px rgba(0, 0, 0, 0.2)"
    md: "0 4px 6px rgba(0, 0, 0, 0.3)"
    lg: "0 10px 15px rgba(0, 0, 0, 0.4)"
    xl: "0 20px 25px rgba(0, 0, 0, 0.5)"

  transition:
    fast: "0.1s ease"
    normal: "0.2s ease"
    slow: "0.3s ease"

  z_index:
    base: 0
    dropdown: 100
    sticky: 200
    modal: 300
    popover: 400
    tooltip: 500

# ──────────────────────────────────────────────
# アニメーション
# ──────────────────────────────────────────────
animations:

  wave_dots:
    keyframes: |
      @keyframes wave-dots {
        0%, 60%, 100% { transform: translateY(0); }
        30% { transform: translateY(-8px); }
      }
    duration: "1.4s"
    timing: "ease-in-out"
    iteration: "infinite"

  pulse:
    keyframes: |
      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }
    duration: "2s"
    timing: "ease-in-out"
    iteration: "infinite"

  fade_in:
    keyframes: |
      @keyframes fade-in {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
      }
    duration: "0.3s"
    timing: "ease-out"
    iteration: "1"

  fade_out:
    keyframes: |
      @keyframes fade-out {
        from { opacity: 1; }
        to { opacity: 0; }
      }
    duration: "0.2s"
    timing: "ease-in"
    iteration: "1"

  slide_in_left:
    keyframes: |
      @keyframes slide-in-left {
        from { transform: translateX(-20px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
    duration: "0.2s"
    timing: "ease-out"
    iteration: "1"

  slide_in_right:
    keyframes: |
      @keyframes slide-in-right {
        from { transform: translateX(20px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
    duration: "0.2s"
    timing: "ease-out"
    iteration: "1"

  slide_in_up:
    keyframes: |
      @keyframes slide-in-up {
        from { transform: translateY(20px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
    duration: "0.2s"
    timing: "ease-out"
    iteration: "1"

  typing_cursor:
    keyframes: |
      @keyframes typing-cursor {
        0%, 100% { opacity: 1; }
        50% { opacity: 0; }
      }
    duration: "1s"
    timing: "step-end"
    iteration: "infinite"

  spin:
    keyframes: |
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
    duration: "1s"
    timing: "linear"
    iteration: "infinite"

  shimmer:
    keyframes: |
      @keyframes shimmer {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
      }
    duration: "1.5s"
    timing: "linear"
    iteration: "infinite"

# ──────────────────────────────────────────────
# Widget スタイル
# ──────────────────────────────────────────────
widgets:

  # ─── 表示系 ───

  text:
    color: "{color.text}"
    font_size: "{typography.font_size_base}"
    line_height: "{typography.line_height_normal}"

  code_block:
    syntax_theme: "one-dark-pro"
    background: "#1e1e1e"
    border: "1px solid {color.border}"
    border_radius: "{radius.md}"
    padding: "{spacing.md}"
    font_family: "{typography.font_family_mono}"
    font_size: "{typography.font_size_sm}"
    line_height: "{typography.line_height_relaxed}"
    show_line_numbers: true
    show_copy_button: true
    show_language_label: true
    max_height: 500
    scrollbar_color: "{color.surface_hover}"

  diff:
    added_bg: "rgba(34, 197, 94, 0.15)"
    added_color: "{color.success}"
    removed_bg: "rgba(239, 68, 68, 0.15)"
    removed_color: "{color.error}"
    unchanged_color: "{color.text_secondary}"
    border_radius: "{radius.md}"
    font_family: "{typography.font_family_mono}"
    font_size: "{typography.font_size_sm}"

  image:
    border_radius: "{radius.md}"
    max_width: "100%"
    background: "{color.surface}"
    border: "1px solid {color.border}"

  screenshot:
    border_radius: "{radius.md}"
    border: "1px solid {color.border}"
    shadow: "{shadow.md}"
    overlay_bg: "rgba(0, 0, 0, 0.6)"
    overlay_color: "#ffffff"
    overlay_font_size: "{typography.font_size_xs}"

  progress:
    bar_color: "{color.primary}"
    background: "{color.surface}"
    height: 4
    border_radius: "{radius.full}"
    label_color: "{color.text_secondary}"
    label_font_size: "{typography.font_size_sm}"
    animation: "shimmer"

  terminal:
    background: "#000000"
    color: "#00ff00"
    font_family: "{typography.font_family_mono}"
    font_size: "{typography.font_size_sm}"
    border_radius: "{radius.md}"
    padding: "{spacing.md}"
    prompt_color: "{color.primary}"
    error_color: "{color.error}"
    max_height: 400

  table:
    header_bg: "{color.surface}"
    header_color: "{color.text}"
    header_font_weight: "{typography.font_weight_bold}"
    row_bg: "transparent"
    row_hover_bg: "{color.surface_hover}"
    border_color: "{color.border}"
    cell_padding: "{spacing.sm} {spacing.md}"
    font_size: "{typography.font_size_sm}"
    stripe: true
    stripe_bg: "rgba(255, 255, 255, 0.02)"

  chart:
    colors:
      - "{color.primary}"
      - "{color.secondary}"
      - "{color.accent}"
      - "{color.success}"
      - "{color.warning}"
      - "{color.error}"
      - "{color.info}"
    background: "transparent"
    grid_color: "{color.border}"
    label_color: "{color.text_secondary}"
    font_size: "{typography.font_size_xs}"

  file_tree:
    indent: 16
    icon_size: 16
    row_height: 28
    hover_bg: "{color.surface_hover}"
    selected_bg: "{color.primary}"
    selected_color: "#ffffff"
    font_size: "{typography.font_size_sm}"
    font_family: "{typography.font_family_mono}"

  markdown:
    heading_color: "{color.text}"
    paragraph_color: "{color.text}"
    link_color: "{color.text_link}"
    code_inline_bg: "{color.surface}"
    code_inline_color: "{color.accent}"
    code_inline_radius: "{radius.sm}"
    blockquote_border_color: "{color.primary}"
    blockquote_bg: "{color.surface}"
    hr_color: "{color.border}"
    list_marker_color: "{color.text_secondary}"

  audio:
    background: "{color.surface}"
    border_radius: "{radius.md}"
    progress_color: "{color.primary}"
    button_color: "{color.text}"
    time_color: "{color.text_secondary}"
    height: 48

  video:
    border_radius: "{radius.md}"
    background: "#000000"
    controls_bg: "rgba(0, 0, 0, 0.7)"
    controls_color: "#ffffff"

  map:
    border_radius: "{radius.md}"
    border: "1px solid {color.border}"
    height: 300

  # ─── コントロール系 ───

  input:
    background: "{color.surface}"
    color: "{color.text}"
    border: "1px solid {color.border}"
    border_focus: "1px solid {color.border_focus}"
    border_radius: "{radius.md}"
    padding: "{spacing.sm} {spacing.md}"
    font_size: "{typography.font_size_base}"
    placeholder_color: "{color.text_disabled}"
    shadow_focus: "0 0 0 2px rgba(99, 102, 241, 0.2)"

  button:
    variants:
      default:
        background: "{color.surface}"
        color: "{color.text}"
        border: "1px solid {color.border}"
        hover_bg: "{color.surface_hover}"
      primary:
        background: "{color.primary}"
        color: "#ffffff"
        border: "none"
        hover_bg: "{color.primary_hover}"
      danger:
        background: "{color.error}"
        color: "#ffffff"
        border: "none"
        hover_bg: "#dc2626"
      ghost:
        background: "transparent"
        color: "{color.text}"
        border: "none"
        hover_bg: "{color.surface_hover}"
    border_radius: "{radius.md}"
    padding: "{spacing.sm} {spacing.md}"
    font_size: "{typography.font_size_sm}"
    font_weight: "{typography.font_weight_medium}"
    transition: "{transition.fast}"

  select:
    background: "{color.surface}"
    color: "{color.text}"
    border: "1px solid {color.border}"
    border_radius: "{radius.md}"
    padding: "{spacing.sm} {spacing.md}"
    dropdown_bg: "{color.surface}"
    dropdown_shadow: "{shadow.lg}"
    option_hover_bg: "{color.surface_hover}"
    option_selected_bg: "{color.primary}"
    option_selected_color: "#ffffff"

  toggle:
    track_off_bg: "{color.surface_active}"
    track_on_bg: "{color.primary}"
    thumb_color: "#ffffff"
    width: 40
    height: 22
    transition: "{transition.normal}"

  slider:
    track_bg: "{color.surface_active}"
    track_fill_bg: "{color.primary}"
    thumb_bg: "#ffffff"
    thumb_shadow: "{shadow.sm}"
    thumb_size: 16
    track_height: 4

  checkbox:
    size: 18
    border: "1px solid {color.border}"
    border_radius: "{radius.sm}"
    checked_bg: "{color.primary}"
    checked_color: "#ffffff"
    hover_border: "{color.border_hover}"

  # ─── レイアウト系 ───

  container:
    padding: 0
    background: "transparent"

  row:
    gap: "{spacing.md}"

  column:
    gap: "{spacing.md}"

  tabs:
    tab_bg: "transparent"
    tab_active_bg: "{color.surface}"
    tab_color: "{color.text_secondary}"
    tab_active_color: "{color.text}"
    tab_border_bottom: "2px solid transparent"
    tab_active_border_bottom: "2px solid {color.primary}"
    tab_padding: "{spacing.sm} {spacing.md}"
    tab_font_size: "{typography.font_size_sm}"
    content_padding: "{spacing.md}"

  collapsible:
    header_bg: "transparent"
    header_hover_bg: "{color.surface_hover}"
    header_color: "{color.text}"
    header_padding: "{spacing.sm} {spacing.md}"
    content_padding: "{spacing.md}"
    icon_color: "{color.text_secondary}"
    border: "1px solid {color.border}"
    border_radius: "{radius.md}"
    animation: "fade_in"

  card:
    variants:
      default:
        background: "{color.surface}"
        border: "1px solid {color.border}"
        border_radius: "{radius.md}"
        padding: "{spacing.md}"
        shadow: "none"
      compact:
        background: "{color.surface}"
        border: "1px solid {color.border}"
        border_radius: "{radius.sm}"
        padding: "{spacing.sm}"
        shadow: "none"
      elevated:
        background: "{color.surface}"
        border: "none"
        border_radius: "{radius.md}"
        padding: "{spacing.md}"
        shadow: "{shadow.md}"
    header_border_bottom: "1px solid {color.border}"
    header_padding: "{spacing.sm} {spacing.md}"
    footer_border_top: "1px solid {color.border}"
    footer_padding: "{spacing.sm} {spacing.md}"

  # ─── ストリーミング系 ───

  stream:
    thinking:
      animation: "wave_dots"
      color: "{color.text_secondary}"
      font_style: "italic"
      content_collapsed_default: false
    content:
      typing_cursor: true
      cursor_animation: "typing_cursor"
      cursor_color: "{color.primary}"
      cursor_width: 2

  indicator:
    states:
      running:
        color: "{color.primary}"
        animation: "pulse"
      success:
        color: "{color.success}"
        animation: "fade_in"
      error:
        color: "{color.error}"
        animation: "fade_in"
      waiting:
        color: "{color.warning}"
        animation: "wave_dots"
      idle:
        color: "{color.text_disabled}"
        animation: "none"
    dot_size: 8
    label_font_size: "{typography.font_size_sm}"
    label_color: "{color.text_secondary}"
    gap: "{spacing.sm}"

  # ─── カスタム ───

  custom: {}

# ──────────────────────────────────────────────
# スロットスタイル
# ──────────────────────────────────────────────
slots:

  header:
    background: "{color.surface}"
    border_bottom: "1px solid {color.border}"
    height: 48

  sidebar:
    background: "{color.background}"
    border_color: "{color.border}"
    width_default: 280
    min_width: 200
    max_width: 500
    resize_handle_color: "{color.border}"
    resize_handle_hover_color: "{color.primary}"

  main:
    background: "{color.background}"
    padding: 0

  panel:
    background: "{color.background}"
    border_top: "1px solid {color.border}"
    height_default: 250
    min_height: 100
    max_height: 600
    resize_handle_color: "{color.border}"
    resize_handle_hover_color: "{color.primary}"

  statusbar:
    background: "{color.surface}"
    border_top: "1px solid {color.border}"
    height: 28
    font_size: "{typography.font_size_xs}"
    color: "{color.text_secondary}"

  floating:
    overlay_bg: "{color.overlay}"
    background: "{color.surface}"
    border: "1px solid {color.border}"
    border_radius: "{radius.lg}"
    shadow: "{shadow.xl}"
    animation: "fade_in"

# ──────────────────────────────────────────────
# スクロールバー
# ──────────────────────────────────────────────
scrollbar:
  width: 8
  track_bg: "transparent"
  thumb_bg: "{color.surface_active}"
  thumb_hover_bg: "{color.text_disabled}"
  thumb_radius: "{radius.full}"
```


## 5. 代币系统

### 5.1 令牌引用语法

要在主题内交叉引用标记，请使用`{category.key}`语法。

```yaml
border_focus: "1px solid {color.primary}"    # color.primary の値に展開される
padding: "{spacing.md}"                       # spacing.md の値に展開される
```

引用仅在主题文件内有效。禁止循环引用。主题引擎在加载时检测到这一点并发出错误。

### 5.2 代币类别

**颜色** — 颜色值。描述如何使用 CSS 颜色表达式（hex、rgba、hsl）。使用语义名称（`primary`、`success`、`error`等）进行定义并分配特定的颜色代码。

**版式** — 与字体相关的值。 `font_family` 是 CSS 字体系列字符串。 `font_size_*` 是一个以 px 为单位的整数。 `font_weight_*` 是 CSS 字体粗细值。 `line_height_*` 是无单位比率。

**间距** — 边距或间隙值。以 px 为单位的整数。名称是相对大小：xs、sm、md、lg、xl、2xl。

**半径** — 圆角半径值。以 px 为单位的整数。 `full`代表9999px的药丸类型。

**shadow** — 框阴影值。 CSS 框阴影字符串。

**过渡** — 过渡值。 CSS 过渡简写字符串。

**z_index** — 堆叠顺序值。整数。


## 6.动画定义

### 6.1 结构

```yaml
animations:
  animation_name:
    keyframes: |
      @keyframes animation-name {
        ...
      }
    duration: "1s"
    timing: "ease-in-out"
    iteration: "infinite"
```

`keyframes` 按原样描述了 CSS @keyframes 规则。 `duration` 是 CSS 动画持续时间。 `timing` 是动画计时函数。 `iteration` 是动画迭代计数。

### 6.2 来自小部件的引用

在小部件的`style_hint.animation`或小部件样式定义的`animation`字段中指定动画名称。

```json
{
  "type": "indicator",
  "label": "Thinking...",
  "state": "running",
  "animation": "wave_dots"
}
```

主题引擎参考`animations.wave_dots`应用CSS动画。如果 Widget JSON 中未指定动画名称，则使用 Widget 样式定义中的默认动画（例如`indicator.states.running.animation`）。

### 6.3 自定义动画

您只需将新动画添加到主题文件的`animations`部分即可定义新动画。如果 Asset JS 引用动画名称，则适用。默认方面不需要进行任何更改。


## 7. Widget样式定义

### 7.1 结构

使用 Widget 类型名称作为键定义 `widgets` 部分中的样式。

```yaml
widgets:
  code_block:
    syntax_theme: "one-dark-pro"
    background: "#1e1e1e"
    font_family: "{typography.font_family_mono}"
    ...
```

小部件类型名称对应于 widget.md 中定义的所有小部件类型（文本、code_block、diff、图像、屏幕截图、进度、终端、表格、图表、file_tree、markdown、音频、视频、地图、输入、按钮、选择、切换、滑块、复选框、容器、行、列、选项卡、可折叠、卡片、流、指示器、自定义）。

### 7.2 变体

某些小部件（按钮、卡片等）具有`variants`。指定在 Widget JSON 的 `style_hint.variant` 中使用哪个变体。

```json
{
  "type": "button",
  "label": "Delete",
  "style_hint": {"variant": "danger"}
}
```

```yaml
button:
  variants:
    default: { background: "...", ... }
    primary: { background: "...", ... }
    danger: { background: "...", ... }
```

如果`style_hint.variant`未指定或未知值，则使用`default`变体。

### 7.3 状态（仅指示器）

指标小部件在`state`字段中有一个状态。主题定义每个状态的颜色和动画。

```yaml
indicator:
  states:
    running: { color: "{color.primary}", animation: "pulse" }
    success: { color: "{color.success}", animation: "fade_in" }
    error: { color: "{color.error}", animation: "fade_in" }
    waiting: { color: "{color.warning}", animation: "wave_dots" }
```

### 7.4 样式提示

Widget JSON 中的`style_hint` 字段是对主题的提示。主题可能会也可能不会解释此提示。可以包含除变体之外的任何键。

```json
{
  "type": "text",
  "text": "Warning message",
  "style_hint": {"color": "warning", "size": "sm", "weight": "bold"}
}
```

主题定义主题引擎如何将`style_hint`转换为CSS。默认主题引擎默认识别以下提示键。

|提示键|描述 |转换为 CSS |
|---|---|---|
| §鲁米§0§|选择小部件变体 |应用变体风格 |
| §鲁米§0§|按代币名称指定颜色 | §鲁米§1§ |
| §鲁米§0§|尺寸：xs/sm/md/lg/xl | §鲁米§1§ |
| §鲁米§0§|字体粗细| §鲁米§1§ |
| §鲁米§0§|文本对齐 | §鲁米§1§ |
| §鲁米§0§|用令牌名称填充 | §鲁米§1§ |
| §鲁米§0§|隐藏 | §鲁米§1§ |

主题也可以添加自己的提示键。主题引擎无法识别的键将被忽略。

### 7.5 自定义小部件样式

使用自定义小部件的`custom_type` 作为键定义`widgets.custom` 部分中的样式。

```yaml
widgets:
  custom:
    3d_viewer:
      background: "#000000"
      border_radius: "{radius.md}"
      height: 400
    graph_editor:
      background: "{color.surface}"
      border: "1px solid {color.border}"
```

自定义小部件的渲染器（JS 放置在`user_data/widget_renderers/` 中）读取并应用此样式。


## 8. 插槽样式

`slots` 部分定义了 shell.html 插槽的外观（标题、侧边栏、主栏、面板、状态栏、浮动）。

插槽的结构和布局（哪个资产进入哪个插槽）不是主题的责任。主题仅定义插槽的背景颜色、边框、默认大小和调整大小手柄颜色。


## 9. 转换为 CSS 变量

### 9.1 转换规则

主题引擎将主题文件转换为 CSS 变量并将它们设置为`:root`。转换规则如下。

代币：`tokens.{category}.{key}`→`--{category}-{key}`

```yaml
tokens:
  color:
    primary: "#6366f1"
  typography:
    font_size_base: 14
  spacing:
    md: 16
```

```css
:root {
  --color-primary: #6366f1;
  --typography-font-size-base: 14px;
  --spacing-md: 16px;
}
```

数字标记（间距、半径、font_size_*、阴影除外）自动给出`px`。字符串标记按原样输出。

### 9.2 注入动画

将`animations`部分的所有关键帧作为`<style>`元素注入。

```css
@keyframes wave-dots {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-8px); }
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

### 9.3 Widget样式注入

小部件样式不会作为 CSS 变量注入。主题引擎在绘制小部件时直接引用样式定义。原因是每种类型的 Widget 样式的结构都不同，并且不能使用平面 CSS 变量来表达。

### 9.4 来自资产的参考

Asset的HTML/JS指的是CSS变量。

```css
/* Asset の CSS */
.my-element {
  color: var(--color-text);
  background: var(--color-surface);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  font-family: var(--typography-font-family);
  font-size: var(--typography-font-size-base);
  transition: background var(--transition-fast);
}
```

当您切换主题时，CSS 变量的值会发生变化，并且资源的外观也会自动更新。资产端不需要更改代码。


## 10.主题应用机制

### 10.1 启动时

1. shell.html 的主题引擎读取 `user_data/config.json` 至 `theme_id`
2. 加载`user_data/themes/{theme_id}.theme.yaml`
3.如果指定`extends`，则递归加载父主题
4. 扩展代币引用（`{category.key}`）
5. 将 CSS 变量设置为`:root`
6.注入动画关键帧
7. 将 Widget 样式定义保存在内存中

### 10.2 主题切换

前端接收主题切换事件。

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "light"
  }
}
```

主题引擎加载新的主题文件、覆盖 CSS 变量并重新注入动画。所有资产将实时更改为新主题。

如需更改主题，请使用后端的`config.write`权限重写`user_data/config.json`的`theme_id`，并用`emit_event("theme.change", {"theme_id": "..."})`通知前端。


## 11.主题继承

### 11.1 扩展

主题可以继承`extends`字段中的另一个主题。

```yaml
theme_id: "dark_blue"
extends: "dark"
tokens:
  color:
    primary: "#3b82f6"
    primary_hover: "#60a5fa"
```

在这种情况下，`dark`主题中的所有值都将成为基础，并且只有`dark_blue`中明确定义的值才会被覆盖。 `dark`、`color.background`、`typography.*`、`spacing.*`等都是遗传的。

### 11.2 合并规则

合并是递归地进行到很深的层次。

```yaml
# 親テーマ (dark)
widgets:
  button:
    variants:
      default: { background: "#1a1a1a", color: "#e5e5e5" }
      primary: { background: "#6366f1", color: "#ffffff" }

# 子テーマ (dark_blue)
widgets:
  button:
    variants:
      primary: { background: "#3b82f6" }
```

结果：

```yaml
widgets:
  button:
    variants:
      default: { background: "#1a1a1a", color: "#e5e5e5" }   # 親から継承
      primary: { background: "#3b82f6", color: "#ffffff" }    # background のみ上書き
```

### 11.3 继承链

多级继承是可能的。如果 A 扩展 B 扩展 C，则按照 C → B → A 的顺序合并。循环继承会被主题引擎检测到并被视为错误。


## 12. Pack 如何提供主题

如果包提供主题，则安装包时主题文件将复制到`user_data/themes/installed/`。

```
user_data/packs/monokai_theme/
├── pack.json
└── themes/
    └── monokai.theme.yaml
```

```json
// pack.json
{
  "pack_id": "monokai_theme",
  "provides": {
    "themes": ["themes/monokai.theme.yaml"]
  }
}
```

安装流程：包批准 → 将`themes/monokai.theme.yaml`复制到`user_data/themes/installed/monokai.theme.yaml` → 如果用户将`config.json`的`theme_id`更改为`monokai`，则会应用。

默认值方面的更改为零。


## 13.后备

### 13.1 如果找不到主题文件

如果与`config.json`中的`theme_id`对应的主题文件不存在，主题引擎将使用硬编码的最小后备主题。后备主题仅在 shell.html 中嵌入以下值。

```
color.background: #000000
color.surface: #111111
color.text: #ffffff
color.border: #333333
color.primary: #6366f1
typography.font_family: system-ui, sans-serif
typography.font_family_mono: monospace
typography.font_size_base: 14
spacing.md: 16
radius.md: 8
```

这是为了提供一个最低限度可以由人类操作的屏幕。

### 13.2 如果主题文件损坏

如果 YAML 解析失败，请使用后备主题并在状态栏中显示错误。

### 13.3 当引用未定义的标记时

如果资产引用`var(--color-nonexistent)`，则将根据CSS规范使用`initial`值。主题引擎检测到未定义的令牌引用并向控制台发出警告。

### 13.4 当Widget样式未定义时

如果主题没有为特定小部件类型定义样式，则主题引擎将使用浏览器的默认样式呈现小部件。


## 14.主题文件的验证

主题引擎在加载时验证以下内容：

必填字段：`theme_id`、`name`、`version`。所需代币：`color.background`、`color.surface`、`color.text`、`color.border`、`color.primary`、`typography.font_family`、`typography.font_family_mono`、`typography.font_size_base`、`spacing.md`、`radius.md`。循环引用：令牌之间的`{category.key}`引用中是否存在循环？循环继承：`extends`链中是否有循环？

如果缺少必填字段或令牌，后备主题将仅补全缺少的值并发出警告。不要完全拒绝这个主题，而是让它尽可能地发挥作用。
