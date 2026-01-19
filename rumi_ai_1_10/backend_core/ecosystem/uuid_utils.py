# backend_core/ecosystem/uuid_utils.py
"""
UUID生成ユーティリティ

Pack/Component/AddonのUUID v5を生成する。
同じ入力に対して常に同じUUIDを生成する決定論的な方式。
"""

import uuid
from typing import Union

# プロジェクト固有の名前空間UUID（固定値 - 変更禁止）
PACK_NAMESPACE_UUID = uuid.UUID("a3e9f8c2-7b4d-5e1a-9c6f-2d8b4a7e3f1c")

# プレフィックス
COMPONENT_PREFIX = "component"
ADDON_PREFIX = "addon"


def generate_pack_uuid(pack_identity: str) -> uuid.UUID:
    """
    Pack IdentityからPack UUIDを生成
    
    Args:
        pack_identity: Pack識別子（例: "github:haru/default-pack"）
    
    Returns:
        決定論的に生成されたUUID v5
    
    Example:
        >>> generate_pack_uuid("github:haru/default-pack")
        UUID('...')  # 常に同じ値
    """
    if not pack_identity or not isinstance(pack_identity, str):
        raise ValueError("pack_identity must be a non-empty string")
    
    return uuid.uuid5(PACK_NAMESPACE_UUID, pack_identity)


def generate_component_uuid(
    pack_uuid: Union[uuid.UUID, str],
    component_type: str,
    component_id: str
) -> uuid.UUID:
    """
    Component UUIDを生成
    
    Args:
        pack_uuid: 親PackのUUID
        component_type: コンポーネントタイプ（例: "chats", "tool_pack"）
        component_id: コンポーネントID（例: "chats_v1"）
    
    Returns:
        決定論的に生成されたUUID v5
    
    Example:
        >>> pack_uuid = generate_pack_uuid("github:haru/default-pack")
        >>> generate_component_uuid(pack_uuid, "chats", "chats_v1")
        UUID('...')  # 常に同じ値
    """
    if isinstance(pack_uuid, str):
        pack_uuid = uuid.UUID(pack_uuid)
    
    if not component_type or not isinstance(component_type, str):
        raise ValueError("component_type must be a non-empty string")
    
    if not component_id or not isinstance(component_id, str):
        raise ValueError("component_id must be a non-empty string")
    
    # フォーマット: "component:{type}:{id}"
    name = f"{COMPONENT_PREFIX}:{component_type}:{component_id}"
    
    return uuid.uuid5(pack_uuid, name)


def validate_uuid(value: str) -> bool:
    """
    文字列が有効なUUIDかどうかを検証
    
    Args:
        value: 検証する文字列
    
    Returns:
        有効なUUIDの場合True
    """
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def parse_uuid(value: Union[str, uuid.UUID]) -> uuid.UUID:
    """
    文字列またはUUIDオブジェクトをUUIDオブジェクトに変換
    
    Args:
        value: UUID文字列またはUUIDオブジェクト
    
    Returns:
        UUIDオブジェクト
    
    Raises:
        ValueError: 無効なUUID形式の場合
    """
    if isinstance(value, uuid.UUID):
        return value
    
    if isinstance(value, str):
        return uuid.UUID(value)
    
    raise ValueError(f"Invalid UUID type: {type(value)}")
