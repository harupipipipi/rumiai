# backend_core/ecosystem/uuid_namespace.py
"""
エコシステム用のUUID名前空間定義

このUUIDはプロジェクト固有の名前空間として使用され、
pack_identityからpack_uuidを決定論的に生成するために使用される。

重要: この値は一度決定したら変更してはならない。
変更すると、既存のすべてのUUIDが無効になる。
"""

import uuid

# プロジェクト固有の名前空間UUID
# このUUIDは手動で生成した固定値であり、uuid4()で一度だけ生成したもの。
# すべてのpack_uuid/component_uuidはこの名前空間を起点にuuid5で派生する。
PACK_NAMESPACE_UUID = uuid.UUID("a3e9f8c2-7b4d-5e1a-9c6f-2d8b4a7e3f1c")

# コンポーネント用のプレフィックス
COMPONENT_PREFIX = "component"

# アドオン用のプレフィックス
ADDON_PREFIX = "addon"
