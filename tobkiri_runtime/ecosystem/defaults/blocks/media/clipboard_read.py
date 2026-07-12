"""defaults.media.clipboard_read — クリップボード読取ブロック"""
from blocks._common import ok, error
from domain.media.processor import read_clipboard


def run(input_data, context):
    """クリップボードの内容を読み取る（スタブ）。

    input_data:
        (なし)

    Returns:
        dict: {"status": "ok", "data": {"content", "format"}}
    """
    try:
        content = read_clipboard()
        return ok({
            "content": content,
            "format": "text/plain",
        })
    except Exception as exc:
        return error(str(exc), code="CLIPBOARD_READ_ERROR")
