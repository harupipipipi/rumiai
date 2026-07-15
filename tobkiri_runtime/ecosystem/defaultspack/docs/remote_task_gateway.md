# Remote Task Gateway

The remote task gateway exposes a small authenticated polling API on the
Kernel Pack API. It lets another PC, phone, or CLI submit natural-language work
to the host PC without adding a new agent runtime.

This gateway uses the existing defaultspack team workspace runtime. Tasks are created
in the operations company, dispatched through `agent.delegate`, and remain
subject to the local approval, workspace, audit, and tool policy paths.

## Host PC

Bind the Kernel API to the LAN interface only when you intend to accept LAN
clients:

```bash
RUMI_API_BIND_ADDRESS=0.0.0.0
```

Clients must send the Kernel API bearer token:

```bash
Authorization: Bearer $RUMI_TOKEN
```

## Submit A Task

```bash
curl -s \
  -H "Authorization: Bearer $RUMI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "このrepoの失敗テストを調べて修正方針を出して",
    "target_agent_ids": ["operations_manager"],
    "client": {"kind": "pc", "name": "office-laptop"}
  }' \
  http://HOST_PC_LAN_IP:8765/api/remote/tasks
```

## Get Status

```bash
curl -s \
  -H "Authorization: Bearer $RUMI_TOKEN" \
  http://HOST_PC_LAN_IP:8765/api/remote/tasks/task_xxx
```

States are normalized to:

```text
queued
running
waiting_approval
blocked
completed
cancelled
stale
```

## Poll Events

```bash
curl -s \
  -H "Authorization: Bearer $RUMI_TOKEN" \
  "http://HOST_PC_LAN_IP:8765/api/remote/tasks/task_xxx/events?after=000010"
```

## Cancel

```bash
curl -s \
  -X POST \
  -H "Authorization: Bearer $RUMI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"cancelled from office-laptop"}' \
  http://HOST_PC_LAN_IP:8765/api/remote/tasks/task_xxx/cancel
```

Cancel marks the company task and linked run state as cancelled and notifies the
operations manager inbox. It does not kill OS processes.

## Readiness

```bash
curl -s \
  -H "Authorization: Bearer $RUMI_TOKEN" \
  http://HOST_PC_LAN_IP:8765/api/remote/host/status
```

## Out Of Scope

This gateway does not implement P2P pairing, internet relay, approval mutation,
SSE, WebSocket streaming, or a mobile-specific UI.
