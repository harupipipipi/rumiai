```markdown
# theme.md — Rumi AI OS テーマ仕様書

## 1. 概要

テーマは UI の見た目を定義する宣言的ファイルである。色、フォント、スペーシング、アニメーション、Widget ごとの描画スタイルを1つの YAML ファイルにまとめ、フロントエンド全体に適用する。

defaults はテーマの「フォーマット仕様」と「適用メカニズム」を提供する。具体的なテーマファイル（配色やフォント指定）は全て user_data に配置される。テーマはバックエンドに一切影響しない。Widget JSON の生成、handler の実行、Flow の処理はテーマの存在を知らない。テーマが変わっても Asset の HTML/JS コードは変更不要である。CSS 変数を参照しているだけだからである。


## 2. 設計思想

**宣言的**: テーマはコードではない。YAML で値を書くだけ。実行ロジックは一切含まない。

**トークンベース**: テーマは色やサイズの値を直接書くのではなく、名前付きトークン（`color.primary`、`spacing.md` 等）として定義する。Asset はトークン名を参照し、テーマが実際の値を解決する。

**バックエンド非依存**: テーマはフロントエンド層（shell.html の Theme Engine）のみが読む。バックエンドの handler、tool、Flow はテーマの存在を知らない。emit_widget で送出された Widget JSON はテーマ非依存のデータであり、描画時に Theme Engine が見た目を適用する。

**完全置換可能**: defaults が初回セットアップ時に配置するデフォルトテーマも、ユーザーや Pack が自由に上書き・差し替えできる。

**継承可能**: テーマは別のテーマを `extends` で継承し、差分だけを定義できる。


## 3. ディレクトリ構成

```
user_data/themes/
├── dark.theme.yaml              # デフォルトのダークテーマ
├── light.theme.yaml             # デフォルトのライトテーマ
└── installed/                   # Pack がインストールしたテーマ
    ├── monokai.theme.yaml
    └── nord.theme.yaml
```

テーマの切り替えは `user_data/config.json` の `theme_id` で行う。

```json
{
  "theme_id": "dark"
}
```

`theme_id` は theme.yaml 内の `theme_id` フィールドと一致する。


## 4. theme.yaml 完全仕様

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


## 5. トークン体系

### 5.1 トークンの参照構文

テーマ内でトークンを相互参照するには `{category.key}` 構文を使う。

```yaml
border_focus: "1px solid {color.primary}"    # color.primary の値に展開される
padding: "{spacing.md}"                       # spacing.md の値に展開される
```

参照はテーマファイル内でのみ有効である。循環参照は禁止。Theme Engine が読み込み時に検出し、エラーとする。

### 5.2 トークンカテゴリ

**color** — 色の値。CSS の色表現（hex, rgba, hsl）で記述する。セマンティック名（`primary`, `success`, `error` 等）で定義し、具体的な色コードを割り当てる。

**typography** — フォントに関する値。`font_family` は CSS の font-family 文字列。`font_size_*` は px 単位の整数。`font_weight_*` は CSS の font-weight 数値。`line_height_*` は単位なしの比率。

**spacing** — 余白やギャップの値。px 単位の整数。命名は xs, sm, md, lg, xl, 2xl の相対サイズ。

**radius** — 角丸の値。px 単位の整数。`full` は 9999px でピル型を表す。

**shadow** — ボックスシャドウの値。CSS の box-shadow 文字列。

**transition** — トランジションの値。CSS の transition 短縮記法文字列。

**z_index** — 重なり順の値。整数。


## 6. アニメーション定義

### 6.1 構造

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

`keyframes` は CSS の @keyframes ルールをそのまま記述する。`duration` は CSS の animation-duration。`timing` は animation-timing-function。`iteration` は animation-iteration-count。

### 6.2 Widget からの参照

Widget の `style_hint.animation` や Widget スタイル定義の `animation` フィールドにアニメーション名を指定する。

```json
{
  "type": "indicator",
  "label": "Thinking...",
  "state": "running",
  "animation": "wave_dots"
}
```

Theme Engine は `animations.wave_dots` を参照して CSS アニメーションを適用する。Widget JSON にアニメーション名が指定されていない場合、Widget スタイル定義のデフォルトアニメーション（例: `indicator.states.running.animation`）が使用される。

### 6.3 カスタムアニメーション

テーマファイルの `animations` セクションに追加するだけで新しいアニメーションを定義できる。Asset の JS がアニメーション名を参照していれば適用される。defaults 側の変更は不要。


## 7. Widget スタイル定義

### 7.1 構造

`widgets` セクションに Widget 型名をキーとしてスタイルを定義する。

```yaml
widgets:
  code_block:
    syntax_theme: "one-dark-pro"
    background: "#1e1e1e"
    font_family: "{typography.font_family_mono}"
    ...
