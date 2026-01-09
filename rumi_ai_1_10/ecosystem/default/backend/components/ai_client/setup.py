#!/usr/bin/env python3
"""
setup.py - 起動時セットアップ集約スクリプト

アプリケーション起動時に呼び出され、以下のメタデータを更新する：
- ai_client/ai_client_metadata.json

将来的に以下も追加予定：
- tool/tool_metadata.json
- prompt/prompt_metadata.json
- supporter/supporter_metadata.json
"""

import os
import sys
import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


# UUIDv5の名前空間（DNS namespace）
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_deterministic_uuid(provider: str, model_id: str) -> str:
    """
    プロバイダーとモデルIDからdeterministicなUUIDを生成
    
    Args:
        provider: プロバイダー名
        model_id: モデルID
    
    Returns:
        UUIDv5文字列
    """
    name = f"{provider}:{model_id}"
    return str(uuid.uuid5(UUID_NAMESPACE, name))


def infer_product_from_model_id(model_id: str) -> str:
    """
    model_idからプロダクト名を推測
    
    Args:
        model_id: モデルID（例: "gemini-2.5-flash", "gpt-4o", "claude-3-opus"）
    
    Returns:
        推測されたプロダクト名
    """
    model_id_lower = model_id.lower()
    
    # 既知のプロダクトパターン
    product_patterns = [
        ("gemini", "Gemini"),
        ("gpt-4", "GPT"),
        ("gpt-3", "GPT"),
        ("o1", "o1"),
        ("o3", "o3"),
        ("claude", "Claude"),
        ("grok", "Grok"),
        ("llama", "Llama"),
        ("mistral", "Mistral"),
        ("mixtral", "Mixtral"),
        ("command", "Command"),
        ("palm", "PaLM"),
        ("codestral", "Codestral"),
        ("deepseek", "DeepSeek"),
        ("qwen", "Qwen"),
    ]
    
    for pattern, product_name in product_patterns:
        if pattern in model_id_lower:
            return product_name
    
    # パターンに一致しない場合はmodel_idの最初の部分を使用
    # 例: "some-model-v1" -> "Some"
    first_part = model_id.split('-')[0] if '-' in model_id else model_id
    return first_part.capitalize()


def scan_ai_profiles(ai_client_dir: Path) -> Dict[str, Any]:
    """
    ai_client配下の全プロファイルをスキャン
    
    Args:
        ai_client_dir: ai_clientディレクトリのパス
    
    Returns:
        メタデータ辞書
    """
    metadata = {
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "providers": {},
        "models": {},
        "products": {},
        "model_count": 0
    }
    
    # ai_client配下のプロバイダーディレクトリを探索
    for provider_dir in ai_client_dir.iterdir():
        if not provider_dir.is_dir():
            continue
        if provider_dir.name.startswith('_') or provider_dir.name.startswith('.'):
            continue
        if provider_dir.name in ('user_data', 'userdata', '__pycache__'):
            continue
        
        # プロバイダーのクライアントファイルが存在するか確認
        client_file = provider_dir / f"{provider_dir.name}_client.py"
        if not client_file.exists():
            continue
        
        provider_name = provider_dir.name
        profile_dir = provider_dir / "ai_profile"
        
        if not profile_dir.exists():
            continue
        
        # プロバイダー情報を初期化
        provider_info = {
            "name": provider_name,
            "client_file": str(client_file.relative_to(ai_client_dir)),
            "profile_dir": str(profile_dir.relative_to(ai_client_dir)),
            "models": [],
            "model_count": 0
        }
        
        # プロファイルを再帰的に探索
        profiles = scan_profile_directory(profile_dir, provider_name, ai_client_dir)
        
        for profile in profiles:
            model_id = profile["id"]
            product = profile.get("product", "Unknown")
            
            # モデル情報を追加
            provider_info["models"].append(model_id)
            metadata["models"][model_id] = profile
            
            # プロダクト別にモデルをグループ化
            if product not in metadata["products"]:
                metadata["products"][product] = []
            if model_id not in metadata["products"][product]:
                metadata["products"][product].append(model_id)
        
        provider_info["model_count"] = len(provider_info["models"])
        metadata["providers"][provider_name] = provider_info
        metadata["model_count"] += provider_info["model_count"]
    
    return metadata


def scan_profile_directory(
    profile_dir: Path,
    provider_name: str,
    ai_client_dir: Path,
    relative_path: str = ""
) -> List[Dict[str, Any]]:
    """
    プロファイルディレクトリを再帰的にスキャン
    
    Args:
        profile_dir: スキャン対象ディレクトリ
        provider_name: プロバイダー名
        ai_client_dir: ai_clientディレクトリ（相対パス計算用）
        relative_path: 現在の相対パス
    
    Returns:
        プロファイル情報のリスト
    """
    profiles = []
    
    for item in profile_dir.iterdir():
        # アンダースコアで始まるものは無視
        if item.name.startswith('_') or item.name.startswith('.'):
            continue
        
        if item.is_dir():
            # サブディレクトリを再帰探索
            sub_relative = f"{relative_path}/{item.name}" if relative_path else item.name
            profiles.extend(
                scan_profile_directory(item, provider_name, ai_client_dir, sub_relative)
            )
        
        elif item.is_file() and item.suffix == '.json':
            # JSONファイルを読み込み
            try:
                profile_info = load_profile(item, provider_name, ai_client_dir)
                if profile_info:
                    profiles.append(profile_info)
            except Exception as e:
                print(f"  警告: プロファイル読み込みエラー ({item}): {e}")
    
    return profiles


