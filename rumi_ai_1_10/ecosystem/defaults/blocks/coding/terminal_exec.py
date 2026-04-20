"""defaults.coding.terminal_exec — ターミナルコマンド実行ブロック（スタブ）"""

from blocks._common import ok, error
from domain.coding.terminal import Terminal


def run(input_data, context=None):
    """コマンドを実行する（スタブ）。

    input_data:
        command (str): 実行するコマンド
        cwd (str|null, optional): 作業ディレクトリ
        timeout (int, optional): タイムアウト秒数（デフォルト: 30）

    returns:
        {"status":"ok","data":{"command":str,"exit_code":int,"stdout":str,"stderr":str}}
    """
    command = input_data.get("command")
    if not command:
        return error("'command' is required", code="INVALID_INPUT")

    cwd = input_data.get("cwd")
    timeout = input_data.get("timeout", 30)

    try:
        terminal = Terminal()
        result = terminal.execute(command, cwd=cwd, timeout=timeout)
        return ok(result)
    except Exception as e:
        return error(str(e), code="EXEC_ERROR")
