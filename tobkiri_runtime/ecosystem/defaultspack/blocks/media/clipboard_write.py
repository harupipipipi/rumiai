"""defaults.media.clipboard_write — クリップボード書込ブロック"""
from blocks._common import ok, error
from domain.media.processor import write_clipboard


def run(input_data, context):
    """クリップボードに内容を書き込む（スタブ）。

    input_data:
        content (str): 書き込む内容

    Returns:
        dict: {"status": "ok", "data": {"written": true}}
    """
    content = input_data.get("content")
    if content is None:
        return error("content is required", code="INVALID_INPUT")

    try:
        write_clipboard(content)
        return ok({"written": True})
    except Exception as exc:
        return error(str(exc), code="CLIPBOARD_WRITE_ERROR")
