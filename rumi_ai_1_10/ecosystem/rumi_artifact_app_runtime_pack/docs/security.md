# Security

Artifact apps deny network by default. Client supplied approval flags are never trusted. Untrusted renderer content cannot combine allow-scripts with allow-same-origin, request remote modules, or persist files directly.

Only server-issued approval tokens and defaultspack-shaped approval requests are valid for tool/MCP/API/media handoff prompts. Export and share packages are declarative package contracts; actual file persistence, zip creation, share-link creation, upload, and token minting stay with their owner packs.
