<!-- docs-i18n-links:start -->
[EN](../../theme.md) | [JP](../ja/theme.md) | [KR](./theme.md) | [CN](../zh-cn/theme.md)
<!-- docs-i18n-links:end -->

# theme.md — Rumi AI OS 테마 사양

## 1. 개요

테마는 UI의 모양을 정의하는 선언적 파일입니다. 각 위젯의 색상, 글꼴, 간격, 애니메이션, 그리기 스타일을 하나의 YAML 파일로 결합하고 전체 프런트엔드에 적용합니다.

기본값은 테마에 대한 ``format specification'' and ``실행 메커니즘''을 제공합니다. 모든 특정 테마 파일(색 구성표 및 글꼴 사양)은 user_data에 저장됩니다. 테마는 백엔드에 영향을 미치지 않습니다. 위젯 JSON 생성, 핸들러 실행 및 Flow 처리는 테마의 존재를 알지 못합니다. 테마가 변경되더라도 Asset HTML/JS 코드는 변경할 필요가 없습니다. 이는 CSS 변수만 참조하기 때문입니다.


## 2. 디자인 철학

**선언적**: 테마는 코드가 아닙니다. YAML에 값을 작성하면 됩니다. 실행 논리가 포함되어 있지 않습니다.

**토큰 기반**: 테마는 색상 및 크기 값을 직접 작성하는 것이 아니라 명명된 토큰(`color.primary`, `spacing.md` 등)으로 정의됩니다. 자산은 토큰 이름을 조회하고 테마는 실제 값을 결정합니다.

**백엔드 독립적**: 테마는 프런트엔드 레이어(shell.html의 테마 엔진)에서만 읽습니다. 백엔드 핸들러, 도구 및 흐름은 테마의 존재를 인식하지 못합니다. Emit_widget이 전송한 Widget JSON은 테마 독립적인 데이터이며, 테마 엔진은 렌더링 시 모양을 적용합니다.

**완전히 교체 가능**: 초기 설정 시 기본적으로 배치된 기본 테마는 사용자나 팩이 자유롭게 덮어쓰거나 교체할 수 있습니다.

**상속 가능**: 테마는 `extends`을 사용하여 다른 테마를 상속하고 차이점만 정의할 수 있습니다.


## 3. 디렉토리 구조

```
user_data/themes/
├── dark.theme.yaml              # デフォルトのダークテーマ
├── light.theme.yaml             # デフォルトのライトテーマ
└── installed/                   # Pack がインストールしたテーマ
    ├── monokai.theme.yaml
    └── nord.theme.yaml
```

`user_data/config.json`의 `theme_id`를 사용하여 테마를 전환할 수 있습니다.

```json
{
  "theme_id": "dark"
}
```

`theme_id`는 theme.yaml의 `theme_id` 필드와 일치합니다.


## 4. theme.yaml 전체 사양

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


## 5. 토큰 시스템

### 5.1 토큰 참조 구문

테마 내에서 토큰을 상호 참조하려면 `{category.key}` 구문을 사용하세요.

```yaml
border_focus: "1px solid {color.primary}"    # color.primary の値に展開される
padding: "{spacing.md}"                       # spacing.md の値に展開される
```

참조는 테마 파일 내에서만 유효합니다. 순환 참조는 금지됩니다. 테마 엔진은 로드 시 이를 감지하고 오류를 발생시킵니다.

### 5.2 토큰 카테고리

**색상** — 색상 값입니다. CSS 색상 표현(hex, rgba, hsl)을 사용하여 설명합니다. 시맨틱 이름(`primary`, `success`, `error` 등)으로 정의하고 특정 색상 코드를 할당합니다.

**타이포그래피** — 글꼴 관련 값입니다. `font_family`은 CSS 글꼴 계열 문자열입니다. `font_size_*`은 px 단위의 정수입니다. `font_weight_*`는 CSS 글꼴 두께 값입니다. `line_height_*`은 단위 없는 비율입니다.