def load_profile(
    profile_path: Path,
    provider_name: str,
    ai_client_dir: Path
) -> Optional[Dict[str, Any]]:
    """
    プロファイルJSONを読み込み、メタデータ用に整形
    
    Args:
        profile_path: プロファイルファイルのパス
        provider_name: プロバイダー名
        ai_client_dir: ai_clientディレクトリ
    
    Returns:
        整形されたプロファイル情報
    """
    with open(profile_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 必須フィールドの確認
    if 'basic_info' not in data:
        return None
    
    basic_info = data['basic_info']
    model_id = basic_info.get('id')
    
    if not model_id:
        return None
    
    # UUID生成（未指定の場合はdeterministic生成）
    model_uuid = basic_info.get('uuid')
    if not model_uuid:
        model_uuid = generate_deterministic_uuid(provider_name, model_id)
    
    # product名を取得（未指定の場合はmodel_idから推測）
    product = basic_info.get('product')
    if not product:
        product = infer_product_from_model_id(model_id)
    
    # tier情報を抽出
    tiers_info = None
    if 'tiers' in data:
        tiers = data['tiers']
        tiers_info = {
            "default_tier": tiers.get('default_tier'),
            "available_tiers": tiers.get('available_tiers', [])
        }
    
    # 整形したプロファイル情報
    return {
        "id": model_id,
        "uuid": model_uuid,
        "name": basic_info.get('name', model_id),
        "product": product,
        "description": basic_info.get('description', ''),
        "provider": provider_name,
        "profile_path": str(profile_path.relative_to(ai_client_dir)),
        "status": basic_info.get('status', 'active'),
        "features": {
            "is_multimodal": data.get('features', {}).get('is_multimodal', False),
            "supports_function_calling": data.get('features', {}).get('supports_function_calling', False),
            "supports_tool_use": data.get('features', {}).get('supports_tool_use', False),
            "supports_streaming": data.get('features', {}).get('supports_streaming', False),
            "supports_reasoning": data.get('features', {}).get('supports_reasoning', False)
        },
        "capabilities": {
            "context_length": data.get('capabilities', {}).get('context_length', 0),
            "max_completion_tokens": data.get('capabilities', {}).get('max_completion_tokens', 0)
        },
        "tiers": tiers_info,
        "related_models": data.get('related_models')
    }


def update_ai_client_metadata(ai_client_dir: Path = None) -> Dict[str, Any]:
    """
    ai_client_metadata.jsonを更新
    
    Args:
        ai_client_dir: ai_clientディレクトリのパス（省略時は自動検出）
    
    Returns:
        生成されたメタデータ
    """
    if ai_client_dir is None:
        # このファイルからの相対パスで検出
        ai_client_dir = Path(__file__).parent.resolve() / "ai_client"
    
    ai_client_dir = Path(ai_client_dir).resolve()
    
    # ディレクトリが存在しない場合は空のメタデータを返す
    if not ai_client_dir.exists():
        print(f"警告: ai_clientディレクトリが存在しません: {ai_client_dir}")
        empty_metadata = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "providers": {},
            "models": {},
            "products": {},
            "model_count": 0,
            "error": f"ai_client directory not found: {ai_client_dir}"
        }
        return empty_metadata
    
    print(f"AI Client メタデータを更新中...")
    
    # プロファイルをスキャン
    try:
        metadata = scan_ai_profiles(ai_client_dir)
    except Exception as e:
        print(f"警告: プロファイルスキャン中にエラーが発生: {e}")
        metadata = {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "providers": {},
            "models": {},
            "products": {},
            "model_count": 0,
            "error": str(e)
        }
    
    # メタデータファイルを保存
    metadata_path = ai_client_dir / "ai_client_metadata.json"
    
    try:
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        print(f"  プロバイダー数: {len(metadata.get('providers', {}))}")
        print(f"  モデル数: {metadata.get('model_count', 0)}")
        print(f"  プロダクト数: {len(metadata.get('products', {}))}")
        print(f"  出力: {metadata_path}")
    except Exception as e:
        print(f"警告: メタデータファイルの保存に失敗: {e}")
    
    return metadata


def run_setup():
    """
    全てのセットアップを実行
    """
    print("=" * 60)
    print("Setup: メタデータの更新を開始")
    print("=" * 60)
    
    # プロジェクトルートを明示的に解決
    # setup.py はプロジェクトルートに配置されている前提
    project_root = Path(__file__).parent.resolve()
    ai_client_dir = project_root / "ai_client"
    
    print(f"プロジェクトルート: {project_root}")
    print(f"ai_clientディレクトリ: {ai_client_dir}")
    
    # ai_client メタデータ更新
    update_ai_client_metadata(ai_client_dir)
    
    # 将来的に追加予定:
    # update_tool_metadata(project_root / "tool")
    # update_prompt_metadata(project_root / "prompt")
    # update_supporter_metadata(project_root / "supporter")
    
    print("=" * 60)
    print("Setup: 完了")
    print("=" * 60)


if __name__ == "__main__":
    run_setup()