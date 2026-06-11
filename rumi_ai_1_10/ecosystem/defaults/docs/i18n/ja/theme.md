<!-- docs-i18n-links:start -->
[EN](../../theme.md) | [JP](./theme.md) | [KR](../ko/theme.md) | [CN](../zh-cn/theme.md)
<!-- docs-i18n-links:end -->

# theme.md — Rumi AI OS テーマの仕様

## 1. 概要

テーマは、UI の外観を定義する宣言ファイルです。各ウィジェットの色、フォント、間隔、アニメーション、描画スタイルを単一の YAML ファイルに結合し、フロントエンド全体に適用します。

デフォルトでは、テーマに対して「`format specification'' and `「強制メカニズム」が提供されます。すべての特定のテーマ ファイル (配色とフォント仕様) は user_data に配置されます。テーマはバックエンドには影響しません。ウィジェットの JSON 生成、ハンドラーの実行、およびフロー処理はテーマの存在を認識しません。テーマが変わってもアセットのHTML/JSコードを変更する必要はありません。これは、CSS 変数のみを参照するためです。


## 2. 設計哲学

**宣言的**: テーマはコードではありません。 YAML に値を記述するだけです。実行ロジックは含まれません。**トークンベース**: テーマは、色とサイズの値を直接記述するのではなく、名前付きトークン (`color.primary`、`spacing.md` など) として定義されます。アセットはトークン名を検索し、テーマは実際の値を解決します。**バックエンドに依存しない**: テーマはフロントエンド層 (shell.html のテーマ エンジン) によってのみ読み取られます。バックエンド ハンドラー、ツール、フローはテーマの存在を認識しません。 Emit_widget によって送信されるウィジェット JSON はテーマに依存しないデータであり、テーマ エンジンはレンダリング時にその外観を適用します。**完全に置き換え可能**: 初期セットアップ中にデフォルトで配置されたデフォルトのテーマは、ユーザーまたはパックによって自由に上書きまたは置き換えることができます。**継承可能**: テーマは `extends` で別のテーマを継承し、相違点のみを定義できます。


## 3. ディレクトリ構造

```
user_data/themes/
├── dark.theme.yaml              # デフォルトのダークテーマ
├── light.theme.yaml             # デフォルトのライトテーマ
└── installed/                   # Pack がインストールしたテーマ
    ├── monokai.theme.yaml
    └── nord.theme.yaml
```

`user_data/config.json`の`theme_id`でテーマを切り替えることができます。

```json
{
  "theme_id": "dark"
}
```

`theme_id` は、theme.yaml の `theme_id` フィールドと一致します。


## 4. テーマ.yaml の完全な仕様

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


## 5. トークンシステム

### 5.1 トークン参照構文

テーマ内のトークンを相互参照するには、`{category.key}` 構文を使用します。

```yaml
border_focus: "1px solid {color.primary}"    # color.primary の値に展開される
padding: "{spacing.md}"                       # spacing.md の値に展開される
```

参照はテーマ ファイル内でのみ有効です。循環参照は禁止されています。テーマ エンジンは読み込み時にこれを検出し、エラーを発行します。

### 5.2 トークンのカテゴリ

**color** — 色の値。 CSSの色表現(hex、rgba、hsl)を用いて記述します。セマンティック名 (`primary`、`success`、`error` など) で定義し、特定のカラー コードを割り当てます。**typography** — フォント関連の値。 `font_family` は CSS フォントファミリー文字列です。 `font_size_*` は px 単位の整数です。 `font_weight_*` は CSS のフォントウェイト値です。 `line_height_*` は単位のない比率です。

**spacing** — マージンまたはギャップの値。ピクセル単位の整数。名前は相対的なサイズです: xs、sm、md、lg、xl、2xl。**radius** — コーナー半径値。ピクセル単位の整数。 `full` は、9999px.**shadow** — ボックス シャドウ値を持つ錠剤の種類を表します。 CSS box-shadow string.**transition** — トランジション値。 CSS トランジションの短縮表現 string.**z_index** — スタック順序の値。整数。


## 6. アニメーションの定義

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

`keyframes` では、CSS の @keyframes ルールをそのまま記述します。 `duration` は CSS アニメーションの継続時間です。 `timing`はアニメーションタイミング関数です。 `iteration` はアニメーションの反復回数です。

### 6.2 ウィジェットからの参照

アニメーション名は、ウィジェットの `style_hint.animation` またはウィジェット スタイル定義の `animation` フィールドで指定します。

```json
{
  "type": "indicator",
  "label": "Thinking...",
  "state": "running",
  "animation": "wave_dots"
}
```

