"""
paths.py - パス定義とPack探索の集約モジュール

ディレクトリ構造の定数、Pack探索ロジック、パス候補解決を
1箇所に集約する。他モジュールは散在定数ではなくこのモジュールを参照する。

依存: stdlib のみ（他の core_runtime モジュールへの依存ゼロ）

探索ルール:
- ecosystem.json の探索: 直下優先 → サブディレクトリ探索
- Pack discovery: ecosystem/* (packs除外) → ecosystem/packs/* (互換)
- canonical pack_id はディレクトリ名
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Tuple


# ======================================================================
# 定数
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_user_data_dir() -> Path:
    configured = os.environ.get("RUMI_USER_DATA")
    if configured:
        return Path(configured)
    return BASE_DIR / "user_data"


USER_DATA_DIR = _resolve_user_data_dir()

# Pack supply roots.  Runtime packs are resolved from MANAGED_PACKS_DIR first;
# bundled directories are seed/fallback locations only.
BUNDLED_LEGACY_ECOSYSTEM_DIR = BASE_DIR / "ecosystem"
PACK_SEEDS_DIR = BASE_DIR / "pack_seeds"
MANAGED_PACKS_DIR = USER_DATA_DIR / "packs"
PACK_STATE_DIR = USER_DATA_DIR / "pack_state"

# Backward-compatible string constants used by existing modules.
ECOSYSTEM_DIR = str(BUNDLED_LEGACY_ECOSYSTEM_DIR)

# core_pack 配置ディレクトリ（Layer 1: OS カーネルモジュール相当）
CORE_PACK_DIR = str(BASE_DIR / "core_runtime" / "core_pack")

# core_pack の pack_id プレフィックス
CORE_PACK_ID_PREFIX = "core_"


# 互換: 旧 packs サブディレクトリ
LEGACY_PACKS_SUBDIR = "packs"

# 公式 Flow ディレクトリ（承認不要、上書き不可）
OFFICIAL_FLOWS_DIR = str(BASE_DIR / "flows")

# ユーザー管理の共有 Flow/Modifier ディレクトリ（承認不要）
USER_SHARED_DIR = str(USER_DATA_DIR / "shared")
USER_SHARED_FLOWS_DIR = str(USER_DATA_DIR / "shared" / "flows")
USER_SHARED_MODIFIERS_DIR = str(USER_DATA_DIR / "shared" / "flows" / "modifiers")

# local_pack 互換（deprecated、優先順位最低）
LOCAL_PACK_ID = "local_pack"
LOCAL_PACK_DIR = str(BASE_DIR / "ecosystem" / "flows")
LOCAL_PACK_MODIFIERS_DIR = str(BASE_DIR / "ecosystem" / "flows" / "modifiers")

# 承認データ保存先
GRANTS_DIR = str(USER_DATA_DIR / "permissions")

# Pack data 保存先
PACK_DATA_BASE_DIR = str(MANAGED_PACKS_DIR)

# Pack discovery 時に除外するディレクトリ名
EXCLUDED_DIRS = frozenset({
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".eggs",
    "packs",       # legacy root — 別走査するため除外
    "flows",       # local_pack 互換用 — pack扱いしない
    "setup_pack",  # setup-pack metadata root — runtime packではない
})


# ======================================================================
# PackLocation dataclass
# ======================================================================

@dataclass(frozen=True)
class PackLocation:
    """
    Packの物理位置情報

    Attributes:
        pack_dir:            Packのルートディレクトリ (ecosystem/<dir>)
        pack_id:             canonical pack_id（= ディレクトリ名）
        ecosystem_json_path: ecosystem.json の絶対パス
        pack_subdir:         ecosystem.json が見つかったディレクトリ（= Packの実体基点）
        is_legacy:           ecosystem/packs/ 互換ルート由来か
        source:              managed/seed/bundled_legacy/legacy
        mutable:             runtime may write into this source
        version:             discovered managed current version, when known
        current_pointer_path: managed current.json path, when applicable
    """
    pack_dir: Path
    pack_id: str
    ecosystem_json_path: Path
    pack_subdir: Path
    is_legacy: bool = False
    source: Literal["managed", "seed", "bundled_legacy", "legacy"] = "bundled_legacy"
    mutable: bool = False
    version: Optional[str] = None
    current_pointer_path: Optional[Path] = None


# ======================================================================
# ecosystem.json 探索
# ======================================================================

def find_ecosystem_json(pack_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    pack_dir 内で ecosystem.json を探索する。

    探索順（直下優先）:
      1. pack_dir/ecosystem.json（直下にあればそれが最も自然な基点）
      2. pack_dir/<subdir>/ecosystem.json（sorted順で最初に見つかったもの）

    除外サブディレクトリ: EXCLUDED_DIRS に該当するもの

    Returns:
        (ecosystem_json_path, pack_subdir) または (None, None)
    """
    if not pack_dir.is_dir():
        return None, None

    # 1. 直下を優先
    direct = pack_dir / "ecosystem.json"
    if direct.exists() and direct.is_file():
        return direct, pack_dir

    # 2. サブディレクトリを sorted 順で探索
    try:
        subdirs = sorted(
            (d for d in pack_dir.iterdir()
             if d.is_dir() and d.name not in EXCLUDED_DIRS and not d.name.startswith(".")),
            key=lambda d: d.name
        )
    except OSError:
        return None, None

    for subdir in subdirs:
        candidate = subdir / "ecosystem.json"
        if candidate.exists() and candidate.is_file():
            return candidate, subdir

    return None, None


