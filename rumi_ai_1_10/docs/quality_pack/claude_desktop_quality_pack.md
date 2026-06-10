<!-- docs-i18n-links:start -->
[EN](./claude_desktop_quality_pack.md) | [JP](../i18n/ja/quality_pack/claude_desktop_quality_pack.md) | [KR](../i18n/ko/quality_pack/claude_desktop_quality_pack.md) | [CN](../i18n/zh-cn/quality_pack/claude_desktop_quality_pack.md)
<!-- docs-i18n-links:end -->

# Claude Desktop-level quality pack for rumi_ai

This document is a practical pack for continuously developing, auditing, and validating rumi_ai with high quality.  
**PR1 only adds quality assets and does not change product behavior. **

---

## 1. Purpose of the pack

1. Consolidate existing tests and missing areas into one operational procedure.
2. Make it possible to isolate failures and reproduce them in a short time.
3. Mechanically check consistency with README/design philosophy (No Favoritism, Fail-Soft, Malicious Assumption, Least Privilege).

---

## 2. Execution commands (recommended order)

Run from repository root:

```bash
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

Full audit mode (including existing legacy lint debt):

```bash
RUMI_FULL_QUALITY=1 bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

Individual execution:

```bash
# root (version-stable entrypoint) テスト
python -m pytest tests -v

# package テスト
cd rumi_ai_1_10
python -m pytest tests -v

# 追加した品質契約テストのみ
python -m pytest tests/test_claude_quality_pack_contract.py -v
cd ..
python -m pytest tests/test_entrypoint_contracts.py -v

# Python 品質ゲート
cd rumi_ai_1_10
python -m ruff check tests/test_claude_quality_pack_contract.py
python -m ruff format --check tests/test_claude_quality_pack_contract.py
python -m mypy tests/test_claude_quality_pack_contract.py
cd ..
python -m ruff check tests/test_entrypoint_contracts.py
python -m ruff format --check tests/test_entrypoint_contracts.py
python -m mypy tests/test_entrypoint_contracts.py

# Frontend/Viewer/Pack-shell
cd rumi_viewer/frontend && npm run lint && npm run build && cd ../..
cd pack-shell && cargo test && cd ..
```

---

## 3. Areas for additional testing

## 3.1 Ideological conformity check
- Check the existence of required sections in thought memos and quality pack documents
- Static verification to see if README/CI definition contract is broken

## 3.2 CLI/Backend Contract
- Contract where root entrypoint (`rumi_ai/__main__.py`) connects to `rumi_ai_1_10.app`
- Version alignment (`rumi_ai/__init__.py` and `rumi_ai_1_10/pyproject.toml`)

## 3.3 UI/Playwright equivalent (static contract)
- `localhost:8765` must be included in CSP of Tauri settings
- `connect-src` does not permit `https://` or `*`
- Type check/build script must exist in frontend package

## 3.4 Settings / Permissions / Failure system
- Root pytest / package pytest / cargo test must be defined in the CI workflow
- release workflow has `v*` tag trigger and `cargo tauri build`

---

## 4. Audit Procedures

1. Check audit log
   - `user_data/audit/security_YYYY-MM-DD.jsonl`
   - `user_data/audit/network_YYYY-MM-DD.jsonl`
   - `user_data/audit/permission_YYYY-MM-DD.jsonl`
2. Check approval status
   - No unauthorized packs are running
   - `modified` Status Pack not running without reauthorization
3. Check permissions
   - capability grant and network grant are least privilege
4. Failure record
   - Leave reproduction commands, expected values, actual values, scope of impact, workarounds, and permanent countermeasure candidates

---

## 5. Manual verification steps (minimum set)

1. Startup safety
   - strict startup: `python app.py`
- Development start: `python app.py --permissive` (Confirm permission conditions)
2. Approval flow
   - Pack scan -> pending -> approve/reject -> status Confirm transition
3. Network permissions
   - to be rejected without a grant
   - grant What is granted after granting
4.Viewer display
   - Viewer can display localhost panel
   - External URL guidance is controlled by CSP/authority

---

## 6. Regression confirmation procedure

1. Execute command equivalent to existing CI (root/package/cargo)
2. Run the added quality contract tests
3. Pass lint/typecheck/build
4. In case of failure, separate whether it is a “test implementation problem” or “product bug”
   - Test implementation issue: fixed in PR1
   - Product bug: Recorded as PR2 candidate
   - Legacy lint debt: Detect with `RUMI_FULL_QUALITY=1` and create a gradual repayment plan

---

## 7. Pre-release check

1. `.github/workflows/test.yml` and `release.yml` are consistent with current operation
2. Additional tests are green
3. Audit/troubleshooting procedures are up to date
4. Descriptions of security modes (strict/permissive) are consistent.
5. Root README and `rumi_ai_1_10/README.md` links are valid

---

## 8. Ideology Compatibility Checklist

- [ ] Specific domain prerequisite logic has not been increased in the official core (No Favoritism)
- [ ] Continuous operation in the event of partial failure (Fail-Soft) is not broken.
- [ ] Approval, verification, and isolation based on malicious Packs are not weakened.
- [ ] External communications and dangerous operations are not diverted outside the Capability.
- [ ] Maintains implementation traceable in audit logs

---

## 9. Isolation procedure in case of failure

1. Classify which gate failed
   - root pytest / package pytest / ruff / mypy / frontend lint-build / cargo test
2. Minimum reproduction
   - Reduced to a single test file or single command
3. Cause classification
   - Configuration inconsistency
   - Inadequate test assumptions
   - Product bug (for PR2)
4. Impact assessment
   - Severity (high/medium/low)
   - Reproducibility (constant/conditional)
- User impact (Security/Data/UX)

---

## 10. AI agent operation prompt (operation template)

Operate by adding the following at the beginning:

```text
README・docs・思想メモを先に読み、No Favoritism / Fail-Soft / 悪意前提 / 最小権限を判断基準にする。
PR1では品質資産のみ、PR2で実害バグを修正する。
失敗時はテスト不備と製品バグを分離し、製品バグは再現条件と優先度付きで記録する。
全検証コマンドを実行し、結果をコマンド単位で報告する。
```

---

## 11. Known PR2 Candidate Record Template

```text
- 事象:
- 再現手順:
- 期待挙動:
- 実際の挙動:
- 重大度:
- 再現性:
- ユーザー影響:
- 思想逸脱:
```
