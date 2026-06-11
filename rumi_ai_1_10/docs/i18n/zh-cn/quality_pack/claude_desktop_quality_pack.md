<!-- docs-i18n-links:start -->
[EN](../../../quality_pack/claude_desktop_quality_pack.md) | [JP](../../ja/quality_pack/claude_desktop_quality_pack.md) | [KR](../../ko/quality_pack/claude_desktop_quality_pack.md) | [CN](./claude_desktop_quality_pack.md)
<!-- docs-i18n-links:end -->

# Claude rumi_ai 桌面级质量包

本文档是一个实用包，用于持续开发、审核和验证 rumi_ai 的高质量。
**PR1仅添加优质资产，不会改变产品行为。**

---

## 1. 包的用途

1. 将现有测试和缺失区域合并为一个操作程序。
2. 能够在短时间内隔离故障并重现故障。
3. 机械地检查自述文件/设计理念的一致性（无偏袒、软失败、恶意假设、最小特权）。

---

## 2.执行命令（推荐顺序）

从存储库根运行：

```bash
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

完整审计模式（包括现有的遗留 lint 债务）：

```bash
RUMI_FULL_QUALITY=1 bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

单独执行：

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

## 3. 额外测试的领域

## 3.1 意识形态一致性检查
- 检查思想备忘录和质量包文档中是否存在所需部分
- 静态验证以查看 README/CI 定义契约是否被破坏

## 3.2 CLI/后端合约
- 根入口点（`rumi_ai/__main__.py`）连接到`rumi_ai_1_10.app`的合约
- 版本对齐（`rumi_ai/__init__.py`和`rumi_ai_1_10/pyproject.toml`）

## 3.3 UI/剧作家等效（静态合约）
- `localhost:8765` 必须包含在 Tauri 设置的 CSP 中
- `connect-src`不允许`https://`或`*`
- 类型检查/构建脚本必须存在于前端包中

## 3.4 设置/权限/故障系统
- 根pytest/包pytest/货物测试必须在CI工作流程中定义
- 发布工作流程具有`v*`标签触发器和`cargo tauri build`

---

## 4. 审核程序

1.检查审计日志
   - `user_data/audit/security_YYYY-MM-DD.jsonl`
   - `user_data/audit/network_YYYY-MM-DD.jsonl`
   - `user_data/audit/permission_YYYY-MM-DD.jsonl`
2.查看审批状态
   - 没有未经授权的包正在运行
   - `modified` 状态包未经重新授权无法运行
3.检查权限
   - 能力授予和网络授予是最小特权
4、故障记录
   - 留下复制命令、预期值、实际值、影响范围、解决方法和永久候选对策

---

## 5.手动验证步骤（最少设置）

1. 启动安全
   - 严格启动：`python app.py`
- 开发开始：`python app.py --permissive`（确认许可条件）
2、审批流程
   - 打包扫描 -> 待处理 -> 批准/拒绝 -> 状态 确认转换
3、网络权限
   - 在没有拨款的情况下被拒绝
   - grant grant后授予什么
4.查看器显示
   - 查看器可以显示本地主机面板
   - 外部 URL 指导由 CSP/权威机构控制

---

## 6.回归确认程序

1.执行相当于现有CI的命令(root/package/cargo)
2. 运行附加的质量合同测试
3. 通过 lint/类型检查/构建
4. 如果失败，区分是“测试实现问题”还是“产品bug”
   - 测试实施问题：在 PR1 中修复
   - 产品错误：记录为 PR2 候选者
   - 遗留的 lint 债务：使用`RUMI_FULL_QUALITY=1`检测并制定逐步还款计划

---

## 7. 发布前检查

1. `.github/workflows/test.yml`和`release.yml`与当前操作一致
2. 额外测试是绿色的
3. 审核/故障排除程序是最新的
4. 安全模式（严格/宽松）的描述一致。
5.根自述文件和`rumi_ai_1_10/README.md`链接有效

---

## 8.意识形态兼容性检查表

- [ ] 官方核心中未增加特定领域先决条件逻辑（无偏袒）
- [ ] 发生部分故障（Fail-Soft）时的连续运行不会中断。
- [ ] 基于恶意Pack的审批、验证和隔离不被削弱。
- [ ] 外部通信和危险操作不会转移到能力之外。
- [ ] 维护审计日志中可追踪的实施情况

---

## 9. 发生故障时的隔离程序

1. 对失败的门进行分类
   - 根 pytest / 包 pytest / ruff / mypy / 前端 lint-build / 货物测试
2. 最低限度的繁殖
   - 减少为单个测试文件或单个命令
3、原因分类
   - 配置不一致
- 测试假设不充分
   - 产品错误（针对 PR2）
4.影响评估
   - 严重性（高/中/低）
   - 再现性（恒定/条件）
- 用户影响（安全/数据/用户体验）

---

## 10.AI代理操作提示（操作模板）

操作时在开头添加以下内容：

```text
README・docs・思想メモを先に読み、No Favoritism / Fail-Soft / 悪意前提 / 最小権限を判断基準にする。
PR1では品質資産のみ、PR2で実害バグを修正する。
失敗時はテスト不備と製品バグを分離し、製品バグは再現条件と優先度付きで記録する。
全検証コマンドを実行し、結果をコマンド単位で報告する。
```

---

## 11.已知 PR2 候选记录模板

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
