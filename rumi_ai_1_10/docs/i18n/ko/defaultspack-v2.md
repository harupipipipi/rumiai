<!-- docs-i18n-links:start -->
[EN](../../defaultspack-v2.md) | [JP](../ja/defaultspack-v2.md) | [KR](./defaultspack-v2.md) | [CN](../zh-cn/defaultspack-v2.md)
<!-- docs-i18n-links:end -->

# defaultspack v2

이 분기는 defaultspack v2 호환성 표면을 추가합니다.

- 모듈 상태 및 카탈로그 도우미
- 백엔드/프론트엔드 로더
- 설정 팩 선택(시작에는 프롬프트 + 초기 all-OK 부여 포함)
- AI 클라이언트, 프롬프트, 도구, 플러그인, 채팅, 메모리, 에이전트, 샌드박스, 마이그레이션을 위한 씬 어댑터

`supports_all_ok`은 `ecosystem/setup_pack/*`의 신뢰할 수 있는 저장소 메타데이터입니다.
업스트림에서는 관리자가 검토한 설치 팩 정의만 신뢰할 수 있습니다. 포크
자체 설치 팩을 추가할 수 있습니다. 이는 신뢰할 수 있는 소스를 변경하는 것과 같습니다.
그 포크.
