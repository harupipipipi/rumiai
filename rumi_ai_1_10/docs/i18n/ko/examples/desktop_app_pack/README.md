<!-- docs-i18n-links:start -->
[EN](../../../../examples/desktop_app_pack/README.md) | [JP](../../../ja/examples/desktop_app_pack/README.md) | [KR](./README.md) | [CN](../../../zh-cn/examples/desktop_app_pack/README.md)
<!-- docs-i18n-links:end -->

# 데스크탑 앱 팩

Rumi AI OS의 **desktop_app.execute** 기능을 사용하는 샘플 팩입니다.
별도의 데스크톱 창(tkinter)에서 앱을 시작합니다.

Pack은 개발자가 복사하고 수정할 수 있는 템플릿 역할도 합니다.

---

## 디렉토리 구조

```
desktop_app_pack/
├── ecosystem.json   # Pack マニフェスト（desktop_app セクション付き）
├── app.py           # デスクトップアプリ（tkinter Hello World + Kernel API 通信）
└── README.md        # このファイル
```

---

## Desktop_app.execute 기능이란 무엇입니까?

`desktop_app.execute`은 팩이 **독립적인 데스크탑 창**에서 애플리케이션을 시작할 수 있게 해주는 Rumi AI OS의 핵심 기능입니다.

뷰어 내의 프런트엔드 디스플레이와는 달리(`viewer:display`):

1. `pack-shell` 바이너리는 커널 시작 확인 및 토큰 획득을 자동화합니다.
2. 환경변수(`RUMI_TOKEN`, `RUMI_PORT`, `RUMI_PACK_ID`)를 통해 Kernel API와 통신
3. tkinter, Qt, Electron, Tauri 등과 같은 모든 GUI 프레임워크를 사용할 수 있습니다.

능력의 정의는 `core_runtime/core_pack/core_desktop_capability/`에 있습니다.

---

## 사용방법

### 1. 팩쉘 빌드

```bash
cd pack-shell
cargo build --release
```

### 2. 팩을 올려놓는다

이 디렉토리를 `ecosystem/`에 복사하세요:

```bash
cp -r docs/examples/desktop_app_pack/ ecosystem/desktop_app_pack/
```

### 3. 커널 시작

```bash
python -m rumi_ai
```

커널이 시작되면 자동으로 `ecosystem/desktop_app_pack/ecosystem.json`을 검사합니다.

### 4. 팩 승인

에코시스템 팩은 처음 승인이 필요합니다(core_packs와 달리 자동으로 승인되지 않음).
Kernel API 또는 관리 화면에서 팩을 승인해주세요.

### 5. 보조금 받기

`desktop_app.execute` 권한 부여가 필요합니다.
**참고**: `desktop_app.execute`는 `dangerous: true`으로 설정됩니다. 승인 승인은 데스크톱 앱이 호스트 OS에서 임의의 프로세스를 시작할 수 있는 권한을 의미합니다.

### 6. pack-shell로 앱 시작

```bash
pack-shell run desktop_app_pack \
  --command "python app.py" \
  --working-dir /path/to/desktop_app_pack \
  --api-token "$RUMI_API_TOKEN"
```

커널 API 및 상태 확인 기능에 대한 연결 정보가 포함된 tkinter 창이 열립니다.

---

## Ecosystem.json 설명

```json
{
  "pack_id": "desktop_app_pack",
  "desktop_app": {
    "command": "python app.py",
    "window": {
      "title": "Desktop App Pack",
      "width": 600,
      "height": 400
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

| 필드 | 설명 |
|-----------|------|
| §루미§0§ | pack-shell을 실행하는 명령입니다. `--command` 인수로 전달됨 |
| §루미§0§ | `DesktopAppManager`은 `RUMI_API_TOKEN`로 간주됩니까? 현재 상태는 항상 `true` |
| §루미§0§ | 바로가기 이름/창 제목에 사용 |
| §루미§0§ | 권장 창 크기(앱 측에서 읽을 때) |
| §루미§0§ | 지원되는 플랫폼 |

---

## 커널 API 통신

`app.py`에는 커널 API에 대한 샘플 통신이 포함되어 있습니다.

```python
import json
from urllib.request import Request, urlopen

port = os.environ.get("RUMI_PORT", "8765")
url = f"http://127.0.0.1:{port}/health"
req = Request(url, headers={"Accept": "application/json"})
with urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(data)  # {"status": "ok"}
```

pack-shell로 설정된 환경 변수:

| 변수 | 설명 |
|------|------|
| §루미§0§ | 커널에서 발행한 임시 토큰 |
| §루미§0§ | 커널 API 포트 번호(기본값: 8765) |
| §루미§0§ | 대상 팩 ID |

---

## 맞춤 설정 팁

- **GUI 변경**: `app.py`의 tkinter 코드를 Qt, wxPython, Electron 등으로 대체할 수 있습니다.
- **API 호출 추가**: `Authorization: Bearer` 헤더에 `RUMI_TOKEN`을 설정하여 커널 API를 호출할 수 있습니다.
- **변경 명령**: `ecosystem.json`의 `desktop_app.command`를 `"node app.js"` 또는 `"./my_binary"`로 변경할 수 있습니다.
- **토큰 계약**: `DesktopAppManager`을 통해 활성화하려면 `RUMI_API_TOKEN`이 필요합니다.
- **팩명 변경** : `ecosystem.json`의 `pack_id`, `pack_identity`을 변경해주세요.
- **창 설정**: `desktop_app.window`의 `title`, `width`, `height`를 변경할 수 있습니다.

---

## 관련 문서

- [Pack 데스크톱 앱 개발 가이드](../../pack_desktop_app_guide.md)
- [팩 개발 가이드](../../pack-development.md)
- [다국어 팩 개발 가이드](../../multilang_pack_guide.md)
- [팩-쉘 추가 정보](../../../../../../pack-shell/i18n/ko/README.md)
