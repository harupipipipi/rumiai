"""defaults.media.image_transform — 画像変換ブロック"""
from blocks._common import ok, error
from domain.media.processor import transform_image


def run(input_data, context):
    """画像に変換操作を適用する（スタブ）。

    input_data:
        path (str): 画像ファイルパス
        operations (list): 変換操作リスト
            例: [{"type": "resize", "width": 800, "height": 600}]

    Returns:
        dict: {"status": "ok", "data": {"output_path", "operations_applied"}}
    """
    path = input_data.get("path")
    if not path:
        return error("path is required", code="INVALID_INPUT")

    operations = input_data.get("operations", [])
    if not isinstance(operations, list):
        return error("operations must be a list", code="INVALID_INPUT")

    try:
        result = transform_image(path, operations)
        return ok(result)
    except Exception as exc:
        return error(str(exc), code="TRANSFORM_ERROR")