**spacing** — 여백 또는 간격 값입니다. px 단위의 정수입니다. 이름은 xs, sm, md, lg, xl, 2xl과 같은 상대적 크기입니다.

**반경** — 코너 반경 값입니다. px 단위의 정수입니다. `full`은 9999px의 알약 유형을 나타냅니다.

**shadow** — 상자 그림자 값입니다. CSS 상자 그림자 문자열.

**전환** — 전환 값. CSS 전환 속기 문자열입니다.

**z_index** — 스택 순서 값입니다. 정수.


## 6. 애니메이션 정의

### 6.1 구조

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

`keyframes`에서는 CSS @keyframes 규칙을 있는 그대로 설명합니다. `duration`은 CSS 애니메이션 기간입니다. `timing`는 애니메이션 타이밍 기능입니다. `iteration`은 애니메이션 반복 횟수입니다.

### 6.2 위젯의 참조

위젯의 `style_hint.animation` 또는 위젯 스타일 정의의 `animation` 필드에 애니메이션 이름을 지정합니다.

```json
{
  "type": "indicator",
  "label": "Thinking...",
  "state": "running",
  "animation": "wave_dots"
}
```

테마 엔진은 `animations.wave_dots`을 참조하여 CSS 애니메이션을 적용합니다. 위젯 JSON에 애니메이션 이름이 지정되지 않은 경우 위젯 스타일 정의(예: `indicator.states.running.animation`)의 기본 애니메이션이 사용됩니다.

### 6.3 맞춤 애니메이션

테마 파일의 `animations` 섹션에 새 애니메이션을 추가하기만 하면 새 애니메이션을 정의할 수 있습니다. Asset JS가 애니메이션 이름을 참조하는 경우 적용됩니다. 기본 측면에서는 변경이 필요하지 않습니다.


## 7. 위젯 스타일 정의

### 7.1 구조

위젯 유형 이름을 키로 사용하여 `widgets` 섹션에서 스타일을 정의합니다.

```yaml
widgets:
  code_block:
    syntax_theme: "one-dark-pro"
    background: "#1e1e1e"
    font_family: "{typography.font_family_mono}"
    ...
```

위젯 유형 이름은 widget.md에 정의된 모든 위젯 유형(텍스트, code_block, diff, 이미지, 스크린샷, 진행률, 터미널, 테이블, 차트, file_tree, markdown, 오디오, 비디오, 지도, 입력, 버튼, 선택, 토글, 슬라이더, 체크박스, 컨테이너, 행, 열, 탭, 축소 가능, 카드, 스트림, 표시기, 사용자 정의)에 해당합니다.

### 7.2 변형

일부 위젯(버튼, 카드 등)에는 `variants`이 있습니다. 위젯 JSON의 `style_hint.variant`에서 사용할 변형을 지정합니다.

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

`style_hint.variant`가 지정되지 않았거나 알 수 없는 값인 경우 `default` 변형이 사용됩니다.

### 7.3 상태(표시기만 해당)

표시기 위젯의 상태는 `state` 필드에 있습니다. 테마는 각 상태에 대한 색상과 애니메이션을 정의합니다.

```yaml
indicator:
  states:
    running: { color: "{color.primary}", animation: "pulse" }
    success: { color: "{color.success}", animation: "fade_in" }
    error: { color: "{color.error}", animation: "fade_in" }
    waiting: { color: "{color.warning}", animation: "wave_dots" }
```

### 7.4 스타일_힌트

위젯 JSON의 `style_hint` 필드는 테마에 대한 힌트입니다. 테마는 이 힌트를 해석할 수도 있고 해석하지 않을 수도 있습니다. 변형 이외의 모든 키가 포함될 수 있습니다.

```json
{
  "type": "text",
  "text": "Warning message",
  "style_hint": {"color": "warning", "size": "sm", "weight": "bold"}
}
```

