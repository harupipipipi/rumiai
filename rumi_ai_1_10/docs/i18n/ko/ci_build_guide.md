<!-- docs-i18n-links:start -->
[EN](../../ci_build_guide.md) | [JP](../ja/ci_build_guide.md) | [KR](./ci_build_guide.md) | [CN](../zh-cn/ci_build_guide.md)
<!-- docs-i18n-links:end -->

# CI/CD 구축 가이드 — rumi_viewer 데스크톱 앱

최종 업데이트 날짜: 2026-03-29

rumi_viewer(Tauri v2 데스크톱 앱)에 대한 CI 빌드 및 릴리스 절차와 과거 실패 기록을 요약한 문서입니다.

---

## 1. 개요

GitHub Actions의 `release.yml`은 태그 푸시를 트리거하여 4개 플랫폼에서 동시 빌드를 수행하고 해당 아티팩트를 GitHub 릴리스에 초안으로 업로드합니다.

| 플랫폼 | 러너 | 대상 | 유물 |
|-----------------|---------|-----------|--------|
| 맥OS ARM | macos 최신 | aarch64-애플-다윈 | .dmg |
| macOS 인텔 | macos-15-인텔 | x86_64-애플-다윈 | .dmg |
| 윈도우 | Windows 최신 | x86_64-pc-windows-msvc | .exe(NSIS) |
| 리눅스 | 우분투 최신 | x86_64-알 수 없는-리눅스-gnu | .deb, .AppImage |

---

## 2. 출시 절차

### 2.1 정규 출시

```bash
# 1. バージョンを更新（tauri.conf.json と Cargo.toml の version）
#    tauri.conf.json: "version": "0.2.0"
#    Cargo.toml:      version = "0.2.0"

# 2. コミット
git add rumi_viewer/src-tauri/tauri.conf.json rumi_viewer/src-tauri/Cargo.toml
git commit -m "release: v0.2.0"

# 3. tag push（これが CI トリガー）
git tag v0.2.0
git push origin master
git push origin v0.2.0

# 4. GitHub Actions が自動で 4 プラットフォームビルド
#    → GitHub Releases に draft release が作られる

# 5. GitHub の Releases ページで draft を確認 → 公開
```

### 2.2 테스트 릴리즈 (CI 동작 확인용)

```bash
# test tag はインクリメントする（v0.1.0-test.1, .2, .3, ...）
# 既存の test tag を確認
git tag -l "v0.1.0-test*"

# 次の番号で tag push
git tag v0.1.0-test.4
git push origin v0.1.0-test.4

# CI の結果を確認
# https://github.com/harupipipipi/rumiai/actions
```

### 2.3 CI 결과 확인 방법

```bash
# ブラウザで確認
# https://github.com/harupipipipi/rumiai/actions

# API で確認（ログイン不要）
curl -s https://api.github.com/repos/harupipipipi/rumiai/actions/runs?per_page=3 \
  | python3 -c "
import json, sys
runs = json.load(sys.stdin)['workflow_runs']
for r in runs:
    print(f\"{r['head_branch']:20s} {r['status']:12s} {r['conclusion'] or '':10s} {r['created_at']}\")
"

# ジョブ単位の確認
curl -s https://api.github.com/repos/harupipipipi/rumiai/actions/runs/<RUN_ID>/jobs \
  | python3 -c "
import json, sys
jobs = json.load(sys.stdin)['jobs']
for j in jobs:
    print(f\"{j['name']:50s} {j['status']:12s} {j['conclusion'] or '':10s}\")
"
```

---

## 3. release.yml의 구조

```
.github/workflows/release.yml
```

- **트리거**: `push.tags: ["v*"]` — `v`로 시작하는 태그 푸시
- **매트릭스**: 4개 OS x 타겟 조합
- **주요 단계**:
  1. 결제
  2. Python / Rust / Node 설정
  3. 패널 프런트엔드 및 defaultspack 프런트엔드 구축
  4. 대상 플랫폼을 위한 `pack-shell` 빌드
  5. `rumi_ai_1_10`에서 `rumi_viewer/src-tauri/gen/app`를 준비합니다.
  6. 빌드(`cargo tauri build --target $target`)
  7. 릴리스 아티팩트 업로드(`softprops/action-gh-release`)

