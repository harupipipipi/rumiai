<!-- docs-i18n-links:start -->
[EN](./p2p_security.md) | [JP](./i18n/ja/p2p_security.md) | [KR](./i18n/ko/p2p_security.md) | [CN](./i18n/zh-cn/p2p_security.md)
<!-- docs-i18n-links:end -->

# P2P Security

P2P is treated as an optional ingress surface, not a trust boundary and not a
tool transport. The safe default is no P2P listener, no peer discovery, and no
internet relay.

## Defaults

- P2P is disabled by default.
- The local HTTP/runtime control plane binds to loopback by default
  (`127.0.0.1`/`localhost`/`::1`).
- There is no LAN discovery, multicast, mDNS, DHT, STUN/TURN relay, or hosted
  internet relay in defaultspack.
- Enabling any future peer intake must be explicit local configuration and must
  preserve the same local-admin route guards used by sensitive routes.

## Ingress Boundary

A peer message is equivalent to an external input event:

```text
peer payload
  -> normalized external event
  -> audience/input policy
  -> chat or agent message
  -> normal response/tool planning
```

The peer can add user-visible input. It cannot directly execute a tool, call a
handler, write a file, run a terminal command, push git, install a pack, change
settings, or create a local approval token.

If a peer asks Rumi to perform a sensitive action, that request becomes chat
context. The local runtime may then propose a tool call, but execution still
passes through local policy, risk classification, approval token binding, and
audit.

## Approval Rules

- Remote peers cannot approve local actions.
- Approval tokens are local, one-time, signed, and bound to operation plus
  argument hash.
- Changing the path, command, git target, content, destination, or other
  protected argument after approval invalidates execution.
- The local user's policy decision wins over peer metadata, peer identity, and
  model output.

## Data Handling

Peer identifiers and payload metadata should be logged only after redaction.
Secrets, bearer tokens, cookies, API keys, and provider credentials must never be
accepted from a peer as authority. If a credential is needed, Rumi should ask the
local user through the existing local secret and approval flows.

## Non-Goals

P2P is not a remote desktop protocol, a distributed tool bus, a remote approval
system, a LAN service discovery feature, or a replacement for provider-specific
webhook verification.