테마는 테마 엔진이 `style_hint`을 CSS로 변환하는 방법을 정의합니다. 기본 테마 엔진은 기본적으로 다음 힌트 키를 인식합니다.

| 힌트 키 | 설명 | CSS로 변환 |
|---|---|---|
| §루미§0§ | 위젯 변형 선택 | 변형 스타일 적용 |
| §루미§0§ | 토큰 이름별 색상 지정 | §루미§1§ |
| §루미§0§ | xs/sm/md/lg/xl 크기 | §루미§1§ |
| §루미§0§ | 글꼴 두께 | §루미§1§ |
| §루미§0§ | 텍스트 정렬 | §루미§1§ |
| §루미§0§ | 토큰 이름으로 패딩 | §루미§1§ |
| §루미§0§ | 숨기기 | §루미§1§ |

테마에 자체 힌트 키를 추가하는 것도 가능합니다. 테마 엔진에서 인식되지 않는 키는 무시됩니다.

### 7.5 사용자 정의 위젯 스타일

Custom Widget의 `custom_type`을 키로 사용하여 `widgets.custom` 섹션에서 스타일을 정의합니다.

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

Custom Widget의 렌더러(`user_data/widget_renderers/`에 배치된 JS)는 이 스타일을 읽고 적용합니다.


## 8. 슬롯 스타일

`slots` 섹션은 shell.html 슬롯(헤더, 사이드바, 메인, 패널, 상태 표시줄, 플로팅)의 모양을 정의합니다.

슬롯의 구조와 레이아웃(애셋이 어느 슬롯에 들어가는지)은 테마의 책임이 아닙니다. 테마는 슬롯의 배경색, 테두리, 기본 크기 및 크기 조정 핸들 색상만 정의합니다.


## 9. CSS 변수로 변환

### 9.1 변환 규칙

테마 엔진은 테마 파일을 CSS 변수로 변환하고 이를 `:root`로 설정합니다. 변환 규칙은 다음과 같습니다.

토큰: `tokens.{category}.{key}` → `--{category}-{key}`

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

숫자 토큰(간격, 반경, 글꼴 크기_*, 그림자 제외)에는 자동으로 `px`이 제공됩니다. 문자열 토큰은 있는 그대로 출력됩니다.

### 9.2 애니메이션 삽입

`animations` 섹션의 모든 키프레임을 `<style>` 요소로 삽입합니다.

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

### 9.3 위젯 스타일 삽입

위젯 스타일은 CSS 변수로 삽입되지 않습니다. 테마 엔진은 위젯을 그릴 때 스타일 정의를 직접 참조합니다. 그 이유는 위젯 스타일의 구조가 유형마다 다르기 때문에 플랫 CSS 변수를 사용하여 표현할 수 없기 때문입니다.

### 9.4 자산 참조

자산의 HTML/JS는 CSS 변수를 참조합니다.

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

테마를 전환하면 CSS 변수의 값이 변경되고 자산의 모양이 자동으로 업데이트됩니다. 자산 측에서는 코드 변경이 필요하지 않습니다.


## 10. 테마 적용 메커니즘

### 10.1 시작 시

1. shell.html의 테마 엔진은 `user_data/config.json`부터 `theme_id`까지 읽습니다.
2. `user_data/themes/{theme_id}.theme.yaml` 로드
3. `extends`이 지정된 경우 상위 테마를 재귀적으로 로드합니다.
4. 토큰 참조 확장(`{category.key}`)
5. CSS 변수를 `:root`으로 설정합니다.
6. 애니메이션 키프레임 삽입
7. 위젯 스타일 정의를 메모리에 유지

### 10.2 테마 전환

프런트 엔드는 테마 전환 이벤트를 수신합니다.

```json
{
  "type": "theme.change",
  "data": {
    "theme_id": "light"
  }
}
```

테마 엔진은 새 테마 파일을 로드하고 CSS 변수를 덮어쓴 다음 애니메이션을 다시 삽입합니다. 모든 자산은 실시간으로 새로운 테마처럼 보이도록 변경됩니다.

