"""
backend_core.ecosystem package

エコシステムの公開APIをまとめる __init__。
app.py から `from backend_core.ecosystem import initialize_ecosystem` のように
インポートできることを保証する。

重要:
- ここが無い（またはinitialize_ecosystem等をexportしない）と
  app.py の初期化が失敗し、compat の sys.path 注入も走らず
  ai_client/tool/prompt などのコンポーネントimportが壊れる。
"""

from .initializer import (
    EcosystemInitializer,
    initialize_ecosystem,
    validate_ecosystem,
)

from .mounts import (
    MountManager,
    get_mount_manager,
    get_mount_path,
    initialize_mounts,
    DEFAULT_MOUNTS,
)

from .registry import (
    Registry,
    get_registry,
    reload_registry,
)

from .active_ecosystem import (
    ActiveEcosystemManager,
    get_active_ecosystem_manager,
    get_active_pack_identity,
    get_component_override,
)

from .addon_manager import (
    AddonManager,
    get_addon_manager,
    reload_addon_manager,
)

__all__ = [
    # initializer
    "EcosystemInitializer",
    "initialize_ecosystem",
    "validate_ecosystem",

    # mounts
    "MountManager",
    "get_mount_manager",
    "get_mount_path",
    "initialize_mounts",
    "DEFAULT_MOUNTS",

    # registry
    "Registry",
    "get_registry",
    "reload_registry",

    # active ecosystem
    "ActiveEcosystemManager",
    "get_active_ecosystem_manager",
    "get_active_pack_identity",
    "get_component_override",

    # addons
    "AddonManager",
    "get_addon_manager",
    "reload_addon_manager",
]
