"""defaults.media.doc_parse — ドキュメントパースブロック"""
from blocks._common import ok, error
from domain.media.processor import parse_document


def run(input_data, context):
    """ドキュメントをパースしてテキストコンテンツを返す（スタブ）。

    input_data:
        path (str): ドキュメントファイルパス
        format (str|None): ドキュメントフォーマットのヒント

    Returns:
        dict: {"status": "ok", "data": {"content", "metadata": {"path", "format"}}}
    """
    path = input_data.get("path")
    if not path:
        return error("path is required", code="INVALID_INPUT")

    doc_format = input_data.get("format")

    try:
        content = parse_document(path)
        return ok({
            "content": content,
            "metadata": {
                "path": path,
                "format": doc_format,
            },
        })
    except Exception as exc:
        return error(str(exc), code="PARSE_ERROR")
