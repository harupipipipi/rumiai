<!-- docs-i18n-links:start -->
[EN](../../operations.md) | [JP](../ja/operations.md) | [KR](../ko/operations.md) | [CN](./operations.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS — 操作指南

操作员指南。总体设计请参见[architecture.md](./architecture.md)，Pack 开发请参见[pack-development.md](./pack-development.md)。

---

## 目录

1. [设置](#设置)
2. [开始](#开始)
3. [安全模式](#安全模式)
4. [HTTP API 概述](#http-api-概述)
5.【包审批管理】(#包装审批管理)
6. [网络权限管理](#network-privilege-management)
7. [能力处理者批准](#capability-handler-approval)
8. [能力授予管理](#能力授予管理)
9.【pip依赖库管理】(#pip-dependency-library-management)
10. [秘密管理](#保密管理)
11.§鲁米§0§
12. [共享商店管理](#共享店铺管理)
13.§鲁米§0§
14. [流程执行](#流程执行)
15. [权限管理](#权限管理)
16. [UDS 套接字设置](#uds-套接字设置)
17. [如何阅读审核日志](#如何读取审计日志)
18. [待导出](#待导出)
19. [身份验证令牌](#身份验证令牌)
20. [结构化日志设置](#结构化日志设置)
21. [已弃用的警告级别控制](#弃用警告级别控制)
22.【健康检查操作】(#健康检查操作)
23. [指标确认](#检查指标)
24. [包模板生成（脚手架）](#包模板生成（脚手架）)
25. [错误代码参考](#错误代码参考)
26. [环境变量参考](#环境变量参考)
27. [疑难解答](#故障排除)

---

## 设置

### 要求

-Python 3.10+
- Docker（生产环境所需）
- git

### 安装

```bash
git clone https://github.com/harupipipipi/rumiai.git
cd rumiai/rumi_ai_1_10

# セットアップ（CLI）
python bootstrap.py --cli init

# または手動
pip install -r requirements.txt
```

### 设置工具

设置工具提供两个界面：CLI 和 Web。

```bash
# CLI モード
python bootstrap.py --cli              # 対話メニュー
python bootstrap.py --cli check        # 環境チェック
python bootstrap.py --cli init         # 初期セットアップ
python bootstrap.py --cli doctor       # 診断
python bootstrap.py --cli recover      # リカバリー
python bootstrap.py --cli run          # アプリ起動

# Web モード
python bootstrap.py --web              # ブラウザ操作（デフォルトポート 8080）
python bootstrap.py --web --port 9000  # ポート指定
```

安装工具会自动执行以下操作：检查 Python / Git / Docker、创建虚拟环境 (.venv)、安装依赖项、初始化 user_data 目录并安装默认包（可选）。

---

## 开始

```bash
# 本番環境（Docker 必須）
python app.py

# 開発環境（Docker 不要）
python app.py --permissive

# ヘッドレスモード
python app.py --headless

# ヘルスチェック実行
python app.py --health

# Pack バリデーション実行
python app.py --validate
```

`--health` 执行运行状况检查，将结果以 JSON 格式打印到 stdout，然后退出。如果状态为`"UP"`，则退出代码为 0，否则退出代码为 1。内置探测器包括磁盘（磁盘可用空间）和 writable_tmp（`/tmp` 可写性）。可用于CI/CD、容器编排的健康检查。

`--validate` 执行包验证，打印结果，然后退出。

---

## 安全模式

使用环境变量`RUMI_SECURITY_MODE`进行设置。

|模式|码头工人 |行为 |
|--------|--------|------|
| `strict`（默认）|必填|如果 Docker 不可用则拒绝执行 |
| §鲁米§0§|不需要|允许主机执行但带有警告 |

```bash
# 本番
export RUMI_SECURITY_MODE=strict

# 開発
export RUMI_SECURITY_MODE=permissive
```

---

## HTTP API 概述

所有端点都需要`Authorization: Bearer YOUR_TOKEN`。

### 包管理

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|所有包列表 |
|获取 | §鲁米§0§|等待批准的包列表 |
|获取 | §鲁米§0§|获取包状态 |
|发布 | §鲁米§0§|打包扫描 |
|发布 | §鲁米§0§|包装审批 |
|发布 | §鲁米§0§|包裹被拒绝 |
|发布 | §鲁米§0§|包进口|
|发布 | §鲁米§0§|包申请 |
|删除 | §鲁米§0§|包卸载 |

### 网络权限

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|所有补助金列表 |
|发布 | §鲁米§0§|授予网络权限 |
|发布 | §鲁米§0§|撤销网络权限 |
|发布 | §鲁米§0§|检查访问权限 |

### 候选能力处理程序

|方法|路径|描述 |
|----------|------|------|
|发布 | §鲁米§0§|候选人扫描 |
|获取 | §鲁米§0§|应用列表 |
|发布 | §鲁米§0§|授权（信任+复制）|
|发布 | §鲁米§0§|被拒绝 |
|获取 | §鲁米§0§|阻止列表 |
|发布 | §鲁米§0§|解除封锁 |

### 能力补助

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|资助名单|
|发布 | §鲁米§0§|格兰特 |
|发布 | §鲁米§0§|撤销拨款 |
|发布 | §鲁米§0§|批量资助（最多 50 名）|

### pip依赖库

|方法|路径|描述 |
|----------|------|------|
|发布 | §鲁米§0§|候选人扫描 |
|获取 | §鲁米§0§|应用列表 |
|发布 | §鲁米§0§|审批+安装|
|发布 | §鲁米§0§|被拒绝 |
|获取 | §鲁米§0§|阻止列表 |
|发布 | §鲁米§0§|解除封锁 |

### 秘密

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|键列表（值被屏蔽）|
|发布 | §鲁米§0§|设置秘密值 |
|发布 | §鲁米§0§|删除秘密值 |

### 流程执行

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|已注册流量列表 |
|发布 | §鲁米§0§|运行流程|

### 商店

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|店铺列表 |
|发布 | §鲁米§0§|创建商店 |
|获取 | §鲁米§0§|共享店铺列表 |
|发布 | §鲁米§0§|共享商店授权|
|发布 | §鲁米§0§|共享商店取消|

### 单位

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|单位列表 |
|发布 | §鲁米§0§|发布单位 |
|发布 | §鲁米§0§|运行单位|

### 特权

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|特权清单 |
|发布 | §鲁米§0§|特权授予|
|发布 | §鲁米§0§|特权执行|

###打包原路线

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§|已登记航线一览 |
|发布 | §鲁米§0§|重新加载路由表 |

### Docker/容器

|方法|路径|描述 |
|----------|------|------|
|获取 | §鲁米§0§| Docker 可用性 |
|获取 | §鲁米§0§|集装箱清单 |
|发布 | §鲁米§0§|启动容器|
|发布 | §鲁米§0§|停止容器 |
|删除 | §鲁米§0§|容器删除|

---

## 包装审批管理

### 检查待批准

```bash
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 包批准

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 拒绝打包

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/reject \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "セキュリティ上の懸念"}'
```

### 重新授权（打包处于修改状态）

如果文件更改导致哈希不匹配，它将进入`modified`状态并自动禁用。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 网络权限管理

### 格兰特 格兰特

```bash
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "my_pack",
    "allowed_domains": ["api.openai.com", "*.anthropic.com"],
    "allowed_ports": [443]
  }'
```

### 赠款清单

```bash
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 访问检查

```bash
curl -X POST http://localhost:8765/api/network/check \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "domain": "api.openai.com", "port": 443}'
```

### 撤销授权

```bash
curl -X POST http://localhost:8765/api/network/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "reason": "不要になった"}'
```

---

## 能力处理程序授权

> **注意**：core_pack 提供的函数（store/secrets/flow/communication/docker）不经过此候选引入工作流程，并在内核启动时自动注册到 FunctionRegistry 中。以下候选人介绍工作流程（扫描 → 批准 → 授予）适用于用户包中包含的自定义功能处理程序。

功能处理程序通过两步操作变得可用。

1. **信任注册**（处理程序批准）：批准扫描检测到的候选者并将处理程序代码（sha256）注册为可信。
2. **Grant**（权限授予）：授予已批准的处理程序对 Pack 的权限。

```
候補スキャン (scan)
    ↓
pending（承認待ち）
    ↓
approve → Trust 登録 + コピー + Registry reload
    ↓
Grant 付与（principal × permission）
    ↓
Pack が capability を使用可能
```

候选人遵循状态转换：扫描→待决→批准/拒绝→阻止。

### 扫描候选人

```bash
curl -X POST http://localhost:8765/api/capability/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 批准等待名单

```bash
curl "http://localhost:8765/api/capability/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 扫描响应

候选扫描后的响应示例：

```json
{
  "success": true,
  "data": {
    "scanned": 3,
    "new_candidates": 2,
    "candidates": [
      {
        "candidate_key": "my_pack:fs_read_v1:fs_read_handler:a1b2c3d4e5f6...",
        "pack_id": "my_pack",
        "slug": "fs_read_v1",
        "handler_id": "fs_read_handler",
        "permission_id": "fs.read",
        "sha256": "a1b2c3d4e5f6...",
        "status": "pending",
        "description": "ファイルシステム読み取り handler",
        "risk": "ファイルシステムへの読み取りアクセスを提供"
      }
    ]
  }
}
```

`candidate_key` 的格式为`{pack_id}:{slug}:{handler_id}:{sha256}`。如果 handler.py 的内容因包含 sha256 而发生变化，它将被视为不同的候选者。

### 候选人批准

`candidate_key` 中包含的`:` 需要 URL 编码。

```bash
ENCODED_KEY="my_pack%3Afs_read_v1%3Afs_read_handler%3Aabc123..."

curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Reviewed and approved"}'
```

批准注册信任（sha256 白名单）+ 复制到`user_data/capabilities/handlers/` + 重新加载注册表。实际使用需要单独拨款。

### 候选人被拒绝

```bash
curl -X POST "http://localhost:8765/api/capability/requests/${ENCODED_KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なファイルシステムアクセス"}'
```

第一次和第二次使用有`rejected`（1小时冷却时间），第三次有`blocked`。

### 解锁

```bash
curl -X POST "http://localhost:8765/api/capability/blocked/${ENCODED_KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

---

## 能力授予管理

能力处理程序获得批准后，需要授予（主体×权限），Pack才能真正使用该能力。

### 格兰特 格兰特

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 赠款清单

```bash
curl "http://localhost:8765/api/capability/grants?principal_id=my_pack" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 撤销授权

```bash
curl -X POST http://localhost:8765/api/capability/grants/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 批量拨款（批量）

一次最多授予 50 笔赠款。尽最大努力进行处理（个别失败不会妨碍其他资助）。

```bash
curl -X POST http://localhost:8765/api/capability/grants/batch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "grants": [
      {"principal_id": "pack_a", "permission_id": "store.get"},
      {"principal_id": "pack_a", "permission_id": "store.set"},
      {"principal_id": "pack_b", "permission_id": "secrets.get", "config": {"allowed_keys": ["API_KEY"]}}
    ]
  }'
```

|参数|必填|描述 |
|-----------|------|------|
| §鲁米§0§| ✅ | Grant 对象数组（最多 50 个）|
| §鲁米§0§| ✅ |目标包 ID |
| §鲁米§0§| ✅ |授权ID |
| §鲁米§0§|可选|拨款设置（`allowed_keys`等）|

响应示例：

```json
{
  "success": true,
  "data": {
    "total": 3,
    "succeeded": 3,
    "failed": 0,
    "results": [
      {"principal_id": "pack_a", "permission_id": "store.get", "success": true},
      {"principal_id": "pack_a", "permission_id": "store.set", "success": true},
      {"principal_id": "pack_b", "permission_id": "secrets.get", "success": true}
    ]
  }
}
```

### 整体流程

```
1. capability handler 候補をスキャン
   POST /api/capability/candidates/scan

2. 候補を承認（Trust 登録 + コピー）
   POST /api/capability/requests/{key}/approve

3. Grant を付与（principal × permission）
   POST /api/capability/grants/grant

4. Pack が capability を使用可能に
```

---

## pip依赖库管理

这是扫描 → 批准 → 安装包的 pip 依赖项的工作流程。

### 扫描候选人

```bash
curl -X POST http://localhost:8765/api/pip/candidates/scan \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 批准等待名单

```bash
curl "http://localhost:8765/api/pip/requests?status=pending" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 批准（安装执行）

`candidate_key` 需要 URL 编码。

```bash
KEY=$(python3 -c "from urllib.parse import quote; print(quote('my_pack:requirements.lock:abc123...', safe=''))")

curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/approve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"allow_sdist": false}'
```

默认为仅轮子（`--only-binary=:all:`）。如果wheel包含不存在的包，请指定`"allow_sdist": true`。

### 被拒绝

```bash
curl -X POST "http://localhost:8765/api/pip/requests/${KEY}/reject" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "不要なパッケージを含んでいる"}'
```

第一次和第二次使用有`rejected`（1小时冷却时间），第三次有`blocked`。

### 解锁

```bash
curl -X POST "http://localhost:8765/api/pip/blocked/${KEY}/unblock" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "再評価の結果許可"}'
```

### 先决条件

假设该包处于批准状态。未经批准的 Pack 的相关部署在严格模式下会被拒绝。

---

## 秘密管理

### 键列表（值被屏蔽）

```bash
curl http://localhost:8765/api/secrets \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 设置秘密值

```bash
curl -X POST http://localhost:8765/api/secrets/set \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY", "value": "sk-..."}'
```

### 删除秘密值

```bash
curl -X POST http://localhost:8765/api/secrets/delete \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "OPENAI_API_KEY"}'
```

秘密值存储在`user_data/secrets/`中，1个密钥= 1个文件。无法使用 API 重新显示（仅限设置和删除）。没有秘密值输出到日志中。

### 加密

秘密值使用 Fernet (AES-128-CBC + HMAC-SHA256) 加密存储。加密密钥按以下优先顺序获取：

1.环境变量`RUMI_SECRETS_KEY`（Base64编码的Fernet密钥）
2.`user_data/settings/.secrets_key`文件
3. 如果以上都不存在，则自动生成密钥并保存在`.secrets_key`中

### 密钥备份

如果加密密钥丢失，则无法解密现有的秘密值。请将`user_data/settings/.secrets_key`备份到安全位置。使用环境变量`RUMI_SECRETS_KEY`从外部管理密钥时也需要备份。

### 明文模式

您可以使用`RUMI_SECRETS_ALLOW_PLAINTEXT`控制未加密的存储。

|价值|行为 |
|-----|------|
| `auto`（默认）|如果加密密钥可用则加密，否则保存为纯文本 |
| §鲁米§0§|始终允许以纯文本形式存储 |
| §鲁米§0§|需要加密密钥。如果密钥丢失，则拒绝存储秘密值 |

建议在生产环境中使用`RUMI_SECRETS_ALLOW_PLAINTEXT=false`。

---

## 打包导入/应用

### 导入（进入暂存区）

```bash
curl -X POST http://localhost:8765/api/packs/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/my_pack.zip"}'
```

支持文件夹/`.zip`/`.rumipack`（zip兼容）。

### 应用（从暂存到生态系统应用）

```bash
curl -X POST http://localhost:8765/api/packs/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"staging_id": "abc123"}'
```

应用期间会自动创建备份。如果`pack_id`和`pack_identity`与现有包不匹配，它将被拒绝。

---

## 共享商店管理

用于在 Pack 之间共享 Store 的管理 API。共享请求需要手动批准 (SharedStoreManager)。

### 共享商店列表

```bash
curl http://localhost:8765/api/stores/shared \
  -H "Authorization: Bearer YOUR_TOKEN"
```

响应示例：

```json
{
  "success": true,
  "data": {
    "shared_stores": [
      {
        "store_id": "shared_data",
        "owner_pack": "pack_a",
        "shared_with": ["pack_b", "pack_c"],
        "status": "approved",
        "approved_at": "2026-01-15T10:00:00Z"
      }
    ]
  }
}
```

### 共享商店授权

```bash
curl -X POST http://localhost:8765/api/stores/shared/approve \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b"
  }'
```

|参数|必填|描述 |
|-----------|------|------|
| §鲁米§0§| ✅ |分享店铺ID |
| §鲁米§0§| ✅ |商店自有包 ID |
| §鲁米§0§| ✅ |分享包ID |

响应示例：

```json
{
  "success": true,
  "data": {
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b",
    "status": "approved",
    "approved_at": "2026-01-15T10:00:00Z"
  }
}
```

### 共享商店取消

```bash
curl -X POST http://localhost:8765/api/stores/shared/revoke \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "shared_data",
    "owner_pack": "pack_a",
    "target_pack": "pack_b"
  }'
```

|参数|必填|描述 |
|-----------|------|------|
| §鲁米§0§| ✅ |目标商店 ID |
| §鲁米§0§| ✅ |商店自有包 ID |
| §鲁米§0§| ✅ |取消共享包 ID |

响应示例：

```json
{
  "success": true,
  "data": {
    "store_id": "shared_data",
    "target_pack": "pack_b",
    "status": "revoked"
  }
}
```

---

## Docker/容器管理

### 检查 Docker 状态

```bash
curl http://localhost:8765/api/docker/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 容器列表

```bash
curl http://localhost:8765/api/containers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 容器启动/停止

```bash
# 起動
curl -X POST http://localhost:8765/api/containers/{pack_id}/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# 停止
curl -X POST http://localhost:8765/api/containers/{pack_id}/stop \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 流程执行

### 获取流列表

```bash
curl http://localhost:8765/api/flows \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 运行流程

```bash
curl -X POST http://localhost:8765/api/flows/hello/run \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"name": "World"}, "timeout": 300}'
```

`inputs`是流输入数据（字典），`timeout`是最大执行时间（秒，默认300，最大600）。

并发运行的数量受`RUMI_MAX_CONCURRENT_FLOWS`环境变量（默认10）的限制。如果达到限制，将返回状态代码`429`。

### 成功响应

```json
{
  "success": true,
  "flow_id": "hello",
  "result": {
    "greeting": {"message": "Hello, World!"}
  },
  "execution_time": 1.234
}
```

`result` 存储流输出。但是，以`_`前缀开头的键（内部键，例如`_kernel_step_status`）将被自动排除。

### 错误响应

```json
{
  "success": false,
  "error": "Flow not found: nonexistent_flow",
  "flow_id": "nonexistent_flow",
  "status_code": 404
}
```

|状态代码 |描述 |
|-------------|------|
| §鲁米§0§|指定的`flow_id`不存在|
| §鲁米§0§|流程执行超时 |
| §鲁米§0§|达到并发执行限制 (`RUMI_MAX_CONCURRENT_FLOWS`) |
| §鲁米§0§|运行 Flow 时发生意外错误 |
| §鲁米§0§|系统暂时不可用（启动等）|

### 响应大小限制

如果流程执行结果超过`RUMI_MAX_RESPONSE_BYTES`（默认 4MB），则会被截断。如果发生截断，响应将标记为`"truncated": true`。

---

## 权限管理

这是一个 API，用于允许和执行 Pack 上的特权操作（例如`pack.update`、`system.restart`等）。它是一种独立于能力授予的机制，用于明确允许主机侧的危险操作。

### 权限列表

```bash
curl http://localhost:8765/api/privileges \
  -H "Authorization: Bearer YOUR_TOKEN"
```

响应示例：

```json
{
  "success": true,
  "data": {
    "privileges": [
      {
        "privilege_id": "pack.update",
        "description": "Pack の更新適用を許可",
        "granted_packs": ["updater_pack"]
      },
      {
        "privilege_id": "system.diagnostics",
        "description": "システム診断情報の取得を許可",
        "granted_packs": []
      }
    ]
  }
}
```

### 特权授予

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/grant/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

|参数|必填|描述 |
|-----------|------|------|
| `pack_id`（路径参数）| ✅ |目标包 ID |
| `privilege_id`（路径参数）| ✅ |授予权限ID |

响应示例：

```json
{
  "success": true,
  "data": {
    "pack_id": "updater_pack",
    "privilege_id": "pack.update",
    "granted_at": "2026-02-15T10:00:00Z"
  }
}
```

### 特权执行

```bash
curl -X POST http://localhost:8765/api/privileges/{pack_id}/execute/{privilege_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"args": {"target_pack": "my_pack", "staging_id": "abc123"}}'
```

|参数|必填|描述 |
|-----------|------|------|
| `pack_id`（路径参数）| ✅ |执行源包ID |
| `privilege_id`（路径参数）| ✅ |要执行的权限 ID |
| §鲁米§0§（身体）|可选|传递给特权操作的参数 |

响应示例：

```json
{
  "success": true,
  "data": {
    "pack_id": "updater_pack",
    "privilege_id": "pack.update",
    "result": {"status": "applied", "target_pack": "my_pack"},
    "executed_at": "2026-02-15T10:05:00Z"
  }
}
```

来自非特权包的执行请求将被拒绝并显示`403 Forbidden`。

---

## UDS套接字设置

用于以严格模式从 Pack 执行容器访问 UDS 套接字的设置。

### 环境变量

|环境变量|描述 |默认|
|----------|------|-----------|
| §鲁米§0§|出口套接字 GID |无 |
| §鲁米§0§|功能套接字 GID |无 |
| §鲁米§0§|出口套接字权限 | §鲁米§1§ |
| §鲁米§0§|能力 Socket 权限 | §鲁米§1§ |
| §鲁米§0§|出口套接字基目录| §鲁米§1§ |
| §鲁米§0§|能力套接字基目录| §鲁米§1§ |

### 配置步骤

1. 确定您的专用GID（例如1099）
2.设置环境变量：
   ```bash
   export RUMI_EGRESS_SOCKET_GID=1099
   export RUMI_CAPABILITY_SOCKET_GID=1099
   ```
3、指定GID的组是在创建socket时自动设置的。
4. `--group-add=1099` 将在`docker run`时自动授予

如果未设置 GID，则无法从容器访问套接字 (nobody:65534)。

---

## 如何读取审计日志

审核日志以`{category}_{YYYY-MM-DD}.jsonl` 格式存储在`user_data/audit/` 中。

### 基础阅读

```bash
# 今日のネットワークログ
cat user_data/audit/network_$(date +%Y-%m-%d).jsonl | jq .

# 拒否されたリクエスト
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.success == false)'

# 権限操作のログ
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq .

# lib 実行ログ
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# capability grant 操作
cat user_data/audit/permission_$(date +%Y-%m-%d).jsonl | jq 'select(.details.permission_type == "capability_grant")'

# principal_id 上書き警告
cat user_data/audit/security_$(date +%Y-%m-%d).jsonl | jq 'select(.action == "principal_id_overridden")'

# 共有辞書の操作履歴
cat user_data/settings/shared_dict/journal.jsonl | jq .

# 循環検出された共有辞書操作
cat user_data/settings/shared_dict/journal.jsonl | jq 'select(.result == "cycle_detected")'
```

### 类别列表

|类别 |内容 |
|----------|------|
| §鲁米§0§|流程执行 |
| §鲁米§0§|应用修改器 |
| §鲁米§0§|块执行 |
| §鲁米§0§|包审批操作|
| §鲁米§0§|权限操作|
| §鲁米§0§|网络通讯|
| §鲁米§0§|安全事件|
| §鲁米§0§|系统事件|

---

## 待导出

`user_data/pending/summary.json` 在启动时自动生成。外部工具只需读取该文件即可了解审批状态。

```bash
cat user_data/pending/summary.json | jq .
```

---

## 身份验证令牌

所有 HTTP API 端点都需要使用 `Authorization: Bearer YOUR_TOKEN` 标头进行身份验证。该令牌源自 HMAC 密钥。

### 验证令牌

该令牌将在启动时显示在控制台中。此外，由于它是从 HMAC 密钥文件 (`user_data/settings/.hmac_key`) 派生的，因此只要存在相同的密钥文件，令牌就是不可变的。

如果密钥文件不存在，则首次启动时会自动生成。

### 代币轮换

通过轮换（重新生成）HMAC 密钥来更改令牌。

```bash
# HMAC 鍵ローテーションを有効にして起動
export RUMI_HMAC_ROTATE=true
python app.py
```

设置`RUMI_HMAC_ROTATE=true` 将在下次启动时用新密钥替换现有的 HMAC 密钥。轮换后，之前的token将不再有效，请更新所有API客户端的配置。

旋转仅执行一次。轮换完成后，将`RUMI_HMAC_ROTATE`返回至`false`或删除环境变量。

---

## 结构化日志设置

### 环境变量

|环境变量|描述 |默认|
|----------|------|-----------|
| §鲁米§0§|日志级别。调试/信息/警告/错误/严重| §鲁米§1§ |
| §鲁米§0§|输出格式。 json/文本 | §鲁米§1§ |

### 如何设置

```bash
export RUMI_LOG_LEVEL=DEBUG
export RUMI_LOG_FORMAT=text
python app.py --headless
```

`configure_logging()` 在 app.py 启动时自动调用，并应用于`rumi.*`命名空间中的记录器。

### JSON格式输出示例

```json
{"timestamp": "2026-02-24T12:00:00.000000Z", "level": "INFO", "module": "rumi.kernel.core", "message": "Flow loaded", "correlation_id": "req-123"}
```

### 文本格式输出示例

```
2026-02-24T12:00:00.000000Z [INFO] rumi.kernel.core - Flow loaded (correlation_id=req-123)
```

---

## 弃用警告级别控制

### 环境变量

|环境变量|描述 |默认|
|----------|------|-----------|
| §鲁米§0§|调用已弃用的 API 时的行为 | §鲁米§1§ |

|价值|行为 |
|-----|------|
| §鲁米§0§| `DeprecationWarning` 发布为 `warnings.warn` |
| §鲁米§0§| `DeprecationWarning` 提出例外 |
| §鲁米§0§|什么都不做 |
| §鲁米§0§| `logging` | 警告级别输出

### 设置示例

```bash
export RUMI_DEPRECATION_LEVEL=error
python app.py --headless
```

---

## 健康检查操作

### 使用 CLI 检查

```bash
python app.py --health
```

如果状态为`"UP"`，则返回退出代码 0，否则返回退出代码 1。

### 程序化使用

```python
from core_runtime.health import get_health_checker, probe_disk_space
checker = get_health_checker()
checker.register_probe("disk", lambda: probe_disk_space("/"))
result = checker.aggregate_health()
# result["status"]: "UP" / "DOWN" / "DEGRADED" / "UNKNOWN"
```

### 添加自定义探针

```python
from core_runtime.health import HealthStatus
def my_probe() -> HealthStatus:
    # カスタムチェックロジック
    return HealthStatus.UP
checker.register_probe("my_service", my_probe)
```

---

## 检查指标

### 拍摄快照

```python
from core_runtime.metrics import get_metrics_collector
collector = get_metrics_collector()
snapshot = collector.snapshot()
# snapshot["counters"], snapshot["gauges"], snapshot["histograms"]
```

### 自动收集的指标

第 15 波中自动收集以下指标：

|指标名称 |类型 |描述 |标签 |
|-------------|------|------|--------|
| §鲁米§0§|柜台 |步骤执行成功计数 |处理程序 |
| §鲁米§0§|柜台 |步骤执行失败计数|处理程序 |
| §鲁米§0§|柜台 |流程执行完成计数 |流_id |
| §鲁米§0§|仪表| Docker 可用性 | — |
| §鲁米§0§|柜台 |容器启动成功次数| — |
| §鲁米§0§|柜台 |容器启动失败次数| — |
| §鲁米§0§|仪表|注册流量数量 | — |
| §鲁米§0§|直方图| Python 文件执行时间（毫秒）| — |

---

## 包模板生成（脚手架）

生成新 Pack 模板的命令行工具。

### 如何使用

```bash
python -m core_runtime.pack_scaffold <pack_id> [--template TEMPLATE] [--output-dir DIR]
```

### 模板列表

|模板|描述 |
|-------------|------|
| `minimal`（默认）|最小配置（ecosystem.json + run.py）|
| §鲁米§0§|具有能力处理程序|
| §鲁米§0§|具有流程定义|
| §鲁米§0§|全部包含 |

### 执行示例

```bash
python -m core_runtime.pack_scaffold my-pack --template full --output-dir ecosystem/
```

---

## 错误码参考

错误代码的组织格式为`RUMI-{CATEGORY}-{3_DIGIT_NUMBER}`。每个错误都附带一个建议。

### 类别列表

|类别 |描述 |示例 |
|---------|------|-----|
| §鲁米§0§|认证/授权 | `RUMI-AUTH-001`（令牌无效）|
| §鲁米§0§|网络| `RUMI-NET-001`（连接失败）|
| §鲁米§0§|流程执行 | `RUMI-FLOW-001`（未发现流）|
| §鲁米§0§|包管理| `RUMI-PACK-001`（pack_id 无效）|
| §鲁米§0§|能力| `RUMI-CAP-001`（未发现的能力）|
| §鲁米§0§|验证 | `RUMI-VAL-001`（空值）|
| §鲁米§0§|系统概况| `RUMI-SYS-001`（内部错误）|

---

## 环境变量引用

控制 Rumi AI OS 行为的环境变量列表。

|变量名 |默认|描述 |
|--------|-----------|------|
| §鲁米§0§| §鲁米§1§ |安全模式。 `strict`（需要 Docker）或 `permissive`（不需要 Docker，用于开发）|
| §鲁米§0§| §鲁米§1§ |日志级别。 §鲁米§2§ / §鲁米§3§ / §鲁米§4§ / §鲁米§5§ / §鲁米§6§ |
| §鲁米§0§| §鲁米§1§ |日志输出格式。 `json`（结构化 JSON）或 `text`（人类文本）|
| §鲁米§0§| §鲁米§1§ |调用已弃用的 API 时的行为。 §鲁米§2§ / §鲁米§3§ / §鲁米§4§ / §鲁米§5§ |
| §鲁米§0§|无 |用于 Fernet 加密 Secrets 的密钥（Base64 编码）。如果未设置，则回退到`.secrets_key`文件或自动生成|
| §鲁米§0§| §鲁米§1§ |允许明文秘密。 `auto`（如果加密密钥不可用，另存为纯文本），`true`（始终允许纯文本），`false`（需要加密密钥，没有密钥则拒绝存储）|
| §鲁米§0§| §鲁米§1§ (4MB) |流程执行结果和出口代理响应的最大大小（字节）|
| §鲁米§0§| §鲁米§1§ |同时执行 Flow 的数量上限 |
| §鲁米§0§| §鲁米§1§ (1MB) | HTTP API 接受的请求正文的最大大小（字节） |
| §鲁米§0§| §鲁米§1§ | API服务器绑定地址。如果外部发布，请更改为`0.0.0.0`（不推荐）|
| §鲁米§0§|无 |以逗号分隔的 CORS 允许来源列表（例如 `http://localhost:3000,http://localhost:8080`）|
| §鲁米§0§| §鲁米§1§ |如果设置为`true`，HMAC 密钥将在下次启动时轮换 |
| §鲁米§0§| §鲁米§1§ |设置为`true`以在诊断日志中包含详细信息 |
| §鲁米§0§|无 |出口 UDS 套接字的 GID。 | §鲁米§1§ |无 |出口 UDS 套接字的 GID。需要在严格模式下从容器访问套接字 |
| §鲁米§0§|无 |能力 UDS 套接字 GID。需要在严格模式下从容器访问套接字 |
| §鲁米§0§| §鲁米§1§ |出口 UDS 套接字权限 |
| §鲁米§0§| §鲁米§1§ |能力UDS套接字权限|
| §鲁米§0§| §鲁米§1§ |出口 UDS 套接字基目录 |
| §鲁米§0§| §鲁米§1§ |能力UDS套接字基目录|
| §鲁米§0§| §鲁米§1§ | `secrets.get`速率限制（次/分钟/包，滑动窗口）|
| §鲁米§0§| §鲁米§1§ | local_pack兼容模式。 `off`（已禁用）或`require_approval`（需要批准后有效，不推荐）|

---

## 故障排除

### Docker 不可用

```
Error: Docker is required but not available
```

开发时，请使用`--permissive`标志或设置环境变量`RUMI_SECURITY_MODE=permissive`。

### 包未获批准

```bash
# 承認待ちを確認
curl http://localhost:8765/api/packs/pending \
  -H "Authorization: Bearer YOUR_TOKEN"

# 承認
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 包修改

如果由于文件更改而发生哈希不匹配，它将自动禁用。请重新授权。

```bash
curl -X POST http://localhost:8765/api/packs/{pack_id}/approve \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 网络访问被拒绝

```bash
# Grant 状態を確認
curl http://localhost:8765/api/network/list \
  -H "Authorization: Bearer YOUR_TOKEN"

# 権限を付与
curl -X POST http://localhost:8765/api/network/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pack_id": "my_pack", "allowed_domains": ["api.example.com"], "allowed_ports": [443]}'
```

### 能力无法使用

您不能仅使用批准（信任+复制）。需要补助金。

```bash
curl -X POST http://localhost:8765/api/capability/grants/grant \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "my_pack", "permission_id": "fs.read"}'
```

### 能力处理程序批准因 SHA-256 不匹配而失败

扫描后handler.py的内容发生了变化。请再次运行扫描，使用新的candidate_key重新创建pending，然后再次批准。

### 安装 pip 依赖项被拒绝

1. 检查包是否被认可（严格模式下需要）
2. 检查`requirements.lock`的语法是否正确（仅允许`NAME==VERSION`）
3. 检查`index_url`是否是带有https的外部主机

### 无法访问 UDS 套接字

1. 检查`RUMI_EGRESS_SOCKET_GID` / `RUMI_CAPABILITY_SOCKET_GID`是否已设置
2.检查socket文件权限：`ls -la /run/rumi/egress/packs/`
3. 最后的手段：`RUMI_EGRESS_SOCKET_MODE=0666`（不推荐）

### 更新包时身份错误

```
Error: pack_identity mismatch
```

您正尝试使用具有不同`pack_identity`的包覆盖现有包。如果是有意替换，请先删除现有的Pack，然后重新应用。

### lib 未执行

```bash
# 監査ログで確認
cat user_data/audit/system_$(date +%Y-%m-%d).jsonl | jq 'select(.action | contains("lib"))'

# 記録を確認（Kernel ハンドラ kernel:lib.list_records）
# 記録をクリアして再実行を強制（Kernel ハンドラ kernel:lib.clear_record）
```

### 修饰符未应用

1. 检查`target_flow_id`是否正确
2. 检查目标Flow中是否存在`phase`
3. 检查是否满足`requires`的条件
4.查看审计日志：
   ```bash
   cat user_data/audit/modifier_application_$(date +%Y-%m-%d).jsonl | jq .
   ```

### 旧目录警告

```
WARNING: Using legacy flow path. This is DEPRECATED and will be removed.
```

从包中的`flow/`或`ecosystem/flows/`迁移至`flows/`、`user_data/shared/flows/`或`flows/`。
