"""
backend_core.ecosystem - 最小インフラ

公式が提供するのは:
- マウント管理（汎用）
- Pack/Component読み込み（汎用）
- UUID生成（汎用）
- 初期化状態管理

公式が提供しないもの:
- 具体的なコンポーネント型
- 具体的なサービス
- アドオン管理（コンポーネント側の責務）
"""

from .mounts import (
    MountManager,
    get_mount_manager,
    get_mount_path,
    DEFAULT_MOUNTS,
)

from .registry import (
    Registry,
    get_registry,
    reload_registry,
    PackInfo,
    ComponentInfo,
)

from .compat import (
    is_ecosystem_initialized,
    mark_ecosystem_initialized,
    get_user_data_dir,
    get_mount_path_safe,
    register_mount_from_component,
    add_to_sys_path,
)

from .uuid_utils import (
    generate_pack_uuid,
    generate_component_uuid,
    validate_uuid,
    parse_uuid,
)

__all__ = [
    # mounts
    "MountManager",
    "get_mount_manager",
    "get_mount_path",
    "DEFAULT_MOUNTS",
    
    # registry
    "Registry",
    "get_registry",
    "reload_registry",
    "PackInfo",
    "ComponentInfo",
    
    # compat
    "is_ecosystem_initialized",
    "mark_ecosystem_initialized",
    "get_user_data_dir",
    "get_mount_path_safe",
    "register_mount_from_component",
    "add_to_sys_path",
    
    # uuid
    "generate_pack_uuid",
    "generate_component_uuid",
    "validate_uuid",
    "parse_uuid",
]
