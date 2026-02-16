"""
マルチステップツール
ReActループの動作確認用。複数回呼び出されることを想定したツール。
"""

import random

TOOL_NAME = "マルチステップ計算"
TOOL_DESCRIPTION = "段階的な計算を行い、ReActループをテストします"
TOOL_ICON = "🔢"

# グローバル状態（テスト用）
_calculation_state = {}


def get_function_declaration() -> dict:
    """Function Calling用の宣言を返す"""
    return {
        "name": "multi_step_calc",
        "description": "段階的な計算を行います。'start'で開始、'next'で次のステップ、'finish'で結果を取得します。AIは計算が完了するまでこのツールを繰り返し呼び出す必要があります。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "アクション: start（計算開始）, next（次のステップ）, finish（結果取得）"
                },
                "initial_value": {
                    "type": "integer",
                    "description": "初期値（startで使用）"
                },
                "session_id": {
                    "type": "string",
                    "description": "セッションID（next/finishで使用）"
                }
            },
            "required": ["action"]
        }
    }


def execute(args: dict, context: dict) -> dict:
    """ツールを実行する"""
    global _calculation_state
    
    callback = context.get('message_callback')
    action = args.get('action', 'start')
    
    try:
        if action == "start":
            # 新しい計算セッションを開始
            initial_value = args.get('initial_value', random.randint(1, 100))
            session_id = f"calc_{random.randint(1000, 9999)}"
            
            # 3〜5ステップ必要な計算を設定
            total_steps = random.randint(3, 5)
            
            _calculation_state[session_id] = {
                "current_value": initial_value,
                "current_step": 0,
                "total_steps": total_steps,
                "history": [f"初期値: {initial_value}"]
            }
            
            if callback:
                callback(f"計算セッション {session_id} を開始しました（全{total_steps}ステップ）")
            
            return {
                "success": True,
                "result": {
                    "status": "started",
                    "session_id": session_id,
                    "current_value": initial_value,
                    "current_step": 0,
                    "total_steps": total_steps,
                    "message": f"計算を開始しました。あと{total_steps}ステップ必要です。'next'アクションでsession_id='{session_id}'を指定して続けてください。"
                }
            }
        
        elif action == "next":
            session_id = args.get('session_id')
            
            if not session_id or session_id not in _calculation_state:
                return {
                    "success": False,
                    "error": f"セッションが見つかりません: {session_id}。'start'アクションで新しいセッションを開始してください。"
                }
            
            state = _calculation_state[session_id]
            
            if state["current_step"] >= state["total_steps"]:
                return {
                    "success": True,
                    "result": {
                        "status": "already_complete",
                        "session_id": session_id,
                        "message": "計算は既に完了しています。'finish'アクションで結果を取得してください。"
                    }
                }
            
            # ランダムな操作を適用
            operations = [
                ("加算", lambda x: x + random.randint(1, 20)),
                ("乗算", lambda x: x * 2),
                ("減算", lambda x: max(1, x - random.randint(1, 10))),
            ]
            op_name, op_func = random.choice(operations)
            
            old_value = state["current_value"]
            state["current_value"] = op_func(old_value)
            state["current_step"] += 1
            state["history"].append(f"ステップ{state['current_step']}: {op_name} → {state['current_value']}")
            
            remaining = state["total_steps"] - state["current_step"]
            
            if callback:
                callback(f"ステップ {state['current_step']}/{state['total_steps']} 完了")
            
            if remaining > 0:
                return {
                    "success": True,
                    "result": {
                        "status": "in_progress",
                        "session_id": session_id,
                        "operation": op_name,
                        "previous_value": old_value,
                        "current_value": state["current_value"],
                        "current_step": state["current_step"],
                        "remaining_steps": remaining,
                        "message": f"あと{remaining}ステップ必要です。'next'アクションで続けてください。"
                    }
                }
            else:
                return {
                    "success": True,
                    "result": {
                        "status": "ready_to_finish",
                        "session_id": session_id,
                        "current_value": state["current_value"],
                        "message": "全ステップ完了しました。'finish'アクションで最終結果を取得してください。"
                    }
                }
        
        elif action == "finish":
            session_id = args.get('session_id')
            
            if not session_id or session_id not in _calculation_state:
                return {
                    "success": False,
                    "error": f"セッションが見つかりません: {session_id}"
                }
            
            state = _calculation_state[session_id]
            
            if state["current_step"] < state["total_steps"]:
                return {
                    "success": False,
                    "error": f"計算が完了していません。あと{state['total_steps'] - state['current_step']}ステップ必要です。"
                }
            
            # セッションをクリア
            final_result = {
                "status": "completed",
                "session_id": session_id,
                "final_value": state["current_value"],
                "total_steps": state["total_steps"],
                "history": state["history"]
            }
            
            del _calculation_state[session_id]
            
            if callback:
                callback("計算完了！")
            
            return {
                "success": True,
                "result": final_result
            }
        
        else:
            return {
                "success": False,
                "error": f"不明なアクション: {action}。start, next, finish のいずれかを指定してください。"
            }
    
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