テーマエンジンは`animations.wave_dots`を参照してCSSアニメーションを適用します。ウィジェット JSON でアニメーション名が指定されていない場合は、ウィジェット スタイル定義のデフォルトのアニメーション (例: `indicator.states.running.animation`) が使用されます。

### 6.3 カスタムアニメーション

新しいアニメーションをテーマ ファイルの `animations` セクションに追加するだけで定義できます。アセット JS がアニメーション名を参照する場合に適用されます。デフォルト側では変更は必要ありません。


## 7. ウィジェットのスタイル定義

### 7.1 構造

ウィジェット タイプ名をキーとして使用して、`widgets` セクションでスタイルを定義します。

```yaml
widgets:
  code_block:
    syntax_theme: "one-dark-pro"
    background: "#1e1e1e"
    font_family: "{typography.font_family_mono}"
    ...
```

ウィジェット タイプ名は、widget.md で定義されているすべてのウィジェット タイプ (テキスト、コード ブロック、差分、画像、スクリーンショット、進行状況、ターミナル、テーブル、チャート、ファイル ツリー、マークダウン、オーディオ、ビデオ、マップ、入力、ボタン、選択、トグル、スライダー、チェックボックス、コンテナ、行、列、タブ、折りたたみ可能、カード、ストリーム、インジケーター、カスタム) に対応します。

### 7.2 バリアント

一部のウィジェット (ボタン、カードなど) には `variants` があります。 Widget JSON の `style_hint.variant` でどのバリアントを使用するかを指定します。

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

`style_hint.variant` が未指定または不明な値の場合、`default` バリアントが使用されます。

### 7.3 状態 (インジケーターのみ)

インジケーター ウィジェットの `state` フィールドには状態があります。テーマは、各状態の色とアニメーションを定義します。

```yaml
indicator:
  states:
    running: { color: "{color.primary}", animation: "pulse" }
    success: { color: "{color.success}", animation: "fade_in" }
    error: { color: "{color.error}", animation: "fade_in" }
    waiting: { color: "{color.warning}", animation: "wave_dots" }
```

### 7.4 スタイルヒント

ウィジェット JSON の `style_hint` フィールドはテーマへのヒントです。テーマはこのヒントを解釈する場合もあれば、解釈しない場合もあります。バリアント以外のキーを含めることができます。

```json
{
  "type": "text",
  "text": "Warning message",
  "style_hint": {"color": "warning", "size": "sm", "weight": "bold"}
}
```

テーマは、テーマ エンジンが `style_hint` を CSS に変換する方法を定義します。デフォルトのテーマ エンジンは、デフォルトで次のヒント キーを認識します。

| Hint key | Description | Conversion to CSS |
|---|---|---|
| `variant` | Select Widget variant | Apply variant style |
| `color` | Color specification by token name | `color: var(--color-{value})` |
| `size` | Size of xs/sm/md/lg/xl | `font-size: var(--font-size-{value})` |
| `weight` | Font weight | `font-weight: var(--font-weight-{value})` |
| `align` | Text alignment | `text-align: {value}` |
| `padding` | Padding with token name | `padding: var(--spacing-{value})` |
| `hidden` | Hide | `display: none` |

テーマに独自のヒント キーを追加することもできます。テーマ エンジンによって認識されないキーは無視されます。

### 7.5 カスタムウィジェットスタイル

Custom Widget の `custom_type` をキーとして使用して、`widgets.custom` セクションでスタイルを定義します。

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

カスタム ウィジェットのレンダラ (`user_data/widget_renderers/` に配置された JS) は、このスタイルを読み取り、適用します。


## 8. スロットのスタイル

`slots` セクションでは、shell.html スロット (ヘッダー、サイドバー、メイン、パネル、ステータスバー、フローティング) の外観を定義します。

スロットの構造とレイアウト (どのアセットがどのスロットに入るのか) はテーマの責任ではありません。テーマは、スロットの背景色、境界線、デフォルト サイズ、およびサイズ変更ハンドルの色のみを定義します。


## 9. CSS変数に変換

### 9.1 変換ルール

テーマ エンジンはテーマ ファイルを CSS 変数に変換し、`:root` に設定します。変換ルールは以下の通りです。

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

数値トークン (間隔、半径、font_size_*、影を除く) には、自動的に `px` が与えられます。文字列トークンがそのまま出力されます。

### 9.2 アニメーションの挿入

`animations` セクションのすべてのキーフレームを `<style>` 要素として挿入します。

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

