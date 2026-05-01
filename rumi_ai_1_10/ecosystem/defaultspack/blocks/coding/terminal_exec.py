"""defaults.coding.terminal_exec — ターミナルコマンド実行ブロック"""

from blocks._common import ok, error
from blocks.coding._approval import has_server_approval
from domain.coding.terminal import Terminal


def run(input_data, context=None):
    """コマンドを実行する。

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
        terminal = Terminal(input_data.get("workspace_root"))
        result = terminal.execute(
            command,
            cwd=cwd,
            timeout=timeout,
            env=input_data.get("env"),
            approved=has_server_approval(context),
        )
        return ok(result)
    except Exception as e:
        return error(str(e), code="EXEC_ERROR")