`rumi_viewer/src-tauri/gen/app`은 Git에서 관리되지 않습니다. CI에서는
`.github/scripts/prepare_tauri_resources.py`은 런타임 도구 및 Tauri를 스테이지합니다.
`build.rs`도 동일한 제외 규칙을 사용하여 `gen/app`을 재생성합니다. 세대 대상
`app.py`, `core_runtime/`, `ecosystem/defaultspack/`, 내장 패널/기본 팩 UI,
`bundled/uv`, `bundled/pack-shell`가 포함되어 있습니다. §루미§2§, §루미§3§,
`user_data`, `__pycache__`, `.rumi_snapshots`, `tests/`는 배포 대상에서 제외됩니다.

PR에서 배포를 확인하려면 수동으로 실행할 수도 있습니다.
`.github/workflows/desktop-installers.yml`를 사용하세요. 윈도우 NSIS, macOS DMG, 리눅스
DEB/AppImage를 작업 아티팩트로 업로드합니다. 일반적인 출력 대상은 다음과 같습니다.

- 윈도우즈: `rumi_viewer/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*.exe`
- macOS: `rumi_viewer/src-tauri/target/{target}/release/bundle/dmg/*.dmg`
- 리눅스: `rumi_viewer/src-tauri/target/x86_64-unknown-linux-gnu/release/bundle/{deb,appimage}/`

### 러너 선정 시 주의사항

GitHub Actions 실행기는 주기적으로 중단됩니다. 사용되지 않는 실행기를 지정하면 작업이 대기열에 남아 실패하게 됩니다.

| 쓸모없는 러너 | 단종 날짜 | 교체 |
|-------------------|--------|------|
| macos-12 | 2024년 후반 | macos-13 → macos-15 |
| macos-13 | 2025-12 | macos-15-인텔 |

**확인 방법**: https://github.com/actions/runner-images. 참조

---

## 4. 아이콘 파일 관리

### 4.1 필수 파일

Tauri v2를 빌드하려면 다음 아이콘 파일이 필요합니다.

```
rumi_viewer/src-tauri/icons/
├── 32x32.png         — 32×32 RGBA PNG
├── 128x128.png       — 128×128 RGBA PNG
├── 128x128@2x.png    — 256×256 RGBA PNG（Retina 用）
├── icon.png          — 512×512 RGBA PNG（アプリアイコン元画像）
├── icon.ico          — Windows 用 ICO（16/32/48/256 サイズ埋め込み）
└── icon.icns         — macOS 用 ICNS（128/256/512 サイズ埋め込み）
```

### 4.2 준수해야 할 사항

- **PNG는 RGBA(color_type=6)여야 합니다**. RGB(color_type=2)를 사용할 때 컴파일 타임에 Tauri의 `generate_context!()` 매크로 패닉이 발생합니다.
- **PNG는 정사각형(너비 == 높이)이어야 합니다**. 정사각형이 아닌 경우 AppImage를 번들링할 때 tauri-bundler가 패닉을 일으킵니다.
- **icon.ico가 필요합니다**. Windows에서 `build.rs`가 존재하지 않는 경우 컴파일 오류 발생
- **tauri.conf.json의 Bundle.icon에 경로를 열거합니다**. 설정하지 않을 경우 기본 경로를 검색하며, 찾을 수 없으면 오류가 발생합니다.

### 4.3 현재 아이콘

자리 표시자(R=100, G=100, B=200인 파란색 단색 사각형). 공식 아이콘이 결정되면 교체됩니다.

### 4.4 아이콘 교체 절차

공식 아이콘을 준비한 후:

```bash
# 方法 1: cargo tauri icon コマンド（Tauri CLI がインストール済みの場合）
# 1024x1024 以上の正方形 RGBA PNG を用意
cargo tauri icon path/to/new_icon.png

# 方法 2: 手動で各サイズを生成
# 画像編集ソフトで 32x32, 128x128, 256x256, 512x512 の RGBA PNG を書き出し
# ICO と ICNS は専用ツールで生成

# 差し替え後は必ず test tag で CI 確認
git add rumi_viewer/src-tauri/icons/
git commit -m "chore: update app icons"
git push origin master
git tag v0.x.y-test.1
git push origin v0.x.y-test.1
```

### 4.5 tauri.conf.json의 Bundle.icon 설정

```json
{
  "bundle": {
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  }
}
```

icon.png는 Bundle.icon(trayIcon.iconPath에서 사용됨)에 포함될 필요가 없습니다.

---

## 5. 업데이트 메커니즘

