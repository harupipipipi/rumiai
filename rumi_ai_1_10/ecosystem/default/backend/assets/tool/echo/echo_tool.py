"""
Echoツール
入力をそのまま返す基本的なテスト用ツール
"""

TOOL_NAME = "エコー"
TOOL_DESCRIPTION = "入力されたテキストをそのまま返します（テスト用）"
TOOL_ICON = "🔊"


def get_function_declaration() -> dict:
    """Function Calling用の宣言を返す"""
    return {
        "name": "echo",
        "description": "入力されたテキストをそのまま返します。ツールの動作確認に使用します。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "エコーするメッセージ"
                },
                "repeat": {
                    "type": "integer",
                    "description": "繰り返し回数（デフォルト: 1）"
                }
            },
            "required": ["message"]
        }
    }


def execute(args: dict, context: dict) -> dict:
    """ツールを実行する"""
    callback = context.get('message_callback')
    abort_event = context.get('abort_event')
    
    try:
        message = args.get('message', '')
        repeat = args.get('repeat', 1)
        
        if callback:
            callback(f"メッセージを{repeat}回繰り返します...")
        
        # 中断チェック
        if abort_event and abort_event.is_set():
            return {"success": False, "error": "中断されました", "aborted": True}
        
        result = "\n".join([message] * repeat)
        
        return {
            "success": True,
            "result": {
                "echoed_message": result,
                "original": message,
                "repeat_count": repeat
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