# ======================================================================
# Pack Discovery
# ======================================================================

def _read_json_file(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _declared_pack_id_from_manifest(pack_subdir: Path) -> Optional[str]:
    pack_manifest = _read_json_file(pack_subdir / "rumi-pack.json")
    if pack_manifest:
        pack_id = pack_manifest.get("pack_id")
        if pack_id:
            return str(pack_id)
    ecosystem = _read_json_file(pack_subdir / "ecosystem.json")
    if ecosystem:
        pack_id = ecosystem.get("pack_id")
        if pack_id:
            return str(pack_id)
    return None


def _declared_version(pack_subdir: Path) -> Optional[str]:
    pack_manifest = _read_json_file(pack_subdir / "rumi-pack.json")
    if pack_manifest and pack_manifest.get("version"):
        return str(pack_manifest["version"])
    ecosystem = _read_json_file(pack_subdir / "ecosystem.json")
    if ecosystem and ecosystem.get("version"):
        return str(ecosystem["version"])
    return None


def _safe_relative_target(base: Path, relative: str) -> Optional[Path]:
    rel_path = Path(relative)
    if rel_path.is_absolute() or "\x00" in relative or ".." in rel_path.parts:
        return None
    target = base / rel_path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return target


def _iter_pack_dirs(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    try:
        return sorted(
            (
                d for d in root.iterdir()
                if d.is_dir() and d.name not in EXCLUDED_DIRS and not d.name.startswith(".")
            ),
            key=lambda d: d.name,
        )
    except OSError:
        return []


def _add_location_if_valid(
    found: Dict[str, PackLocation],
    *,
    canonical_pack_id: str,
    pack_dir: Path,
    source: Literal["managed", "seed", "bundled_legacy", "legacy"],
    mutable: bool,
    is_legacy: bool = False,
    version: Optional[str] = None,
    current_pointer_path: Optional[Path] = None,
) -> None:
    if canonical_pack_id in found:
        return
    eco_json, pack_subdir = find_ecosystem_json(pack_dir)
    if eco_json is None or pack_subdir is None:
        return
    declared_id = _declared_pack_id_from_manifest(pack_subdir)
    if declared_id and declared_id != canonical_pack_id and source == "managed":
        return
    found[canonical_pack_id] = PackLocation(
        pack_dir=pack_dir,
        pack_id=canonical_pack_id,
        ecosystem_json_path=eco_json,
        pack_subdir=pack_subdir,
        is_legacy=is_legacy,
        source=source,
        mutable=mutable,
        version=version or _declared_version(pack_subdir),
        current_pointer_path=current_pointer_path,
    )


def discover_pack_locations(
    ecosystem_dir: Optional[str] = None,
    *,
    include_managed: bool = True,
) -> List[PackLocation]:
    """
    Packの物理位置を全探索する。

    走査順:
      1. user_data/packs/*/current.json の解決先
      2. user_data/packs/* 直下 ecosystem.json fallback
      3. BASE_DIR/pack_seeds/* fallback
      4. BASE_DIR/ecosystem/* legacy read-only fallback
      5. BASE_DIR/ecosystem/packs/* legacy read-only fallback

    重複 pack_id が出た場合:
      - ecosystem/* 由来が優先（互換ルートは無視）
      - 同一ルート内での重複は最初に見つかったものを採用

    Args:
        ecosystem_dir: エコシステムルート（デフォルト ECOSYSTEM_DIR）
        include_managed: Trueならuser_data/pack_seedsを含める。Falseなら指定rootだけを検証する。

    Returns:
        PackLocation のリスト（pack_id 昇順）
    """
    root = Path(ecosystem_dir or ECOSYSTEM_DIR)
    found: Dict[str, PackLocation] = {}  # pack_id -> PackLocation

    if include_managed:
        # --- Pass 1: managed current pointers ---
        for pack_root in _iter_pack_dirs(MANAGED_PACKS_DIR):
            pointer_path = pack_root / "current.json"
            current = _read_json_file(pointer_path)
            if not current:
                continue
            pointer_pack_id = str(current.get("pack_id") or pack_root.name)
            if pointer_pack_id != pack_root.name:
                continue
            rel = current.get("path")
            if not isinstance(rel, str) or not rel:
                continue
            target = _safe_relative_target(pack_root, rel)
            if target is None:
                continue
            _add_location_if_valid(
                found,
                canonical_pack_id=pointer_pack_id,
                pack_dir=target,
                source="managed",
                mutable=True,
                version=str(current.get("version") or "") or None,
                current_pointer_path=pointer_path,
            )

        # --- Pass 2: managed direct ecosystem.json fallback ---
        for pack_root in _iter_pack_dirs(MANAGED_PACKS_DIR):
            _add_location_if_valid(
                found,
                canonical_pack_id=pack_root.name,
                pack_dir=pack_root,
                source="managed",
                mutable=True,
            )

        # --- Pass 3: bundled seed fallback ---
        for pack_dir in _iter_pack_dirs(PACK_SEEDS_DIR):
            _add_location_if_valid(
                found,
                canonical_pack_id=pack_dir.name,
                pack_dir=pack_dir,
                source="seed",
                mutable=False,
            )

    # --- Pass 4: BASE_DIR/ecosystem/* read-only legacy fallback ---
    if root.is_dir():
        for pack_dir in _iter_pack_dirs(root):
            _add_location_if_valid(
                found,
                canonical_pack_id=pack_dir.name,
                pack_dir=pack_dir,
                source="bundled_legacy",
                mutable=False,
                is_legacy=False,
            )

    # --- Pass 5: BASE_DIR/ecosystem/packs/* read-only legacy fallback ---
    legacy_root = root / LEGACY_PACKS_SUBDIR
    for pack_dir in _iter_pack_dirs(legacy_root):
        _add_location_if_valid(
            found,
            canonical_pack_id=pack_dir.name,
            pack_dir=pack_dir,
            source="legacy",
            mutable=False,
            is_legacy=True,
        )

    # pack_id 昇順で返す
    return sorted(found.values(), key=lambda loc: loc.pack_id)


# ======================================================================
# Pack 内パス候補ヘルパー
# ======================================================================

def get_pack_flow_dirs(pack_subdir: Path) -> List[Path]:
    """
    Pack 内の Flow ファイル探索候補ディレクトリを返す。

    候補順:
      1. pack_subdir/flows/
      2. pack_subdir/backend/flows/  (互換)

    Returns:
        存在するディレクトリのみのリスト
    """
    candidates = [
        pack_subdir / "flows",
        pack_subdir / "backend" / "flows",
    ]
    return [d for d in candidates if d.is_dir()]


def get_pack_modifier_dirs(pack_subdir: Path) -> List[Path]:
    """
    Pack 内の Modifier ファイル探索候補ディレクトリを返す。

    候補順:
      1. pack_subdir/flows/modifiers/
      2. pack_subdir/backend/flows/modifiers/  (互換)

    Returns:
        存在するディレクトリのみのリスト
    """
    candidates = [
        pack_subdir / "flows" / "modifiers",
        pack_subdir / "backend" / "flows" / "modifiers",
    ]
    return [d for d in candidates if d.is_dir()]


def get_pack_block_dirs(pack_subdir: Path) -> List[Path]:
    """
    Pack 内の Block（実行ファイル）探索候補ディレクトリを返す。

    blocks/ は Flow 内の ``python_file_call`` ハンドラが参照する実行ファイルを
    格納するためのディレクトリであり、Registry の components/ スキャン対象ではない。
    blocks/ を使用する Pack は components/ ディレクトリ内にコンポーネントを配置し、
    blocks/ は python_file_call 用のスクリプトのみを格納すべきである。

    候補順:
      1. pack_subdir/blocks/
      2. pack_subdir/backend/blocks/
      3. pack_subdir/backend/components/  (互換)
      4. pack_subdir/backend/              (互換: ファイルが直接置かれるケース)

    Returns:
        存在するディレクトリのみのリスト
    """
    # NOTE: functions/ は FunctionRegistry 経由で解決されるため、探索対象に含めない。
    candidates = [
        pack_subdir / "blocks",
        pack_subdir / "backend" / "blocks",
        pack_subdir / "backend" / "components",
        pack_subdir / "backend",
    ]
    return [d for d in candidates if d.is_dir()]


def get_pack_lib_dirs(pack_subdir: Path) -> List[Path]:
    """
    Pack 内の lib ディレクトリ候補を返す。

    候補順:
      1. pack_subdir/lib/
      2. pack_subdir/backend/lib/  (互換)

    Returns:
        存在するディレクトリのみのリスト
    """
    candidates = [
        pack_subdir / "lib",
        pack_subdir / "backend" / "lib",
    ]
    return [d for d in candidates if d.is_dir()]


# ======================================================================
# Shared flows/modifiers ヘルパー
# ======================================================================

def get_shared_flow_dir() -> Path:
    """user_data/shared/flows ディレクトリの Path を返す（存在チェックなし）。"""
    return Path(USER_SHARED_FLOWS_DIR)


def get_shared_modifier_dir() -> Path:
    """user_data/shared/flows/modifiers ディレクトリの Path を返す（存在チェックなし）。"""
    return Path(USER_SHARED_MODIFIERS_DIR)


# ======================================================================
# ecosystem.json pack_id 不一致検出ヘルパー
# ======================================================================

def check_pack_id_mismatch(
    location: PackLocation,
) -> Optional[str]:
    """
    ecosystem.json 内の pack_id がディレクトリ名と異なる場合、
    警告メッセージを返す。一致していれば None。

    呼び出し元が diagnostics/audit に記録する責務を持つ。
    """
    import json as _json

    try:
        with open(location.ecosystem_json_path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        return None  # 読めなければ別のバリデーションで捕捉される

    declared_id = data.get("pack_id")
    if declared_id and declared_id != location.pack_id:
        return (
            f"ecosystem.json declares pack_id='{declared_id}' but "
            f"canonical pack_id (directory name) is '{location.pack_id}'. "
            f"Internal key will use '{location.pack_id}'."
        )
    return None


# ======================================================================
# pack_subdir 用 boundary チェックヘルパー
# ======================================================================

def is_path_within(target: Path, boundary: Path) -> bool:
    """
    target が boundary 配下にあるか判定する。

    シンボリックリンクは resolve() で実体パスに変換してから比較する。
    """
    try:
        resolved_target = target.resolve()
        resolved_boundary = boundary.resolve()
        resolved_target.relative_to(resolved_boundary)
        return True
    except (ValueError, OSError):
        return False
