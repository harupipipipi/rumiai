# backend_core/ecosystem/spec/schema/validator.py
"""
JSON Schema 検証ユーティリティ

エコシステムの各種定義ファイルを検証する。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# jsonschemaライブラリを使用（なければフォールバック）
try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    JsonSchemaValidationError = Exception


class SchemaValidationError(Exception):
    """スキーマ検証エラー"""
    
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []
    
    def __str__(self):
        if self.errors:
            error_list = "\n  - ".join(self.errors)
            return f"{self.args[0]}\n  - {error_list}"
        return self.args[0]


# スキーマファイルのディレクトリ
_SCHEMA_DIR = Path(__file__).parent

# スキーマキャッシュ
_schema_cache: Dict[str, dict] = {}


def _load_schema(schema_name: str) -> dict:
    """スキーマファイルを読み込む"""
    if schema_name in _schema_cache:
        return _schema_cache[schema_name]
    
    schema_file = _SCHEMA_DIR / f"{schema_name}.schema.json"
    
    if not schema_file.exists():
        raise FileNotFoundError(f"スキーマファイルが見つかりません: {schema_file}")
    
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    _schema_cache[schema_name] = schema
    return schema


def _validate_with_jsonschema(data: dict, schema: dict) -> List[str]:
    """jsonschemaライブラリを使用して検証"""
    validator = Draft7Validator(schema)
    errors = []
    
    for error in sorted(validator.iter_errors(data), key=lambda e: e.path):
        path = "/".join(str(p) for p in error.absolute_path)
        if path:
            errors.append(f"[/{path}] {error.message}")
        else:
            errors.append(error.message)
    
    return errors


def _validate_basic(data: dict, schema: dict) -> List[str]:
    """基本的な検証（jsonschemaがない場合のフォールバック）"""
    errors = []
    
    # 必須フィールドのチェック
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"必須フィールド '{field}' がありません")
    
    # プロパティの型チェック
    properties = schema.get("properties", {})
    for field, value in data.items():
        if field in properties:
            prop_schema = properties[field]
            expected_type = prop_schema.get("type")
            
            if expected_type:
                # 型の配列対応（["string", "null"]など）
                if isinstance(expected_type, list):
                    type_names = expected_type
                else:
                    type_names = [expected_type]
                
                type_map = {
                    "string": str,
                    "integer": int,
                    "number": (int, float),
                    "boolean": bool,
                    "array": list,
                    "object": dict,
                    "null": type(None)
                }
                
                valid_types = tuple(
                    type_map.get(t, object) for t in type_names if t in type_map
                )
                
                if valid_types and not isinstance(value, valid_types):
                    errors.append(
                        f"フィールド '{field}' の型が不正です: "
                        f"期待={type_names}, 実際={type(value).__name__}"
                    )
    
    # additionalPropertiesのチェック
    if schema.get("additionalProperties") is False:
        allowed_props = set(properties.keys())
        for field in data.keys():
            if field not in allowed_props:
                errors.append(f"不明なフィールド '{field}'")
    
    return errors


def validate(
    data: dict,
    schema_name: str,
    raise_on_error: bool = True
) -> List[str]:
    """
    データをスキーマで検証
    
    Args:
        data: 検証対象のデータ
        schema_name: スキーマ名（"ecosystem", "component_manifest", "addon"）
        raise_on_error: エラー時に例外を発生させるか
    
    Returns:
        エラーメッセージのリスト（エラーがなければ空）
    
    Raises:
        SchemaValidationError: raise_on_error=True かつ検証エラーの場合
    """
    schema = _load_schema(schema_name)
    
    if HAS_JSONSCHEMA:
        errors = _validate_with_jsonschema(data, schema)
    else:
        errors = _validate_basic(data, schema)
    
    if errors and raise_on_error:
        raise SchemaValidationError(
            f"{schema_name} の検証に失敗しました",
            errors
        )
    
    return errors


def validate_ecosystem(
    data: dict,
    raise_on_error: bool = True
) -> List[str]:
    """
    ecosystem.json を検証
    
    Args:
        data: ecosystem.jsonの内容
        raise_on_error: エラー時に例外を発生させるか
    
    Returns:
        エラーメッセージのリスト
    """
    return validate(data, "ecosystem", raise_on_error)


def validate_component_manifest(
    data: dict,
    raise_on_error: bool = True
) -> List[str]:
    """
    Component manifest.json を検証
    
    Args:
        data: manifest.jsonの内容
        raise_on_error: エラー時に例外を発生させるか
    
    Returns:
        エラーメッセージのリスト
    """
    return validate(data, "component_manifest", raise_on_error)


def validate_addon(
    data: dict,
    raise_on_error: bool = True
) -> List[str]:
    """
    Addon定義を検証
    
    Args:
        data: addon.jsonの内容
        raise_on_error: エラー時に例外を発生させるか
    
    Returns:
        エラーメッセージのリスト
    """
    return validate(data, "addon", raise_on_error)


def validate_json_patch_operations(
    operations: List[dict]
) -> List[str]:
    """
    JSON Patch操作リストを検証（move/copy禁止）
    
    Args:
        operations: パッチ操作のリスト
    
    Returns:
        エラーメッセージのリスト
    """
    errors = []
    allowed_ops = {"add", "remove", "replace", "test"}
    forbidden_ops = {"move", "copy"}
    
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            errors.append(f"操作 {i}: オブジェクトである必要があります")
            continue
        
        op_type = op.get("op")
        path = op.get("path")
        
        if not op_type:
            errors.append(f"操作 {i}: 'op' フィールドがありません")
        elif op_type in forbidden_ops:
            errors.append(f"操作 {i}: '{op_type}' は禁止されています")
        elif op_type not in allowed_ops:
            errors.append(f"操作 {i}: 不明な操作 '{op_type}'")
        
        if path is None:
            errors.append(f"操作 {i}: 'path' フィールドがありません")
        elif not isinstance(path, str):
            errors.append(f"操作 {i}: 'path' は文字列である必要があります")
        elif path and not path.startswith('/'):
            errors.append(f"操作 {i}: 'path' は '/' で始まる必要があります")
        
        if op_type in ("add", "replace", "test") and "value" not in op:
            errors.append(f"操作 {i}: '{op_type}' には 'value' が必要です")
    
    return errors


def get_schema(schema_name: str) -> dict:
    """
    スキーマを取得
    
    Args:
        schema_name: スキーマ名
    
    Returns:
        スキーマ辞書
    """
    return _load_schema(schema_name)


def list_available_schemas() -> List[str]:
    """
    利用可能なスキーマ名のリストを取得
    
    Returns:
        スキーマ名のリスト
    """
    schema_files = _SCHEMA_DIR.glob("*.schema.json")
    return [f.stem.replace(".schema", "") for f in schema_files]


def clear_schema_cache():
    """スキーマキャッシュをクリア"""
    _schema_cache.clear()
