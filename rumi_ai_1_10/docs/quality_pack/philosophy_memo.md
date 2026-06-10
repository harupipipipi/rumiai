<!-- docs-i18n-links:start -->
[EN](./philosophy_memo.md) | [JP](../i18n/ja/quality_pack/philosophy_memo.md) | [KR](../i18n/ko/quality_pack/philosophy_memo.md) | [CN](../i18n/zh-cn/quality_pack/philosophy_memo.md)
<!-- docs-i18n-links:end -->

# rumi_ai Thought Memo (Development Judgment Criteria)

## 1. Purpose

rumi_ai is not an "app with built-in chat and tools", but an execution platform that provides **Flow execution, approval, isolation, permissions, and audit**. The official core does not favor any particular domain, and the functions are handled by the Pack (No Favoritism).

## 2. User Experience (UX) Goals

It is important for users to be able to safely add Packs and operate without stopping the entire system. The core of the UX is to be able to disable broken packs and track their status through audit logs and diagnostics (Fail-Soft + Observability).

## 3. Core of safety design

1. **Malicious Pack assumption**: Unapproved Packs cannot be executed, and even after approval, they are automatically invalidated due to hash mismatch.
2. **Isolated execution**: Docker is required in strict mode, Pack is in principle `--network=none`.
3. **Minimum Privilege**: External communication and host privileges only via Capability (Trust + Grant).
4. **Auditability**: Records authority operations, communications, and execution results in audit logs to make them traceable.

## 4. Quality standards

1. **Continuously verifiable**: Keep pytest / cargo test / lint / typecheck / build repeatable.
2. **Regression resistance**: Have contract tests (CLI, settings, CI, security boundaries) that do not break existing functionality.
3. **Operability**: Document failure isolation procedures, manual verification, and pre-release checks.
4. **Ideology consistency**: Confirm that changes do not violate No Favoritism / Fail-Soft / Malicious Assumption / Least Privilege.

## 5. Change judgment rules (used in this work)

1. PR1 adds **quality assets only** (tests, validation scripts, checklists, audit procedures, operational documentation) and does not change product behavior.
2. PR2 prioritizes and fixes bugs detected in PR1 that have a high user impact, reproducibility, and ideological deviation.
3. When in doubt, prioritize the options that are ``safe,'' ``auditable,'' and ``hard to relapse.''