### 5.1 현재 상태: 구현되지 않음

2026년 3월 29일 기준으로 앱의 자동 업데이트 메커니즘은 **구현되지 않습니다**.

- `tauri-plugin-updater`은 Cargo.toml에 포함되지 않습니다.
- `tauri.conf.json` ~ `plugins.updater`에는 섹션이 없습니다.
- `capabilities/default.json`에 대한 업데이트 권한이 없습니다.

업데이트하려면 사용자가 GitHub 릴리스에서 새 바이너리를 수동으로 다운로드하고 다시 설치해야 합니다.

### 5.2 향후 계획: U단계

roadmap.md 업데이트 계획에 구현 예정:

- **U-1**: 버전 관리(현재 버전 가져오기, 최신 버전 가져오기)
- **U-2**: 업데이트 확인 API(Cloudflare Workers 또는 R2)
- **U-3**: Rust 런처 자체 업데이트
- **U-4**: 커널(Python 소스 코드) 업데이트
- **U-5**: 팩 업데이트

### 5.3 Tauri v2 업데이트 플러그인(참조)

Tauri v2에는 공식 업데이트 플러그인이 있습니다. 구현 단계:

```
1. cargo add tauri-plugin-updater  (Cargo.toml)
2. tauri.conf.json に plugins.updater を追加
3. capabilities/default.json に "updater:default" を追加
4. アップデートサーバー（JSON エンドポイント）を用意
5. Rust 側で updater::Builder を初期化
```

하지만 Rumi AI의 아키텍처는 Rust 런처뿐만 아니라 Python 커널 및 팩도 업데이트해야 하므로 Tauri의 표준 업데이트만으로는 충분하지 않습니다. U단계에서 자신만의 업데이트 흐름을 디자인하세요.

---

## 6. 실패기록

### 6.1 v0.1.0-test.1 — 첫 번째 CI 실행(멸종)

**날짜 및 시간**: 2026-03-28 19:17 UTC
**결과**: 수동 취소(작업 4개 중, 성공하기 전에 취소됨)
**원인**: 세 가지 독립적인 문제가 동시에 발생

#### 문제 1: macOS Intel 러너 지원 중단

- **증상**: `macos-13` 실행자가 지정된 작업이 대기열에 남아 있고 진행되지 않습니다.
- **원인**: GitHub Actions는 2025년 12월에 `macos-13` 실행기를 영구적으로 제거했습니다.
- **근거**: GitHub 공식 실행기 이미지 만료 일정

#### 문제 2: Windows에서 icon.ico가 없습니다.

- **증상**: Windows 빌드에서 `build.rs` 컴파일 오류
- **원인**: `tauri-build`의 `build.rs`에는 `icons/icon.ico`가 필요합니다. 저장소에는 16×16 `icon.png`의 83바이트만 있었습니다.
- **근거**: Tauri v2의 `build.rs`는 Windows 바이너리의 리소스로 `.ico`을 포함합니다.

#### 문제 3: Linux에서 AppImage 번들 실패

- **증상**: AppImage를 번들링할 때 `tauri-bundler` 패닉이 발생함
- **원인**: `tauri-bundler`가 아이콘 디렉터리에서 사각형 PNG(너비 == 높이)를 필터링하여 결과가 0개 발생했습니다. 기존 `icon.png`은 16×16이었으나, 번들러가 요구하는 최소 크기를 충족하지 못했거나, 번들러가 `icon.png`를 찾지 못했을 수 있습니다.
- **참고**: deb/rpm 번들이 성공했습니다. AppImage만 실패함

### 6.2 v0.1.0-test.2 — 러너 수정 + 아이콘 생성(RGB 버전)

**날짜 및 시간**: 2026-03-28 20:15 UTC
**결과**: 작업 4개 중 2개는 실패했고, 2개는 성공할 것으로 예상됐으나 결국 전멸했습니다.

| 직업 | 결과 | 실패한 단계 |
|--------|------|------------|
| macOS ARM(macos-최신) | 실패 | 화물 타우리로 구축 |
| macOS Intel(macos-15-intel) | 실패 | 화물 타우리로 구축 |
| Linux(우분투 최신) | 실패 | 화물 타우리로 구축 |
| Windows(Windows 최신) | 실패 | 화물 타우리로 구축 |

