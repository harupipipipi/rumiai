#!/usr/bin/env python3
"""
ai_client.py - 開発者向けCLIユーティリティ

UI無しで以下の操作が可能：
- モデル一覧表示
- invoke_schema表示
- direct invoke テスト
- ai_client_metadata.json 生成確認
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv('.env.local')


def cmd_list_models(args):
    """モデル一覧を表示"""
    try:
        from ai_client.ai_client_loader import AIClientLoader
    except ImportError as e:
        print(f"エラー: AIClientLoaderのインポートに失敗しました: {e}")
        sys.exit(1)
    
    try:
        loader = AIClientLoader()
        loader.load_all_clients()
    except Exception as e:
        print(f"エラー: クライアントの読み込みに失敗しました: {e}")
        sys.exit(1)
    
    models = loader.get_all_models()
    
    if args.provider:
        models = [m for m in models if m['provider'] == args.provider]
    
    if args.json:
        print(json.dumps(models, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"利用可能なモデル: {len(models)}個")
        print(f"{'='*60}\n")
        
        if not models:
            print("  モデルが見つかりません。")
            print("  APIキーが正しく設定されているか確認してください。")
            return
        
        for model in models:
            features = model.get('features', {})
            tags = []
            if features.get('is_multimodal'):
                tags.append('multimodal')
            if features.get('supports_function_calling') or features.get('supports_tool_use'):
                tags.append('tools')
            if features.get('supports_reasoning'):
                tags.append('reasoning')
            if features.get('supports_streaming'):
                tags.append('streaming')
            
            tags_str = ', '.join(tags) if tags else '-'
            
            print(f"  {model['id']}")
            print(f"    名前: {model['name']}")
            print(f"    プロバイダー: {model['provider']}")
            if model.get('product'):
                print(f"    プロダクト: {model['product']}")
            print(f"    機能: {tags_str}")
            print()


def cmd_show_schema(args):
    """invoke_schemaを表示"""
    try:
        from ai_manager import AIClient
    except ImportError as e:
        print(f"エラー: AIClientのインポートに失敗しました: {e}")
        sys.exit(1)
    
    try:
        ai_manager = AIClient()
    except Exception as e:
        print(f"エラー: AIClientの初期化に失敗しました: {e}")
        print("APIキーが正しく設定されているか確認してください。")
        sys.exit(1)
    
    # get_invoke_schema メソッドの存在確認
    if not hasattr(ai_manager, 'get_invoke_schema'):
        print("エラー: get_invoke_schema メソッドが利用できません")
        print("ai_manager.py が最新版か確認してください。")
        sys.exit(1)
    
    schema = ai_manager.get_invoke_schema(args.model_id)
    
    if schema is None:
        print(f"エラー: モデル '{args.model_id}' が見つかりません")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Invoke Schema: {args.model_id}")
        print(f"{'='*60}\n")
        
        print("【基本情報】")
        print(f"  モデル: {schema['model_id']}")
        print(f"  プロバイダー: {schema['provider']}")
        print(f"  説明: {schema.get('description', '-')}")
        print()
        
        print("【パラメータ】")
        for param_name, param_info in schema.get('parameters', {}).items():
            param_type = param_info.get('type', 'unknown')
            default = param_info.get('default', '-')
            
            if param_type in ('number', 'integer'):
                min_val = param_info.get('min', '-')
                max_val = param_info.get('max', '-')
                print(f"  {param_name}: {param_type} (min={min_val}, max={max_val}, default={default})")
            else:
                print(f"  {param_name}: {param_type} (default={default})")
        print()
        
        print("【機能】")
        features = schema.get('features', {})
        for feat_name, feat_val in features.items():
            print(f"  {feat_name}: {feat_val}")
        print()
        
        if schema.get('tiers'):
            print("【Tier】")
            tiers = schema['tiers']
            print(f"  デフォルト: {tiers.get('default_tier', '-')}")
            print(f"  利用可能: {', '.join(tiers.get('available_tiers', []))}")
            print()


def cmd_invoke(args):
    """direct invokeを実行"""
    try:
        from ai_manager import AIClient
    except ImportError as e:
        print(f"エラー: AIClientのインポートに失敗しました: {e}")
        sys.exit(1)
    
    try:
        ai_manager = AIClient()
    except Exception as e:
        print(f"エラー: AIClientの初期化に失敗しました: {e}")
        print("APIキーが正しく設定されているか確認してください。")
        sys.exit(1)
    
    # direct_invoke メソッドの存在確認
    if not hasattr(ai_manager, 'direct_invoke'):
        print("エラー: direct_invoke メソッドが利用できません")
        print("ai_manager.py が最新版か確認してください。")
        sys.exit(1)
    
    # パラメータを構築
    params = {}
    if args.temperature is not None:
        params['temperature'] = args.temperature
    if args.max_tokens is not None:
        params['max_tokens'] = args.max_tokens
    
    # ツール設定
    tools_config = None
    if args.tools:
        if args.tools == 'all':
            tools_config = {'mode': 'all'}
        elif args.tools == 'none':
            tools_config = {'mode': 'none'}
        else:
            tools_config = {'mode': 'allowlist', 'allowlist': args.tools.split(',')}
    
    # 実行
    try:
        result = ai_manager.direct_invoke(
            model_id=args.model_id,
            message=args.message,
            system_prompt=args.system_prompt,
            api_tier=args.tier,
            params=params,
            tools_config=tools_config
        )
    except Exception as e:
        print(f"エラー: direct_invoke の実行に失敗しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    if result is None:
        print("エラー: 結果が返されませんでした")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Direct Invoke 結果")
        print(f"{'='*60}\n")
        
        if result.get('success'):
            print("【応答】")
            print(result.get('response_text', ''))
            print()
            
            if result.get('tool_uses'):
                print("【ツール使用指示】")
                for tu in result['tool_uses']:
                    print(f"  - {tu['name']}: {json.dumps(tu.get('args', {}), ensure_ascii=False)}")
                print()
            
            print("【メタ情報】")
            print(f"  モデル: {result.get('used_model_id')}")
            print(f"  プロバイダー: {result.get('used_provider')}")
            if result.get('used_api_tier'):
                print(f"  Tier: {result.get('used_api_tier')}")
            if result.get('usage'):
                usage = result['usage']
                print(f"  トークン: 入力={usage.get('prompt_tokens', '?')}, 出力={usage.get('completion_tokens', '?')}")
        else:
            print(f"エラー: {result.get('error', '不明なエラー')}")


def cmd_update_metadata(args):
    """メタデータを更新"""
    try:
        from setup import run_setup
    except ImportError as e:
        print(f"エラー: setup モジュールのインポートに失敗しました: {e}")
        print("setup.py がプロジェクトルートに存在するか確認してください。")
        sys.exit(1)
    except Exception as e:
        print(f"エラー: setup モジュールの読み込み中に問題が発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    try:
        run_setup()
    except Exception as e:
        print(f"エラー: メタデータ更新中に問題が発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_show_products(args):
    """プロダクト一覧を表示"""
    try:
        from ai_client.ai_client_loader import AIClientLoader
    except ImportError as e:
        print(f"エラー: AIClientLoaderのインポートに失敗しました: {e}")
        sys.exit(1)
    
    try:
        loader = AIClientLoader()
        loader.load_all_clients()
    except Exception as e:
        print(f"エラー: クライアントの読み込みに失敗しました: {e}")
        sys.exit(1)
    
    products = {}
    for model_id, profile in loader.model_profiles.items():
        product = profile.get('basic_info', {}).get('product')
        if product:
            if product not in products:
                products[product] = []
            products[product].append(model_id)
    
    if args.json:
        print(json.dumps({
            'products': sorted(products.keys()),
            'product_models': products
        }, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"利用可能なプロダクト: {len(products)}個")
        print(f"{'='*60}\n")
        
        if not products:
            print("  プロダクトが見つかりません。")
            return
        
        for product_name in sorted(products.keys()):
            model_list = products[product_name]
            print(f"  {product_name}")
            for model_id in model_list:
                print(f"    - {model_id}")
            print()


def cmd_show_metadata(args):
    """メタデータを表示"""
    metadata_file = Path('ai_client') / 'ai_client_metadata.json'
    
    if not metadata_file.exists():
        print("エラー: ai_client_metadata.json が見つかりません")
        print("'python ai_client.py update' を実行してメタデータを生成してください。")
        sys.exit(1)
    
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"エラー: メタデータの読み込みに失敗しました: {e}")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"AI Client メタデータ")
        print(f"{'='*60}\n")
        
        print(f"  バージョン: {metadata.get('version', '-')}")
        print(f"  生成日時: {metadata.get('generated_at', '-')}")
        print(f"  プロバイダー数: {len(metadata.get('providers', {}))}")
        print(f"  モデル数: {metadata.get('model_count', 0)}")
        print()
        
        if metadata.get('providers'):
            print("【プロバイダー】")
            for provider_name, provider_info in metadata['providers'].items():
                print(f"  {provider_name}: {provider_info.get('model_count', 0)}モデル")
            print()
        
        if metadata.get('error'):
            print(f"【エラー】")
            print(f"  {metadata['error']}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description='AI Client CLI - 開発者向けユーティリティ',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python ai_client.py list                      # モデル一覧を表示
  python ai_client.py list -p gemini            # Geminiモデルのみ表示
  python ai_client.py list -j                   # JSON形式で出力
  
  python ai_client.py schema gemini-2.5-flash   # スキーマを表示
  python ai_client.py schema gemini-2.5-pro -j  # JSON形式で出力
  
  python ai_client.py invoke gemini-2.5-flash "こんにちは"
  python ai_client.py invoke gemini-2.5-flash "計算して" --tools all
  python ai_client.py invoke gemini-2.5-pro "分析して" -t standard --temperature 0.5
  
  python ai_client.py products                  # プロダクト一覧を表示
  python ai_client.py metadata                  # メタデータを表示
  python ai_client.py update                    # メタデータを更新
"""
    )
    subparsers = parser.add_subparsers(dest='command', help='コマンド')
    
    # list コマンド
    list_parser = subparsers.add_parser('list', help='モデル一覧を表示')
    list_parser.add_argument('--provider', '-p', help='プロバイダーでフィルタ')
    list_parser.add_argument('--json', '-j', action='store_true', help='JSON形式で出力')
    list_parser.set_defaults(func=cmd_list_models)
    
    # schema コマンド
    schema_parser = subparsers.add_parser('schema', help='invoke_schemaを表示')
    schema_parser.add_argument('model_id', help='モデルID')
    schema_parser.add_argument('--json', '-j', action='store_true', help='JSON形式で出力')
    schema_parser.set_defaults(func=cmd_show_schema)
    
    # invoke コマンド
    invoke_parser = subparsers.add_parser('invoke', help='direct invokeを実行')
    invoke_parser.add_argument('model_id', help='モデルID')
    invoke_parser.add_argument('message', help='メッセージ')
    invoke_parser.add_argument('--system-prompt', '-s', help='システムプロンプト')
    invoke_parser.add_argument('--tier', '-t', help='API tier')
    invoke_parser.add_argument('--temperature', type=float, help='Temperature')
    invoke_parser.add_argument('--max-tokens', type=int, help='最大出力トークン')
    invoke_parser.add_argument('--tools', help='ツール設定 (all/none/tool1,tool2)')
    invoke_parser.add_argument('--json', '-j', action='store_true', help='JSON形式で出力')
    invoke_parser.set_defaults(func=cmd_invoke)
    
    # products コマンド
    products_parser = subparsers.add_parser('products', help='プロダクト一覧を表示')
    products_parser.add_argument('--json', '-j', action='store_true', help='JSON形式で出力')
    products_parser.set_defaults(func=cmd_show_products)
    
    # metadata コマンド
    metadata_parser = subparsers.add_parser('metadata', help='メタデータを表示')
    metadata_parser.add_argument('--json', '-j', action='store_true', help='JSON形式で出力')
    metadata_parser.set_defaults(func=cmd_show_metadata)
    
    # update コマンド
    update_parser = subparsers.add_parser('update', help='メタデータを更新')
    update_parser.set_defaults(func=cmd_update_metadata)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()