<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](../ja/README.md) | [KR](./README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# 루미 리모트 모바일

Rumi Remote Mobile은 PC에서 호스팅되는 Rumi를 관리하기 위한 Flutter 클라이언트입니다.
신뢰할 수 있는 네트워크의 iOS 및 Android 장치에서 `defaultspack`.

앱은 독립 실행형이 아닌 포트 `8765`의 커널 팩 API를 대상으로 합니다.
포트 `8766`에서 defaultspack 채팅 전송. 커널 API에는 전달자가 필요합니다.
토큰이며 LAN 액세스를 위한 더 안전한 표면입니다.

## PC 설정

신뢰할 수 있는 LAN에 바인딩된 커널 API로 Rumi를 시작하십시오.

```powershell
$env:RUMI_API_BIND_ADDRESS="0.0.0.0"
python -m rumi_ai
```

`rumi_ai_1_10/user_data/hmac_keys.json`에서 활성 API 토큰을 읽거나 다음을 실행합니다.

```powershell
cd rumi_ai_1_10
python -c "from core_runtime.hmac_key_manager import HMACKeyManager; print(HMACKeyManager().get_active_key())"
```

앱에서 서버 URL을 `http://<pc-lan-ip>:8765`으로 설정하고 토큰을 붙여넣습니다.
PC 방화벽을 개인 네트워크로 제한하십시오. 이 포트를 노출하지 마세요.
공용 인터넷으로 직접 연결됩니다.

Tauri 데스크탑 뷰어를 사용할 때 뷰어 창을 닫으면 뷰어로 전송됩니다.
백그라운드를 유지하고 원격 클라이언트에서 커널 API를 사용할 수 있도록 유지합니다. 트레이를 사용하세요
커널을 중지하고 Rumi를 완전히 종료하려면 메뉴의 `Quit` 항목을 선택하세요.

Android 디버그/프로필 빌드는 신뢰할 수 있는 LAN 개발을 위한 일반 텍스트 HTTP를 허용합니다.
Android 릴리스 빌드는 일반 텍스트 트래픽을 전역적으로 허용하지 않습니다. HTTPS 또는
LAN 전용 빌드를 배포하는 경우 명시적인 릴리스 네트워크 정책.

## API 적용 범위

| 목적 | 방법 | 경로 |
| --- | --- | --- |
| 건강검진 | §루미§0§ | §루미§1§ |
| 모듈 목록 | §루미§0§ | §루미§1§ |
| 모듈 세부정보 | §루미§0§ | §루미§1§ |
| 모듈 활성화 | §루미§0§ | §루미§1§ |
| 모듈 비활성화 | §루미§0§ | §루미§1§ |
| 모듈 다시 로드 | §루미§0§ | §루미§1§ |
| 롤백 모듈 | §루미§0§ | §루미§1§ |
| 마이그레이션 상태 | §루미§0§ | §루미§1§ |
| 팩 요청 | §루미§0§ | §루미§1§ |

## 개발

```powershell
cd rumi_mobile
flutter pub get
flutter analyze
flutter test
```

Android 디버그 빌드에는 Flutter/Android SDK 환경이 필요합니다.

```powershell
flutter build apk --debug
```

iOS 빌드에는 macOS 및 Xcode가 필요합니다.

```bash
flutter build ios --no-codesign
```