**수정 사항(v0.1.0-test.2에 적용)**:
- `macos-13` → `macos-15-intel`로 대체 → **러너 문제 해결** (작업 시작 및 빌드 진행)
- Python 표준 라이브러리(struct + zlib)를 사용하여 PNG/ICO/ICNS 생성 → 파일이 성공적으로 생성되었습니다.
- `tauri.conf.json`에 `bundle.icon` 추가

**새롭게 발견된 문제**:

#### 문제 4: PNG는 RGB이고 Tauri에는 RGBA가 필요합니다.

- **증상**: 모든 플랫폼에서 동일한 오류가 발생합니다.
  ```
  error: proc macro panicked
   --> src/lib.rs:150:14
    |
  150 |         .run(tauri::generate_context!())
    |              ^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
    = help: message: icon .../icons/32x32.png is not RGBA
  ```
- **원인**: Python에서 생성된 PNG의 color_type은 `2`(RGB, 3바이트/픽셀)이었습니다. Tauri의 `generate_context!()` 매크로는 컴파일 시 PNG를 디코딩하고 RGBA(color_type=6, 4바이트/픽셀)가 아닌 경우 패닉이 발생합니다.
- **학습 내용**: **Tauri의 아이콘 PNG를 RGBA(color_type=6)로 생성해야 합니다**. RGB는 허용되지 않습니다.

### 6.3 v0.1.0-test.3 — RGBA 수정(완전한 성공)

**날짜 및 시간**: 2026-03-28 22:21 UTC
**결과**: 4개 작업 모두 성공

| 직업 | 결과 | 빌드 시간 |
|--------|------|-----------|
| macOS ARM(macos-최신) | 성공 | ~3분 |
| macOS Intel(macos-15-intel) | 성공 | ~5.5분 |
| Linux(우분투 최신) | 성공 | ~4분 |
| Windows(Windows 최신) | 성공 | ~5.5분 |

**수정 세부정보**:
- PNG 생성의 `color_type`를 `2`(RGB) → `6`(RGBA)로 변경했습니다.
- `bytes([r, g, b])` → `bytes([r, g, b, 255])`에서 픽셀 데이터 변경
- 유효성 검사 단계에 IHDR color_type=6 확인이 추가되었습니다.

**모든 단계의 성공 여부를 확인하세요**:
- 체크아웃 → Rust 설치 → Tauri CLI 설치 → **cargo tauri로 빌드** → **릴리스 아티팩트 업로드** 모두 성공

---

## 7. 문제 해결

### "아이콘 ...이 RGBA가 아닙니다." 오류

PNG가 RGB 모드입니다. RGBA(알파 채널 포함)로 재현되어야 합니다.

```bash
# 確認方法
python3 -c "
import struct
with open('rumi_viewer/src-tauri/icons/32x32.png', 'rb') as f:
    f.read(8)  # signature
    f.read(4)  # IHDR length
    f.read(4)  # 'IHDR'
    data = f.read(13)
    w, h, depth, ctype = struct.unpack('>IIBB', data[:10])
    print(f'{w}x{h} depth={depth} color_type={ctype}')
    # color_type=6 なら RGBA、2 なら RGB（NG）
"
```

### 주자가 대기열에 남아 진행되지 않습니다.

러너가 더 이상 사용되지 않을 수 있습니다. `release.yml`의 `runs-on`를 확인하세요.

```bash
grep "runs-on\|os:" .github/workflows/release.yml
```

https://github.com/actions/runner-images.에서 현재 사용 가능한 러너를 확인하세요.

### AppImage 번들 패닉

아이콘 디렉터리에 정사각형(너비 == 높이) PNG가 없거나 크기가 부족합니다. `ls -la rumi_viewer/src-tauri/icons/`에서 확인되었습니다.

### 초안 릴리스가 생성되지 않았습니다.

`softprops/action-gh-release@v2`는 `files` 패턴과 일치하는 파일이 없으면 릴리스를 생성하지 못할 수 있습니다. 빌드 아티팩트 경로를 확인하세요.

```
rumi_viewer/src-tauri/target/<target>/release/bundle/
├── dmg/   (macOS)
├── nsis/  (Windows)
├── deb/   (Linux)
└── appimage/ (Linux)
```

---

## 8. 변경 내역

| 날짜 | 목차 |
|------|------|
| 2026-03-29 | 첫 번째 에디션이 생성되었습니다. v0.1.0-test.1~3 | 장애 기록 현황, 빌드 절차, 아이콘 관리, 업데이트 메커니즘에 대해 설명합니다.
