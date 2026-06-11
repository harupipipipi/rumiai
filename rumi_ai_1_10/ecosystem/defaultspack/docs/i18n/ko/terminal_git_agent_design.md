<!-- docs-i18n-links:start -->
[EN](../../terminal_git_agent_design.md) | [JP](../ja/terminal_git_agent_design.md) | [KR](./terminal_git_agent_design.md) | [CN](../zh-cn/terminal_git_agent_design.md)
<!-- docs-i18n-links:end -->

# 터미널 Git 에이전트 설계

말기 위험:

- 낮음: `pwd`, `ls`, `cat`, `git status`와 같은 읽기 전용 명령입니다.
- 매체: 로컬 테스트/빌드 명령.
- 높음: 쓰기, 설치, chmod, rm, 네트워크 및 git push를 수행합니다.
- 중요: 작업 공간 외부의 파괴적인 명령 또는 비밀 유출 패턴.

Git 작업:

- 상태, 차이점, 로그는 안전한 읽기입니다.
- 추가, 커밋, 복원, 숨김에는 확인 메타데이터가 필요합니다.
- 푸시에는 네트워크 승인 및 감사가 필요합니다.

UI에 대한 출력이 요약되고 실행 기록에서는 원시 출력을 계속 사용할 수 있습니다.
