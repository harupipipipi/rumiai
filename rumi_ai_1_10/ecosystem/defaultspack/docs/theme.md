<!-- docs-i18n-links:start -->
[EN](./theme.md) | [JP](./i18n/ja/theme.md) | [KR](./i18n/ko/theme.md) | [CN](./i18n/zh-cn/theme.md)
<!-- docs-i18n-links:end -->

# theme.md — Rumi AI OS theme specification

## 1. Overview

A theme is a declarative file that defines the look of the UI. Combine colors, fonts, spacing, animations, and drawing styles for each widget into a single YAML file and apply it to the entire front end.

Defaults provide a ``format specification'' and ``enforcement mechanism'' for a theme. All specific theme files (color scheme and font specifications) are placed in user_data. The theme has no effect on the backend. Widget JSON generation, handler execution, and Flow processing do not know the existence of a theme. Even if the theme changes, the Asset HTML/JS code does not need to be changed. This is because it only references CSS variables.


## 2. Design philosophy

**Declarative**: Themes are not code. Just write the value in YAML. It does not contain any execution logic.**Token-based**: Themes are defined as named tokens (`color.primary`, `spacing.md`, etc.) rather than writing color and size values directly. Asset looks up the token name and the theme resolves the actual value.**Backend independent**: Theme is read only by the frontend layer (Theme Engine in shell.html). Backend handlers, tools, and flows are unaware of the existence of the theme. The Widget JSON sent by emit_widget is theme-independent data, and the Theme Engine applies the appearance when rendering.**Completely replaceable**: The default theme placed by defaults during initial setup can be freely overwritten or replaced by the user or pack.**Inheritable**: A theme can inherit another theme with `extends` and define only the differences.


## 3. Directory structure

```
user_data/themes/
├── dark.theme.yaml              # デフォルトのダークテーマ
├── light.theme.yaml             # デフォルトのライトテーマ
└── installed/                   # Pack がインストールしたテーマ
    ├── monokai.theme.yaml
    └── nord.theme.yaml
```

The theme can be switched using `theme_id` of `user_data/config.json`.

```json
{
  "theme_id": "dark"
}
```

`theme_id` matches the `theme_id` field in theme.yaml.


## 4. theme.yaml complete specification

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


## 5. Token system

### 5.1 Token reference syntax

To cross-reference tokens within a theme, use the `{category.key}` syntax.

```yaml
border_focus: "1px solid {color.primary}"    # color.primary の値に展開される
padding: "{spacing.md}"                       # spacing.md の値に展開される
```

References are only valid within theme files. Circular references are prohibited. Theme Engine detects this when loading and issues an error.

### 5.2 Token Categories

**color** — Color value. Describe using CSS color expression (hex, rgba, hsl). Define with a semantic name (`primary`, `success`, `error`, etc.) and assign a specific color code.**typography** — Font-related values. `font_family` is a CSS font-family string. `font_size_*` is an integer in px. `font_weight_*` is a CSS font-weight value. `line_height_*` is a unitless ratio.

**spacing** — Margin or gap value. An integer in px. The names are relative sizes: xs, sm, md, lg, xl, 2xl.**radius** — Corner radius value. An integer in px. `full` represents a pill type with 9999px.**shadow** — Box shadow value. CSS box-shadow string.**transition** — Transition value. CSS transition shorthand string.**z_index** — Stacking order value. integer.


## 6. Animation definition

### 6.1 Structure

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

`keyframes` describes the CSS @keyframes rule as is. `duration` is CSS animation-duration. `timing` is animation-timing-function. `iteration` is animation-iteration-count.

### 6.2 References from Widgets

Specify the animation name in the `style_hint.animation` of the widget or the `animation` field of the widget style definition.

```json
{
  "type": "indicator",
  "label": "Thinking...",
  "state": "running",
  "animation": "wave_dots"
}
```

Theme Engine applies CSS animations by referring to `animations.wave_dots`. If no animation name is specified in the Widget JSON, the default animation in the Widget style definition (e.g. `indicator.states.running.animation`) is used.

### 6.3 Custom animation

You can define new animations by simply adding them to the `animations` section of your theme file. Applies if the Asset JS references the animation name. No changes are required on the defaults side.


## 7. Widget style definition

### 7.1 Structure

Define the style in the `widgets` section using the Widget type name as a key.

```yaml
widgets:
  code_block:
    syntax_theme: "one-dark-pro"
    background: "#1e1e1e"
    font_family: "{typography.font_family_mono}"
    ...
```

Widget type names correspond to all widget types defined in widget.md (text, code_block, diff, image, screenshot, progress, terminal, table, chart, file_tree, markdown, audio, video, map, input, button, select, toggle, slider, checkbox, container, row, column, tabs, collapsible, card, stream, indicator, custom).

### 7.2 variants

Some Widgets (button, card, etc.) have `variants`. Specify which variant to use in `style_hint.variant` of Widget JSON.

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

If `style_hint.variant` is unspecified or unknown value, `default` variant is used.

### 7.3 states (indicator only)

The indicator Widget has a state in the `state` field. Themes define colors and animations for each state.

```yaml
indicator:
  states:
    running: { color: "{color.primary}", animation: "pulse" }
    success: { color: "{color.success}", animation: "fade_in" }
    error: { color: "{color.error}", animation: "fade_in" }
    waiting: { color: "{color.warning}", animation: "wave_dots" }
```

### 7.4 style_hint

The `style_hint` field in Widget JSON is a hint to the theme. The theme may or may not interpret this hint. Any key other than variant can be included.

```json
{
  "type": "text",
  "text": "Warning message",
  "style_hint": {"color": "warning", "size": "sm", "weight": "bold"}
}
```

