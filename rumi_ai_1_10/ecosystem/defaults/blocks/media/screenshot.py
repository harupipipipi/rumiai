"""defaults.media.screenshot — スクリーンショットブロック"""
from blocks._common import ok, error
from domain.media.processor import take_screenshot


def run(input_data, context):
    """スクリーンショットを撮影する（スタブ）。

    input_data:
        region (dict|None): キャプチャ領域（将来拡張）
            例: {"x": 0, "y": 0, "width": 800, "height": 600}

    Returns:
        dict: {"status": "ok", "data": {"path", "width", "height"}}
    """
    # region は将来拡張用。現在は無視する。
    _region = input_data.get("region")

    try:
        result = take_screenshot()
        return ok(result)
    except Exception as exc:
        return error(str(exc), code="SCREENSHOT_ERROR")
