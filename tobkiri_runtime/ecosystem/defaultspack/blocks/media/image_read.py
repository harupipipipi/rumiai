"""defaults.media.image_read — 画像メタデータ取得ブロック"""
from blocks._common import ok, error
from domain.media.processor import read_image


def run(input_data, context):
    """画像ファイルのメタデータを返す。

    input_data:
        path (str): 画像ファイルパス

    Returns:
        dict: {"status": "ok", "data": {"path", "width", "height", "format", "size_bytes"}}
    """
    path = input_data.get("path")
    if not path:
        return error("path is required", code="INVALID_INPUT")

    try:
        metadata = read_image(path)
        return ok(metadata)
    except FileNotFoundError as exc:
        return error(str(exc), code="FILE_NOT_FOUND")
    except Exception as exc:
        return error(str(exc), code="READ_ERROR")
