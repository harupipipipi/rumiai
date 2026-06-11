<!-- docs-i18n-links:start -->
[EN](./defaultspack-v2.md) | [JP](./i18n/ja/defaultspack-v2.md) | [KR](./i18n/ko/defaultspack-v2.md) | [CN](./i18n/zh-cn/defaultspack-v2.md)
<!-- docs-i18n-links:end -->

# defaultspack v2

This branch adds the defaultspack v2 compatibility surface.

- module state and catalog helpers
- backend/frontend loaders
- setup pack selection (startup include prompt + initial all-OK grant)
- thin adapters for AI client, prompt, tool, plugin, chat, memory, agent, sandbox, migration

`supports_all_ok` is trusted repository metadata from `ecosystem/setup_pack/*`.
In upstream, only maintainer-reviewed setup pack definitions are trusted. Forks
can add their own setup packs, which is equivalent to changing trusted source in
that fork.