### 9.3 ウィジェットスタイルの挿入

ウィジェット スタイルは CSS 変数として挿入されません。テーマ エンジンは、ウィジェットを描画するときにスタイル定義を直接参照します。その理由は、ウィジェット スタイルの構造がタイプごとに異なり、フラットな CSS 変数を使用して表現できないためです。

### 9.4 アセットからの参照

アセットの HTML/JS は CSS 変数を参照します。

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

テーマを切り替えると、CSS 変数の値が変更され、アセットの外観が自動的に更新されます。アセット側でコードを変更する必要はありません。


## 10. テーマ適用の仕組み

### 10.1 起動時

1.shell.html のテーマ エンジンは `user_data/config.json` から `theme_id` を読み取ります。
2. ロード`user_data/themes/{theme_id}.theme.yaml`
3. `extends` が指定されている場合、親テーマを再帰的に読み込みます
4. トークン参照を展開します (`{category.key}`)
5. CSS 変数を `:root` に設定します。
6. アニメーションキーフレームを挿入する
7. ウィジェットのスタイル定義をメモリに保存する

### 10.2 テーマの切り替え

フロントエンドはテーマ切り替えイベントを受け取ります。

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "light"
  }
}
```

テーマ エンジンは新しいテーマ ファイルをロードし、CSS 変数を上書きし、アニメーションを再挿入します。すべてのアセットがリアルタイムで新しいテーマのように変更されます。

テーマを変更するには、`user_data/config.json`の`theme_id`をバックエンドの`config.write`権限で書き換え、`emit_event("theme.change", {"theme_id": "..."})`でフロントエンドに通知します。


## 11. テーマの継承

### 11.1 を拡張します

テーマは、`extends` フィールド内の別のテーマを継承できます。

```yaml
theme_id: "dark_blue"
extends: "dark"
tokens:
  color:
    primary: "#3b82f6"
    primary_hover: "#60a5fa"
```

この場合、`dark` テーマ内のすべての値がベースとなり、`dark_blue` で明示的に定義された値のみが上書きされます。 `dark`、`color.background`、`typography.*`、`spacing.*`などはすべて継承されます。

### 11.2 マージルール

マージは深いレベルまで再帰的に行われます。

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

複数レベルの継承が可能です。 A が B を拡張する場合、C を拡張すると、C → B → A の順序でマージされます。循環継承はテーマ エンジンによって検出され、エラーとして処理されます。


## 12. パックがテーマを提供する方法

パックがテーマを提供する場合、パックのインストール時にテーマ ファイルが `user_data/themes/installed/` にコピーされます。

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

インストールの流れ：パック承認→`themes/monokai.theme.yaml`を`user_data/themes/installed/monokai.theme.yaml`にコピー→ユーザーが`config.json`の`theme_id`を`monokai`に変更すると適用されます。

デフォルト側には変更はありません。


## 13. フォールバック

### 13.1 テーマファイルが見つからない場合

`config.json` の `theme_id` に対応するテーマ ファイルが存在しない場合、テーマ エンジンはハードコーディングされた最小限のフォールバック テーマを使用します。フォールバック テーマには、shell.html に次の値が埋め込まれているだけです。

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

最低限人間が操作できる画面を提供するためです。

### 13.2 テーマファイルが破損している場合

YAML 解析が失敗した場合は、フォールバック テーマを使用し、ステータスバーにエラーを表示します。

### 13.3 未定義のトークンが参照された場合

Asset が `var(--color-nonexistent)` を参照する場合、CSS 仕様に従って `initial` 値が使用されます。テーマ エンジンは未定義のトークン参照を検出し、コンソールに警告を発行します。

### 13.4 ウィジェットのスタイルが未定義の場合

テーマで特定のウィジェット タイプのスタイルが定義されていない場合、テーマ エンジンはブラウザのデフォルト スタイルを使用してウィジェットをレンダリングします。


## 14. テーマファイルの検証

テーマ エンジンはロード時に以下を検証します。

必須フィールド: `theme_id`、`name`、`version`。必要なトークン: `color.background`、`color.surface`、`color.text`、`color.border`、`color.primary`、`typography.font_family`、`typography.font_family_mono`、`typography.font_size_base`、`spacing.md`、`radius.md`。循環参照: トークン間の `{category.key}` 参照に循環はありますか?循環継承: `extends` チェーン内に循環はありますか?

必須フィールドまたはトークンが欠落している場合、フォールバック テーマは欠落している値のみを補完し、警告を発行します。テーマを完全に拒否するのではなく、可能な限り機能するようにします。