```

Widget 型名は widget.md に定義された全 Widget 型（text, code_block, diff, image, screenshot, progress, terminal, table, chart, file_tree, markdown, audio, video, map, input, button, select, toggle, slider, checkbox, container, row, column, tabs, collapsible, card, stream, indicator, custom）に対応する。

### 7.2 variants

一部の Widget（button, card 等）は `variants` を持つ。Widget JSON の `style_hint.variant` でどの variant を使うか指定する。

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

`style_hint.variant` が未指定または未知の値の場合、`default` variant が使用される。

### 7.3 states（indicator 専用）

indicator Widget は `state` フィールドで状態を持つ。テーマは状態ごとの色とアニメーションを定義する。

```yaml
indicator:
  states:
    running: { color: "{color.primary}", animation: "pulse" }
    success: { color: "{color.success}", animation: "fade_in" }
    error: { color: "{color.error}", animation: "fade_in" }
    waiting: { color: "{color.warning}", animation: "wave_dots" }
```

### 7.4 style_hint

Widget JSON の `style_hint` フィールドはテーマへのヒントである。テーマはこのヒントを解釈してもしなくてもよい。variant 以外にも任意のキーを含められる。

```json
{
  "type": "text",
  "text": "Warning message",
  "style_hint": {"color": "warning", "size": "sm", "weight": "bold"}
}
```

Theme Engine が `style_hint` を CSS に変換する方法はテーマ側で定義する。defaults の Theme Engine は以下のヒントキーをデフォルトで認識する。

| ヒントキー | 説明 | CSS への変換 |
|---|---|---|
| `variant` | Widget variant の選択 | variant のスタイルを適用 |
| `color` | トークン名による色指定 | `color: var(--color-{value})` |
| `size` | xs/sm/md/lg/xl のサイズ | `font-size: var(--font-size-{value})` |
| `weight` | フォントウェイト | `font-weight: var(--font-weight-{value})` |
| `align` | テキスト配置 | `text-align: {value}` |
| `padding` | トークン名によるパディング | `padding: var(--spacing-{value})` |
| `hidden` | 非表示 | `display: none` |

テーマが独自のヒントキーを追加することも可能。Theme Engine が認識しないキーは無視される。

### 7.5 Custom Widget のスタイル

`widgets.custom` セクションに Custom Widget の `custom_type` をキーとしてスタイルを定義する。

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

Custom Widget のレンダラー（`user_data/widget_renderers/` に配置される JS）がこのスタイルを読み取って適用する。


## 8. スロットスタイル

`slots` セクションで shell.html のスロット（header, sidebar, main, panel, statusbar, floating）の見た目を定義する。

スロットの構造やレイアウト（どの Asset がどのスロットに入るか）はテーマの責務ではない。テーマが定義するのはスロットの背景色、ボーダー、デフォルトサイズ、リサイズハンドルの色のみである。


## 9. CSS 変数への変換

### 9.1 変換規則

Theme Engine はテーマファイルを CSS 変数に変換し、`:root` に設定する。変換規則は以下の通り。

トークン: `tokens.{category}.{key}` → `--{category}-{key}`

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

数値のトークン（spacing, radius, font_size_*, shadow 以外）には自動的に `px` が付与される。文字列のトークンはそのまま出力される。

### 9.2 アニメーションの注入

`animations` セクションの全 keyframes を `<style>` 要素として注入する。

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

### 9.3 Widget スタイルの注入

Widget スタイルは CSS 変数として注入しない。Theme Engine が Widget を描画する際にスタイル定義を直接参照する。理由は Widget スタイルの構造が型ごとに異なり、フラットな CSS 変数では表現しきれないため。

### 9.4 Asset からの参照

Asset の HTML/JS は CSS 変数を参照する。

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

テーマが切り替わると CSS 変数の値が変わり、Asset の見た目が自動的に更新される。Asset 側のコード変更は不要。


## 10. テーマの適用メカニズム

### 10.1 起動時

1. shell.html の Theme Engine が `user_data/config.json` から `theme_id` を読む
2. `user_data/themes/{theme_id}.theme.yaml` を読み込む
3. `extends` が指定されていれば親テーマを再帰的に読み込む
4. トークン参照（`{category.key}`）を展開する
5. CSS 変数を `:root` に設定する
6. アニメーション keyframes を注入する
7. Widget スタイル定義をメモリに保持する

### 10.2 テーマ切り替え

フロントエンドがテーマ切り替えイベントを受信する。

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "light"
  }
}
```

