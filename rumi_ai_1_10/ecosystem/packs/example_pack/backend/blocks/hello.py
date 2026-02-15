"""
サンプル python_file_call ブロック

このファイルは python_file_call から呼び出される。
"""


def run(input_data, context=None):
    """
    メイン実行関数
    
    Args:
        input_data: Flowから渡される入力データ
        context: 実行コンテキスト（省略可能）
            - flow_id: Flow ID
            - step_id: ステップID
            - phase: フェーズ名
            - ts: タイムスタンプ
            - owner_pack: 所有Pack ID
            - inputs: 入力データ（input_dataと同じ）
    
    Returns:
        JSON互換の出力データ
    """
    name = "World"
    
    if isinstance(input_data, dict):
        name = input_data.get("name", name)
    elif isinstance(input_data, str):
        name = input_data
    
    result = {
        "message": f"Hello, {name}!",
        "received_input": input_data,
    }
    
    if context:
        result["context_info"] = {
            "flow_id": context.get("flow_id"),
            "step_id": context.get("step_id"),
            "phase": context.get("phase"),
        }
    
    return result