테마를 변경하려면 `user_data/config.json`의 `theme_id`를 백엔드의 `config.write` 권한으로 다시 작성하고 `emit_event("theme.change", {"theme_id": "..."})`로 프런트엔드에 알립니다.


## 11. 테마 상속

### 11.1 확장

테마는 `extends` 필드에서 다른 테마를 상속받을 수 있습니다.

```yaml
theme_id: "dark_blue"
extends: "dark"
tokens:
  color:
    primary: "#3b82f6"
    primary_hover: "#60a5fa"
```

이 경우 `dark` 테마의 모든 값이 기본이 되며, `dark_blue`에 명시적으로 정의된 값만 덮어쓰게 됩니다. `dark`, `color.background`, `typography.*`, `spacing.*` 등은 모두 상속됩니다.

### 11.2 병합 규칙

병합은 깊은 수준까지 재귀적으로 수행됩니다.

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

결과:

```yaml
widgets:
  button:
    variants:
      default: { background: "#1a1a1a", color: "#e5e5e5" }   # 親から継承
      primary: { background: "#3b82f6", color: "#ffffff" }    # background のみ上書き
```

### 11.3 상속 체인

다단계 상속이 가능합니다. A가 B를 확장하면 C를 확장하면 C → B → A의 순서로 병합됩니다. 순환 상속은 테마 엔진에서 감지되어 오류로 처리됩니다.


## 12. 팩이 테마를 제공하는 방법

팩이 테마를 제공하는 경우 팩 설치 시 테마 파일이 `user_data/themes/installed/`에 복사됩니다.

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

설치 흐름 : 팩 승인 → `themes/monokai.theme.yaml`을 `user_data/themes/installed/monokai.theme.yaml`로 복사 → 사용자가 `config.json`의 `theme_id`를 `monokai`로 변경하면 적용됩니다.

기본 측면에는 변경 사항이 없습니다.


## 13. 폴백

### 13.1 테마 파일을 찾을 수 없는 경우

`config.json`의 `theme_id`에 해당하는 테마 파일이 존재하지 않는 경우 테마 엔진은 하드 코딩된 최소 대체 테마를 사용합니다. fallback 테마에는 shell.html에 다음 값만 내장되어 있습니다.

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

최소한 사람이 조작할 수 있는 화면을 제공하기 위함이다.

### 13.2 테마 파일이 손상된 경우

YAML 구문 분석이 실패하면 대체 테마를 사용하고 상태 표시줄에 오류를 표시합니다.

### 13.3 정의되지 않은 토큰을 참조하는 경우

자산이 `var(--color-nonexistent)`을 참조하는 경우 CSS 사양에 따라 `initial` 값이 사용됩니다. 테마 엔진은 정의되지 않은 토큰 참조를 감지하고 콘솔에 경고를 표시합니다.

### 13.4 위젯 스타일이 정의되지 않은 경우

테마가 특정 위젯 유형에 대한 스타일을 정의하지 않는 경우 테마 엔진은 브라우저의 기본 스타일을 사용하여 위젯을 렌더링합니다.


## 14. 테마 파일 유효성 검사

테마 엔진은 로드 시 다음을 확인합니다.

필수 항목: `theme_id`, `name`, `version`. 필수 토큰: `color.background`, `color.surface`, `color.text`, `color.border`, `color.primary`, `typography.font_family`, `typography.font_family_mono`, `typography.font_size_base`, `spacing.md`, `radius.md`. 순환 참조: `{category.key}` 참조에 토큰 간 순환이 있습니까? 순환 상속: `extends` 체인에 순환이 있습니까?

필수 필드 또는 토큰이 누락된 경우 대체 테마는 누락된 값만 완료하고 경고를 발행합니다. 테마를 완전히 거부하는 대신 가능한 한 잘 작동하도록 만드세요.