Theme Engine は新しいテーマファイルを読み込み、CSS 変数を上書きし、アニメーションを再注入する。全ての Asset がリアルタイムに新テーマの見た目に切り替わる。

テーマ切り替えはバックエンドの `config.write` 権限で `user_data/config.json` の `theme_id` を書き換え、`emit_event("theme.change", {"theme_id": "..."})` でフロントエンドに通知する。


## 11. テーマの継承

### 11.1 extends

テーマは `extends` フィールドで別のテーマを継承できる。

```yaml
theme_id: "dark_blue"
extends: "dark"
tokens:
  color:
    primary: "#3b82f6"
    primary_hover: "#60a5fa"
```

この場合、`dark` テーマの全ての値がベースとなり、`dark_blue` で明示的に定義された値だけが上書きされる。`dark` の `color.background`, `typography.*`, `spacing.*` 等は全て継承される。

### 11.2 マージ規則

マージは深い階層まで再帰的に行われる。

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

結果:

```yaml
widgets:
  button:
    variants:
      default: { background: "#1a1a1a", color: "#e5e5e5" }   # 親から継承
      primary: { background: "#3b82f6", color: "#ffffff" }    # background のみ上書き
```

### 11.3 継承チェーン

多段継承が可能。A extends B extends C の場合、C → B → A の順にマージされる。循環継承は Theme Engine が検出し、エラーとする。


## 12. Pack がテーマを提供する方法

Pack がテーマを提供する場合、Pack のインストール時にテーマファイルが `user_data/themes/installed/` にコピーされる。

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

インストールフロー: Pack 承認 → `themes/monokai.theme.yaml` を `user_data/themes/installed/monokai.theme.yaml` にコピー → ユーザーが `config.json` の `theme_id` を `monokai` に変更すれば適用される。

defaults 側の変更はゼロ。


## 13. フォールバック

### 13.1 テーマファイルが見つからない場合

`config.json` の `theme_id` に対応するテーマファイルが存在しない場合、Theme Engine はハードコードされた最小限のフォールバックテーマを使用する。フォールバックテーマは shell.html に埋め込まれた以下の値のみを持つ。

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

これは人間が最低限操作可能な画面を提供するためのものである。

### 13.2 テーマファイルが壊れている場合

YAML パースに失敗した場合、フォールバックテーマを使用し、statusbar にエラーを表示する。

### 13.3 未定義のトークンが参照された場合

Asset が `var(--color-nonexistent)` を参照した場合、CSS の仕様に従い `initial` 値が使われる。Theme Engine は未定義のトークン参照を検出してコンソールに警告を出す。

### 13.4 Widget スタイルが未定義の場合

テーマが特定の Widget 型のスタイルを定義していない場合、Theme Engine はその Widget をブラウザのデフォルトスタイルで描画する。


## 14. テーマファイルのバリデーション

Theme Engine は読み込み時に以下を検証する。

必須フィールド: `theme_id`, `name`, `version`。必須トークン: `color.background`, `color.surface`, `color.text`, `color.border`, `color.primary`, `typography.font_family`, `typography.font_family_mono`, `typography.font_size_base`, `spacing.md`, `radius.md`。循環参照: トークン間の `{category.key}` 参照に循環がないか。循環継承: `extends` チェーンに循環がないか。

必須フィールドまたは必須トークンが欠けている場合、フォールバックテーマから欠けている値だけを補完し、警告を出す。テーマ全体を拒否するのではなく、可能な限り動作させる。
```