The theme defines how the Theme Engine converts `style_hint` to CSS. The defaults Theme Engine recognizes the following hint keys by default.

| Hint key | Description | Conversion to CSS |
|---|---|---|
| `variant` | Select Widget variant | Apply variant style |
| `color` | Color specification by token name | `color: var(--color-{value})` |
| `size` | Size of xs/sm/md/lg/xl | `font-size: var(--font-size-{value})` |
| `weight` | Font weight | `font-weight: var(--font-weight-{value})` |
| `align` | Text alignment | `text-align: {value}` |
| `padding` | Padding with token name | `padding: var(--spacing-{value})` |
| `hidden` | Hide | `display: none` |

It is also possible for themes to add their own hint keys. Keys not recognized by Theme Engine are ignored.

### 7.5 Custom Widget Styles

Define the style in the `widgets.custom` section using Custom Widget's `custom_type` as the key.

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

The Custom Widget's renderer (JS placed in `user_data/widget_renderers/`) reads and applies this style.


## 8. Slot Style

The `slots` section defines the appearance of the shell.html slots (header, sidebar, main, panel, statusbar, floating).

The structure and layout of slots (which Asset goes into which slot) is not the responsibility of the theme. Themes only define the slot's background color, border, default size, and resizing handle color.


## 9. Convert to CSS variable

### 9.1 Conversion rules

Theme Engine converts the theme file into CSS variables and sets them to `:root`. The conversion rules are as follows.

Token: `tokens.{category}.{key}` → `--{category}-{key}`

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

Numerical tokens (other than spacing, radius, font_size_*, shadow) are automatically given `px`. String tokens are output as is.

### 9.2 Injecting animation

Inject all keyframes of the `animations` section as `<style>` elements.

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

### 9.3 Widget Style Injection

Widget styles are not injected as CSS variables. The Theme Engine directly references the style definition when drawing the widget. The reason is that the structure of Widget styles differs for each type, and cannot be expressed using flat CSS variables.

### 9.4 Reference from Asset

Asset's HTML/JS refers to CSS variables.

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

When you switch themes, the values of CSS variables change and the look of your Assets is automatically updated. No code changes are required on the Asset side.


## 10. Theme application mechanism

### 10.1 At startup

1. shell.html's Theme Engine reads `user_data/config.json` to `theme_id`
2. Load `user_data/themes/{theme_id}.theme.yaml`
3. If `extends` is specified, load the parent theme recursively
4. Expand token references (`{category.key}`)
5. Set CSS variable to `:root`
6. Inject animation keyframes
7. Keep Widget style definitions in memory

### 10.2 Theme switching

The front end receives theme switching events.

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "light"
  }
}
```

The Theme Engine loads the new theme file, overwrites CSS variables, and reinjects animations. All Assets will change to look like the new theme in real time.

To change the theme, rewrite `theme_id` of `user_data/config.json` with the backend's `config.write` authority, and notify the frontend with `emit_event("theme.change", {"theme_id": "..."})`.


## 11. Theme inheritance

### 11.1 extends

A theme can inherit another theme in the `extends` field.

```yaml
theme_id: "dark_blue"
extends: "dark"
tokens:
  color:
    primary: "#3b82f6"
    primary_hover: "#60a5fa"
```

In this case, all values in the `dark` theme will be the base, and only the values explicitly defined in `dark_blue` will be overwritten. `dark`, `color.background`, `typography.*`, `spacing.*`, etc. are all inherited.

### 11.2 Merge rules

Merging is done recursively up to a deep level.

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

Result:

```yaml
widgets:
  button:
    variants:
      default: { background: "#1a1a1a", color: "#e5e5e5" }   # 親から継承
      primary: { background: "#3b82f6", color: "#ffffff" }    # background のみ上書き
```

### 11.3 Inheritance Chain

Multi-level inheritance is possible. If A extends B extends C, merged in the order of C → B → A. Circular inheritance is detected by the Theme Engine and treated as an error.


## 12. How the Pack provides themes

If the Pack provides a theme, the theme files are copied to `user_data/themes/installed/` when the Pack is installed.

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

Installation flow: Pack approval → Copy `themes/monokai.theme.yaml` to `user_data/themes/installed/monokai.theme.yaml` → It will be applied if the user changes `theme_id` of `config.json` to `monokai`.

There are zero changes on the defaults side.


## 13. Fallback

### 13.1 If the theme file is not found

If a theme file corresponding to `theme_id` in `config.json` does not exist, the Theme Engine uses a hard-coded minimal fallback theme. The fallback theme only has the following values ​​embedded in shell.html.

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

This is to provide a screen that can be operated by humans at the bare minimum.

### 13.2 If the theme file is corrupted

If YAML parsing fails, use a fallback theme and display an error in the statusbar.

### 13.3 When an undefined token is referenced

If Asset references `var(--color-nonexistent)`, the `initial` value will be used according to the CSS specifications. Theme Engine detects undefined token references and issues a warning to the console.

### 13.4 When Widget style is undefined

If a theme does not define styles for a particular widget type, the Theme Engine renders the widget using the browser's default style.


## 14. Validation of theme files

The Theme Engine verifies the following at load time:

Required fields: `theme_id`, `name`, `version`. Required tokens: `color.background`, `color.surface`, `color.text`, `color.border`, `color.primary`, `typography.font_family`, `typography.font_family_mono`, `typography.font_size_base`, `spacing.md`, `radius.md`. Circular references: Are there any cycles in the `{category.key}` references between tokens? Circular inheritance: `extends` Are there any cycles in the chain?

If a required field or token is missing, the fallback theme will only complete the missing value and issue a warning. Instead of rejecting the theme entirely, make it work as much as possible.
