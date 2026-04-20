"""defaults.coding.terminal_stream — ターミナルストリーム実行ブロック（スタブ）"""

from blocks._common import ok, error
from domain.coding.terminal import Terminal


def run(input_data, context=None):
    """コマンドをストリーム実行する（スタブ）。

    input_data:
        command (str): 実行するコマンド
        cwd (str|null, optional): 作業ディレクトリ

    returns:
        {"status":"ok","data":{"command":str,"stream_id":str,"started":true}}
    """
    command = input_data.get("command")
    if not command:
        return error("'command' is required", code="INVALID_INPUT")

    cwd = input_data.get("cwd")

    try:
        terminal = Terminal()
        result = terminal.stream(command, cwd=cwd)
        return ok(result)
    except Exception as e:
        return error(str(e), code="STREAM_ERROR")
